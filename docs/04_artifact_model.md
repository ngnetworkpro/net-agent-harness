# Artifact model

The artifact-first pattern becomes valuable in networking because changes must be reviewable and auditable.
Ollama’s structured outputs and Pydantic-style schemas are a strong match for these machine-readable records.

## Core artifacts

In the current harness flow:

- change_request.json
- config_render.json
- validation_report.json
- execution_plan.json
- run_summary.json

## Artifact expectations

- `change_request.json` is the durable post-plan artifact and includes authoritative `resolved_targets`.
- `plan_decision` is written by orchestration, not trusted directly from LLM output.
- `config_render.json` is produced only when the decision is `apply`.
- artifacts include lineage metadata:
  - `parent_artifact_id`: upstream artifact id
  - `child_artifact_ids`: downstream artifact ids
- artifact schemas are strict and reject unknown fields to reduce silent drift.

## Artifact lineage graph

The change workflow lineage is:

`ChangeRequest -> ConfigRender -> ValidationReport -> ExecutionPlan`

ExecutionPlan is marked `ready` only when validation approves execution. It is marked
`blocked` when validation fails/warns or if upstream artifacts are missing/failed.
