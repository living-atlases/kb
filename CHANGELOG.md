# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Test code is indexed, tagged `content_type=test`. Previously the blocklist
  dropped `test/`, `tests/` and `integration-test/` wholesale, so the most
  precise statement of what a component is supposed to do was the one thing the
  KB could not read. Measured over the manifest, unblocking them naively would
  add 126k chunks to a 195k index — but 98k of that is fixtures (checklistbank's
  test datasets alone are 59k). `kb_indexer` now indexes only test files with a
  code extension and tags them, which costs ~28k chunks (+14%). The fixture
  directories stay blocked. Test chunks are de-ranked in `/api/answer` so they
  do not crowd out the implementation; `content_type=test` goes at them
  directly.

  The classifier is shared with `kb_coverage.py` via a new `kb_testfiles.py`,
  so what counts as a test file is defined once.

- `superseded_by` / `superseded_note` in `ansible/repos.yml`, carried into
  `testing.json` and both reports. Ten ALA components are already being
  replaced by `atlas-index` (source: the "Replaces" table in its own README,
  with the partial cases kept partial — `ala-sensitive-data-service` loses only
  its static home UI). Without this, a table ranking components by test level
  invites someone to fund test work on software that is on its way out.
- Test inventory (`kb_coverage.py`, `GET /api/testing`, MCP tool
  `get_ala_test_coverage`). "How well tested is component X?" was unanswerable
  from the semantic index: the blocklist drops `test/`, `tests/` and
  `integration-test/`, so no test file is embedded, and the query API exposes no
  per-repo filter. The other half of the KB does have the answer — the
  persistent clones under `{kb_home}/repos`, refreshed hourly by the watcher.
  `kb_coverage.py` walks them and writes `data/testing.json`: per component, the
  number of declared test cases split into unit / integration / e2e, production
  LOC, detected stack, and which coverage tooling the build configures. No
  embedding, no network — a filesystem walk, so the watcher runs it on the same
  pull that triggers a re-index.

  Counting is per framework, not per annotation: `@Test` alone would report zero
  tests for every Grails app in the stack, where Spock feature methods are
  quoted strings. Classification is by content where the path lies — Grails
  keeps its Geb browser specs under `src/integration-test`, so those are
  reclassified as e2e rather than integration.

  It is not measured line coverage, which would need a full build per repo.
  Each entry carries a `test_level` (`good`/`moderate`/`low`/`minimal`/`none`)
  and a one-sentence `assessment` so the output is usable without reading code.
  Components under 2 kLOC are left `unscored`: a 1 kLOC wrapper with 7 tests
  outranked biocache-service, which is arithmetic, not a verdict. There is
  deliberately no floor on the number of cases — spatial-service has 14 over
  84 kLOC, and that is the most important finding in the set.

  `kb_coverage.py --report [--api URL] [--org ORG]` renders it as a markdown
  table from the local artifact or a deployed KB, so a table in a review is a
  command rather than a copy-paste that goes stale.
- Index `AtlasOfLivingAustralia/quail`, the QGIS plugin for querying Living
  Atlas occurrence data. Blocklist `resources.py`: the Qt resource compiler
  writes a single 915 KB file of base64 blobs there (~460 chunks in a 1.4 MB
  source tree) whose own header says changes to it are lost. With it excluded
  the repo contributes 28 files / 159 KB of real source and Sphinx docs.
- `tests/test_manifest.py`: pins the `repos.yml` contract — org/base_url shape,
  no duplicate entries, tier1 keys resolve, wiki companions, issue-indexing
  defaults per org — and the `is_blocked` semantics (directory-component vs
  filename patterns), so a blocklist pattern that silently swallows source is
  caught in CI.
- GitHub Issues & PRs ingestion (`kb_issues.py`): issues and pull requests are
  chunked into the KB with `content_type="issue"`/`"pr"` metadata — bug
  workarounds, design discussions and Q&A that never reach the docs. Indexed for
  ALA orgs by default (GBIF repos opt-in via `issues: true`); bot/dependabot
  noise dropped, comments capped, incremental via a per-repo `updated_at`
  high-water mark. The watcher polls updated issues hourly and re-indexes on
  change (`issue_update` added to watcher state). Issues/PRs are de-ranked
  slightly in `/api/answer` so curated answers and source still win.
- GitHub Releases ingestion (`kb_releases.py`): release notes / changelogs are
  chunked into the KB with `content_type="release"` metadata, and the latest
  version per component is aggregated into `data/versions.json`.
- REST API: `content_type` filter on `POST /api/query` (`release` / `source`),
  plus `GET /api/versions` and `GET /api/versions/{org}/{name}`.
- MCP tool `get_ala_component_versions` and a `content_type` option on
  `query_ala_kb` — for keeping deployment dependency lists
  (e.g. `la-toolkit-backend/assets/dependencies.yaml`) up to date.
- Watcher polls the latest GitHub release per repo (releases can ship without
  moving HEAD) and re-indexes release notes on change; state migrated to a
  per-repo `{head_sha, release_date}` shape.
- `la-toolkit-backend` added to the indexed repository manifest. Per-repo
  `releases: false` opts a repo out of release indexing.

### Fixed
- CI is green again. The `mcp` dependency was declared as `mcp>=1.27` with no upper bound, so fresh installs resolved to mcp 2.x, where `mcp.server.fastmcp` no longer exists; the MCP tool tests failed on import (7 failures since 2026-08-05) and a new host provisioned from scratch would have installed a server SDK the code cannot import. Pinned to `mcp>=1.27,<2` in `server/requirements.txt` and in both playbooks.
- Swagger/OpenAPI docs are reachable again. `FastAPI()` was instantiated with the default `docs_url="/docs"`, but nginx only proxies `/api/` to the backend (path preserved), so the `https://kb.l-a.site/api/docs` URL advertised in the README returned 404. The app now mounts `docs_url="/api/docs"`, `redoc_url="/api/redoc"` and `openapi_url="/api/openapi.json"`.
- Watcher cycles no longer pile up. A cycle can outlast its hourly period, and
  with no concurrency guard the hourly cron stacked watchers indefinitely — 69
  live watchers spawning 26 concurrent indexers exhausted host memory and wedged
  the API behind ChromaDB lock contention, so every MCP tool returned an empty
  error. `kb_watcher.py` now takes an exclusive `data/watcher.lock` and the cron
  line wraps the run in `flock -n`; a later firing exits 0 immediately.
- `save_state()` writes atomically (temp file + `os.replace`). Concurrent
  watchers were truncating `watcher_state.json`, losing every high-water mark
  and making each cycle re-index all 65 repos from scratch.
- A cycle now stops after `CYCLE_BUDGET` (50 min) and resumes next run, and the
  per-indexer timeout drops from 30 to 15 min.
- Repos whose indexing fails now record the failure and back off exponentially
  (1 h → 24 h) instead of being retried in full every hour.
- REST API: ChromaDB access is serialized behind a lock with a bounded wait, and
  callers that cannot be served get a 503 instead of occupying a threadpool
  worker indefinitely. A single stalled Chroma call used to consume every worker
  and take the whole process down with it.
- REST API: `/health` is async, so it reports liveness even when Chroma is
  blocked. As a sync endpoint it ran in the same exhausted threadpool and timed
  out, making a reachable service look dead.
- REST API: `/api/answer` and the `/api/chat` SSE generator ran blocking Chroma
  calls directly on the event loop; they now run in a worker thread.
- MCP: httpx failures are caught and reported by name. A timeout stringifies to
  `""`, so an unhandled one reached clients as `Error executing tool <name>: `
  with nothing after the colon. Short 10s timeouts on the plain lookups were
  raised to 60s, and the per-call `AsyncClient` (leaked on every invocation) is
  now a shared instance.

### Operational note
Killing indexers mid-write can leave records in ChromaDB's `embeddings_queue`
that were never applied to the HNSW segment. ChromaDB 0.6.3 deadlocks applying
that backlog on the next query — every thread parked in `futex_wait`, no
progress, forever. The index itself stays readable (`hnswlib` loads and queries
it in under a second), so recovery is to mark the vector segment caught up in
`max_seq_id`; the skipped chunks come back on the next re-index of their repos.

## [1.0.0] - 2026-06-16

First public release.

### Added
- Semantic search knowledge base over Living Atlas / ALA / GBIF repositories,
  backed by ChromaDB and `all-MiniLM-L6-v2` embeddings.
- REST API (FastAPI): `POST /api/query`, `GET /api/collections`,
  `POST /api/chat` (RAG, SSE streaming), `GET /health`.
- MCP server (FastMCP) over HTTP/streamable-HTTP and stdio:
  `query_ala_kb`, `list_ala_kb_collections`.
- Dart/Flutter client library with an embeddable KB chat widget.
- Ansible deployment: `setup_kb.yml`, `deploy.yml`, `install_ollama.yml`,
  with systemd services, nginx reverse proxy, TLS, and disk offload.
- Incremental re-indexing via `kb_watcher.py` (hourly `git ls-remote` polling).
- GitHub Actions CI running the pytest suite on Python 3.11.

### Indexer
- Slim index: expanded blocklist excludes vendored assets, generated files, and
  test data (~75% chunk reduction without losing source/docs/config).
- Broader CI/CD coverage: extensionless config files (Dockerfile, Jenkinsfile,
  Makefile, …) are now indexed.
- Automatic default-branch detection (HEAD) — handles repos that default to
  `develop`/`dev` instead of `master`/`main`.
- Single repository manifest (`ansible/repos.yml`) as the source of truth.
