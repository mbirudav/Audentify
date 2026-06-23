"""Orchestration (Phase 4, lands LAST). Ties the three stages into the core loop:

    Stage 1 (identify recording + resolve work)
      -> Stage 2 (check each registry for gaps, skipping composition checks if no work)
      -> Stage 3 (estimate the annual leak as a range)

Depends only on the interfaces, so it can be stubbed/tested against fakes before the real
implementations exist. Real wiring is last because it needs them.

Open question to settle before this is wired: sync vs async. A request that scrapes 3
registries + fingerprints a file will time out if synchronous — if we go async, add an
app/jobs/ layer + submit-job/poll-status API. (See plan.md "Risks".)
"""

from __future__ import annotations

from app.schemas.audit import AuditRequest, AuditResponse


def run_audit(request: AuditRequest) -> AuditResponse:
    raise NotImplementedError("Phase 4: orchestrate Stage 1 -> 2 -> 3 behind the interfaces.")
