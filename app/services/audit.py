"""Orchestration (Phase 4, lands LAST). Ties the three stages into the core loop:

    Stage 1 (identify recording + resolve work)
      -> Stage 2 (check each registry for gaps, skipping composition checks if no work)
      -> Stage 3 (estimate the annual leak as a range)

Depends only on the interfaces, so it can be stubbed/tested against fakes before the real
implementations exist. Real wiring is last because it needs them.

SYNC vs ASYNC (settled for v1): the loop is SYNCHRONOUS. v1 is fixture-backed and info-only
— no real scraping or fingerprinting happens in a request, so there is no timeout risk that
would force an async submit/poll design. If live multi-registry scraping (or audio
fingerprinting) is later added, the network-bound work moves behind an `app/jobs/` layer: the
endpoint enqueues a job and returns a job id, and the client polls a status endpoint. The
stage interfaces are unchanged by that move — only this orchestrator's call sites would be
wrapped in a worker. Until then, synchronous keeps the whole thing trivial.

OFFLINE DEGRADATION (binds the test path): nothing here may touch the live network in a
tested path. `settings.allow_live_network` is OFF by default, so:
  * Stage 1 falls back to the no-network ManualIdentifier; work resolution falls back to None.
  * The MANUAL-WORK fallback (below) resolves the documented interface friction — a user's
    manually-entered ISWC can't flow through the frozen WorkResolver, so the ORCHESTRATOR
    constructs the WorkResult directly from TrackInput.iswc.
  * Each Stage 2 adapter's `check` is wrapped: a network-gated adapter raising offline yields
    a RegistrationStatus.ERROR row (provenance preserved) rather than crashing the loop.
  * SoundExchange's self-report toggle is the ONE registry that produces a real, non-ERROR
    result end-to-end offline (no public lookup exists, so it never needs the network).
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from app.config import get_settings
from app.domain import RegistrationStatus
from app.pipeline.interfaces import Estimator, GapChecker, Identifier, WorkResolver
from app.schemas.audit import AuditRequest, AuditResponse
from app.schemas.gaps import GapReport, RegistrationResult
from app.schemas.identity import IdentityResult, WorkResult


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def run_audit(
    request: AuditRequest,
    *,
    identifier: Identifier | None = None,
    work_resolver: WorkResolver | None = None,
    checkers: list[GapChecker] | None = None,
    estimator: Estimator | None = None,
    estimator_band: Decimal | None = None,
    session=None,
    soundexchange_self_report: bool | None = None,
) -> AuditResponse:
    """Run the synchronous core loop: identify -> check gaps -> estimate.

    Everything external is dependency-injectable (identifier/work_resolver/checkers/
    estimator/session) so the e2e test drives the whole loop with fixture-backed adapters and
    an in-memory SQLite session — no network, no Postgres. When a dependency is not injected
    we fall back to a real one, but only ever picking a live (network) implementation when
    `settings.allow_live_network` is on; otherwise we degrade to the offline path.
    """
    settings = get_settings()

    # --- Session lifecycle -------------------------------------------------------------
    # An injected session is owned by the caller (don't close it). When we open our own we
    # commit (so provenance rows persist) and close it in a finally.
    owns_session = session is None
    if owns_session:
        from app.db.session import SessionLocal

        session = SessionLocal()

    try:
        # --- Stage 1: identity (recording) ---------------------------------------------
        if identifier is None:
            track = request.track
            if settings.allow_live_network and (track.spotify_url or track.spotify_id):
                from app.pipeline.stage1_identity.spotify import SpotifyIdentifier

                identifier = SpotifyIdentifier()
            else:
                from app.pipeline.stage1_identity.manual import ManualIdentifier

                identifier = ManualIdentifier()
        recording = identifier.identify(request.track)

        # --- Stage 1: work resolution (composition) ------------------------------------
        if work_resolver is not None:
            work = work_resolver.resolve_work(recording)
        elif settings.allow_live_network and recording.isrc:
            from app.pipeline.stage1_identity.work_resolver import (
                MusicBrainzWorkResolver,
            )

            work = MusicBrainzWorkResolver().resolve_work(recording)
        else:
            work = None

        # Manual-work fallback (resolves the documented contract friction): the frozen
        # WorkResolver only ever sees a RecordingResult, so a user's manually-entered ISWC
        # can't flow through it. The orchestrator reads TrackInput.iswc directly and builds
        # the WorkResult itself — without this, composition checks could never run offline.
        if work is None and request.track.iswc:
            work = WorkResult(
                title=recording.title,
                iswc=request.track.iswc,
                writers=[],
                source="manual",
            )

        identity = IdentityResult(recording=recording, work=work)

        # --- Stage 2: gaps -------------------------------------------------------------
        if checkers is None:
            from app.pipeline.stage2_gaps.ascap import ASCAPAdapter
            from app.pipeline.stage2_gaps.bmi import BMIAdapter
            from app.pipeline.stage2_gaps.mlc import MLCAdapter
            from app.pipeline.stage2_gaps.soundexchange import SoundExchangeAdapter

            checkers = [
                MLCAdapter(session=session),
                ASCAPAdapter(session=session),
                BMIAdapter(session=session),
                SoundExchangeAdapter(
                    session=session,
                    self_reported_registered=soundexchange_self_report,
                ),
            ]

        results: list[RegistrationResult] = []
        for checker in checkers:
            try:
                results.append(checker.check(identity))
            except Exception as e:  # noqa: BLE001 — a failed check degrades to ERROR, never crashes
                # A network-off (or otherwise broken) adapter must NOT crash the loop. We
                # record an ERROR row with provenance so the UI flags "couldn't check" rather
                # than silently implying no gap.
                results.append(
                    RegistrationResult(
                        registry=checker.registry,
                        side=checker.keys_on,
                        status=RegistrationStatus.ERROR,
                        checked_at=_utcnow(),
                        notes=f"check failed: {e}",
                    )
                )

        gap_report = GapReport(
            checks=results,
            unresolved=[
                r.registry for r in results if r.status is RegistrationStatus.UNRESOLVED
            ],
        )

        # --- Stage 3: estimate ---------------------------------------------------------
        # `estimator_band` lets a caller (e.g. the UI's adjustable band slider) widen/narrow
        # the uncertainty spread without importing the estimator itself — keeping the UI
        # isolated from pipeline internals. Ignored when an estimator is injected directly.
        if estimator is None:
            from app.pipeline.stage3_estimate.calculator import RateCardEstimator

            if estimator_band is not None:
                estimator = RateCardEstimator(session, band=estimator_band)
            else:
                estimator = RateCardEstimator(session)
        estimate = estimator.estimate(identity, request.assumptions, gaps=results)

        response = AuditResponse(identity=identity, gaps=gap_report, estimate=estimate)

        if owns_session:
            # Commit before close so the provenance rows persisted during Stage 2 survive.
            session.commit()

        return response
    finally:
        if owns_session:
            session.close()
