# RSS Hub Rollout Findings

## Release Inputs

- Source repo latest application commit: `1868ce5` (`Add self-serve workspace collaboration console`).
- New container image already built and pushed: `harbor.pic-aichem.online/rss-hub/rsshub:20260418-182221`.
- Deployment repo prod overlay was updated and pushed as commit `18fb681` (`Deploy RSS Hub image 20260418-182221`).

## Guardrails

- Main Flux mono-repo is strictly read-only for this task.
- Rollout must go through the independent deployment repo and Flux reconcile.
- Live validation target is `https://rss-hub.pic-aichem.online`.

## Rollout Outcome

- Harbor `latest` now points at the same manifest digest as image tag `20260418-182221`.
- Flux `GitRepository/agentcluster-flux-rss-hub` fetched revision `main@sha1:18fb681e1e751d7391dd37cb436f578a04e1c345`.
- Flux `Kustomization/agentcluster-flux-rss-hub` reached `Ready=True` and `Healthy=True`.
- `rss-hub-web` and `rss-hub-worker` are both running `harbor.pic-aichem.online/rss-hub/rsshub:20260418-182221`.
- Public root now redirects to `/login/`, and authenticated requests to `/` and `/console/` return `200`.

## Provider Gap Diagnosis

- Console currently lets users choose workspace default translator and summarizer, but it does not expose any productized way to create or validate providers.
- Existing provider creation still lives in Django admin only.
- In the live production database there are currently zero `OpenAIAgent`, zero `DeepLAgent`, and zero `LibreTranslateAgent` rows.
- Because there are no valid agents, Console correctly shows only the “not set” default options for translator/summarizer.

## Production Feed Error Diagnosis

- The production database currently has one feed: `jeffgeerling`.
- Fetch is healthy for that feed (`fetch_status=True`), but translation is failing (`translation_status=False`).
- The user-observed “8 errors” are the last eight entries in that single feed failing translation individually.
- Root cause from the feed log: `Translate Engine Not Set`.
- This is not a network or source parsing issue; it is a configuration gap caused by enabling translation on a feed before any translator exists.
