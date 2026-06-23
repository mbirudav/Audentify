"""Thin external wrappers: retry / backoff / rate-limit / keys / User-Agent.

These hold the HTTP/API concerns so stage logic never touches raw requests. A stage
orchestrates; it does not know about retries or rate limits. Each wrapper here is an
independent unit of work (spotify, musicbrainz, acoustid, http) — parallel-safe to build.
"""
