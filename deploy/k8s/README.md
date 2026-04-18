# RSS Hub Kubernetes Manifests

This directory contains a non-applied Kubernetes packaging for the current RSS Hub runtime.

## Layout

- `base/`
  - namespace
  - shared config and secret templates
  - CloudNativePG cluster
  - OpsTree Redis CR
  - web deployment
  - worker deployment
  - service
  - `HTTPRoute`
  - `CronJob` resources
- `overlays/prod/`
  - production overlay entrypoint

## Assumptions

- Public hostname: `rss-hub.pic-aichem.online`
- Gateway: `gateway/core-service-gateway`
- Namespace label required for route attachment:
  - `gateway.pic-aichem.online/core-service-gateway: "true"`
- PostgreSQL:
  - CloudNativePG single-instance cluster
  - storage class: `longhorn`
- Redis:
  - OpsTree `Redis` CR
  - single instance
  - image aligned with the current cluster operator usage:
    - `quay.io/opstree/redis:v7.0.15`

## Before Apply

Replace placeholder secret values in:

- `base/secret-template.yaml`
- `base/postgres-auth-secret-template.yaml`
- `base/redis-auth-secret-template.yaml`

Review and update:

- image repository/tag in `overlays/prod/kustomization.yaml`
- CPU/memory requests/limits
- PostgreSQL / Redis volume sizes
- whether the default superuser should really be created on web startup

Suggested secret values to prepare:

- `SECRET_KEY`
- `FIELD_ENCRYPTION_KEY`
- `DEFAULT_SUPERUSER_USERNAME`
- `DEFAULT_SUPERUSER_EMAIL`
- `DEFAULT_SUPERUSER_PASSWORD`
- PostgreSQL app password
- Redis password

## Runtime Notes

- Web runs migrations through an init container before startup.
- Web still performs `collectstatic` and optional default superuser creation on container start.
- Worker runs `python manage.py async_worker`.
- Recurring feed/digest/cleanup jobs are modeled as Kubernetes `CronJob` resources in `Asia/Shanghai`.
- Route attachment depends on the namespace label already included in `base/namespace.yaml`.
- PostgreSQL service endpoint follows CNPG standard naming:
  - `rss-hub-postgres-rw`
- Application pods inject:
  - `REDIS_URL=redis://:$(REDIS_PASSWORD)@rss-hub-redis:6379/0`
  - `ASYNC_REDIS_URL=redis://:$(REDIS_PASSWORD)@rss-hub-redis:6379/1`

## Validation Notes

- `kubectl kustomize deploy/k8s/overlays/prod` renders successfully.
- `kubectl apply --dry-run=client --validate=false -f <rendered-yaml>` accepts the rendered manifest set locally.
- `kubectl apply --dry-run=server -k ...` cannot fully validate this package against the live cluster while the target namespace does not exist yet. After the namespace object passes dry-run, the API server rejects the remaining namespaced resources with `namespaces "rss-hub" not found`.
- To get stricter read-only coverage without creating anything, the rendered manifests were revalidated with server-side dry-run after substituting an already existing namespace that carries the same `gateway.pic-aichem.online/core-service-gateway=true` attachment label. In that mode, the API server accepted:
  - config map and secrets
  - service
  - web and worker deployments
  - all cronjobs
  - `HTTPRoute`
  - CloudNativePG `Cluster`
  - OpsTree standalone `Redis`
- The standalone Redis service name is no longer just an inference from cluster naming patterns. Upstream redis-operator implementation creates:
  - `<redis-name>` as the normal service
  - `<redis-name>-headless` as the headless service
  so `rss-hub-redis:6379` is consistent with the operator's own implementation for a standalone `Redis` CR.

## Remaining Caveat

- Redis service naming is now backed by upstream source code, but it still has not been exercised against this exact cluster by creating a real `Redis` object in a disposable namespace. The remaining uncertainty is therefore operational, not schema-level.

No cluster write was performed during this phase.
