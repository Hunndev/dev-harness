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
7. Playwright E2E is a verification lens over both FE modes, not a third mode, and applies to web FE only. Apply it when a change crosses a multi-screen user flow (routing, auth, core-task completion) or a mixed task changes screen and data flow together; purely local single-component changes are N/A. The FE product repository owns all Playwright dependencies, configs, and specs — the harness only decides when to reuse existing specs (default) or add new ones (only for routes/flows/state transitions the existing specs do not cover; adding a spec happens in an implementation step, never in the verification fork — on a spec gap found during verification, loop back to the implementation step, which authors and verifies the new spec as an allowed exception to the TDD Red scope limit). When setup or changes are required by a user-approved FE product implementation, the hb-fe implementation step may create or modify those dependencies, configs, and specs inside the FE product repo. Classify the run environment as `local-mock` (default), `local-dev-api`, or `actual-dev`. Before creating any browser context, logging in, or performing any mutation, resolve and record the browser baseURL and the API/Chat origins in `e2e-check.md`; only local origins or an explicitly user-approved dev allowlist are permitted — a production or unknown host aborts the run (fail-closed). Always run with `user-inst` isolated contexts: when a scenario involves both accounts, create one browser context for the `user` account and a separate browser context for the `inst` account, each created independently, with cookies, localStorage, sessionStorage, and auth state isolated between the two contexts; single-role scenarios create only the context(s) for the accounts they need, under the same isolation rules; both are dev-only test accounts — never real user sessions or data. On `actual-dev`, only minimal mutations by the dev test accounts (`user`/`inst`) are allowed, each mutation tagged with a unique run ID (e.g., test chat messages for the user-approved user-inst realtime chat E2E scenario), with creation scope and cleanup status recorded in `e2e-check.md`. High-risk or destructive changes (reservations, blocks, reports, payments, tickets, editing/deleting existing data, direct DB manipulation, secret changes) are forbidden without explicit user approval — this gate targets real data and infrastructure, so mock-only flows on `local-mock` are exempt; running against production is forbidden outright. Record per-scenario verdicts as `정상 / 비정상 / 미확인` in `e2e-check.md` with one screenshot per scenario — copy **every** scenario's screenshot into `.harness/artifacts/{track}/{identifier}/e2e-evidence/` for preservation; video or trace is additionally **required** for `비정상`/`미확인` scenarios and **only those runs are preserved** (video/trace for `정상` is optional and not preserved by default); `e2e-check.md` must record **only preserved-copy paths that stay valid after worktree cleanup** (if a scenario could not run at all, record the failure log and an explicit "증거 없음" reason instead of screenshot/video/trace — the video/trace requirement is waived for that scenario); `e2e-check.md` also records the run's **HEAD SHA and a content fingerprint of the E2E-target source/spec files** — a previous run may be reused only when the current HEAD SHA, fingerprint, environment, and scenario set are **all identical**, otherwise re-run; on `actual-dev`, evidence and reuse are additionally bound to the **deployment identity** — the served FE bundle URL and content digest, the API/Chat deployment identity when exposed, and a fingerprint of behavior-affecting config/fixtures (secrets excluded) — and if that identity cannot be proven, actual-dev results must **not** be reused; maintenance-track work under this lens runs it through the conditional E2E item in M6 (auto) / M8 (deep), producing the same `e2e-check.md`; the final verify verdict stays `PASS | FAIL` — any `비정상` forces FAIL, and while any `미확인` remains the verdict cannot be PASS: record FAIL with the reason "미확인 잔존" and ask the user. Full definition: the "E2E 검증 렌즈 (Playwright)" section in `CLAUDE.md`.
8. Never create a new ADR from the maintenance track — new ADRs originate from the planning track only. Maintenance verifies conformance via the shared methodology core: `hb-shared maintenance convention-check` (file: `SHARED/commands/maintenance/convention-check.md` in the dev-harness repo).

## Track Selection

- Use `planning` when the user is deciding architecture, routing, state management, design system rules, or API contract direction.
- Use `feature` when adding a new screen, component, route, flow, or user-visible capability.
- Use `maintenance` when fixing a bug, visual regression, responsive issue, performance issue, dependency problem, or refactor.
- Use `hotfix` only for very small, clearly scoped fixes with minimal blast radius.
- Escalate to `deep` when the change touches shared components, state architecture, routing, design system rules, mobile shell behavior, or multiple routes.
