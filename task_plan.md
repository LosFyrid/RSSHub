# RSS Hub Production Rollout Plan

## Goal

Roll out the latest RSS Hub release to production via the independent Flux deployment repository, then verify the live service at `https://rss-hub.pic-aichem.online` with the new registration and console UX.

## Current Follow-up

- Add a productized provider management entry in Console so translator/summarizer setup no longer depends on Django admin.
- Diagnose the reported feed errors in production and expose the root cause more clearly in the UI.

## Constraints

- Do not modify `/Users/losfyrid/projects/agentcluster-Flux`.
- Follow GitOps flow only for rollout changes.
- Use the independent deployment repo at `/Users/losfyrid/projects/agentcluster-Flux-rss-hub`.
- Keep cluster changes aligned with Flux/Kubernetes best practice.

## Phases

| Phase | Status | Notes |
| --- | --- | --- |
| Record rollout context | completed | Planning files created and baseline repo state captured. |
| Publish release artifacts | completed | Immutable tag `20260418-182221` and `latest` both available in Harbor. |
| Update deployment repo | completed | Prod overlay updated, committed, and pushed to deployment repo `main`. |
| Reconcile Flux and verify rollout | completed | Flux applied revision `18fb681` and web/worker rolled to the new image. |
| Live acceptance check | completed | Public root redirects to login, login succeeds, dashboard and console routes return 200. |
| Diagnose provider gap and feed errors | in_progress | Live DB shows no translator/summarizer agents at all, and the only failing feed is missing a translation engine. |
| Ship console provider management | pending | Add safe provider creation/status UI in Console and improve runtime diagnostics on feed detail. |
| Redeploy and verify | pending | Build/push new image, update deploy repo, reconcile Flux, and validate live behavior. |

## Errors Encountered

| Error | Attempt | Resolution |
| --- | --- | --- |
| `kubectl` custom-columns expression hit zsh globbing | 1 | Re-ran status checks without the glob-sensitive formatter. |
| Live pod label lookup using the wrong selector returned no pod | 1 | Switched to `app.kubernetes.io/component` selectors already present on the running web/worker pods. |
