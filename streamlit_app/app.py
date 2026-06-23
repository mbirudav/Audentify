"""v0 Streamlit UI (Phase 4, [P]). Fully isolated from the backend so swapping in Next.js
later doesn't ripple into the logic.

This talks to the REAL `run_audit` and the frozen schemas ONLY — it imports nothing from the
pipeline internals, so the loop's wiring can change underneath it freely. Three panels per
the success criteria:
  1. Identity — recording (ISRC) + work (ISWC + writers), or an explicit "work unresolved"
     message (we never imply "no gap" when we simply couldn't check the composition side).
  2. Registration map — one row per registry with side/status/confidence/provenance.
     UNRESOLVED and ERROR rows are flagged as "couldn't check", NOT as "no gap"; NOT_FOUND
     rows are highlighted as candidate leaks.
  3. Estimated annual leak — the low-high RANGE plus per-royalty-type line items with their
     exposed assumptions (volume, rate, band, version, leak status). Band + volume are
     adjustable and the audit re-runs on submit. The softness is labelled (placeholder rates,
     artist-entered volume) so we never present false precision.

Run:
    uv run streamlit run streamlit_app/app.py     (needs `uv sync --extra ui`)

PREREQUISITE — the RateCard table must be seeded first, or Stage 3 returns no line items:
    uv run python -c "from app.db.session import SessionLocal; \\
        from app.rates.loader import seed_rate_cards; \\
        s = SessionLocal(); seed_rate_cards(s); s.commit(); s.close()"

OFFLINE: with `allow_live_network` OFF (the default), the demo still produces a populated
result — manual identity needs no network, the manual-ISWC fallback lets composition checks
run, and SoundExchange's self-report toggle answers the master side end-to-end. The
network-gated PRO/MLC adapters degrade to ERROR rows (flagged, never silent).
"""

from __future__ import annotations

from decimal import Decimal

import streamlit as st

from app.domain import RegistrationStatus, RoyaltyType
from app.schemas.audit import AuditRequest
from app.schemas.estimate import RoyaltyAssumptions
from app.schemas.identity import TrackInput
from app.services.audit import run_audit

# Tri-state SoundExchange self-report: the label the artist picks -> the bool|None we pass.
_SOUNDEXCHANGE_OPTIONS: dict[str, bool | None] = {
    "I don't know": None,
    "Yes, I'm registered": True,
    "No, I'm not registered": False,
}

# Per-royalty-type volume inputs. The UNIT differs per type (the core domain point: "volume"
# is streams for some royalty types, spins for others) — so we label each explicitly.
_VOLUME_FIELDS: list[tuple[RoyaltyType, str, str]] = [
    (RoyaltyType.MECHANICAL, "Mechanical — annual streams", "streams (MLC, per-stream)"),
    (RoyaltyType.PERFORMANCE, "Performance — annual streams", "streams (PRO, pooled approx.)"),
    (
        RoyaltyType.DIGITAL_PERFORMANCE,
        "Digital performance — annual spins",
        "spins (SoundExchange, non-interactive)",
    ),
]

_DEMO_KEY = "demo_prefill"


def _prefill_demo() -> None:
    """Pre-fill the form so the loop produces a POPULATED result fully OFFLINE: manual
    identity (no network), a manually-entered ISWC (so composition checks have a work to run
    against), and SoundExchange = registered (the registry that answers end-to-end offline)."""
    st.session_state[_DEMO_KEY] = {
        "title": "Test Track",
        "artist": "Test Artist",
        "isrc": "US-S1Z-99-00001",
        "iswc": "T-123.456.789-0",
        "spotify_url": "",
        "soundexchange": "Yes, I'm registered",
        RoyaltyType.MECHANICAL.value: 1_000_000,
        RoyaltyType.PERFORMANCE.value: 1_000_000,
        RoyaltyType.DIGITAL_PERFORMANCE.value: 50_000,
        "band_pct": 30,
    }


def _demo(key: str, default):
    return st.session_state.get(_DEMO_KEY, {}).get(key, default)


def _status_emoji(status: RegistrationStatus) -> str:
    return {
        RegistrationStatus.REGISTERED: "✅",
        RegistrationStatus.NOT_FOUND: "🚨",
        RegistrationStatus.AMBIGUOUS: "⚠️",
        RegistrationStatus.UNRESOLVED: "❔",
        RegistrationStatus.ERROR: "❌",
    }.get(status, "•")


def _render_identity(identity) -> None:
    st.subheader("1 · Identity")
    rec = identity.recording
    col_rec, col_work = st.columns(2)
    with col_rec:
        st.markdown("**Recording (master)**")
        st.write(
            {
                "title": rec.title,
                "artist": rec.artist_name,
                "ISRC": rec.isrc,
                "source": rec.source,
            }
        )
    with col_work:
        st.markdown("**Work (composition)**")
        if identity.work is None:
            st.warning(
                "Work unresolved — composition checks (MLC / ASCAP / BMI) can't run. "
                "This is NOT 'no gap'; we simply couldn't check the composition side. "
                "Add an ISWC to enable those checks."
            )
        else:
            work = identity.work
            writers = ", ".join(w.name for w in work.writers) or "(none listed)"
            st.write(
                {
                    "title": work.title,
                    "ISWC": work.iswc,
                    "writers": writers,
                    "source": work.source,
                }
            )


def _render_registration_map(gaps) -> None:
    st.subheader("2 · Registration map")
    rows = []
    for r in gaps.checks:
        rows.append(
            {
                "registry": r.registry.value,
                "side": r.side.value,
                "status": f"{_status_emoji(r.status)} {r.status.value}",
                "confidence": (
                    f"{r.confidence_band.value} ({r.confidence_score})"
                    if r.confidence_band is not None
                    else "—"
                ),
                "matched_id": r.matched_identifier or "—",
                "checked_at": r.checked_at.isoformat(timespec="seconds") if r.checked_at else "—",
                "notes / provenance": r.notes or "—",
            }
        )
    st.dataframe(rows, hide_index=True, use_container_width=True)

    # Use the schema's own definition of a candidate leak (NOT_FOUND) so the UI never drifts
    # from the rest of the system if that rule changes.
    leaks = gaps.candidate_leaks
    couldnt = [
        r for r in gaps.checks
        if r.status in (RegistrationStatus.UNRESOLVED, RegistrationStatus.ERROR)
    ]
    if leaks:
        st.error(
            "Candidate leaks (NOT_FOUND — checked, no registration found): "
            + ", ".join(r.registry.value for r in leaks)
        )
    if couldnt:
        st.info(
            "Couldn't check (UNRESOLVED / ERROR — flagged, NOT 'no gap'): "
            + ", ".join(f"{r.registry.value} [{r.status.value}]" for r in couldnt)
        )


def _render_estimate(estimate) -> None:
    st.subheader("3 · Estimated annual leak")
    st.metric(
        "Estimated annual leak (range)",
        f"${estimate.total_low:,.2f} – ${estimate.total_high:,.2f} {estimate.currency}",
    )
    st.caption(
        "Soft by design: rates are PLACEHOLDERS (not yet the real CRB/PRO/MLC schedules) and "
        "volume is artist-entered. The headline sums only the candidate-leak line items — "
        "it's 'money you're plausibly leaking', not all royalties you could theoretically earn."
    )
    if not estimate.line_items:
        st.warning(
            "No line items. Either no volume was entered, or the RateCard table isn't seeded "
            "(run seed_rate_cards — see the module docstring)."
        )
        return
    for li in estimate.line_items:
        with st.expander(
            f"{li.royalty_type.value}: ${li.low:,.2f} – ${li.high:,.2f} {li.currency}",
            expanded=True,
        ):
            st.write(
                {
                    "rate_version": li.rate_version,
                    "rate_effective_date": li.rate_effective_date,
                    **li.assumptions,
                }
            )


def main() -> None:
    st.set_page_config(page_title="Audentify", page_icon="🎵", layout="wide")
    st.title("Audentify")
    st.caption("Surfaces royalties indie artists are unknowingly losing. (MVP: information only.)")

    # "Load demo example" sits OUTSIDE the form (a form can hold only its submit button).
    if st.button("Load demo example (offline)"):
        _prefill_demo()

    with st.form("audit"):
        st.markdown("**Track**")
        c1, c2 = st.columns(2)
        title = c1.text_input("Title", value=_demo("title", ""))
        artist = c2.text_input("Artist", value=_demo("artist", ""))
        c3, c4 = st.columns(2)
        isrc = c3.text_input("ISRC (master key)", value=_demo("isrc", ""))
        iswc = c4.text_input(
            "ISWC (composition key — enables MLC/ASCAP/BMI checks)",
            value=_demo("iswc", ""),
        )
        spotify_url = st.text_input(
            "Spotify URL (optional; only used when live network is enabled)",
            value=_demo("spotify_url", ""),
            placeholder="https://open.spotify.com/track/...",
        )

        st.markdown(
            "**SoundExchange (master / digital performance)** — no public lookup exists, "
            "so self-report:"
        )
        se_label = st.radio(
            "Are you registered with SoundExchange?",
            list(_SOUNDEXCHANGE_OPTIONS),
            index=list(_SOUNDEXCHANGE_OPTIONS).index(_demo("soundexchange", "I don't know")),
            horizontal=True,
        )

        st.markdown("**Annual volume** (unit differs per royalty type — that's the point):")
        volumes: dict[RoyaltyType, int] = {}
        for royalty_type, label, unit_hint in _VOLUME_FIELDS:
            volumes[royalty_type] = st.number_input(
                label,
                min_value=0,
                step=1_000,
                value=int(_demo(royalty_type.value, 0)),
                help=f"Unit: {unit_hint}",
            )

        st.markdown(
            "**Uncertainty band** (± spread on every line item; wider = less precise):"
        )
        band_pct = st.slider(
            "Band (%)", min_value=0, max_value=90, value=int(_demo("band_pct", 30))
        )

        submitted = st.form_submit_button("Run audit")

    if not submitted:
        st.info(
            "Fill the form (or load the demo) and run the audit. The loop is synchronous "
            "and offline by default."
        )
        return

    track = TrackInput(
        title=title or None,
        artist_name=artist or None,
        isrc=isrc or None,
        iswc=iswc or None,
        spotify_url=spotify_url or None,
    )
    assumptions = RoyaltyAssumptions(
        annual_volume={rt: int(v) for rt, v in volumes.items() if v > 0},
    )
    request = AuditRequest(track=track, assumptions=assumptions)

    try:
        response = run_audit(
            request,
            soundexchange_self_report=_SOUNDEXCHANGE_OPTIONS[se_label],
            estimator_band=Decimal(str(band_pct)) / Decimal("100"),
        )
    except ValueError as e:
        # e.g. ManualIdentifier with neither title nor ISRC — show it, don't crash the app.
        st.error(f"Couldn't run the audit: {e}")
        return

    _render_identity(response.identity)
    _render_registration_map(response.gaps)
    _render_estimate(response.estimate)


if __name__ == "__main__":
    main()
