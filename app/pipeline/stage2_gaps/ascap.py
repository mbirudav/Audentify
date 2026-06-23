"""ASCAP adapter (Phase 3). Composition side — performance royalties.

Keys on the WORK identity (title + writer + ISWC) from Stage 1's work_resolver. ASCAP's
public "Repertory" search returns HTML, so `_parse` reads the page with BeautifulSoup.

NO live scraping in this build: `_query` returns the constructor-injected fixture; the live
branch is gated behind the http client's `allow_live_network` flag. "public" data is not the
same as "permitted to scrape" — ASCAP's ToS may prohibit automated access.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from app.domain import CopyrightSide, RegistryName
from app.pipeline.stage2_gaps.base_adapter import (
    Candidate,
    RawResponse,
    RegistryAdapter,
)
from app.schemas.identity import IdentityResult

ASCAP_SEARCH_URL = "https://www.ascap.com/repertory"  # illustrative; not called live


class ASCAPAdapter(RegistryAdapter):
    registry = RegistryName.ASCAP
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
        resp = client.get(ASCAP_SEARCH_URL, params=params)
        return RawResponse(
            body=resp.text,
            url=str(resp.request.url),
            params=params,
            status_code=resp.status_code,
        )

    def _parse(self, raw: RawResponse) -> list[Candidate]:
        if not raw.body:
            return []
        soup = BeautifulSoup(raw.body, "html.parser")
        candidates: list[Candidate] = []
        for row in soup.select("tr.result-row"):
            title_cell = row.select_one("td.title")
            if title_cell is None:
                continue
            title = title_cell.get_text(strip=True)
            iswc_cell = row.select_one("td.iswc")
            work_id_cell = row.select_one("td.ascap-work-id")
            writers_cell = row.select_one("td.writers")
            identifier = (
                iswc_cell.get_text(strip=True)
                if iswc_cell
                else (work_id_cell.get_text(strip=True) if work_id_cell else None)
            )
            candidates.append(
                Candidate(
                    match_value=title,
                    identifier=identifier,
                    extra={
                        "writers": writers_cell.get_text(strip=True)
                        if writers_cell
                        else None
                    },
                )
            )
        return candidates
