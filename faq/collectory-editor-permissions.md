# FAQ: What permissions let a data provider edit their collectory entry?

**Question.** A data provider user can't edit their metadata in collectory even
after being set as a contact / Administrator. What roles are actually required,
and how do `ContactFor`, the Administrator flag and `ROLE_EDITOR` relate?

## Short answer

In `collectory` the security model uses CAS roles **`ROLE_ADMIN`** and
**`ROLE_EDITOR`**. The common gotcha: **`ROLE_EDITOR` is not created in CAS by
default** — so selecting "Administrator" on a `ContactFor` relationship does not
automatically grant an editing role that CAS recognises, and the user still
can't edit anything.

What this means in practice:

- Admin-level management actions are guarded by `ROLE_ADMIN` (e.g.
  `ManageController` is annotated `@PermissionRequired(roles = ['ROLE_ADMIN'])`).
- Self-service editing of an entity relies on the user having an editor role
  **and** being a recognised contact/editor for that entity (checked via
  `collectoryAuthService`).
- If `ROLE_EDITOR` doesn't exist in your CAS/userdetails instance, create/assign
  it there first; the `ContactFor` + "Administrator" checkbox alone is not enough.

## Where to look

- `documentation` wiki → `User-Roles-and-Services.md`:
  "In `collectory` service the `ROLE_ADMIN` and `ROLE_EDITOR` are now used
  (although `ROLE_EDITOR` is not created in CAS by default)".
- `collectory` → `grails-app/controllers/au/org/ala/collectory/ManageController.groovy`
  (`@PermissionRequired(roles = ['ROLE_ADMIN'])`), and `collectoryAuthService`.

## Sources

- AtlasOfLivingAustralia/documentation wiki — User-Roles-and-Services
- AtlasOfLivingAustralia/collectory
