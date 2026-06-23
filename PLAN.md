# plan.md — Audentify Build Plan

The actionable roadmap. The PRD is the source of truth for *what* and *why*; this doc is *in what order* and *what each piece looks like*. Update it as we go.

> **Read CLAUDE.md "The two copyrights" before building anything.** A track is two separate copyrights — **master** (ISRC) and **composition** (ISWC + writer IPI). ISRC is the join key for the master side **only**; ASCAP/BMI key on the composition. Stage 1 must resolve **both**.

---

## Directory structure

```
Audentify/
├── CLAUDE.md                  # persistent context, read every session
├── plan.md                    # this file
├── README.md
├── pyproject.toml             # deps (or requirements.txt)
├── .env.example               # secrets template: SPOTIFY_*, ACOUSTID_API_KEY, DATABASE_URL
├── alembic.ini
├── alembic/
│   └── versions/              # migrations
├── app/
│   ├── main.py                # FastAPI entrypoint
│   ├── config.py              # settings via pydantic-settings
│   ├── domain.py              # cross-stage enums: RoyaltyType, RegistryName, ConfidenceBand, RegistrationStatus
│   ├── db/
│   │   ├── session.py         # engine + session
│   │   └── models.py          # Works, Recordings, Parties(IPI), Splits, RegistrationStatus, RateCard, RawRegistryResponse
│   ├── schemas/               # Pydantic request/response models — FREEZE EARLY (this unblocks parallel work)
│   ├── clients/               # thin external wrappers: retry / backoff / rate-limit / keys (no pipeline logic)
│   │   ├── spotify.py
│   │   ├── musicbrainz.py     # work-relations → ISWC + writers; custom User-Agent, ~1 req/s
│   │   ├── acoustid.py
│   │   └── http.py            # shared httpx client for scrapers
│   ├── cache/                 # raw-response cache + provenance (or persist via RawRegistryResponse table)
│   ├── pipeline/
│   │   ├── interfaces.py      # ABCs: Identifier, WorkResolver, GapChecker, Estimator — FREEZE EARLY
│   │   ├── stage1_identity/
│   │   │   ├── spotify.py        # recording identity → ISRC
│   │   │   ├── manual.py         # title + ISRC + writer entry
│   │   │   ├── fingerprint.py    # Chromaprint + AcoustID + MusicBrainz (needs fpcalc binary)
│   │   │   └── work_resolver.py  # recording → work (ISWC + writers) — the composition side
│   │   ├── stage2_gaps/
│   │   │   ├── base_adapter.py   # registry adapter ABC; declares master vs composition keying
│   │   │   ├── mlc.py            # composition (mechanical); may accept ISRC search input
│   │   │   ├── ascap.py          # composition (performance); needs work identity
│   │   │   ├── bmi.py            # composition (performance); needs work identity
│   │   │   ├── soundexchange.py  # master; no public lookup → manual self-report
│   │   │   └── matching.py       # rapidfuzz + confidence scoring (pure, fully testable)
│   │   └── stage3_estimate/
│   │       └── calculator.py     # per-royalty-type; reads rates from the versioned RateCard table
│   ├── rates/
│   │   └── rates.yaml          # SEED for the versioned RateCard table — NOT the source of truth
│   └── services/
│       └── audit.py           # orchestration: ties the 3 stages into the core loop
├── streamlit_app/
│   └── app.py                 # v0 UI — build against stubbed services once schemas are frozen
└── tests/
    ├── test_models.py         # incl. splits-sum-to-100 validation
    ├── test_matching.py       # highest-value unit test: confidence thresholds, false positives
    ├── test_stage1.py
    ├── test_stage2.py
    └── test_stage3.py
```

**Why this shape:** `pipeline/` holds the three stages, each behind an interface in `interfaces.py` so any implementation is swappable; `stage2_gaps/` puts every registry behind its own adapter so a broken scraper never touches the others. `clients/` keeps external API/HTTP concerns (retry, rate-limit, keys, User-Agent) out of the stage logic — so a stage *orchestrates* and never holds raw HTTP. `cache/` (or a `RawRegistryResponse` table) stores timestamped raw responses as both a dev-speed cache and the evidence trail behind every gap claim. `rates/rates.yaml` only *seeds* the versioned `RateCard` table — the table, not the file, is the source of truth, so a past estimate can be reproduced at its effective rate. `streamlit_app/` is fully isolated from the backend so swapping in Next.js later doesn't ripple into the logic. Note `work_resolver.py` in Stage 1: it resolves the **composition** (ISWC + writers) that ASCAP/BMI key on — ISRC alone is the master side only.

---

## Build phases

> Phase **order** below is the right *learning* sequence. The *dependency graph* is looser — see **Parallelization** for what can be built concurrently. Items tagged **[P]** are parallel-safe once interfaces + schemas are frozen.

### Phase 0 — Scaffold + data model *(do first; universal blocker)*
- Init repo, `pyproject.toml`, virtualenv, `.env.example`, FastAPI skeleton, Postgres connection.
- Define the five core linked entities in `models.py`: Works, Recordings, Parties (each with an IPI), Splits, RegistrationStatus. (`RateCard` lands with Phase 2 and `RawRegistryResponse` with Phase 3 — note them now so the schema isn't a surprise later.)
- First Alembic migration.
- **Splits must sum to 100%** per work and per recording — Postgres can't enforce a cross-row sum cleanly, so this is app-level validation (and a test). Get this right now; everything hangs off the schema.
- **Freeze `pipeline/interfaces.py` (ABCs) and `schemas/` here too** — the moment these contracts exist, the stages stop depending on each other. This is the single highest-leverage thing for parallel work.
- *Learning checkpoint:* why master vs composition are separate entities, and why IPIs are the thing that lets registries match a work to a person.

### Phase 1 — Stage 1: identity resolution
Goal: track in → **two** outputs behind interfaces — the **recording** (canonical track + ISRC) *and* the **work** (ISWC + writers/IPIs). ISRC alone does not feed the composition-side registries (CLAUDE.md "The two copyrights").
- **[P]** `spotify.py` first — easiest, returns ISRC directly (recording side). Covers most distributed tracks. Note: Spotify gives **no** writers/ISWC.
- **[P]** `manual.py` — title + ISRC + writer entry. Core, not optional (new artists are badly indexed, and it's the fallback for the work side too).
- **[P]** `work_resolver.py` — recording → work (ISWC + writers) via MusicBrainz work-relations. This is what makes Stage 2's ASCAP/BMI checks possible at all. **Hard dependency: ASCAP/BMI gap checks need this.**
- **[P]** `fingerprint.py` last — Chromaprint + AcoustID + MusicBrainz for raw files. Needs the `fpcalc` binary, so most setup overhead.
- *Learning checkpoint:* what ISRC vs ISWC are, why master and composition are different copyrights, and why ISRC is the join key for the **master** side only — the composition side joins on ISWC + writer IPI.

### Phase 2 — Stage 3: revenue estimate *(easy win, before Stage 2 on purpose)*
Goal: estimated annual leak as a **range**.
- **[P]** `calculator.py`: **per royalty type**, not one flat formula. Mechanical (MLC) is per-stream; PRO performance is a pooled/survey distribution (a per-stream rate is an approximation); SoundExchange is per-play on non-interactive only. "Volume" means streams for some types, spins for others. Build it against a *mock* identity result — it doesn't need Stage 1 to actually run.
- Rates loaded from the **versioned `RateCard` table** (seeded from `rates.yaml`), each row carrying `version` + `effective_date`. Volume is artist-entered for v1.
- Output a range with assumptions exposed and adjustable — no false precision.
- *Learning checkpoint:* the royalty types (master via SoundExchange; composition performance via PRO; composition mechanical via MLC) and which rate base maps to which.

### Phase 3 — Stage 2: registration-gap check *(the hard part / the moat)*
Goal: a map of where the artist is vs isn't registered, **with provenance** (what was checked, where, when, confidence).
- `base_adapter.py` first, then **one** registry end-to-end before adding the rest. Each adapter declares what it keys on:
  - **[P]** `mlc.py` — composition (mechanical); may accept ISRC as a search input (verify against the live site).
  - **[P]** `ascap.py` / `bmi.py` — composition (performance); need **work identity** (title + writer + ISWC) from Stage 1's `work_resolver`.
  - **[P]** `soundexchange.py` — master; no public lookup → manual self-report toggle.
- Cache raw registry responses (timestamped) — for dev speed, to avoid bans, and as the evidence behind every gap claim.
- **[P]** `matching.py`: rapidfuzz fuzzy match on title/writer → confidence score. Low confidence flags for a human instead of asserting a gap. **Pure function — TDD it with synthetic data before any scraper exists.**
- *Learning checkpoint:* why fuzzy matching needs a confidence threshold, and what false-positive vs false-negative cost looks like here (telling someone they're leaking money when they aren't is worse than missing one).

### Phase 4 — Wire the loop + Streamlit UI
- `services/audit.py` orchestrates Stage 1 → 2 → 3. (Can be stubbed against interfaces earlier; real wiring needs real implementations, so it lands last.)
- **[P]** Streamlit screen: enter a track → see (1) identity + ISRC/ISWC, (2) registration map per collector with provenance, (3) estimated annual leak range. **Scaffold against stubbed services as soon as schemas are frozen — don't wait for the real stages.**
- This hits the success criteria — a demoable end-to-end app.

---

## Parallelization (read this before fanning out work)

The build *order* above is the right learning sequence. The true **dependency graph** is looser — once two contracts are frozen, most work runs concurrently. **Freeze these two first; they are the lever:**

1. **Data model** (`db/models.py`) — universal blocker; everything reads/writes these entities. Build alone, first.
2. **`pipeline/interfaces.py` + `schemas/`** — the instant these contracts exist, stages stop depending on each other. Freeze immediately after the model.

### Hard serial (cannot parallelize)
- `data model` → `interfaces.py` + `schemas/` → everything else.
- `work_resolver.py` (Stage 1's ISWC/writer output) → composition-side gap checks (`ascap.py`, `bmi.py`). **Hidden dependency** the naïve plan misses: those registries need work identity, not ISRC.
- `services/audit.py` real wiring → **last** (needs real implementations; can be stubbed against interfaces earlier).

### Fan-out — safe to build in parallel once interfaces + schemas are frozen
Each is a clean, independent unit of work (and a clean unit for a concurrent agent):
- **[P] Stage 3 calculator** + `RateCard` table — needs only the rate table + a defined input shape; build against a mock identity result. **Easiest parallel win.**
- **[P] Stage 1 implementations** — `spotify.py`, `manual.py`, `fingerprint.py`, `work_resolver.py` are independent of S2/S3 and of each other.
- **[P] Stage 2 adapters** — `mlc.py`, `ascap.py`, `bmi.py`, `soundexchange.py` are independent of each other *by design* (that's the adapter pattern's payoff). Caveat: `ascap.py`/`bmi.py` can be *coded* in parallel but can't be *end-to-end tested* until `work_resolver.py` produces real work identity.
- **[P] `matching.py`** — pure function, zero dependencies; TDD with synthetic data before any scraper exists.
- **[P] `clients/`** — each external wrapper (spotify, musicbrainz, acoustid, http) is independent.
- **[P] Streamlit UI** — scaffold against stubbed services as soon as schemas are frozen.
- **[P] Tests for pure modules** — `test_matching`, `test_stage3` calc, splits-sum validation — alongside or before the module (TDD).

### Practical note (mostly-solo build)
"Parallel" here mainly means *nothing blocks you*: freeze interfaces + schemas, then jump between the calculator, one Stage 2 adapter, and `matching.py` in any order without one stalling on another. If running multiple agents concurrently, hand each one a single **[P]** item above.

---

## Risks / open questions
- **Scraping legality (Stage 2).** "Public" data isn't the same as "permitted to scrape." MLC/ASCAP/BMI terms of service may prohibit automated access, and they run anti-bot measures + change their HTML often. The adapter pattern protects us *technically*; it does not protect us *legally*. Confirm each site's ToS before relying on its scraper, and treat licensed feeds as the real plan, not just the scale plan.
- **Work-resolution coverage.** MusicBrainz won't have work-relations for every indie track, so ISWC/writer data will sometimes be missing. Manual entry is the fallback, and the composition-side gap check must **degrade gracefully** — flag "couldn't resolve the work" rather than assert there's no gap.
- **Volume data.** Spotify gives a 0–100 popularity score, not stream counts. v1 leans on artist-entered volume; that's the softest input in the whole estimate and should be labeled as such in the UI.
- **Rate accuracy.** CRB statutory + PRO/MLC schedules change. The versioned `RateCard` table is exactly so we can update without touching logic — keep `version` + `effective_date` on every rate row, and stamp each estimate with the rate version it used.
- **Sync vs async (decide before wiring `audit.py`).** A request that scrapes 3 registries + fingerprints a file will time out if synchronous. v1 may run sync, but if not, add an `app/jobs/` layer and a submit-job + poll-status API. Decide before `audit.py` is wired — retrofitting async after is painful.

---

## First coding session = Phase 0
Scaffold the repo, nail the data model, and freeze `interfaces.py` + `schemas/`. Stop there and review the schema together before writing any stage logic.
