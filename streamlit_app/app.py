"""v0 Streamlit UI (Phase 4, [P]). Fully isolated from the backend so swapping in Next.js
later doesn't ripple into the logic.

Scaffold against STUBBED services as soon as schemas are frozen — don't wait for the real
stages. Three panels per the success criteria:
  1. identity + ISRC/ISWC
  2. registration map per collector, with provenance
  3. estimated annual leak range, with adjustable assumptions

Run:  uv run streamlit run streamlit_app/app.py   (needs `uv sync --extra ui`)
"""

from __future__ import annotations

import streamlit as st


def main() -> None:
    st.set_page_config(page_title="Audentify", page_icon="🎵")
    st.title("Audentify")
    st.caption("Surfaces royalties indie artists are unknowingly losing.")

    st.info(
        "Phase 0 scaffold. Wire this against stubbed services once the schemas are frozen "
        "(they are): identity → registration map → estimated annual leak range."
    )

    with st.form("track"):
        st.text_input("Spotify URL / track", placeholder="https://open.spotify.com/track/...")
        st.form_submit_button("Audit", disabled=True)


if __name__ == "__main__":
    main()
