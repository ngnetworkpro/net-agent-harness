# Architecture

This repository uses an artifact-first, staged architecture with deterministic orchestration.

## Canonical stage order

1. `route`
2. `plan`
3. `render`
4. `execute`
5. `review`

Stages are intentionally separated; later stages must not reinterpret earlier decisions.

## Current active behavior

- `route` and `plan` are active and deterministic where possible.
- `render` is active only when plan decision is `apply`.
- `execute` remains disabled by default in this prototype.
- `review` is represented by post-render validation artifacts and run summaries.

## Ownership boundaries

### Orchestration (authoritative)

- Domain routing
- Inventory-backed target resolution
- Plan decision gating (`apply` / `no_op` / `blocked`)
- Stage progression and artifact persistence
- Safety controls (for example, path validation for run/artifact identifiers)

### LLM-backed agents (supporting)

- Intent interpretation and change planning fields
- Vendor-aware render content generation
- Validation reasoning and findings generation

Agent outputs are provisional until orchestration validates and persists durable artifacts.

## Render/execute safety gates

- Render consumes approved plan artifacts; it does not decide whether change is needed.
- Render is skipped for `no_op` and `blocked`.
- Execute must not run unless decision is `apply` and policy/approval gates pass.

## Data and artifact flow

Typical flow in this repository:

`intent` → `change_request.json` → `config_render.json` → `validation_report.json` → `run_summary.json`
