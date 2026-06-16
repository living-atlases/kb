# living-atlas-kb

Knowledge base service for Living Atlas / ALA repositories — semantic search over documentation, configuration, and source code, exposed as an **MCP tool** for AI assistants and as a REST API.

- **MCP endpoint:** `https://kb.l-a.site/mcp`
- **REST API:** `https://kb.l-a.site/api/`
- **API docs:** `https://kb.l-a.site/api/docs`
- **Live collections:** `https://kb.l-a.site/api/collections`

---

## MCP Integration (Claude / AI agents)

The primary use-case. Connect any MCP-capable AI assistant to query the KB.

### Claude Desktop (`claude_desktop_config.json`)

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

File location:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`

### OpenCode / Claude Code

Add to `~/.config/opencode/opencode.json` (or project-level `.opencode.json`):

```json
{
  "mcp": {
    "servers": {
      "living-atlas-kb": {
        "type": "http",
        "url": "https://kb.l-a.site/mcp"
      }
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json` in your project root, or `~/.cursor/mcp.json` globally:

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

### VS Code (GitHub Copilot)

Add to `.vscode/settings.json` or user settings:

```json
{
  "github.copilot.chat.mcp.servers": {
    "living-atlas-kb": {
      "type": "http",
      "url": "https://kb.l-a.site/mcp"
    }
  }
}
```

### Cline / Roo Code

Settings → MCP Servers → Add:

```json
{
  "living-atlas-kb": {
    "type": "http",
    "url": "https://kb.l-a.site/mcp"
  }
}
```

### Self-hosted / stdio mode

If running a local instance, you can also use stdio transport pointing to the local server:

```json
{
  "mcpServers": {
    "living-atlas-kb-local": {
      "command": "python3",
      "args": ["/opt/la-toolkit-kb/server/mcp_stdio.py"],
      "env": {
        "CHROMA_PATH": "/opt/la-toolkit-kb/data/chromadb",
        "OLLAMA_BASE_URL": "http://127.0.0.1:11434"
      }
    }
  }
}
```

### Available MCP tools

Once connected, the KB exposes:

| Tool | Description |
|---|---|
| `query_la_kb` | Semantic search over all indexed repos |
| `list_la_kb_collections` | List available collections with doc counts |

---

## API Usage

### Semantic search

```bash
curl -X POST https://kb.l-a.site/api/query \
  -H 'Content-Type: application/json' \
  -d '{"question": "How do I configure collectory?", "collection": "la_toolkit_kb", "n_results": 5}'
```

### AI chat (RAG + streaming)

```bash
curl -N -X POST https://kb.l-a.site/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"question": "How do I deploy biocache-service?", "collection": "la_toolkit_kb"}'
```

Response is a server-sent events (SSE) stream:

```
data: {"token": "To deploy biocache-service"}
data: {"token": " you need to..."}
data: [DONE]
```

---

## Indexed Repositories

All repos are defined in [`ansible/repos.yml`](ansible/repos.yml) — single source of truth.

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
| [atlas-index](https://github.com/AtlasOfLivingAustralia/atlas-index) | AtlasOfLivingAustralia | New species search index (replaces bie-index) |
| [image-service](https://github.com/AtlasOfLivingAustralia/image-service) | AtlasOfLivingAustralia | Image management service |
| [specieslist-webapp](https://github.com/AtlasOfLivingAustralia/specieslist-webapp) | AtlasOfLivingAustralia | Species lists web app (legacy) |
| [species-lists](https://github.com/AtlasOfLivingAustralia/species-lists) | AtlasOfLivingAustralia | Species lists service (new) |
| [authoritative-lists](https://github.com/AtlasOfLivingAustralia/authoritative-lists) | AtlasOfLivingAustralia | Authoritative species lists management |
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
| [ala-cas-5](https://github.com/AtlasOfLivingAustralia/ala-cas-5) | AtlasOfLivingAustralia | CAS 6.x authentication server for LA portals |
| [volunteer-portal](https://github.com/AtlasOfLivingAustralia/volunteer-portal) | AtlasOfLivingAustralia | DigiVol citizen science volunteer portal |
| [ecodata](https://github.com/AtlasOfLivingAustralia/ecodata) | AtlasOfLivingAustralia | Ecological and environmental data service |
| [profile-hub](https://github.com/AtlasOfLivingAustralia/profile-hub) | AtlasOfLivingAustralia | Species profile hub |
| [fieldcapture](https://github.com/AtlasOfLivingAustralia/fieldcapture) | AtlasOfLivingAustralia | Field data capture application |
| [biocollect](https://github.com/AtlasOfLivingAustralia/biocollect) | AtlasOfLivingAustralia | Biological data collection application |
| [commonui-bs5-2024](https://github.com/AtlasOfLivingAustralia/commonui-bs5-2024) | AtlasOfLivingAustralia | Bootstrap 5 common UI components for LA portals |
| [base-branding](https://github.com/living-atlases/base-branding) | living-atlases | LA base branding and theming |
| [ipt](https://github.com/gbif/ipt) | gbif | GBIF Integrated Publishing Toolkit — DarwinCore data publishing |
| [gbif-api](https://github.com/gbif/gbif-api) | gbif | GBIF public Java API model — shared types/enums |
| [dwca-io](https://github.com/gbif/dwca-io) | gbif | Darwin Core Archive reader/writer library |
| [occurrence](https://github.com/gbif/occurrence) | gbif | GBIF occurrence processing and download service |
| [registry](https://github.com/gbif/registry) | gbif | GBIF registry of datasets, organizations, nodes, installations |
| [checklistbank](https://github.com/gbif/checklistbank) | gbif | GBIF ChecklistBank — taxonomic checklist storage and API |

---

## Self-hosting / Deployment

`https://kb.l-a.site` is the **public reference instance**. You can run your own with the
included Ansible playbooks.

### Prerequisites

- A target host running **Ubuntu** with SSH access (`ansible_user` with sudo).
- **Ansible** 2.9+ on your control machine.
- A DNS name pointing at the host if you want public HTTPS (TLS is terminated by nginx;
  see `ansible/files/copy-kb-cert.sh` for a Let's Encrypt deploy-hook example).

### Steps

1. **Configure your inventory** — copy the example and edit it:

   ```bash
   cp inventory.example.ini inventory.ini
   # edit inventory.ini: set your host, kb_domain, kb_user, kb_home
   ```

   `inventory.ini` is gitignored, so your real host stays local. Any variable can also be
   overridden at the command line, e.g. `-e "kb_domain=kb.myatlas.org"`.

2. **Initial setup + first index** (installs deps, systemd services, nginx, then indexes):

   ```bash
   ansible-playbook -i inventory.ini ansible/setup_kb.yml
   ```

3. **Optional — RAG chat** via a local Ollama LLM:

   ```bash
   ansible-playbook -i inventory.ini ansible/install_ollama.yml
   ```

4. **Update code / restart services** without re-indexing:

   ```bash
   ansible-playbook -i inventory.ini ansible/deploy.yml
   ```

### How indexing stays fresh

`kb_watcher.py` runs hourly (cron, installed by the playbook) and polls each repo with
`git ls-remote`; it re-indexes **only** repositories whose default branch has new commits.
To force a re-index of a single repo:

```bash
ansible-playbook -i inventory.ini ansible/setup_kb.yml \
  --tags reindex -e "reindex_repo=Org/name"
```

---

## Contributing

### Add a repository to the index

Open a PR editing [`ansible/repos.yml`](ansible/repos.yml) — the single source of truth:

```yaml
tiers:
  tier2:
    repos:
      - name: your-repo
        org: YourOrg
        url: https://github.com/YourOrg/your-repo.git
        # branch is auto-detected from the repo's default HEAD; override only if needed.
        patterns:
          - "**/*.md"
          - "src/**/*.java"   # adjust to your stack
        description: "Short description of what this service does"
```

**Criteria:** actively maintained public LA/GBIF ecosystem service with meaningful docs or config.
After merge, the maintainer re-runs `ansible/setup_kb.yml` (or the watcher picks it up) to index it.

### Local development

```bash
cd server
pip install -r requirements.txt
uvicorn api:app --reload
```

### Tests & conventions

```bash
pytest tests/ -v
```

- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/).
- CI (`.github/workflows/ci.yml`) runs the pytest suite on every push/PR.

---

## License

Licensed under the [Apache License 2.0](LICENSE).

Copyright © Living Atlases / GBIF community.
