# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
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
