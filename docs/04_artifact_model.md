# Artifact model

The artifact-first pattern becomes valuable in networking because changes must be reviewable and auditable.
Ollama’s structured outputs and Pydantic-style schemas are a strong match for these machine-readable records.

## Core artifacts

In the current harness flow:

- change_request.json
- config_render.json
- validation_report.json
- run_summary.json

## Artifact expectations

- `change_request.json` is the durable post-plan artifact and includes authoritative `resolved_targets`.
- `plan_decision` is written by orchestration, not trusted directly from LLM output.
- `config_render.json` is produced only when the decision is `apply`.
- artifact schemas are strict and reject unknown fields to reduce silent drift.
