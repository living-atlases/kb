# FAQ: Protecting Living Atlas services from scraping and bots (basics)

**Question.** How do I protect biocache/BIE/spatial from aggressive scraping and
AI crawlers at the infrastructure layer?

## Short answer (what the stack supports out of the box)

The ALA/Living Atlas deployment exposes several built-in knobs via the `nginx`
webserver role and inventory. The basics:

- **robots / user-agent blocking** (inventory variables consumed by the nginx
  role):

  ```
  webserver_nginx=true
  robots_disallow_paths=["/ws", "/geoserver", "/geonetwork"]
  robots_disallow_useragents=["SemrushBot", "Mappy", "BUbiNG"]
  ```

  Add abusive crawler user-agents and the heavy paths (web services, geoserver,
  geonetwork) you don't want crawled.

- **fail2ban** to ban IPs showing abusive patterns — see the
  "Secure your LA infrastructure" wiki page (there is also a fail2ban WordPress
  plugin for the CMS node).

- **blacklist file** for the hubs (`blacklist_file: blacklist.json` in the
  bie-hub / hub roles) to block specific clients/keys.

- **nginx caching / limits**: cache expensive read endpoints and set
  `nginx_client_max_body_size`; keep `biocache` and `biocache/ws` on separate
  names/servers to avoid CORS/cache cross-talk (see FAQ in the wiki).

These cover robots, user-agent and IP-level mitigation. More advanced measures
(proof-of-work challenges, ASN/GeoIP-based blocking, behavioural detection such
as CrowdSec) are **not** part of the stack today and would be custom additions in
front of nginx.

## Where to look

- `ala-install` → `ansible/inventories/workshop/spatial-livingatlas.yml`
  (`robots_disallow_paths`, `robots_disallow_useragents`, `nginx_client_max_body_size`).
- `ala-install` → `ansible/roles/bie-hub/defaults/main.yml` (`blacklist_file`).
- `documentation` wiki → "Secure your LA infrastructure" (fail2ban), "FAQ" (nginx/CORS).

## Sources

- AtlasOfLivingAustralia/ala-install
- AtlasOfLivingAustralia/documentation wiki — Secure-your-LA-infrastructure, FAQ
