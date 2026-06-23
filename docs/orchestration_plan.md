# Audentify — Orchestration Plan (Phases 1–4)

Parallelized execution strategy for building Stage 1 (identity) → Stage 3 (estimate) →
Stage 2 (gap check) → Phase 4 (wire `services/audit.py` + Streamlit UI), implementing
behind the **already-frozen** contracts.

- **PRD / source of truth:** `CLAUDE.md`
- **Build plan:** `PLAN.md`
- **Frozen contracts (do not edit):** `app/pipeline/interfaces.py`, `app/schemas/*.py`,
  `app/domain.py`, `app/db/models.py`
- **State:** Phase 0 done. Every implementation file is a phase-tagged
  `raise NotImplementedError` stub. All test files are `pytest.mark.skip` placeholders.
- **Branch:** `auto/build-phases-1-4` (off `main`). Origin: `github.com/mbirudav/Audentify`.

### Hard constraints (carry into every spawn prompt)
1. **No live network / no scraping.** All external calls (Spotify, MusicBrainz, AcoustID,
   registry sites) go through fixtures. A live path may exist but must sit behind an
   **off-by-default** flag (`settings.allow_live_network: bool = False`). Tests never touch
   the network.
2. **No hardcoded rates.** The calculator reads the **`RateCard` table**, seeded from
   `app/rates/rates.yaml`. A rate literal anywhere in `calculator.py` is a defect.
3. **Info-only.** No money movement, no licensing, no collection. Estimates are ranges with
   visible assumptions.
4. **Two-copyrights discipline.** ISRC = master key only. Composition-side checks
   (MLC/ASCAP/BMI) key on the **work** (ISWC + writer IPI) and must return `UNRESOLVED`
   (never `NOT_FOUND`) when `identity.work` is absent.
5. **Don't touch frozen files.** If a contract feels wrong, **stop and flag** — do not edit
   `interfaces.py`, `schemas/`, `domain.py`, or `models.py` without a checkpoint sign-off.
6. **Provenance on every gap claim.** A `RegistrationResult` carries registry, side, status,
   confidence band+score, `checked_at`, and (when fetched) a `raw_response_id`.

---

## 1. Dependency DAG

### 1.1 The two real levers (already pulled — Phase 0)
`db/models.py` (universal blocker) → `interfaces.py` + `schemas/` (the contract freeze).
**Both are done and frozen.** This is why Phases 1–3 fan out so widely: the stages no longer
depend on *each other*, only on these frozen contracts. Every node below depends on the
freeze; that edge is omitted from the graph as a given.

### 1.2 Node graph (what actually blocks what)

```
                         [ Phase 0: FROZEN ]
              models.py · interfaces.py · schemas/ · domain.py
                                   │
        ┌──────────────────────────┼───────────────────────────────────┐
        │                          │                                    │
  ─ Phase 1: Stage 1 ─       ─ Phase 2: Stage 3 ─              ─ Phase 3: Stage 2 ─
        │                          │                                    │
  clients/spotify ─► s1/spotify    rates.yaml ─► RateCard         matching.py  (PURE)
  clients/mb ──────► s1/work_res   loader/seed      │                  │   (no deps)
  clients/acoustid ► s1/fingerprint     │           ▼                  ▼
  (none) ──────────► s1/manual          └──► calculator.py        base_adapter.check()
        │                                  (reads table)          (shared flow: guard·
        │                                                          fetch·parse·match·
        │   ┌─── SERIAL EDGE 1 ───┐                                persist·result)
        │   │ work_resolver MUST   │                                    │
        │   │ exist before ASCAP/  │            ┌───────────────────────┼─────────────┐
        │   │ BMI e2e-testable     │            ▼          ▼            ▼              ▼
        │   └──────────┬──────────┘          mlc.py    ascap.py      bmi.py    soundexchange.py
        │              │                    (ISRC try) (work req)  (work req)  (manual self-report)
        │              └───────────────────────────────┘  ▲           ▲
        │                  work_resolver output ──────────┴───────────┘  (e2e only)
        │                                                                     │
        └──────────────────────┬──────────────────────────────────────────────┘
                               │
                        ─ Phase 4 (LAST) ─
                               │
        ┌──────────────────────┴───────────────────────┐
        │                                               │
  clients/http + cache/store           ┌──── SERIAL EDGE 2 ────┐
  (transport + provenance persist;     │ services/audit.py wires │
   used by ALL Stage 2 adapters,       │ Stage 1→2→3; needs real │
   build with base_adapter)            │ impls → lands LAST      │
        │                              └───────────┬────────────┘
        ▼                                          ▼
  fixtures + conftest                       streamlit_app/app.py
  (shared test harness;                     (scaffold vs stubs EARLY;
   build first inside Phase 3)               re-point to audit at end)
```

### 1.3 Edge inventory

**Hard serial edges (cannot parallelize — these gate the whole plan):**

| # | Edge | Why | Enforced by |
|---|------|-----|-------------|
| S1 | `matching.py` **→** Stage 2 adapters (`base_adapter.check()` + all 4) | adapters call `score_match` / `band_for_score` to turn a parsed candidate into a confidence band; without it they can't produce a real `RegistrationResult` | **Gate C2** before any adapter merges |
| S2 | `work_resolver.py` **→** `ascap.py` / `bmi.py` **end-to-end** | composition registries key on the work (ISWC + writers); ISRC won't join. They can be *coded* against the `WorkResult` schema in parallel, but can't be *e2e-tested* until a real `WorkResult` exists | **Gate C3**: adapters may be written in parallel; their e2e tests are unskipped only after S2 lands |
| S3 | real Stage 1/2/3 impls **→** `services/audit.py` real wiring | orchestration ties the three stages; real wiring needs real implementations (it can be *stubbed* against interfaces earlier) | **Gate C4**: audit.py is the last code node |
| S0 | shared test harness (`conftest.py` + `tests/fixtures/`) **→** every Phase-3 adapter test | adapters load registry HTML/JSON from fixtures; the harness + a fixture convention must exist before adapters are testable | built **first inside the Phase 3 session**, before the registry fan-out |

**Soft / coordination edges (parallel-safe, but watch the shared file):**

| Edge | Note |
|------|------|
| `clients/*` → matching `stageN/*` | each client wrapper is independent and can be built in the same session as its consumer; the consumer must not embed transport logic (retry/rate-limit lives in the client) |
| `base_adapter.check()` → `mlc/ascap/bmi/soundexchange` `_query()` | the shared `check()` flow (guard side, fetch-cached, parse, match, persist, build result) is written **once**; the 4 adapters then only implement `_query()` + parse. base_adapter is the in-session serial prefix of Phase 3 |
| `clients/http` + `cache/store` → all Stage 2 adapters | transport + raw-response persistence are shared infra for the adapter fan-out; build alongside base_adapter |
| Streamlit `app.py` → stubbed `audit` (early), real `audit` (end) | scaffold the 3 panels against a fake `run_audit` as soon as the session starts; re-point to the real `run_audit` at Gate C4. **Streamlit is a long-pole that should start early and finish late.** |

**Independent nodes (zero cross-edges — pure fan-out once frozen):**
`s1/spotify`, `s1/manual`, `s1/fingerprint`, `work_resolver`, `calculator + seed`,
`matching`, each `clients/*`. Within Phase 1 the four identifiers + resolver are mutually
independent; within Phase 2 the calculator stands alone.

### 1.4 File-level conflict surface (why this parallelizes cleanly)
The package `__init__.py` files (`stage1_identity`, `stage2_gaps`, `stage3_estimate`,
`clients`) are **pure docstrings with no re-exports**. Agents adding implementations import
the concrete class directly from its module, so **no two agents need to edit the same
`__init__.py`**. The only shared-file hotspots are:
- `pyproject.toml` (a session may add a dep extra or a pytest marker) — **serialize edits
  here; one agent owns it per session, or fold into the integration step**.
- `conftest.py` / `tests/fixtures/` — **owned by the Phase 3 session's first task** (S0);
  Phase 1 and Phase 2 sessions add their own fixtures in separate files under the same dir.
- `app/config.py` — the `allow_live_network` flag is added **once** (assign to the Phase 1
  session, since it lands first and the flag gates Stage 1's clients).

---

## 2. Session map

Four sessions, ordered by the learning sequence (`PLAN.md`) but overlapped where the DAG
permits. "Session" = one orchestration unit (a `main` agent + its sub-agent team or, for a
solo run, one focused work block). **Phases 1 and 2 have no dependency between them and can
run fully concurrently** (different sessions, different files). Phase 3 starts as soon as
`matching.py` is green (it does not need Phases 1–2 to finish). Phase 4 wiring is strictly
last; its Streamlit half starts early.

| Session | Phase | Scope | Starts after | Parallel within? | Worktree? |
|---------|-------|-------|--------------|------------------|-----------|
| **A — Identity** | 1 | `clients/{spotify,musicbrainz,acoustid}`, `s1/{spotify,manual,fingerprint,work_resolver}`, `test_stage1`, `config.allow_live_network` | Phase 0 (now) | Yes — 4 identifier/resolver agents + client wrappers | optional |
| **B — Estimate** | 2 | `rates.yaml` (real-ish placeholders), RateCard **seed loader**, `calculator.py`, `test_stage3` | Phase 0 (now) — **concurrent with A** | Low (one cohesive unit; split seed-loader vs calculator if desired) | optional |
| **C — Gaps** | 3 | `matching.py` **first**, then `base_adapter.check()` + `clients/http` + `cache/store`, then `{mlc,ascap,bmi,soundexchange}`, `test_matching` + `test_stage2`, shared `conftest`+fixtures | **`matching.py` green** (C2). Coding can begin concurrent with A/B; adapter merges gate on C2 | Yes — but **serial prefix** (matching → base_adapter), then 4 adapters fan out | **recommended** (4 adapters + scrapers churn many files) |
| **D — Wire + UI** | 4 | Streamlit `app.py` (early, vs stubs), `services/audit.py` (last), `app/main.py` audit endpoint, end-to-end smoke test | Streamlit: now (vs stub). audit.py: after A+B+C land (C4) | UI and audit are separable | no |

**Recommended wall-clock overlap (solo-with-agents or small team):**

```
t →
A (Identity)    ███████████████░░░░░░░░░░░░░░░░
B (Estimate)    ████████░░░░░░░░░░░░░░░░░░░░░░░░
C (Gaps)        ░░░matching██░░base+infra██░░adapters████████
D-UI (stub)     ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░██  (scaffold early, re-point late)
D-audit                                  ░░░░░░░░░██  (last)
                C1        C2     C3              C4
```

A and B run from t0. C's `matching.py` is tiny and pure — finish it at t0 too so the adapter
fan-out is unblocked early (it's serial edge S1 and the riskiest long-pole otherwise). D-UI
scaffolds against a fake at t0 and only re-points at the end.

---

## 3. Agent team spawn prompts

Each prompt is self-contained: paste it as the task for one agent. **Every agent inherits
the six hard constraints in the header** — they're restated tersely per prompt as a
guardrail. Agents implement **only their listed files**, replace the `NotImplementedError`
stub bodies, and unskip the matching test placeholders they own.

> **Shared preamble (prepend to every spawn):**
> "Read `CLAUDE.md` ('The two copyrights' section) and `app/pipeline/interfaces.py` +
> `app/schemas/` before writing code. These contracts are FROZEN — do not edit them,
> `app/domain.py`, or `app/db/models.py`; if one seems wrong, STOP and report it. No live
> network and no scraping in any code path that tests exercise — use fixtures; any live call
> sits behind `settings.allow_live_network` (default False). No hardcoded rates. Info-only.
> Run `uv run ruff check` and `uv run pytest -q` before declaring done; only your own files'
> tests should newly pass (don't unskip tests you don't own). Return: files changed, what
> each does, fixtures added, and any contract friction."

### Session A — Stage 1 (Identity)

**A0 — config flag (do first, 1 task, blocks A1/A3):**
> Add `allow_live_network: bool = False` to `app/config.py` `Settings`. Document it: "Master
> switch for real external calls (Spotify/MusicBrainz/AcoustID); OFF by default so tests and
> CI never hit the network." No other change. This is the seam every Stage 1 client checks
> before making a real request.

**A1 — Spotify identifier + client:**
> Implement `app/clients/spotify.py` (`SpotifyClient.get_track`, wrapping spotipy) and
> `app/pipeline/stage1_identity/spotify.py` (`SpotifyIdentifier.identify` →
> `RecordingResult` with title/artist/ISRC/duration/spotify_id, `source="spotify"`). The
> client makes a **real** spotipy call **only** if `settings.allow_live_network`; otherwise
> it raises a clear "live network disabled" error. The identifier parses a Spotify URL **or**
> id from `TrackInput`. **Spotify returns NO writers/ISWC** — `RecordingResult` only;
> `work` stays unresolved (that's `work_resolver`'s job). Add `tests/fixtures/spotify_*.json`
> (a captured track payload) and `tests/test_stage1.py::test_spotify_returns_isrc_but_no_work`
> driven off the fixture (no network). Unskip only that test.

**A2 — Manual identifier:**
> Implement `app/pipeline/stage1_identity/manual.py` (`ManualIdentifier.identify`). Build a
> `RecordingResult` from `TrackInput.{title,artist_name,isrc}`. This path is **also the work
> fallback**: if writer fields are present, it must be able to express them as `PartyRef`s so
> a later step can build a `WorkResult` (coordinate the exact shape with A4 — manual is the
> non-MusicBrainz route to the composition side). Raise a clear error if neither title nor
> isrc is given. Add a unit test (no network, no DB).

**A3 — Fingerprint identifier + AcoustID client (build last in A):**
> Implement `app/clients/acoustid.py` (`AcoustIDClient.lookup`) and
> `app/pipeline/stage1_identity/fingerprint.py` (`FingerprintIdentifier.identify`): fpcalc
> fingerprint → AcoustID → MusicBrainz recording → `RecordingResult`, `source="fingerprint"`.
> The `fpcalc` binary and all HTTP are **live-only** (behind `allow_live_network`); when off,
> raise "fingerprinting requires live network + fpcalc binary". Document the fpcalc system
> dep in a module docstring (Railway/Render won't have it). Test with a fixture AcoustID
> response + a tiny stub fingerprint — **never invoke fpcalc in tests**.

**A4 — Work resolver + MusicBrainz client (the composition hinge — coordinate with C):**
> Implement `app/clients/musicbrainz.py` (`MusicBrainzClient.work_relations_for_isrc`,
> honoring the custom UA + ~1 req/s already in config) and
> `app/pipeline/stage1_identity/work_resolver.py`
> (`MusicBrainzWorkResolver.resolve_work`): recording → follow MusicBrainz **work-relations**
> → `WorkResult(iswc, writers=[PartyRef...], source="musicbrainz")`. **Return `None`** when
> no work-relation exists (common for indie tracks) — callers must degrade gracefully, never
> assert "no gap". Real MB calls are live-only (behind the flag). Add a fixture MB
> work-relations response and
> `tests/test_stage1.py::test_work_resolver_populates_iswc_and_writers` (off the fixture) plus
> a "returns None when no work-relation" test. **This is serial edge S2** — Session C's
> ASCAP/BMI e2e tests consume this `WorkResult`; keep the writer/IPI shape exactly as the
> `PartyRef` schema specifies.

### Session B — Stage 3 (Estimate)

**B1 — RateCard seed loader (do first in B):**
> Write a seeding utility (suggest `app/rates/loader.py`,
> `seed_rate_cards(session, yaml_path) -> int`) that reads `app/rates/rates.yaml` and
> **upserts** `RateCard` rows (idempotent on the `rate_card_version_unique` constraint:
> royalty_type+registry+version+effective_date). The **table is the source of truth**; YAML
> only seeds it. Add a test that seeds into an in-memory/SQLite-or-mocked session and asserts
> rows land + re-running is idempotent. Keep `rates.yaml` placeholders but tag each row's
> `notes` with the real CRB/PRO/MLC schedule it should later cite. Do **not** put rates in
> code.

**B2 — Per-royalty-type calculator:**
> Implement `app/pipeline/stage3_estimate/calculator.py` (`RateCardEstimator.estimate`).
> **Per royalty type, never one flat formula:** MECHANICAL (MLC, per-stream), PERFORMANCE
> (PRO, pooled/survey — per-stream is an explicit approximation), DIGITAL_PERFORMANCE
> (SoundExchange, per-play non-interactive). Pull the rate from the **RateCard table** (latest
> effective, or `assumptions.rate_version` if pinned) — **read the table, never hardcode**.
> Volume is per-type from `RoyaltyAssumptions.annual_volume`. Output a **range** (low/high)
> per `RoyaltyLineItem`, stamp each with `rate_version` + `rate_effective_date`, and expose
> the assumptions used in the `assumptions` dict (so the UI can show + adjust them). Build
> against a **mock `IdentityResult`** — you do **not** need Stage 1 to run. Unskip
> `tests/test_stage3.py`: assert (a) one line item per royalty type, (b) output is a range,
> (c) the rate came from the versioned table (change the version → estimate changes). Use a
> seeded/mocked RateCard so the test needs no live DB.

### Session C — Stage 2 (Gaps)  ·  **worktree recommended**

**C1 — Shared test harness + fixtures (do FIRST — serial edge S0):**
> Create `tests/conftest.py` and `tests/fixtures/` with a convention for loading captured
> registry payloads (HTML/JSON) by filename, plus a fixture factory that builds an
> `IdentityResult` (a) with a resolved work and (b) without one. No network anywhere. This
> harness is what every adapter test below loads from — land it before the adapter fan-out.

**C2 — `matching.py` (PURE, do SECOND — serial edge S1, the highest-value unit):**
> Implement `app/pipeline/stage2_gaps/matching.py`: `score_match(query, candidate) -> float`
> (rapidfuzz similarity normalized to 0..1) and `band_for_score(score) -> ConfidenceBand`
> (threshold map to HIGH/MEDIUM/LOW). **Pure functions, zero deps.** TDD it: unskip
> `tests/test_matching.py` — exact title → HIGH; a near-miss → **not asserted** (MEDIUM/LOW →
> the caller will mark AMBIGUOUS, not NOT_FOUND). A false positive (telling someone they leak
> when they don't) is the worst outcome, so pin the thresholds with synthetic data here. This
> gates **all** adapters (Gate C2) — get it green before C3/C4.

**C3 — base adapter + shared infra (do THIRD — in-session serial prefix):**
> Implement the shared `RegistryAdapter.check()` flow in
> `app/pipeline/stage2_gaps/base_adapter.py`: (1) **guard the copyright side** — a COMPOSITION
> adapter with `identity.work is None` returns a `RegistrationResult` with status
> **`UNRESOLVED`** (never NOT_FOUND); (2) call the subclass `_query()` (fetch via
> `clients/http`, but **fixture-backed in tests**); (3) persist the raw response via
> `cache/store.save_raw_response` and capture its `raw_response_id`; (4) parse → fuzzy-match
> via `matching.py` → set status + `confidence_band`/`confidence_score`; (5) return a
> provenance-complete `RegistrationResult` (`registry`, `side`, `status`, confidence,
> `matched_identifier`, `checked_at`, `raw_response_id`). Also implement `app/clients/http.py`
> (`get_http_client` → configured httpx.Client; **live-only** behind the flag) and
> `app/cache/store.py` (`save_raw_response` → write a `RawRegistryResponse` with
> `content_hash`, return its id). Adapters below only implement `_query()` + parse.

**C4 — Registry adapters (FAN OUT — 4 parallel agents, after C3):**

> **C4-mlc** — `app/pipeline/stage2_gaps/mlc.py` `_query()` + parse. MLC is composition-side
> but keeps ISRC→work links, so **try ISRC as a search input** (note in code it's verified
> against fixtures, not the live site in this build). Build end-to-end first among the four.
> Add a fixture MLC response + a `test_stage2` case: a found work → REGISTERED with provenance.

> **C4-ascap** — `app/pipeline/stage2_gaps/ascap.py` `_query()` + parse, keyed on
> **title + writer (+ ISWC)** from `identity.work`. Code it against the `WorkResult` schema
> now; its **e2e test consumes Session A4's real `WorkResult`** (serial edge S2). Add the
> required-test: `test_composition_adapter_unresolved_without_work` (work=None → UNRESOLVED).

> **C4-bmi** — `app/pipeline/stage2_gaps/bmi.py` `_query()` + parse, same shape as ASCAP,
> independent adapter. Fixture BMI response + a found/not-found test.

> **C4-sx** — `app/pipeline/stage2_gaps/soundexchange.py`: **no public lookup** — implement
> the **manual self-report toggle**, not a scrape. The artist tells us registered/not; record
> it as a `RegistrationResult` with `source`/notes = "self-report" and full provenance. MASTER
> side (keys on ISRC). Test the self-report → REGISTERED/NOT_FOUND mapping.

> **C4-shared test** — unskip `tests/test_stage2.py`:
> `test_gap_claim_stores_provenance` (every result has registry/side/status/checked_at and a
> `raw_response_id` when a response was fetched) and the UNRESOLVED-without-work case above.

### Session D — Wire the loop + Streamlit UI

**D1 — Streamlit scaffold (start EARLY, vs stubs):**
> Build the three panels in `streamlit_app/app.py` against a **stubbed `run_audit`** (a local
> fake returning a hand-built `AuditResponse`) — **don't wait for the real stages**: (1)
> identity + ISRC/ISWC, (2) registration map per collector **with provenance** (show
> status, confidence, checked_at, registry side; flag `unresolved` registries explicitly —
> never imply "no gap"), (3) estimated annual leak **range** with the assumptions exposed and
> adjustable. Keep the UI **fully isolated** from backend logic (so Next.js can replace it
> later). Re-point to the real `run_audit` at D2.

**D2 — `services/audit.py` real wiring (LAST — serial edge S3):**
> Implement `run_audit(AuditRequest) -> AuditResponse` in `app/services/audit.py`: Stage 1
> (identify recording → `resolve_work`) → Stage 2 (run each registry adapter; **skip /
> mark UNRESOLVED the composition checks when `work is None`**, route by `REGISTRY_SIDE`) →
> Stage 3 (estimate the range). Assemble `GapReport` (checks + `unresolved`) and
> `EstimateResult`. **Settle sync vs async first** (see `PLAN.md` Risks): v1 may run sync; if
> a real audit would time out, note where an `app/jobs/` submit+poll layer goes — but for this
> fixture-backed build, sync is fine. Wire the FastAPI audit endpoint in `app/main.py`. Add an
> end-to-end smoke test that runs a fixture track all the way through (no network). Re-point
> `streamlit_app/app.py` from the stub to this `run_audit`.

---

## 4. Checkpoint gates

Stop-the-line review points. Each gate has an **owner action** (what must be true) and a
**verification** (how to confirm). No downstream node starts until its upstream gate is green.

| Gate | When | Must be true | Verify | Blocks |
|------|------|--------------|--------|--------|
| **C0 — Contract integrity** | continuously | `interfaces.py`, `schemas/`, `domain.py`, `models.py` **unchanged**; no new rate literal in `calculator.py`; no un-flagged network call | `git diff --stat` shows none of the frozen files; `grep -rn` for numeric rate literals in `stage3_estimate/`; `grep -rn allow_live_network` covers every external client | everything (it's the invariant) |
| **C1 — Stage 1 green** | end of Session A | 3 identifiers + work_resolver return correct shapes off fixtures; Spotify yields recording-only; work_resolver returns `None` gracefully; `allow_live_network` gates every live call | `uv run pytest tests/test_stage1.py -q` passes; manual check that no test hits the network | ASCAP/BMI **e2e** (S2); audit.py (S3) |
| **C2 — `matching.py` green** | early in Session C | `score_match`/`band_for_score` implemented; thresholds pin exact→HIGH and near-miss→not-asserted; **pure, no deps** | `uv run pytest tests/test_matching.py -q` passes | **all** Stage 2 adapters (S1) |
| **C3 — Estimate green** | end of Session B | calculator is per-royalty-type, outputs ranges, reads RateCard table; seed loader idempotent; **zero hardcoded rates** | `uv run pytest tests/test_stage3.py -q` passes; flip a rate version in a seeded card → estimate changes | audit.py Stage 3 leg |
| **C4 — base_adapter + infra green** | mid Session C | shared `check()` flow done; COMPOSITION-without-work → **UNRESOLVED**; raw response persisted with `raw_response_id`; http client is live-only | adapter unit run; assert UNRESOLVED path + provenance fields populated | the 4 adapter `_query()` impls |
| **C5 — Stage 2 adapters green** | end of Session C | 4 adapters parse fixtures into provenance-complete results; ASCAP/BMI e2e use a **real `WorkResult`** from C1; SoundExchange is self-report; MLC tries ISRC | `uv run pytest tests/test_stage2.py -q` passes; `test_gap_claim_stores_provenance` + UNRESOLVED-without-work both pass | audit.py Stage 2 leg (S3) |
| **C6 — End-to-end** | end of Session D | `run_audit` runs a fixture track Stage 1→2→3; `AuditResponse` well-formed; Streamlit shows all 3 panels off the real service; composition checks skip/UNRESOLVE when no work | `uv run pytest -q` (full suite, nothing skipped that should run); `uv run streamlit run streamlit_app/app.py` renders 3 panels; `GET /health` ok | ship / demo |
| **G-merge — Integration** | merging each worktree | no two branches edited the same shared file (`pyproject.toml`, `conftest.py`, an `__init__.py`); full suite green on the merge | `git merge --no-ff` clean; `uv run ruff check && uv run pytest -q` | next session's start |

**Human review checkpoints (per `PLAN.md` "stop and review" ethos, and the mini-lesson
contract in `CLAUDE.md`):**
- After **C1**: confirm the recording/work split is populated correctly (the two-copyrights
  bedrock) before building anything that joins on it.
- After **C2**: review the confidence thresholds *with Maruthi* — false-positive cost is the
  product's credibility; this is the one threshold worth a human eye.
- Before **D2**: settle **sync vs async** explicitly (it's hard to retrofit). Sign off that
  v1-sync is acceptable for the fixture build.

---

## 5. Context budget estimates

Rough per-agent input-context cost. The repo is small and the contracts are the bulk of the
required reading; **the dominant cost is the shared "must-read" set, not the target files.**
Budgets assume an agent reads the shared set once + its own files + writes its impl/tests.

**Shared must-read set (every agent loads this):** `CLAUDE.md` (~3k tok), the relevant
`schemas/*.py` (~1–2k), `interfaces.py` (~1k), `domain.py` (~1.5k). ≈ **6–8k tokens baseline**
per agent. `models.py` (~3.5k) is needed by B (RateCard), C (RawRegistryResponse/RegCheck),
and D (joins) but not the Stage 1 identifiers.

| Agent / unit | Reads (beyond shared) | Writes | Est. input ctx | Est. total budget |
|---|---|---|---|---|
| A0 config flag | `config.py` | small edit | ~2k | **~10k** |
| A1 Spotify | spotipy docs skim, `clients/spotify` stub | client + identifier + fixture + 1 test | ~6k | **~18k** |
| A2 Manual | `manual` stub, coordinate A4 shape | identifier + test | ~4k | **~14k** |
| A3 Fingerprint | acoustid+fpcalc skim, 2 stubs | client + identifier + fixture + test | ~7k | **~20k** |
| A4 Work resolver | MusicBrainz work-rel skim, `PartyRef` schema close-read, 2 stubs | client + resolver + 2 fixtures + 2 tests | ~8k | **~24k** (Stage 1's heaviest) |
| B1 Seed loader | `models.py` RateCard, `rates.yaml` | loader + test | ~6k | **~16k** |
| B2 Calculator | `models.py` RateCard, `estimate.py` close-read | calculator + 2 tests | ~6k | **~20k** |
| C1 Harness | existing test patterns | conftest + fixtures dir | ~4k | **~12k** |
| C2 matching | rapidfuzz skim, `domain.ConfidenceBand` | matching + TDD tests | ~3k | **~12k** (pure, cheap) |
| C3 base+infra | `models.py` (RawRegistryResponse/RegCheck), `gaps.py`, httpx skim | base_adapter + http + store | ~8k | **~26k** (Stage 2's heaviest) |
| C4-mlc/ascap/bmi/sx (each) | base_adapter (just-written), 1 adapter stub, 1 fixture | `_query`+parse + fixture + test | ~5k each | **~16k each** |
| D1 Streamlit | streamlit skim, `audit.py` schema, all 3 result schemas | UI (3 panels) + stub | ~6k | **~22k** (UI verbosity) |
| D2 audit wiring | every interface, `REGISTRY_SIDE`/`REGISTRY_ROYALTY` maps, all impls' public shapes | orchestrator + endpoint + e2e test | ~10k | **~30k** (integrative — reads the most) |

**Session rollups (sum of member agents + ~5k orchestration overhead):**

| Session | Agents | Est. total context |
|---|---|---|
| A — Identity | A0–A4 | **~80–90k** |
| B — Estimate | B1–B2 | **~40k** |
| C — Gaps | C1–C3 + 4×C4 | **~120–130k** (the largest; worktree-isolate it) |
| D — Wire+UI | D1, D2 | **~55k** |

**Budgeting notes:**
- **Frontload the shared read.** If running a true multi-agent fan-out, have the orchestrator
  read `CLAUDE.md` + contracts once and pass a distilled brief, rather than each of ~12 agents
  re-reading ~7k of contracts (saves ~70k aggregate).
- **C is the budget hotspot** because of base_adapter + the 4-way adapter fan-out. The
  worktree keeps its file churn off the others; its agents share the (small) base_adapter
  read. Run the 4 C4 adapters concurrently — they don't read each other.
- **D2 is the single most expensive agent** (it integrates everything), but it reads *public
  shapes*, not full implementations — keep it that way; it shouldn't need to re-read the
  bodies A/B/C wrote, only their class names + method signatures (which the interfaces already
  pin). That's the payoff of the frozen ABCs.
- Total fresh-context across the whole build ≈ **295–315k tokens** of input if frontloaded
  once; naively (every agent re-reads everything) it balloons past **450k**. The freeze is
  what keeps it cheap — stages read contracts, not each other.

---

## 6. Execution summary (the one-screen version)

1. **Now (t0), concurrently:** launch **A** (Stage 1, worktree optional), **B** (Stage 3),
   and **C2** (`matching.py` — finish it immediately; it gates all of Stage 2). Scaffold
   **D1** (Streamlit) against a fake `run_audit`.
2. **Gate C2 green →** build **C1** (harness) + **C3** (base_adapter + http + cache), then
   **fan out C4** (mlc/ascap/bmi/sx) — 4 parallel agents.
3. **Gate C1 (Stage 1) green →** unskip ASCAP/BMI **e2e** tests against the real `WorkResult`
   (serial edge S2 satisfied).
4. **Gates C1 + C3(estimate) + C5(adapters) green →** wire **D2** (`services/audit.py` +
   endpoint), settle sync/async, re-point Streamlit to the real service.
5. **Gate C6 →** full suite green, 3-panel demo, `/health` ok. Ship the audit (info-only).

**The three edges that must never be violated:** `matching.py` before any adapter (S1);
`work_resolver` before ASCAP/BMI e2e (S2); real impls before `audit.py` wiring (S3). Plus the
standing invariant **C0**: frozen contracts stay frozen, no hardcoded rates, no un-flagged
network.
