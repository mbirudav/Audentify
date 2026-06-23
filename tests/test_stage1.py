"""Stage 1 tests (Phase 1). Identity resolution: recording (ISRC) + work (ISWC + writers).

Placeholder until Stage 1 implementations land. Note the key contract to test: Spotify
yields a recording but NO work — work_resolver must populate the composition side.
"""

import pytest

pytestmark = pytest.mark.skip(reason="Phase 1: implement Stage 1 identifiers first.")


def test_spotify_returns_isrc_but_no_work():
    ...


def test_work_resolver_populates_iswc_and_writers():
    ...
