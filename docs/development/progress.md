# Progress Log

## 2026-04-18

- Verified GitHub token permission fix with direct GitHub API and git transport tests.
- Verified Flux still shows transient GitHub HTTPS timeout from source-controller.
- Confirmed GitHub public status does not show an active incident right now.
- Read current workspace, feed, hub views, forms, templates, CSS, and test coverage.
- Defined this iteration boundary: add login and workspace membership for UI only, keep public feed URLs unchanged.
- Started persistent planning docs and acceptance checklist before code changes.
- Added workspace membership model, migration, and hub auth entry points.
- Scoped hub data and write actions to accessible workspaces.
- Added account password change and workspace member creation inside the hub UI.
- Rewrote hub copy to better explain workspace, UI language, feed output language, and bulk mode.
- Fixed the front-end theme script so theme switching still works even when bulk-edit DOM is absent.
- Verified with targeted Django tests and a clean `makemigrations --check`.
- Added full workspace member management in the hub UI: role changes, member removal, and owner-lockout safeguards.
- Added a prominent current-workspace switcher near the top of the dashboard, restricted to workspaces the current user can access.
- Adjusted membership permission semantics so owners can fully manage members, while managers can manage non-owner members only.
- Diagnosed the failing Saturday digest CronJob in Kubernetes and traced it to backend-specific JSON SQL in the digest management command.
- Reworked `digest_generator` day filtering to be database-agnostic and verified it with a dedicated command test.
