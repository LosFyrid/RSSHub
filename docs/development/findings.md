# Findings

## 2026-04-18

- GitHub token permissions are now correct. Direct Contents API and `git ls-remote` tests pass with `losfyrid-repo-auth`.
- Flux source failures are no longer permission-related. Latest source-controller errors show GitHub HTTPS timeout from the cluster side.
- GitHub official status page currently reports all systems operational, with no incident reported for 2026-04-18. The latest public incident was on 2026-04-17.
- Current hub UI is anonymous and unrestricted.
- Current `Workspace` model is a content grouping/default-provider concept, not yet a permission boundary.
- No workspace membership model exists in the codebase yet.
- Public RSS/OPML endpoints are mounted under `/rss/` and root feed routes and are currently anonymous.
- Current front-end copy exposes too much implementation language such as provider override and workspace defaults without enough explanation.
- Existing tests already cover many hub flows, so auth and scoping should be added by extending those tests rather than replacing them.
- The failing `rss-hub-digest-generator-saturday-*` resources in the `rss-hub` namespace are CronJob-created digest generation jobs, not deployment garbage. They exist to generate scheduled digest outputs for Saturday.
- The Saturday digest job failed because `core/management/commands/digest_generator.py` used `.extra(where=[\"JSON_EXTRACT(...) LIKE ?\"], params=[...])`, which is SQLite-oriented and breaks under PostgreSQL/psycopg with `the query has 0 placeholders but 1 parameters were passed`.
- Feed updater CronJobs in the same namespace are healthy; the failure is isolated to the digest generator query path.
- Public RSS and OPML subscription URLs are intentionally still anonymous in this phase. Only the management UI is auth-protected.
