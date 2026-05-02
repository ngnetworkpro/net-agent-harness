# AGENTS.md

## Project purpose

This repository implements a network change planning and execution pipeline.

The system is designed to turn natural-language change requests into safe, reviewable, vendor-specific network changes. The architecture is intentionally staged and should remain deterministic where possible.

Primary goals:

- Preserve safety and traceability.
- Prefer deterministic orchestration and validation logic in Python.
- Use LLM reasoning for interpretation and planning, not for workflow control unless clearly justified.
- Avoid inventing devices, interfaces, VLANs, sites, or current state.

## Pipeline stages

The pipeline is staged and should remain:

1. route
2. plan
3. render
4. execute
5. review

Do not collapse these stages unless explicitly asked to redesign the architecture.

### Stage responsibilities

#### route

- Determine the relevant network domain for the request, such as vlan, acl, routing, wireless, or vpn.
- Prefer deterministic Python routing first.
- Unknown or low-confidence routing must fail safely.
- Do not silently fall through to an arbitrary domain.

#### plan

- Interpret the request within the selected domain.
- Extract scope, requested change, assumptions, dependencies, and rollback guidance.
- Resolve current state and target devices before moving forward.
- Decide exactly one of:
  - `apply`
  - `no_op`
  - `blocked`
- `no_op` means the desired state already exists.
- `blocked` means the request cannot proceed safely because of ambiguity, missing data, unresolved targets, or policy constraints.

#### render

- Translate an approved diff into vendor-specific API operations or CLI commands.
- Render does not decide whether a change is needed.
- Render must consume an approved planned change or diff, not reinterpret the original natural-language request.
- Prefer API-driven rendering for supported platforms.
- Keep CLI/SSH rendering as fallback and for completeness.

#### execute

- Apply rendered operations.
- Respect approval gates and dry-run behavior.
- Do not execute if the plan decision is not `apply`.

#### review

- Compare expected and observed results.
- Record success, failure, drift, and rollback conditions.
- Use review to improve future planning, validation, and rendering behavior.

## Domain modeling

Keep domain concepts modular.

Rules:

- `core_terms` must remain domain-neutral.
- VLAN, routing, ACL, wireless, VPN, and similar concepts belong in separate domain context files.
- Load only the relevant domain context for a request.
- Prefer structured outputs, typed models, and explicit schemas.

Do not move domain-specific concepts into orchestration unless there is a strong reason.

## Routing rules

- Prefer a Python router over a separate routing agent unless real usage proves it insufficient.
- Start simple and deterministic.
- Upgrade routing only when ambiguity or misclassification justifies it.
- A future hybrid router is acceptable, but routing should not become agentic by default.

## Planning rules

Planning is the authoritative stage for deciding whether a change is required.

Rules:

- Plan must compare desired state against current state.
- Plan must resolve targets from inventory before producing a durable change artifact.
- Target resolution should be authoritative in orchestration, not trusted solely from LLM output.
- If no targets can be resolved safely, the result must be `blocked`.
- If the requested state already exists, the result must be `no_op`.
- Render should only run for `apply`.

When possible, planning should produce a structured diff that downstream stages can consume directly.

## Inventory and target resolution

- Inventory-backed target resolution is required before rendering.
- Prefer deterministic Python resolution in orchestration.
- LLM tools may inspect inventory during planning, but the final `resolved_targets` written to artifacts must come from authoritative Python resolution.
- Do not assume a site, device, interface, VLAN, or role exists unless inventory or current-state lookup confirms it.
- Missing targets are a blocking condition, not a warning.

## Vendor preferences

Current design preferences:

- Prefer API-driven changes for Juniper Mist and Cisco Meraki.
- Keep CLI/SSH rendering available as fallback and for completeness.
- Use `allowed_vlans_mode="all"` internally instead of expanding all VLANs numerically.
- `native_vlan` may be optional in inventory models, but logic may use an effective native VLAN where needed.

## Modeling rules

Prefer explicit types and structured models.

Guidelines:

- Use Pydantic models or dataclasses for shared artifacts and state.
- Keep artifacts stable and durable.
- Treat planner output as provisional where appropriate.
- Treat orchestration-produced artifacts as authoritative.

In particular:

- `PlannedChange` is planner output.
- `ChangeRequest` is the durable artifact after orchestration validation.
- `resolved_targets` in `ChangeRequest` should be set by deterministic inventory resolution.

## Implementation style

- Prefer incremental refactors over large rewrites.
- Preserve the existing architecture unless explicitly asked to redesign it.
- Keep functions focused and testable.
- Reuse shared normalization and filtering logic rather than duplicating it.
- Prefer predictable control flow over clever abstractions.
- Call out ambiguity and missing information explicitly.

## Safety rules

- Fail safely on unknown intent, unresolved targets, or ambiguous scope.
- Do not fabricate inventory matches.
- Do not fabricate current state.
- Do not treat empty resolution results as success.
- Do not let render or execute reinterpret blocked or no-op plans.

## Testing expectations

Recommend or add tests when changing:

- routing behavior,
- planning logic,
- target resolution,
- inventory normalization,
- rendering behavior,
- plan decision logic.

At minimum, cover:

- successful target resolution,
- unresolved target blocking,
- no-op planning behavior,
- render rejection for non-apply plans,
- inventory normalization for mock and real adapters.

## Collaboration guidance for AI assistants

When helping in this repository:

- First identify which stage the change belongs to: route, plan, render, execute, or review.
- Preserve stage ownership boundaries.
- Prefer deterministic Python for orchestration and validation tasks.
- Use LLM reasoning for interpretation, extraction, and planning support.
- Ask for missing model definitions or sample data before guessing.
- Suggest the smallest safe change that solves the problem.
