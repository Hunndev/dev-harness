---
name: hb-be
description: Use when working in the BUCCL Django backend repository with the dev-harness flow, including planning, feature work, maintenance, TDD, ADR conflict checks, regression verification, and review artifacts.
---

# BUCCL BE Harness

Use this skill when the user asks for `hb-be`, BE pipeline, backend harness, Django harness, or a workflow similar to `dev-harness` for the BUCCL Django backend.

## Source Of Truth

Read `CLAUDE.md` first, then the matching command document under `commands/`. If you are operating from the dev-harness repository root instead of the BE plugin root, prefix these paths with `BE/`.

- Planning: `commands/planning/auto.md` or `commands/planning/deep.md`
- Feature: `commands/feature/auto.md` or `commands/feature/deep.md`
- Maintenance: `commands/maintenance/hotfix.md`, `commands/maintenance/auto.md`, or `commands/maintenance/deep.md`
- Shared protocols: `commands/shared/tdd.md`, `commands/shared/verify.md`, `commands/shared/update-docs.md`

## Command Mapping

Codex does not execute Claude slash commands directly. Treat these phrases as intent aliases:

- `hb-be planning auto` or `/hb-be:planning:auto`
- `hb-be planning deep` or `/hb-be:planning:deep`
- `hb-be feature auto` or `/hb-be:feature:auto`
- `hb-be feature deep` or `/hb-be:feature:deep`
- `hb-be maintenance hotfix` or `/hb-be:maintenance:hotfix`
- `hb-be maintenance auto` or `/hb-be:maintenance:auto`
- `hb-be maintenance deep` or `/hb-be:maintenance:deep`
- `hb-be shared update-docs` or `/hb-be:shared:update-docs`

## Codex Operating Rules

1. Keep the same artifact paths as the Claude harness: `.harness/artifacts/{track}/{identifier}/`.
2. Use `.harness/docs/code-convention.yaml`, `.harness/docs/adr.yaml`, `.harness/docs/architecture.yaml`, and `.harness/docs/module-registry.yaml` as the project truth when present.
3. For feature and maintenance work, follow the Red-Green-Refactor protocol in `commands/shared/tdd.md`. Test runner is **pytest** (matches the declared Django stack).
4. Never create a new ADR from the maintenance track — new ADRs originate from the planning track only. Maintenance verifies conformance via the shared methodology core: `hb-shared maintenance convention-check` (file: `SHARED/commands/maintenance/convention-check.md` in the dev-harness repo).
5. Verify Django work with `pytest`, the project's lint command (e.g. `ruff check`, `flake8`), and `python manage.py check` unless the target repo narrows the scope.
6. Capture TDD evidence under `.harness/artifacts/{track}/{identifier}/` as `tdd-baseline-log.txt`, `tdd-green-log.txt`, and `tdd-refactor-notes.md`.

## Track Selection

- Use `planning` when the user is deciding architecture, data model, API contract direction, async/Celery flow, or storage strategy.
- Use `feature` when adding a new API, model, service, background job, or user-visible capability.
- Use `maintenance` when fixing a bug, performance issue, dependency problem, or refactor.
- Use `hotfix` only for very small, clearly scoped fixes with minimal blast radius (typo, single-line fix, urgent patch).
- Escalate to `deep` when the change touches multiple modules, shared services, ADR-governed decisions, or has unclear blast radius.
