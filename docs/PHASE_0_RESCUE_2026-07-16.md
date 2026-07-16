# Phase 0 repository rescue

**Date:** 16 July 2026<br>
**Branch:** `fix/p0-repo-rescue`<br>
**Goal:** make the prototype safe and reproducible before changing the simulation loop.

## Completed

- Consolidated all implementation work into a sanitized `main` without importing the commit that contained the old Gemini credential.
- Published the API-key removal commit to the remote feature-branch tip.
- Verified that the credential preserved in the old commit is rejected by Google's API.
- Added a one-command fake-provider stack: `cd koivulahti && ./dev.sh up`.
- Made Gemini and ambient integrations opt-in; decision processing defaults to disabled.
- Replaced the retired hardcoded Gemini model with configurable `GEMINI_MODEL`, defaulting to `gemini-3.1-flash-lite`.
- Verified `gemini-3.1-flash-lite` with a live structured-output request.
- Moved Gemini credentials from the request URL to the `x-goog-api-key` header.
- Removed the unused second Gemini SDK client.
- Removed host publishing for PostgreSQL, Redis, llama.cpp and the gateway from the base stack.
- Bound the API to `127.0.0.1` by default and added a loopback-only diagnostics override.
- Replaced first-boot-only SQL initialization with an ordered, checksummed migration runner.
- Added a deterministic fake LLM provider for CI and local development.
- Added `pyproject.toml`, `uv.lock`, a hash-locked container `requirements.lock`, Ruff, pytest markers, Bandit and pip-audit.
- Added GitHub Actions jobs for quality, dependency/security checks, all application builds, secret scanning and disposable fake-provider E2E.
- Rewrote the root README as the canonical current project entry point and marked December 2025 plans as historical.

## Verification snapshot

- Offline tests: **14 passed**, 40 integration tests deselected.
- Fake-provider integration suite: **33 passed**, 7 soft checks xpassed.
- Docker application images: **6/6 built** from hash-locked dependencies.
- Ruff: passed.
- Bandit high-severity scan: passed.
- pip-audit: no known vulnerabilities.
- Fresh migration run: 001-005 applied and recorded.
- Second migration run: 001-005 detected as already applied.
- Default startup: API healthy, events and posts readable.
- Base host ports: only `127.0.0.1:8082` is published.

## External cleanup still required

The old secret-bearing commit is not part of `main`, and the key is currently rejected. It remains reachable through the remote feature branch's history until that branch is deleted or rewritten. Removing that remote history is destructive and should be done explicitly after confirming no other clone depends on it.

## Next implementation gate

Phase 1 starts only after CI is green on GitHub. Its scope is deliberately narrow:

1. Persist run identity, simulation clock and config hash.
2. Replace lossy Redis list jobs with durable, idempotent work records and an outbox.
3. Implement legal world actions for six characters: `MOVE`, `TALK`, `HELP`, `BORROW`, `RETURN`, `APOLOGIZE`.
4. Restrict the runtime event catalog to the events those actions can actually produce.
5. Prove replay with matching event-log and state hashes over seven simulated days.
