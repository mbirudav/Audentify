"""Stage 1 — identity resolution. Track in -> TWO outputs behind interfaces:
the RECORDING (canonical track + ISRC) and the WORK (ISWC + writers/IPIs).

ISRC alone does NOT feed the composition-side registries (CLAUDE.md "The two copyrights"),
so work_resolver is not optional — ASCAP/BMI gap checks hard-depend on it.
"""
