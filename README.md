# Audentify

A leak-audit tool that surfaces royalties indie artists are unknowingly losing.

**Core loop:** artist inputs a track → identify it → check where it's registered → estimate the annual leak.

> MVP is the **audit** (information only). No money handling, no licenses, no collection. See `CLAUDE.md` and `plan.md`.

## The two copyrights (read before touching identity or gaps)
Every recording is **two separate copyrights**:
- **Master** (sound recording) — the specific recording. Key: **ISRC**. Money: SoundExchange (non-interactive digital) / distributor (interactive).
- **Composition** (the work) — melody + lyrics. Key: **ISWC + writer IPI**. Money: PROs (ASCAP/BMI/SESAC, performance) + the MLC (mechanical).

ISRC is the join key for the **master side only**. ASCAP/BMI key on the composition, so Stage 1 must resolve **both** the recording (ISRC) *and* the work (ISWC + writers).

## Layout
```
app/
  config.py            settings (pydantic-settings)
  domain.py            cross-stage enums
  db/                  SQLAlchemy engine + models (the data model)
  schemas/             Pydantic request/response contracts — frozen early
  clients/             thin external API wrappers (retry/rate-limit/keys)
  cache/               raw-response cache + provenance
  pipeline/
    interfaces.py      ABCs: Identifier, WorkResolver, GapChecker, Estimator — frozen early
    stage1_identity/   recording (ISRC) + work (ISWC + writers)
    stage2_gaps/       one adapter per registry (master vs composition keying)
    stage3_estimate/   per-royalty-type calculator (reads the versioned RateCard table)
  rates/rates.yaml     SEED for the RateCard table — not the source of truth
  services/audit.py    orchestrates the 3 stages
streamlit_app/         v0 UI
alembic/               migrations
tests/
```

## Local dev

```bash
# 1. Bring up the dev Postgres (matches .env defaults)
docker compose up -d

# 2. Create the venv and install core + dev deps
uv sync --extra dev

# 3. Apply migrations
uv run alembic upgrade head

# 4. Run the API
uv run uvicorn app.main:app --reload

# 5. Run tests
uv run pytest
```

Stage-specific deps install on demand: `uv sync --extra stage1 --extra stage2 --extra ui`.

**System deps (deploy):** `fingerprint.py` needs the `fpcalc` (Chromaprint) binary in the image; AcoustID needs an API key; MusicBrainz needs a custom User-Agent + ~1 req/sec.

## Status
Phase 0 scaffold: data model, `interfaces.py`, and `schemas/` are populated. Stage implementations are interface-conforming stubs (raise `NotImplementedError`) pending schema review.
