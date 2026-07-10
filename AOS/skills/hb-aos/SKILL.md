---
name: hb-aos
description: Use when working in the BUCCL Android WebView app repository (buccl-aos) with the dev-harness flow, including planning, feature work, maintenance, WebView shell changes, bridge contract work, device checks, permission checks, release checks, TDD, and review artifacts.
---

# BUCCL AOS Harness

Use this skill when the user asks for `hb-aos`, AOS pipeline, Android harness, WebView shell or bridge work through the harness, or a workflow similar to `dev-harness` for the BUCCL Android WebView app (buccl-aos).

## Source Of Truth

Read `CLAUDE.md` first, then the matching command document under `commands/`. If you are operating from the dev-harness repository root instead of the AOS plugin root, prefix these paths with `AOS/`.

- Planning: `commands/planning/auto.md` or `commands/planning/deep.md`
- Feature: `commands/feature/auto.md` or `commands/feature/deep.md`
- Maintenance: `commands/maintenance/hotfix.md`, `commands/maintenance/auto.md`, or `commands/maintenance/deep.md`
- Shared protocols: `commands/shared/tdd.md`, `commands/shared/verify.md`, `commands/shared/update-docs.md`

## Command Mapping

Codex does not execute Claude slash commands directly. Treat these phrases as intent aliases:

- `hb-aos planning auto` or `/hb-aos:planning:auto`
- `hb-aos planning deep` or `/hb-aos:planning:deep`
- `hb-aos feature auto` or `/hb-aos:feature:auto`
- `hb-aos feature deep` or `/hb-aos:feature:deep`
- `hb-aos maintenance hotfix` or `/hb-aos:maintenance:hotfix`
- `hb-aos maintenance auto` or `/hb-aos:maintenance:auto`
- `hb-aos maintenance deep` or `/hb-aos:maintenance:deep`
- `hb-aos shared update-docs` or `/hb-aos:shared:update-docs`

## Codex Operating Rules

1. Keep the same artifact paths as the Claude harness: `.harness/artifacts/{track}/{identifier}/`.
2. Use `.harness/docs/code-convention.yaml`, `.harness/docs/adr.yaml`, `.harness/docs/architecture.yaml`, `.harness/docs/module-registry.yaml`, and `.harness/docs/bridge-contract.yaml` as the project truth when present.
3. For feature and maintenance work, follow the Red-Green-Refactor protocol in `commands/shared/tdd.md`.
4. AOS work splits into two modes — classify the task at the start. **Shell feature** (WebView settings, push, deep link, permissions, cookie/session sync, store release) produces `design-intent.md`, `device-check.md`, `permission-check.md`, `release-check.md`. **Bridge contract** (web-to-native API via `WebAppInterface.kt`) produces `bridge-check.md` covering function signatures, message formats, error handling, and sibling-platform (iOS) contract parity, plus an update to `.harness/docs/bridge-contract.yaml` (kept identical on both platforms). Mixed work produces both.
5. Verify Android work with `./gradlew lint`, `./gradlew testDebugUnitTest`, and `./gradlew assembleDebug` unless the target repo lacks the task or the user narrows the scope.
6. After significant shell changes, verify on an emulator or real device when available: main screens, push reception, deep link entry, and permission flows.
7. Never create a new ADR from the maintenance track — new ADRs originate from the planning track only. Maintenance verifies conformance via the shared methodology core: `hb-shared maintenance convention-check` (file: `SHARED/commands/maintenance/convention-check.md` in the dev-harness repo).
8. Never modify the sibling iOS repository (ios-buccl) from this harness. Record sibling-platform impact in `parity-proposal.md` and switch to `hb-ios` for iOS work. Every `INDEX.md` records whether sibling-platform (iOS) follow-up is needed.

## Track Selection

- Use `planning` when the user is deciding WebView architecture, bridge contract direction, push or deep link structure, permission policy, or release strategy.
- Use `feature` when adding a new bridge function, push category, deep link route, permission flow, or WebView shell capability.
- Use `maintenance` when fixing a bug, crash, push delivery issue, deep link mismatch, cookie/session sync issue, dependency problem, or refactor.
- Use `hotfix` only for very small, clearly scoped fixes with minimal blast radius.
- Escalate to `deep` when the change touches the bridge contract, cookie/session sync, manifest-wide permissions, multiple intent-filters, or release/signing configuration.
