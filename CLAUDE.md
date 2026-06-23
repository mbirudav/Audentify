# CLAUDE.md — Audentify

Persistent context. Read this first, every session.

## Who you're working with
Maruthi — founder, strong on product/strategy, leveling up on technical execution. Incoming CMU student. **Build *with* him, not just for him:** explain the "why" in short mini-lessons as you go, prefer Python, and be direct — flag bad ideas instead of agreeing to be polite. He wants to genuinely understand what gets built, not just receive code.

## What this is
A leak-audit tool that surfaces royalties indie artists are unknowingly losing. Core loop: artist inputs a track → identify it → check where it's registered → estimate the annual leak.

**MVP = information only. No money handling, no licenses, no collection.** That's deliberate — it keeps the build license-free with no regulatory burden.

## The two copyrights (domain bedrock — read before touching identity or gaps)
Every piece of recorded music is **two separate copyrights**, and the entire pipeline depends on not conflating them:

- **Master (sound recording)** — the specific recording. Owned by the artist + label/distributor. Identified by an **ISRC**. Collected digitally (non-interactive only — Pandora, SiriusXM) by **SoundExchange**; interactive-stream master money (Spotify on-demand) is paid directly to the distributor, not a society.
- **Composition (the work / the song)** — melody + lyrics. Owned by songwriters + publishers. Identified by an **ISWC** plus each writer's **IPI**. Performance royalties collected by **PROs** (ASCAP, BMI, SESAC); mechanical royalties collected by the **MLC**.

**Consequences that bind the architecture (this is the most common way to build it wrong):**
- **ISRC is the master key, not the universal join key.** ASCAP/BMI are composition-side and keyed on title + writer + ISWC. (MLC is composition-side but keeps ISRC→work links, so ISRC *may* work as a search input there — verify in Stage 2.)
- **Spotify returns ISRC but not writers or ISWC.** So Stage 1 must do a *second* resolution step: recording → work (ISWC + writers), realistically via MusicBrainz work-relations or manual entry.
- The data model is already composition-aware (Works, Parties-with-IPI, Splits). Stage 1 must actually *populate* the work side — not just the recording side — or Stage 2's composition checks have nothing to join on.

## Stack
FastAPI (Python 3.11+) · `pydantic-settings` for config · PostgreSQL + SQLAlchemy + Alembic · Streamlit for the v0 UI (→ Next.js + Tailwind later) · `spotipy`, `pyacoustid`/Chromaprint, `musicbrainzngs` (Stage 1) · `httpx`, `playwright`, `beautifulsoup4`, `rapidfuzz` (Stage 2). Deploy: Railway or Render.

**System deps (don't get caught on deploy):** `fingerprint.py` needs the `fpcalc` (Chromaprint) binary in the deploy image — Railway/Render won't have it by default. AcoustID needs an API key; MusicBrainz needs a custom User-Agent and ~1 req/sec rate limiting.

## Architecture rules (hold these)
- Each pipeline stage sits behind an **interface (ABC)** so implementations are swappable.
- **Stage 1 resolves both the recording (ISRC) and the work (ISWC + writer IPIs).** ISRC alone does not feed the composition-side registries — see "The two copyrights."
- Each registry (MLC, ASCAP, BMI, …) is its own **adapter** behind a common base — built this way from day one, even though scraping is a temporary bridge. Each adapter declares what it keys on (master vs composition).
- **Every gap claim stores its provenance** — what was checked, which registry, when, and the confidence. Cache raw registry responses (timestamped); the product's credibility rests on having evidence behind "you're leaking money here."
- **Rates live in a versioned DB table** (every row carries `version` + `effective_date`) so a past estimate can be reproduced at the rate that was effective then. A YAML may *seed* the table, but the table — not the file — is the source of truth. Never hardcode a rate inside the calculator.
- **Estimates are per-royalty-type, not one flat formula.** Mechanical (MLC, per-stream), performance (PRO, pooled/survey distribution), and SoundExchange (per-play, non-interactive) have different rate bases; "volume" means streams for some types, spins for others. Always output **ranges with visible, adjustable assumptions** — never false precision.
- Fuzzy matches carry a **confidence score.** Low confidence → flag for a human, don't assert a gap. (False positive — telling someone they're leaking when they aren't — is worse than a miss.)

## Build order (settled — don't relitigate)
data model → Stage 1 (identity) → Stage 3 (estimate, the easy win) → Stage 2 (gap check, the hard moat). See plan.md "Parallelization" for what within/across these phases can be built concurrently.

## Don't relitigate
- MVP is the audit (information), not collection (money).
- Build order above.
- Stage 2 scraping is a v1 bridge; the adapter pattern stays so licensed feeds can drop in later. **Legal note:** "public" data ≠ "permitted to scrape" — registry ToS may prohibit automated access; the adapter pattern protects us technically, not legally. Licensed feeds are the real plan, not just the scale plan.
- No ML in v1. The only "model" is fuzzy string matching.
