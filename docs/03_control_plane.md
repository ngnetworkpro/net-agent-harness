# Control plane responsibilities

The control plane is authoritative for workflow state, target resolution, and stage gating.

## Deterministic responsibilities

1. Route requests to the correct domain, or fail safely.
2. Resolve target devices from inventory before rendering.
3. Decide exactly one plan outcome: `apply`, `no_op`, or `blocked`.
4. Enforce stage order (`route` → `plan` → `render` → `execute` → `review`).
5. Persist durable artifacts and run history for auditability.

## Safety and security controls

The control plane must enforce:

- no render or execute for `no_op` or `blocked` plans
- bounded scope for any backend operation
- approval requirements before execution
- strict artifact/run identifier validation to prevent unsafe file-path handling
- schema validation for persisted artifacts to reject unknown or malformed fields

## Agent and orchestration boundary

Agents can interpret intent and generate structured outputs, but orchestration remains authoritative for:

- resolved targets
- plan decision and diff gating
- backend selection and fallback ordering
- artifact persistence and status transitions

This separation keeps safety-critical logic in deterministic Python rather than prompt behavior.

## Evidence requirements

For every run, the control plane should preserve:

- stage transitions
- artifact revisions
- validation findings and decision rationale
- final run status and closure summary
