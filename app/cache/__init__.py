"""Raw-response cache + provenance.

Timestamped raw registry responses live here (or in the RawRegistryResponse table). Two
jobs: dev-speed cache to avoid re-hitting (and getting banned by) registries, and the
evidence trail behind every gap claim. The DB table is the durable store; this package is
the access layer.
"""
