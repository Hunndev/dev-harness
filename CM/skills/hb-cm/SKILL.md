---
name: hb-cm
description: Use when working in the BUCCL Node.js/TypeScript community backend repository with the dev-harness flow, including planning, feature work, maintenance, TDD, ADR conflict checks, regression verification, and review artifacts.
---

# BUCCL CM Harness

Use this skill when the user asks for `hb-cm`, CM pipeline, community backend harness, Node/Express harness, or a workflow similar to `dev-harness` for the BUCCL community backend.

## Source Of Truth

Read `CLAUDE.md` first, then the matching command document under `commands/`. If you are operating from the dev-harness repository root instead of the CM plugin root, prefix these paths with `CM/`.

- Planning: `commands/planning/auto.md` or `commands/planning/deep.md`
- Feature: `commands/feature/auto.md` or `commands/feature/deep.md`
- Maintenance: `commands/maintenance/hotfix.md`, `commands/maintenance/auto.md`, or `commands/maintenance/deep.md`
- Shared protocols: `commands/shared/tdd.md`, `commands/shared/verify.md`, `commands/shared/update-docs.md`

## Command Mapping

Codex does not execute Claude slash commands directly. Treat these phrases as intent aliases:

- `hb-cm planning auto` or `/hb-cm:planning:auto`
- `hb-cm planning deep` or `/hb-cm:planning:deep`
- `hb-cm feature auto` or `/hb-cm:feature:auto`
- `hb-cm feature deep` or `/hb-cm:feature:deep`
- `hb-cm maintenance hotfix` or `/hb-cm:maintenance:hotfix`
- `hb-cm maintenance auto` or `/hb-cm:maintenance:auto`
- `hb-cm maintenance deep` or `/hb-cm:maintenance:deep`
- `hb-cm shared update-docs` or `/hb-cm:shared:update-docs`

## Codex Operating Rules

1. Keep the same artifact paths as the Claude harness: `.harness/artifacts/{track}/{identifier}/`.
2. Use `.harness/docs/code-convention.yaml`, `.harness/docs/adr.yaml`, `.harness/docs/architecture.yaml`, and `.harness/docs/module-registry.yaml` as the project truth when present.
3. For feature and maintenance work, follow the Red-Green-Refactor protocol in `commands/shared/tdd.md`. Test runner is **Jest** (matches the declared Node/TS stack).
4. Never create a new ADR from the maintenance track — new ADRs originate from the planning track only. Maintenance verifies conformance via `commands/maintenance/convention-check.md`.
5. Verify Node/TS work with `npm test`, `npm run lint` (ESLint), and `npm run build` (tsc) unless the target repo narrows the scope.
6. Capture TDD evidence under `.harness/artifacts/{track}/{identifier}/` as `tdd-baseline-log.txt`, `tdd-green-log.txt`, and `tdd-refactor-notes.md`.

## Track Selection

- Use `planning` when the user is deciding architecture, schema, API contract direction, realtime/Socket.io flow, or caching strategy.
- Use `feature` when adding a new endpoint, service, realtime channel, background worker, or user-visible capability.
- Use `maintenance` when fixing a bug, performance issue, dependency problem, or refactor.
- Use `hotfix` only for very small, clearly scoped fixes with minimal blast radius (typo, single-line fix, urgent patch).
- Escalate to `deep` when the change touches multiple modules, shared services, ADR-governed decisions, or has unclear blast radius.
