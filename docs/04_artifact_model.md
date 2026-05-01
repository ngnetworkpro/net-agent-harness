# Artifact model

The artifact-first pattern becomes valuable in networking because changes must be reviewable and auditable.
Ollama’s structured outputs and Pydantic-style schemas are a strong match for these machine-readable records.

## Core artifacts:

- change_request.json
- inventory.json
- topology_snapshot.json
- intended_state.json
- execution_plan.json
- config_render.json
- validation_report.json
- rollback_plan.json
- incident_summary.json
- closure_report.json
