---
name: hb-shared
description: Use for shared dev-harness methodology commands used across all BUCCL plugins (BE/CM/FE/CHAT) — requirements capture, acceptance criteria, design intent, prior-art research, convention checks, and feasibility review.
---

# BUCCL Shared Harness

Use this skill when the user asks for `hb-shared`, shared harness methodology, or any cross-plugin step (requirements, criteria, design intent, prior-art, convention check, feasibility) used by BE/CM/FE/CHAT.

## Source Of Truth

Read the matching command document under `commands/`. If you are operating from the dev-harness repository root instead of the SHARED plugin root, prefix these paths with `SHARED/`.

- Requirements: `commands/feature/requirements.md`
- Acceptance criteria: `commands/feature/criteria.md`
- Design intent: `commands/feature/design-intent.md`
- Prior art: `commands/feature/prior-art.md`
- Convention check: `commands/maintenance/convention-check.md`
- Feasibility: `commands/planning/feasibility.md`

## Command Mapping

Codex does not execute Claude slash commands directly. Treat these phrases as intent aliases:

- `hb-shared feature requirements` or `/hb-shared:feature:requirements`
- `hb-shared feature criteria` or `/hb-shared:feature:criteria`
- `hb-shared feature design-intent` or `/hb-shared:feature:design-intent`
- `hb-shared feature prior-art` or `/hb-shared:feature:prior-art`
- `hb-shared maintenance convention-check` or `/hb-shared:maintenance:convention-check`
- `hb-shared planning feasibility` or `/hb-shared:planning:feasibility`

## Codex Operating Rules

1. Keep the same artifact paths as the stack plugins: `.harness/artifacts/{track}/{identifier}/`.
2. These commands are **stack-agnostic** — do not assume a test runner or framework. Stack-specific build/test steps live in the BE/CM/FE/CHAT plugins.
3. Use `.harness/docs/*.yaml` as the project truth when present.
4. Push heavy reading/research into subagents and keep only the conclusion and artifact paths in the main context.
