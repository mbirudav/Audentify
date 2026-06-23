"""Stage 2 — registration-gap check (the moat). One ADAPTER per registry behind a common
base, so a broken scraper never touches the others. Each adapter declares what it keys on
(master vs composition). Every gap claim stores provenance.

Legal note: 'public' data != 'permitted to scrape'. Registry ToS may prohibit automated
access; the adapter pattern protects us technically, not legally. Licensed feeds are the
real plan — confirm each site's ToS before relying on its scraper.
"""
