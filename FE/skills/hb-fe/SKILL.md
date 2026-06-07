---
name: hb-fe
description: Use when working in the BUCCL React frontend repository with the dev-harness flow, including planning, feature work, maintenance, design application, visual checks, responsive checks, accessibility notes, TDD, and review artifacts.
---

# BUCCL FE Harness

Use this skill when the user asks for `hb-fe`, FE pipeline, frontend harness, design application through the harness, or a workflow similar to `dev-harness` for the BUCCL React frontend.

## Source Of Truth

Read `CLAUDE.md` first, then the matching command document under `commands/`. If you are operating from the dev-harness repository root instead of the FE plugin root, prefix these paths with `FE/`.

- Planning: `commands/planning/auto.md` or `commands/planning/deep.md`
- Feature: `commands/feature/auto.md` or `commands/feature/deep.md`
- Maintenance: `commands/maintenance/hotfix.md`, `commands/maintenance/auto.md`, or `commands/maintenance/deep.md`
- Shared protocols: `commands/shared/tdd.md`, `commands/shared/verify.md`, `commands/shared/update-docs.md`

## Command Mapping

Codex does not execute Claude slash commands directly. Treat these phrases as intent aliases:

- `hb-fe planning auto` or `/hb-fe:planning:auto`
- `hb-fe planning deep` or `/hb-fe:planning:deep`
- `hb-fe feature auto` or `/hb-fe:feature:auto`
- `hb-fe feature deep` or `/hb-fe:feature:deep`
- `hb-fe maintenance hotfix` or `/hb-fe:maintenance:hotfix`
- `hb-fe maintenance auto` or `/hb-fe:maintenance:auto`
- `hb-fe maintenance deep` or `/hb-fe:maintenance:deep`
- `hb-fe shared update-docs` or `/hb-fe:shared:update-docs`

## Codex Operating Rules

1. Keep the same artifact paths as the Claude harness: `.harness/artifacts/{track}/{identifier}/`.
2. Use `.harness/docs/code-convention.yaml`, `.harness/docs/adr.yaml`, `.harness/docs/architecture.yaml`, and `.harness/docs/module-registry.yaml` as the project truth when present.
3. For feature and maintenance work, follow the Red-Green-Refactor protocol in `commands/shared/tdd.md`.
4. FE work splits into two modes — classify the task at the start. **Design implementation** (Claude design → screen) produces `design-source.md`, `design-intent.md`, `visual-check.md`, `responsive-check.md`, `accessibility-notes.md`. **API binding** (screen → BE data) produces `api-binding-check.md` covering API contract match, loading/empty/error/success state handling, no mock data left in production paths, and calls routed through the `src/api`/`src/utils/api.js` layer. Most screen work is a mix — produce both.
5. Verify React work with `npm run lint`, `npm test -- --watchAll=false`, and `npm run build` unless the target repo lacks the command or the user narrows the scope.
6. After significant frontend changes, use browser verification when a local target is available.

## Track Selection

- Use `planning` when the user is deciding architecture, routing, state management, design system rules, or API contract direction.
- Use `feature` when adding a new screen, component, route, flow, or user-visible capability.
- Use `maintenance` when fixing a bug, visual regression, responsive issue, performance issue, dependency problem, or refactor.
- Use `hotfix` only for very small, clearly scoped fixes with minimal blast radius.
- Escalate to `deep` when the change touches shared components, state architecture, routing, design system rules, mobile shell behavior, or multiple routes.
