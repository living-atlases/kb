# FAQ: lft/rgt values change after name matching — when must I reprocess?

**Question.** After importing a new DwCA into BIE and rebuilding the name index,
the taxonomic `lft`/`rgt` values change, and some records then look "missing"
when querying Solr via biocache-service unless the data is reprocessed. Can I
avoid a full reprocess when the DwCA is refreshed regularly?

## Short answer

`lft`/`rgt` are **nested-set boundaries** assigned by the names/taxonomic index.
Each occurrence record stores the matched taxon's `lft`/`rgt`, and Solr uses them
for hierarchical (taxon subtree) queries. When the name index is rebuilt those
boundaries can shift, so occurrence records carry **stale** `lft`/`rgt` until they
are **re-matched (name matching runs during processing/interpretation) and
re-indexed** — which is why subtree queries appear to drop records.

There is no supported way to keep correct `lft`/`rgt`-based subtree results
*without* re-matching the affected records against the new index. The commands
depend on your backend.

### Pipelines backend (modern / default)

Name matching happens in the **interpretation** stage, so after pointing the
install at the new name index, re-run interpretation → index → solr for the
affected data resource (via the pipelines Jenkins jobs or the `la-pipelines` CLI):

```
./la-pipelines interpret dr123 --cluster
./la-pipelines index     dr123 --cluster
./la-pipelines solr      dr123 --cluster
```

(`sample`, `jackknife`, `clustering` only need re-running if their inputs changed.)

### Legacy biocache-store backend

> ⚠️ Legacy — only for old `biocache-store` deployments, not Pipelines.

```
biocache process-single <Record UUID>   # test one record
biocache process -dr <druid>            # reprocess the resource
biocache index   -dr <druid>            # reindex the resource
```

### Minimising cost on frequent DwCA refreshes

- Reprocess/reindex **per data resource** (`drXXX`), not everything, so only
  changed resources pay the cost.
- Only **rebuild the name index** when the taxonomy actually changes. A
  content-only DwCA refresh that doesn't alter the taxonomy doesn't move
  `lft`/`rgt`, so no full re-match is needed.

## Where to look

- `documentation` wiki → `Name-indexer.md` (note its own ⚠️ Legacy markers on the
  `biocache process/index` commands; points to pipelines Jenkins jobs / `la-pipelines`).
- `documentation` wiki → "A Guide to Getting Names into the ALA" (reprocess & reindex).
- `pipelines` → `livingatlas/pipelines.md` (`la-pipelines` step reference).
- `bie-index` wiki → "Things to check for a new bie index" (older but informative).

## Sources

- AtlasOfLivingAustralia/documentation wiki — Name-indexer, Getting-Names-into-the-ALA
- AtlasOfLivingAustralia/pipelines (livingatlas/pipelines.md)
- AtlasOfLivingAustralia/bie-index wiki
