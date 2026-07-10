---
name: hb-ios
description: Use when working in the BUCCL iOS WebView app repository (ios-buccl) with the dev-harness flow, including planning, feature work, maintenance, WebView shell changes, bridge contract work, device checks, permission checks, release checks, TDD, and review artifacts.
---

# BUCCL iOS Harness

Use this skill when the user asks for `hb-ios`, iOS pipeline, iOS harness, WebView shell or bridge work through the harness, or a workflow similar to `dev-harness` for the BUCCL iOS WebView app (ios-buccl).

## Source Of Truth

Read `CLAUDE.md` first, then the matching command document under `commands/`. If you are operating from the dev-harness repository root instead of the iOS plugin root, prefix these paths with `iOS/`.

- Planning: `commands/planning/auto.md` or `commands/planning/deep.md`
- Feature: `commands/feature/auto.md` or `commands/feature/deep.md`
- Maintenance: `commands/maintenance/hotfix.md`, `commands/maintenance/auto.md`, or `commands/maintenance/deep.md`
- Shared protocols: `commands/shared/tdd.md`, `commands/shared/verify.md`, `commands/shared/update-docs.md`

## Command Mapping

Codex does not execute Claude slash commands directly. Treat these phrases as intent aliases:

- `hb-ios planning auto` or `/hb-ios:planning:auto`
- `hb-ios planning deep` or `/hb-ios:planning:deep`
- `hb-ios feature auto` or `/hb-ios:feature:auto`
- `hb-ios feature deep` or `/hb-ios:feature:deep`
- `hb-ios maintenance hotfix` or `/hb-ios:maintenance:hotfix`
- `hb-ios maintenance auto` or `/hb-ios:maintenance:auto`
- `hb-ios maintenance deep` or `/hb-ios:maintenance:deep`
- `hb-ios shared update-docs` or `/hb-ios:shared:update-docs`

## Codex Operating Rules

1. Keep the same artifact paths as the Claude harness: `.harness/artifacts/{track}/{identifier}/`.
2. Use `.harness/docs/code-convention.yaml`, `.harness/docs/adr.yaml`, `.harness/docs/architecture.yaml`, `.harness/docs/module-registry.yaml`, and `.harness/docs/bridge-contract.yaml` as the project truth when present.
3. For feature and maintenance work, follow the Red-Green-Refactor protocol in `commands/shared/tdd.md`.
4. iOS work splits into two modes — classify the task at the start. **Shell feature** (WebView settings, push, deep link, permissions, cookie/session sync, store release) produces `design-intent.md`, `device-check.md`, `permission-check.md`, `release-check.md`. **Bridge contract** (web-to-native API via `WebViewBridge.swift`) produces `bridge-check.md` covering function signatures, message formats, error handling, and sibling-platform (AOS) contract parity, plus an update to `.harness/docs/bridge-contract.yaml` (kept identical on both platforms). Mixed work produces both.
5. Verify iOS work with `xcodebuild -scheme bucclapp build`, `xcodebuild -scheme bucclapp test`, and `xcodebuild -scheme bucclapp build` unless the target repo lacks the task or the user narrows the scope.
6. After significant shell changes, verify on an emulator or real device when available: main screens, push reception, deep link entry, and permission flows.
7. Never create a new ADR from the maintenance track — new ADRs originate from the planning track only. Maintenance verifies conformance via the shared methodology core: `hb-shared maintenance convention-check` (file: `SHARED/commands/maintenance/convention-check.md` in the dev-harness repo).
8. Never modify the sibling AOS repository (buccl-aos) from this harness. Record sibling-platform impact in `parity-proposal.md` and switch to `hb-aos` for AOS work. Every `INDEX.md` records whether sibling-platform (AOS) follow-up is needed.

## Track Selection

- Use `planning` when the user is deciding WebView architecture, bridge contract direction, push or deep link structure, permission policy, or release strategy.
- Use `feature` when adding a new bridge function, push category, deep link route, permission flow, or WebView shell capability.
- Use `maintenance` when fixing a bug, crash, push delivery issue, deep link mismatch, cookie/session sync issue, dependency problem, or refactor.
- Use `hotfix` only for very small, clearly scoped fixes with minimal blast radius.
- Escalate to `deep` when the change touches the bridge contract, cookie/session sync, Info.plist-wide permissions, multiple Universal Link·커스텀 스킴s, or release/signing configuration.
