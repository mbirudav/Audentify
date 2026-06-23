"""BMI adapter (Phase 3). Composition side — performance royalties.

Like ASCAP, keys on the WORK identity (title + writer + ISWC). Independent of the other
adapters by design (the adapter pattern's payoff): BMI's repertoire search backend returns
JSON, so `_parse` reads the JSON body rather than HTML.

NO live scraping in this build: `_query` returns the constructor-injected fixture; the live
branch is gated behind the http client's `allow_live_network` flag. "public" data is not the
same as "permitted to scrape" — BMI's ToS may prohibit automated access.
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

BMI_SEARCH_URL = "https://repertoire.bmi.com/api/search"  # illustrative; not called live


class BMIAdapter(RegistryAdapter):
    registry = RegistryName.BMI
    keys_on = CopyrightSide.COMPOSITION

    def _query(self, identity: IdentityResult) -> RawResponse | None:
        if self._injected_raw is not None:
            return self._injected_raw
        from app.clients.http import get_http_client  # gated; raises when network is off

        client = get_http_client()
        work = identity.work
        writer = work.writers[0].name if work and work.writers else None
        params = {"title": work.title if work else identity.recording.title}
        if writer:
            params["writer"] = writer
        resp = client.get(BMI_SEARCH_URL, params=params)
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
        for work in data.get("works", []):
            title = work.get("title")
            if not title:
                continue
            identifier = work.get("iswc") or work.get("bmiWorkId")
            candidates.append(
                Candidate(
                    match_value=title,
                    identifier=identifier,
                    extra={"writers": work.get("writers", [])},
                )
            )
        return candidates
