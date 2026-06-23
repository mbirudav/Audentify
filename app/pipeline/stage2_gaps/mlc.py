"""MLC adapter (Phase 3). Composition side — mechanical royalties.

The MLC is composition-side but keeps ISRC->work links, so ISRC MAY work as a search input
(here it's fixture-backed; NOT verified against the live MLC site/ToS). The MLC public
search returns JSON, so `_parse` reads the JSON body. Built end-to-end first as the
reference adapter.

NO live scraping in this build: `_query` returns the constructor-injected fixture; the live
branch is gated behind the http client's `allow_live_network` flag. "public" data is not the
same as "permitted to scrape".
"""

from __future__ import annotations

import json

from app.domain import CopyrightSide, RegistryName
from app.pipeline.stage2_gaps.base_adapter import (
    Candidate,
    RawResponse,
    RegistryAdapter,
)
from app.schemas.identity import IdentityResult

MLC_SEARCH_URL = "https://api.themlc.com/v1/works/search"  # illustrative; not called live


class MLCAdapter(RegistryAdapter):
    registry = RegistryName.MLC
    keys_on = CopyrightSide.COMPOSITION

    def _query(self, identity: IdentityResult) -> RawResponse | None:
        # Fixture-backed: return the injected raw response. A live integration would build
        # the request from ISRC (MLC keeps ISRC->work links) using the gated http client.
        if self._injected_raw is not None:
            return self._injected_raw
        from app.clients.http import get_http_client  # gated; raises when network is off

        client = get_http_client()
        isrc = identity.recording.isrc
        params = {"isrc": isrc} if isrc else {"title": identity.recording.title}
        resp = client.get(MLC_SEARCH_URL, params=params)
        return RawResponse(
            body=resp.text,
            url=str(resp.request.url),
            params=params,
            status_code=resp.status_code,
        )

    def _parse(self, raw: RawResponse) -> list[Candidate]:
        if not raw.body:
            return []
        data = json.loads(raw.body)
        candidates: list[Candidate] = []
        for work in data.get("results", []):
            title = work.get("workTitle")
            if not title:
                continue
            # Prefer the ISWC as the matched identifier; fall back to the MLC song code.
            identifier = work.get("iswc") or work.get("mlcSongCode")
            candidates.append(
                Candidate(
                    match_value=title,
                    identifier=identifier,
                    extra={"writers": work.get("writers", [])},
                )
            )
        return candidates
