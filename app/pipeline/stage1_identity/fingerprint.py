"""Fingerprint identifier (Phase 1, [P], last). Chromaprint + AcoustID + MusicBrainz.

For raw audio files with no metadata. The flow is:
    audio file --(fpcalc / Chromaprint)--> (fingerprint, duration)
              --(AcoustID lookup)--------> MusicBrainz recording id + title/artist
              --(MusicBrainz, optional)--> ISRC for the recording

SYSTEM DEPENDENCY: this needs the `fpcalc` (Chromaprint) BINARY on PATH in the deploy image.
Railway/Render won't have it by default — it must be installed into the container (e.g. the
`libchromaprint-tools` / `chromaprint` package, or a vendored `fpcalc`). AcoustID also needs
an API key (`settings.acoustid_api_key`) and MusicBrainz needs the custom UA.

Both fpcalc AND all HTTP are live-only: gated behind `settings.allow_live_network`. When the
flag is off (the default, and ALWAYS in tests) `identify` raises before touching fpcalc or
the network. Tests never invoke fpcalc; a fingerprint test drives the post-fpcalc path off a
captured AcoustID fixture with a fake AcoustIDClient.

Clients are constructor-injected (AcoustIDClient, optional MusicBrainzClient) so tests stay
network-free.
"""

from __future__ import annotations

from typing import Any

from app.clients.acoustid import AcoustIDClient
from app.clients.musicbrainz import MusicBrainzClient
from app.config import get_settings
from app.pipeline.interfaces import Identifier
from app.schemas.identity import RecordingResult, TrackInput


class FingerprintIdentifier(Identifier):
    source = "fingerprint"

    def __init__(
        self,
        acoustid_client: AcoustIDClient | None = None,
        musicbrainz_client: MusicBrainzClient | None = None,
    ) -> None:
        self._acoustid = acoustid_client or AcoustIDClient()
        self._musicbrainz = musicbrainz_client or MusicBrainzClient()

    def _fingerprint(self, audio_file_path: str) -> tuple[int, str]:
        """Run fpcalc (Chromaprint) on the file -> (duration_seconds, fingerprint).

        Imported + invoked only on the live path; never reached in tests.
        """
        import acoustid

        return acoustid.fingerprint_file(audio_file_path)

    def identify(self, track: TrackInput) -> RecordingResult:
        # Hard gate: fpcalc binary + AcoustID/MusicBrainz HTTP are all live-only.
        if not get_settings().allow_live_network:
            raise RuntimeError("fingerprinting requires live network + fpcalc binary")

        if not track.audio_file_path:
            raise ValueError(
                "FingerprintIdentifier needs an audio_file_path on the TrackInput."
            )

        duration, fingerprint = self._fingerprint(track.audio_file_path)
        result = self._acoustid.lookup(fingerprint, duration)
        return self._recording_from_acoustid(result, fallback_duration_s=duration)

    def _recording_from_acoustid(
        self, result: dict[str, Any], fallback_duration_s: int | None = None
    ) -> RecordingResult:
        """Map an AcoustID lookup response -> RecordingResult, enriching the ISRC from
        MusicBrainz when the recording carries an MBID.

        Best match = highest-scoring result that actually has a recording. Split out from
        `identify` so a fingerprint test can exercise the mapping off a fixture (no fpcalc).
        """
        results = result.get("results") or []
        best_recording: dict[str, Any] | None = None
        for res in sorted(results, key=lambda r: r.get("score", 0), reverse=True):
            recordings = res.get("recordings") or []
            if recordings:
                best_recording = recordings[0]
                break

        if not best_recording:
            raise ValueError("AcoustID returned no recording match for the fingerprint.")

        artists = best_recording.get("artists") or []
        artist_name = ", ".join(a["name"] for a in artists if a.get("name")) or None
        duration_s = best_recording.get("duration") or fallback_duration_s
        duration_ms = int(duration_s * 1000) if duration_s else None

        isrc = self._isrc_for_mbid(best_recording.get("id"))

        return RecordingResult(
            title=best_recording.get("title", "Unknown title"),
            artist_name=artist_name,
            isrc=isrc,
            duration_ms=duration_ms,
            source=self.source,
        )

    def _isrc_for_mbid(self, recording_mbid: str | None) -> str | None:
        """Look up the ISRC for a MusicBrainz recording id. Live-only; on the test path the
        flag is off so we never get here (identify raises first). Returns None on any miss so
        a failed enrichment never breaks identification."""
        if not recording_mbid or not get_settings().allow_live_network:
            return None
        try:
            import musicbrainzngs

            detail = musicbrainzngs.get_recording_by_id(
                recording_mbid, includes=["isrcs"]
            )
            isrcs = detail.get("recording", {}).get("isrc-list") or []
            return isrcs[0] if isrcs else None
        except Exception:
            return None
