"""Stage 3 — revenue estimate (the easy win, built before Stage 2 on purpose).

Estimated annual leak as a RANGE, PER royalty type — never one flat formula. Reads rates
from the versioned RateCard table (seeded from rates.yaml). Buildable against a mock
identity result; it doesn't need Stage 1 to actually run.
"""
