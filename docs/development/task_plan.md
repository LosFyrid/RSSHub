# Auth And UX Iteration Plan

## Goal

Add lightweight login-protected management UI and workspace-based multi-tenant access to RSS Hub, while keeping public RSS/OPML subscription links unchanged. In the same iteration, reduce developer-facing wording in the hub UI and clarify product concepts such as workspace, output language, provider defaults, and bulk edit mode.

## Confirmed Decisions

- Hub UI requires login.
- RSS and OPML feed output URLs remain public in this phase.
- Do not integrate with external IAM.
- Use Django auth and project PostgreSQL directly for user/password management.
- `workspace` acts like a lightweight organization boundary.
- Workspace membership plus role is the intended direction.
- UI language and feed output language are separate concepts.
- Structure fields should not be bulk-editable.
- Feed provider defaults live at workspace level, with per-feed override allowed.
- Bulk actions only apply to explicitly checked feeds.

## Scope For This Iteration

1. Add authentication entry points for hub usage.
2. Add workspace membership model and request scoping helpers.
3. Restrict hub UI data and actions to accessible workspaces.
4. Improve hub wording and information hierarchy.
5. Add tests for auth gating, membership scoping, and revised UX flows.
6. Complete workspace member management with role update and remove flows.
7. Add a prominent current-workspace switcher that only lists accessible workspaces.
8. Diagnose and fix the digest CronJob PostgreSQL compatibility bug without changing public RSS/OPML URLs.

## Out Of Scope

- Private subscription URLs or tokenized feed URLs.
- Email verification, password reset mail flow, SSO, OAuth, or IAM integration.
- Deployment manifest changes.
- Cluster changes.
- Translation strategy changes.

## Risks

- Existing tests assume anonymous hub access and will need updates.
- Current admin and hub may share assumptions about unrestricted workspace visibility.
- Public RSS remains public, so tenant isolation only applies to management UI in this phase.

## Acceptance Checklist

- [x] Unauthenticated requests to hub UI redirect to login.
- [x] Login page is available in Chinese and English UI copy.
- [x] Authenticated users only see workspaces they belong to, unless superuser.
- [x] Feed list, group list, workspace defaults, bulk edit, and OPML import respect membership scoping.
- [x] Workspace wording in UI explains it as a collaboration boundary, not a technical field.
- [x] UI language switching does not change feed output language.
- [x] Bulk edit controls are only shown inside explicit bulk mode.
- [x] Theme switching still works after template changes.
- [x] Targeted test suite passes.
- [x] Workspace members can be created, reprivileged, and removed from the hub UI.
- [x] Manager can manage non-owner members, while owner-only safeguards prevent owner lockout.
- [x] The dashboard has a prominent current workspace switcher limited to accessible workspaces.
- [x] Public RSS and OPML URLs remain public.
- [x] Digest generator no longer relies on backend-specific JSON SQL that breaks on PostgreSQL.
