"""Stage 1 tests (Phase 1). Identity resolution: recording (ISRC) + work (ISWC + writers).

Everything here runs off captured fixtures via STUB clients — never the network, never
fpcalc. The key contracts under test:
  * Spotify yields a RECORDING (ISRC) but NO work — populating the work is the resolver's job.
  * ManualIdentifier builds a recording from user fields and refuses an empty input.
  * The work resolver follows MusicBrainz work-relations to ISWC + writer PartyRefs, and
    returns None (degrade gracefully) when there's no work-relation.
  * The fingerprint mapping turns an AcoustID response into a RecordingResult, and the live
    gate keeps fpcalc/network off the test path.
"""

from __future__ import annotations

import pytest

from app.domain import PartyRole
from app.pipeline.stage1_identity.fingerprint import FingerprintIdentifier
from app.pipeline.stage1_identity.manual import ManualIdentifier
from app.pipeline.stage1_identity.spotify import SpotifyIdentifier
from app.pipeline.stage1_identity.work_resolver import MusicBrainzWorkResolver
from app.schemas.identity import RecordingResult, TrackInput
from tests.factories import load_json_fixture, make_recording

# --- Stub clients: return loaded fixtures, no network -----------------------------------


class StubSpotifyClient:
    def __init__(self, track: dict) -> None:
        self._track = track

    def get_track(self, spotify_id: str) -> dict:
        return self._track


class StubMusicBrainzClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def work_relations_for_isrc(self, isrc: str) -> dict:
        return self._payload


class StubAcoustIDClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def lookup(self, fingerprint: str, duration: int) -> dict:
        return self._payload


# --- Spotify: recording with ISRC, but NEVER a work -------------------------------------


def test_spotify_returns_isrc_but_no_work():
    track_dict = load_json_fixture("spotify_track.json")
    identifier = SpotifyIdentifier(client=StubSpotifyClient(track_dict))

    recording = identifier.identify(
        TrackInput(spotify_url="https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT")
    )

    assert isinstance(recording, RecordingResult)
    assert recording.isrc == "GBARL9300135"
    assert recording.title == "Never Gonna Give You Up"
    assert recording.artist_name == "Rick Astley"
    assert recording.duration_ms == 213573
    assert recording.spotify_id == "4cOdK2wGLETKBW3PvgPWqT"
    assert recording.source == "spotify"
    # The Spotify path is master-side only: RecordingResult has no concept of a work, and the
    # identifier must not invent ISWC/writers. The work is the resolver's job.
    assert not hasattr(recording, "work")
    assert not hasattr(recording, "iswc")
    assert not hasattr(recording, "writers")


def test_spotify_accepts_bare_id_and_uri():
    track_dict = load_json_fixture("spotify_track.json")
    identifier = SpotifyIdentifier(client=StubSpotifyClient(track_dict))

    by_id = identifier.identify(TrackInput(spotify_id="4cOdK2wGLETKBW3PvgPWqT"))
    by_uri = identifier.identify(TrackInput(spotify_id="spotify:track:4cOdK2wGLETKBW3PvgPWqT"))

    assert by_id.isrc == by_uri.isrc == "GBARL9300135"


def test_spotify_raises_without_id_or_url():
    identifier = SpotifyIdentifier(client=StubSpotifyClient({}))
    with pytest.raises(ValueError):
        identifier.identify(TrackInput(title="no spotify reference"))


# --- Manual: build recording from user fields, refuse empty -----------------------------


def test_manual_identifier_builds_recording():
    identifier = ManualIdentifier()
    recording = identifier.identify(
        TrackInput(title="Bedroom Demo", artist_name="Indie Artist", isrc="QZES72012345")
    )

    assert recording.title == "Bedroom Demo"
    assert recording.artist_name == "Indie Artist"
    assert recording.isrc == "QZES72012345"
    assert recording.source == "manual"


def test_manual_identifier_isrc_only_gets_placeholder_title():
    identifier = ManualIdentifier()
    recording = identifier.identify(TrackInput(isrc="QZES72012345"))

    assert recording.isrc == "QZES72012345"
    assert recording.title  # required field is populated even without a user title


def test_manual_identifier_raises_when_empty():
    identifier = ManualIdentifier()
    with pytest.raises(ValueError):
        identifier.identify(TrackInput())


# --- Work resolver: composition side (ISWC + writers) -----------------------------------


def test_work_resolver_populates_iswc_and_writers():
    payload = load_json_fixture("musicbrainz_work_relations.json")
    resolver = MusicBrainzWorkResolver(client=StubMusicBrainzClient(payload))

    recording = make_recording(isrc="GBARL9300135")
    work = resolver.resolve_work(recording)

    assert work is not None
    assert work.source == "musicbrainz"
    assert work.iswc == "T-010.140.236-1"
    assert work.title == "Never Gonna Give You Up"

    # At least one writer PartyRef with the WRITER role (Stage 2 keys on this exact shape).
    assert len(work.writers) >= 1
    assert all(w.role is PartyRole.WRITER for w in work.writers)

    writers_by_name = {w.name: w for w in work.writers}
    assert "Mike Stock" in writers_by_name
    assert writers_by_name["Mike Stock"].ipi == "00150394842"
    # A writer with no IPI in the source data carries ipi=None, not a crash.
    assert writers_by_name["Pete Waterman"].ipi is None


def test_work_resolver_returns_none_when_no_relation():
    payload = load_json_fixture("musicbrainz_no_work_relation.json")
    resolver = MusicBrainzWorkResolver(client=StubMusicBrainzClient(payload))

    recording = make_recording(isrc="QZES72012345")
    assert resolver.resolve_work(recording) is None


def test_work_resolver_returns_none_without_isrc():
    # No ISRC on the recording -> nothing to follow on the composition side.
    resolver = MusicBrainzWorkResolver(client=StubMusicBrainzClient({}))
    recording = make_recording(isrc=None)
    assert resolver.resolve_work(recording) is None


# --- Fingerprint: mapping off a fixture + live gate -------------------------------------


def test_fingerprint_identify_blocked_without_live_network():
    # allow_live_network is False in tests -> must raise BEFORE touching fpcalc or network.
    identifier = FingerprintIdentifier(
        acoustid_client=StubAcoustIDClient(load_json_fixture("acoustid_lookup.json"))
    )
    with pytest.raises(RuntimeError, match="fingerprinting requires live network"):
        identifier.identify(TrackInput(audio_file_path="/tmp/never-read.mp3"))


def test_fingerprint_maps_best_acoustid_match():
    # Exercise the post-fpcalc mapping directly off a fixture (no fpcalc, no network).
    identifier = FingerprintIdentifier(
        acoustid_client=StubAcoustIDClient(load_json_fixture("acoustid_lookup.json"))
    )
    result = identifier._recording_from_acoustid(load_json_fixture("acoustid_lookup.json"))

    assert result.source == "fingerprint"
    assert result.title == "Never Gonna Give You Up"  # highest-scoring match wins
    assert result.artist_name == "Rick Astley"
    assert result.duration_ms == 213_000
    # ISRC enrichment is live-only (MusicBrainz); with the flag off it stays None.
    assert result.isrc is None
