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
## Intent artifacts

Intent artifacts sit above `ChangeRequest` in the artifact hierarchy. They are
intended for workflows that span more than a single device change — for example,
a site-wide VLAN rollout, a topology re-addressing, an IPAM allocation, or a
device provisioning batch. A single intent artifact can reference multiple child
`ChangeRequest`, `ConfigRender`, and `ExecutionPlan` artifacts.

### Available intent types

| Model | Use case |
|---|---|
| `SiteIntent` | Site-scoped change across many devices |
| `TopologyIntent` | Network-wide topology change |
| `IPAMIntent` | IP address management workflow |
| `ProvisioningIntent` | Device or service provisioning batch |

### Shared intent fields

All intent models carry these fields:

| Field | Type | Description |
|---|---|---|
| `meta` | `ArtifactMeta` | Run ID, artifact ID, version, created_at, created_by |
| `scope` | `ScopeRef` | Sites, devices, regions, or roles in scope |
| `summary` | `str` | Human-readable description of the intent |
| `assumptions` | `list[str]` | Assumptions made when formulating this intent |
| `dependencies` | `list[str]` | Other changes or conditions this intent depends on |
| `desired_state` | `dict` | High-level desired network state |
| `constraints` | `list[str]` | Constraints that must be respected |
| `approval_required` | `bool` | Whether explicit approval is required before execution |
| `approval_notes` | `str | None` | Who or what must approve; approval criteria |
| `status` | `IntentStatus` | Lifecycle status: draft, approved, in_progress, completed, blocked, cancelled |
| `child_artifacts` | `list[ArtifactRef]` | References to child ChangeRequest, ConfigRender, ExecutionPlan artifacts |

### Artifact references

`ArtifactRef` ties an intent to its child artifacts:

```json
{
  "artifact_id": "change-request-run-abc",
  "artifact_type": "change_request",
  "run_id": "run-abc",
  "description": "VLAN 300 on sw1"
}
```

`artifact_type` uses the canonical artifact names (`change_request`,
`config_render`, `execution_plan`, `validation_report`).
