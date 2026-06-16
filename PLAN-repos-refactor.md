# Plan: Refactorizar definición de repos de la KB

## Problema

- `repos_tier1.yml`, `repos_tier2.yml` y `repos.yml` coexisten — solo el último se usa realmente
- `org:` y `url:` se repiten en cada entrada (~30 veces para ALA solo)
- Patterns por repo son inconsistentes, difíciles de mantener y excluyen contenido útil
- Polling cron diario/semanal indexa aunque no haya cambios

---

## Cambios propuestos

### 1. Eliminar `repos_tier1.yml` y `repos_tier2.yml`

Son versiones obsoletas/redundantes. Solo `repos.yml` se referencia en `setup_kb.yml` (línea 104).
Los otros dos se eliminan sin impacto funcional.

---

### 2. Reestructurar `repos.yml` — agrupar por org

Eliminar repetición de `org:` y `url:` construyendo la URL desde `base_url + name`:

```yaml
# repos.yml — Single source of truth
# URL construida como: {base_url}/{name}.git
# Branch por defecto: develop/dev, fallback main/master (según repo)

orgs:
  AtlasOfLivingAustralia:
    base_url: https://github.com/AtlasOfLivingAustralia
    repos:
      - collectory
      - biocache-service
      - biocache-hubs
      - ala-bie-hub
      - bie-index
      - atlas-index
      - image-service
      - specieslist-webapp
      - species-lists
      - authoritative-lists
      - spatial-hub
      - spatial-service
      - regions
      - logger-service
      - ala-namematching-service
      - ala-sensitive-data-service
      - dashboard
      - alerts
      - doi-service
      - userdetails
      - ala-cas-5
      - volunteer-portal
      - ecodata
      - profile-hub
      - fieldcapture
      - biocollect
      - commonui-bs5-2024
      - ala-install

  living-atlases:
    base_url: https://github.com/living-atlases
    repos:
      - name: la-toolkit
        branch: main          # override
      - base-branding

  gbif:
    base_url: https://github.com/gbif
    repos:
      - name: pipelines
        description: "DarwinCore data processing (livingatlas module)"
      - ipt
      - gbif-api
      - dwca-validator
      - dwca-io
      - occurrence
      - registry
      - checklistbank

# Tier1: repos críticos — indexados primero en setup desde cero
# (no implican frecuencia distinta en el watcher)
tier1:
  - AtlasOfLivingAustralia/ala-install
  - living-atlases/la-toolkit
  - gbif/pipelines
```

**Reglas de construcción de URL:**
- `url = base_url + "/" + name + ".git"`
- `branch = develop/dev when available; fallback to main/master per repository` por defecto, override con `branch: main` en la entrada
- Override de `description` solo cuando aporta contexto que el nombre no da

---

### 3. Eliminar patterns — indexar todo el texto

Sin filtro glob. El indexer clona y procesa todos los ficheros de texto plano.

Blocklist global mínimo (excluir siempre):
```
.git/
node_modules/
build/
target/
.gradle/
*.jar
*.class
*.pyc
*.png *.jpg *.gif *.ico
*.zip *.tar.gz
```

Ventaja: sin falsos negativos, sin mantenimiento de patterns por repo.
Si el ruido es problema en la KB, se ajusta el chunking/embedding, no los patterns.

---

### 4. Cambiar estrategia de actualización a RSS/Atom polling

GitHub expone un feed de commits por repo:
```
https://github.com/ORG/REPO/commits/BRANCH.atom
```

**Nuevo script: `kb_watcher.py`**

Lógica:
1. Para cada repo del manifest: fetch del Atom feed
2. Comparar el SHA del commit más reciente con el almacenado en `~/.kb/state/REPO.last_sha`
3. Si hay commits nuevos: ejecutar `kb_indexer.py --repo ORG/NAME`
4. Actualizar el SHA almacenado

Cron: `0 * * * *` (cada hora, un único job)

```
# /etc/cron.d/la-kb
0 * * * * kb source /opt/la-kb/venv/bin/activate && python3 /opt/la-kb/scripts/kb_watcher.py >> /opt/la-kb/logs/watcher.log 2>&1
```

Ventajas sobre el modelo actual:
- Repos activos se actualizan más frecuentemente que repos estables
- No hay distinción artificial tier1/tier2 para scheduling
- Un solo cron job en lugar de dos
- Re-indexado solo cuando hay cambios reales

---

## Ficheros afectados

| Fichero | Acción |
|---|---|
| `ansible/repos_tier1.yml` | Eliminar |
| `ansible/repos_tier2.yml` | Eliminar |
| `ansible/repos.yml` | Reescribir con estructura compacta por org |
| `ansible/setup_kb.yml` | Actualizar: leer nueva estructura, cambiar crons |
| `ansible/files/kb_indexer.py` | Actualizar parser para nueva estructura YAML, añadir `--repo` flag |
| `ansible/files/kb_watcher.py` | Nuevo: RSS/Atom poller + estado SHA por repo |

---

## Lo que NO cambia

- ChromaDB como vector store
- Servidor MCP/API (`server/`)
- Lógica de embedding y chunking
- Deploy ansible general (inventory, deploy.yml)

---

## Preguntas abiertas

1. Nota: el indexado se estaba ejecutando en el servidor y se desplegó vía Ansible;
   confirmar si proviene de este repo o de `ansible-extras`.
2. ¿Se quiere un blocklist más agresivo para `ala-install`?
   Tiene mucho `molecule/` (tests Ansible) que probablemente no aporta a la KB.
3. Regla explícita: nunca procesar repos privados. Solo incluir repos públicos en el feed y en la ingestión.
