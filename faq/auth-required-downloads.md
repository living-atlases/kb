# FAQ: Require login before species/occurrence downloads

**Question.** How do I force users to be logged in before they can download
occurrence/species records? Where is `authService` and how does authentication
work in the occurrence/biocache stack?

## Short answer

Authentication on downloads is enforced in two layers:

1. **biocache-hub (the UI/webapp)** decides which paths require a logged-in user.
   This is driven by the config property
   `security.cas.authenticateOnlyIfLoggedInFilterPattern`, whose default already
   includes the download proxy paths:

   ```
   security.cas.authenticateOnlyIfLoggedInFilterPattern=/occurrences/*,/explore/your-area,/query,/proxy/download/*,/
   ```

   Add/keep the download paths in that pattern to require login. The hub talks to
   CAS/OIDC for the actual sign-in (`security.cas.*`, `bypass_cas`).

2. **biocache-service (the WS)** validates the caller on the download endpoints.
   `DownloadController` uses `AuthService` to resolve the user. `AuthService`
   documents three authentication routes for download users (JWT/OAuth via
   `AlaUserProfile`, legacy API key, and email). Sensitive-data access on
   downloads is gated by `download_auth_sensitive=true`.

So: to require login, ensure the hub filter pattern covers the download paths and
that CAS/OIDC is enabled (not bypassed); biocache-service then receives the
authenticated principal and applies role/sensitive checks.

## Where to look

- `biocache-service` → `src/main/java/au/org/ala/biocache/service/AuthService.java`
  (interface; "Authentication for download users has 3 routes").
- `biocache-service` → `src/main/java/au/org/ala/biocache/web/DownloadController.java`.
- `ala-install` → `ansible/roles/biocache-hub/templates/config/config.properties`
  (`security.cas.authenticateOnlyIfLoggedInFilterPattern`, `security.cas.bypass`).
- Inventory flags: `download_auth_sensitive`, `logging_enabled`.

## Sources

- AtlasOfLivingAustralia/biocache-service
- AtlasOfLivingAustralia/ala-install (biocache-hub role)
- AtlasOfLivingAustralia/documentation wiki — API-Keys
