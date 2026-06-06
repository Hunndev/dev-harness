---
name: hb-chat
description: Use when working on the BUCCL chat MSA with TypeScript, Express, Socket.io, MySQL, Redis, attachment handling, BE integration, ADRs, contracts, planning, feature, maintenance, and dual review gates.
---

# BUCCL Chat Harness

Use this skill when the user asks for `hb-chat`, BUCCL chat service, chat MSA, Socket.io messaging, room/message/attachment/invite/presence implementation, or chat-specific planning/contract/review.

## Source Of Truth

Read `CLAUDE.md` first, then the matching command document under `commands/`. If you are operating from the dev-harness repository root instead of the CHAT plugin root, prefix these paths with `CHAT/`.

- Planning: `commands/planning/auto.md` or `commands/planning/deep.md`
- Feature: `commands/feature/auto.md` or `commands/feature/deep.md`
- Maintenance: `commands/maintenance/hotfix.md`, `commands/maintenance/auto.md`, `commands/maintenance/deep.md`
- ADR: `commands/adr/new.md`
- Contract: `commands/contract/websocket.md`, `commands/contract/api.md`
- Shared: `commands/shared/verify.md`, `commands/shared/update-docs.md`, `commands/shared/review-gates.md`, `commands/shared/tdd.md`

## Command Mapping

Codex does not execute Claude slash commands directly. Treat these phrases as intent aliases:

- `hb-chat planning auto` or `/hb-chat:planning:auto`
- `hb-chat planning deep` or `/hb-chat:planning:deep`
- `hb-chat feature auto` or `/hb-chat:feature:auto`
- `hb-chat feature deep` or `/hb-chat:feature:deep`
- `hb-chat maintenance hotfix` or `/hb-chat:maintenance:hotfix`
- `hb-chat maintenance auto` or `/hb-chat:maintenance:auto`
- `hb-chat maintenance deep` or `/hb-chat:maintenance:deep`
- `hb-chat adr new` or `/hb-chat:adr:new`
- `hb-chat contract websocket` or `/hb-chat:contract:websocket`
- `hb-chat contract api` or `/hb-chat:contract:api`
- `hb-chat shared update-docs` or `/hb-chat:shared:update-docs`
- `hb-chat shared verify` or `/hb-chat:shared:verify`

## Operating Rules

1. Keep artifacts under `.harness/artifacts/{track}/{identifier}/`.
2. Use `.harness/docs/*.yaml` as source of truth (adr, architecture, module-registry, code-convention, websocket-events, api-contract, database-schema, integration-boundary, operations, review-policy).
3. Do not modify BE, FE, or buccl-community unless the user explicitly approves cross-repo work; propose the needed contract, get approval, then switch to `hb-be`/`hb-fe`/`hb-cm`.
4. Do not read the BE DB directly. Use the BE API for verified lesson/tour applicant lists (userId source of truth = BE).
5. Do not store attachment originals in the DB (Object Storage + metadata only).
6. Every Socket.io event must be registered in `websocket-events.yaml`; every REST change in `api-contract.yaml`; every DB change in `database-schema.yaml` with a migration review.
7. New ADRs originate from the planning/adr track only — maintenance/feature verify conformance via `commands/maintenance/convention-check.md`.
8. Use Jest for tests; follow Red-Green-Refactor in `commands/shared/tdd.md`.
9. Run `npm test`, `npm run lint`, `npm run build`, `npx tsc --noEmit` before completion.
10. Completion requires the dual review gate (`commands/shared/review-gates.md`): tests + lint + build pass AND both Codex review and Claude review have no blocking findings.

## Track Selection

- `planning` — deciding architecture, schema, read/receipt policy, Socket.io event naming/versioning, scale-out, attachment/permission model, BE/FE integration direction.
- `feature` — adding a room/message/attachment/invite/presence API, Socket event, or service.
- `maintenance` — bug, race condition, message duplication, read-state corruption, performance, dependency.
- `hotfix` — very small, clearly scoped fix.
- `deep` — multi-module, BE/FE integration, migration, Socket event change, or unclear blast radius.
- `adr:new` — register a design decision as an ADR candidate.
- `contract:websocket` / `contract:api` — review/update the realtime or REST contract before/after a change.
