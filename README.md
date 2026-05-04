# living-atlas-kb

Knowledge base service for Living Atlas / ALA repositories — semantic search and AI chat over documentation, configuration, and source code.

- **REST API:** `https://kb.l-a.site/api/`
- **MCP remote:** `https://kb.l-a.site/mcp`
- **API docs:** `https://kb.l-a.site/api/docs`
- **Live collections:** `https://kb.l-a.site/api/collections`

---

## Indexed Repositories

### Tier 1 — Daily updates

| Repository | Org | Description |
|---|---|---|
| [ala-install](https://github.com/AtlasOfLivingAustralia/ala-install) | AtlasOfLivingAustralia | Ansible roles and playbooks for deploying LA services |
| [la-toolkit](https://github.com/living-atlases/la-toolkit) | living-atlases | LA Toolkit: conversational project configuration |
| [gbif-pipelines](https://github.com/gbif/pipelines) | gbif | GBIF Pipelines: DarwinCore data processing (livingatlas module) |

### Tier 2 — Weekly updates (Sundays)

| Repository | Org | Description |
|---|---|---|
| [collectory](https://github.com/AtlasOfLivingAustralia/collectory) | AtlasOfLivingAustralia | Biodiversity collections registry |
| [biocache-service](https://github.com/AtlasOfLivingAustralia/biocache-service) | AtlasOfLivingAustralia | Occurrence records service |
| [biocache-hubs](https://github.com/AtlasOfLivingAustralia/biocache-hubs) | AtlasOfLivingAustralia | Occurrence hub web app |
| [ala-bie-hub](https://github.com/AtlasOfLivingAustralia/ala-bie-hub) | AtlasOfLivingAustralia | Biodiversity Information Explorer hub |
| [bie-index](https://github.com/AtlasOfLivingAustralia/bie-index) | AtlasOfLivingAustralia | BIE species index service |
| [image-service](https://github.com/AtlasOfLivingAustralia/image-service) | AtlasOfLivingAustralia | Image management service |
| [specieslist-webapp](https://github.com/AtlasOfLivingAustralia/specieslist-webapp) | AtlasOfLivingAustralia | Species lists web app (legacy) |
| [species-lists](https://github.com/AtlasOfLivingAustralia/species-lists) | AtlasOfLivingAustralia | Species lists service (new) |
| [spatial-hub](https://github.com/AtlasOfLivingAustralia/spatial-hub) | AtlasOfLivingAustralia | Spatial analysis hub |
| [spatial-service](https://github.com/AtlasOfLivingAustralia/spatial-service) | AtlasOfLivingAustralia | Spatial analysis service |
| [regions](https://github.com/AtlasOfLivingAustralia/regions) | AtlasOfLivingAustralia | Regions management service |
| [logger-service](https://github.com/AtlasOfLivingAustralia/logger-service) | AtlasOfLivingAustralia | Event logging service |
| [ala-namematching-service](https://github.com/AtlasOfLivingAustralia/ala-namematching-service) | AtlasOfLivingAustralia | Taxonomic name matching service |
| [ala-sensitive-data-service](https://github.com/AtlasOfLivingAustralia/ala-sensitive-data-service) | AtlasOfLivingAustralia | Sensitive data service |
| [dashboard](https://github.com/AtlasOfLivingAustralia/dashboard) | AtlasOfLivingAustralia | LA Dashboard service |
| [alerts](https://github.com/AtlasOfLivingAustralia/alerts) | AtlasOfLivingAustralia | User alerts service |
| [doi-service](https://github.com/AtlasOfLivingAustralia/doi-service) | AtlasOfLivingAustralia | DOI minting service |
| [userdetails](https://github.com/AtlasOfLivingAustralia/userdetails) | AtlasOfLivingAustralia | User management service |
| [base-branding](https://github.com/living-atlases/base-branding) | living-atlases | LA base branding and theming |
| [ipt](https://github.com/gbif/ipt) | gbif | GBIF Integrated Publishing Toolkit — DarwinCore data publishing |
| [gbif-api](https://github.com/gbif/gbif-api) | gbif | GBIF public Java API model — shared types/enums |
| [dwca-validator](https://github.com/gbif/dwca-validator) | gbif | Darwin Core Archive validator |
| [dwca-io](https://github.com/gbif/dwca-io) | gbif | Darwin Core Archive reader/writer library |
| [occurrence](https://github.com/gbif/occurrence) | gbif | GBIF occurrence processing and download service |
| [registry](https://github.com/gbif/registry) | gbif | GBIF registry of datasets, organizations, nodes, installations |
| [checklistbank](https://github.com/gbif/checklistbank) | gbif | GBIF ChecklistBank — taxonomic checklist storage and API |

---

## How to Add a Repository

Missing a repo? Open a PR:

1. Edit [`ansible/repos_tier2.yml`](ansible/repos_tier2.yml) and add an entry:

```yaml
- name: your-repo
  org: YourOrg
  url: https://github.com/YourOrg/your-repo.git
  branch: main
  patterns:
    - "**/*.md"
    - "src/**/*.java"   # adjust to your stack
  description: "Short description of what this service does"
```

2. Open a PR targeting `main`.
3. After merge, run `ansible/setup_kb.yml` on the server to index the new repo.

**Criteria for inclusion:**
- Actively maintained LA/GBIF ecosystem service
- Has meaningful documentation or configuration worth indexing

---

## API Usage

### Semantic search

```bash
curl -X POST https://kb.l-a.site/api/query \
  -H 'Content-Type: application/json' \
  -d '{"question": "How do I configure collectory?", "collection": "la_toolkit_kb", "n_results": 5}'
```

### AI chat (RAG + Qwen)

```bash
curl -X POST https://kb.l-a.site/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"question": "How do I deploy biocache-service?", "collection": "la_toolkit_kb"}'
```

### MCP (Claude / AI agents)

```json
{
  "mcpServers": {
    "living-atlas-kb": {
      "type": "http",
      "url": "https://kb.l-a.site/mcp"
    }
  }
}
```

---

## Development

```bash
cd server
pip install -r requirements.txt
uvicorn api:app --reload
```

Tests:

```bash
pytest tests/
```
