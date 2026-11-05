# net-agent-harness

Personal lab project for a network-engineering agent harness focused on safe, structured change planning.

## Project Goal

Build a model-backed harness that can take a plain-English network change request and walk it through a structured, staged workflow — `route` → `plan` → `render` → `execute` → `review` — without ever touching live infrastructure by default. The goal is to prove the harness shape, typed artifact contracts, and model workflow in a safe prototype before any real network systems are introduced.

The longer-term vision is a harness that supports network-engineering workflows such as change planning, inventory/topology discovery, config rendering, validation and compliance checks, incident summarization, and (much later) tightly controlled execution. The current version starts with one vertical slice so each layer can be tested end to end before the system grows more complex.

## Tech Stack

| Layer                   | Technology                                                                                                                    |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Language                | Python 3.11+                                                                                                                  |
| Agent framework         | [PydanticAI](https://docs.pydantic.dev/latest/concepts/pydantic_ai/)                                                          |
| Data validation         | [Pydantic v2](https://docs.pydantic.dev/) / [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) |
| Model providers         | [Ollama](https://ollama.com/) (default: `qwen3.5:9b`) · NVIDIA API · OpenAI                                                   |
| CLI                     | [Typer](https://typer.tiangolo.com/) + [Rich](https://rich.readthedocs.io/)                                                   |
| Optional inventory      | [NetBox](https://netboxlabs.com/) (read-only REST adapter)                                                                    |
| Package management      | [uv](https://github.com/astral-sh/uv)                                                                                         |
| Testing                 | [pytest](https://pytest.org/) + pytest-cov                                                                                    |
| Linting / type checking | [Ruff](https://docs.astral.sh/ruff/) + [mypy](https://mypy-lang.org/)                                                         |

## Current scope

The pipeline currently handles end-to-end VLAN change planning and rendering:

- Accepts a plain-English network change request
- Deterministically routes the request to a network domain (`vlan`, `acl`, `routing`, `wireless`)
- Runs a `change_planner` agent that produces a structured `PlannedChange` with scope, risk, assumptions, and a `desired_state`
- Resolves concrete target devices from inventory (mock or NetBox) in deterministic Python — not from LLM output
- Evaluates whether the desired state is already satisfied (`no_op`), requires changes (`apply`), or cannot proceed safely (`blocked`), producing a structured `PlanDecision` with per-device `DeviceChange` diffs (`VlanChangeOperation`, `InterfaceChangeOperation`, `SviChangeOperation`)
- Supports VLAN creation (`ensure_present`, defaulting unnamed VLANs to `str(vlan_id)`) and removal (`ensure_absent`), access port assignments (`set_access_vlan`), trunk updates (`set_trunk`, `set_native_vlan`, `update_trunk_allowed_vlans`), and Layer 3 SVI creation/removal (`ensure_present` / `ensure_absent`)
- Renders a candidate `ConfigRender` artifact from an approved change request using either `direct_api` (API primary + vendor CLI fallback) or source-backed `terraform` HCL rendering
- Validates the rendered candidate into a `ValidationReport` artifact and generates an `ExecutionPlan` artifact
- Keeps execution disabled by default and treats validation/review as the final active stage in this prototype
- Supports read-only direct-answer queries for topology and IPAM capabilities

## Recent updates

Recent architecture and safety updates now reflected in this README:

- Completed end-to-end VLAN operations across evaluation, render payload construction, API primary strategies (Juniper Mist, Cisco Meraki), and CLI fallback strategies (JunOS, Meraki, Cisco IOS, Cisco NX-OS): VLAN creation/removal, trunk native VLAN and allowed VLAN list management, and SVI creation/removal
- Defaulted unnamed VLANs (`name=""` or omitted) to the stringified VLAN ID (`str(vlan_id)`) during desired-state normalization and evaluation so Mist VLAN creations proceed cleanly
- Hardened artifact and model contracts with stricter schema validation (`extra="forbid"` on key models)
- Tightened typed modeling for requested desired state, VLAN spec, and port spec fields
- Added path traversal protection for run/artifact storage identifiers
- Improved inventory resolution flow and NetBox integration validation behavior
- Strengthened render/planning boundaries so deterministic orchestration owns routing, target resolution, and plan decision gating

## Architecture

The repo follows an artifact-first, staged pipeline:

- `models/` defines the schemas the system relies on
- `glossaries/` contains modular YAML files (core terms + domain-specific) that ground the agents
- `agents/` contains focused agent implementations; a shared `agent_factory` wires agents to the configured model provider
- `tools/` contains narrow, typed functions the agents may call
- `adapters/` isolates integrations such as Ollama or optional NetBox/Nornir/NAPALM clients
- `orchestration/` handles routing, domain context loading, intent evaluation, and stage progression
- `services/` handles run and artifact persistence, progress reporting, and tracing
- `policies/` is reserved for approvals, scope checks, and future guardrails

This layout keeps orchestration and policy in application code rather than hiding critical behavior inside prompts alone.

## Documentation map

- `docs/01_architecture.md` — current staged architecture and stage ownership
- `docs/02_lifecycle.md` — lifecycle flow and stage gates
- `docs/03_control_plane.md` — deterministic orchestration and safety responsibilities
- `docs/04_artifact_model.md` — artifact contracts and authoritative fields
- `docs/05_tool_layer.md` — tool-layer boundaries and backend labeling
- `docs/06_permissions_model.md` — permissions and approval expectations

## Repository layout

```text
net-agent-harness/
├── pyproject.toml
├── README.md
├── .env.example
├── src/
│   └── net_agent_harness/
│       ├── main.py
│       ├── config.py
│       ├── agents/
│       │   ├── agent_factory.py
│       │   ├── change_planner.py
│       │   ├── config_render_agent.py
│       │   ├── incident_agent.py
│       │   ├── inventory_agent.py
│       │   └── validation_agent.py
│       ├── adapters/
│       ├── glossaries/
│       │   ├── core_terms.yaml
│       │   └── domains/
│       ├── models/
│       ├── orchestration/
│       ├── policies/
│       ├── services/
│       ├── tools/
│       └── prompts/
├── docs/
└── tests/
```

## Requirements

Recommended local environment:

- Python 3.11+
- A supported model provider: Ollama running locally, an NVIDIA API key, or an OpenAI API key

The project defaults to Ollama with `qwen3.5:9b`. If `NET_AGENT_NVIDIA_API_KEY` is set, the NVIDIA provider is selected automatically unless `NET_AGENT_PROVIDER` overrides it.

## Getting started

### 1. Clone the repository

```bash
git clone https://github.com/ngnetworkpro/net-agent-harness.git
cd net-agent-harness
```

### 2. Create a virtual environment

On macOS or Linux:

```bash
uv venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
uv venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
uv sync --extras dev
```

This installs the package in editable mode, plus the optional development tools declared in `pyproject.toml`.

### 4. Configure environment

Copy `.env.example` to `.env` and set the values relevant to your provider:

```bash
cp .env.example .env
```

Key settings:

| Variable | Purpose | Default |
|---|---|---|
| `NET_AGENT_PROVIDER` | `ollama`, `nvidia`, or `openai` | auto-selected |
| `NET_AGENT_OLLAMA_MODEL` | Model name when using Ollama | `qwen3.5:9b` |
| `NET_AGENT_NVIDIA_API_KEY` | API key for NVIDIA provider | — |
| `NET_AGENT_NVIDIA_MODEL` | Model name when using NVIDIA | `minimaxai/minimax-m3` |
| `NET_AGENT_OPENAI_API_KEY` | API key for OpenAI provider | — |
| `NET_AGENT_OPENAI_MODEL` | Model name when using OpenAI | `gpt-4o-mini` |
| `NET_AGENT_INVENTORY_SOURCE` | `mock` or `netbox` | `mock` |

### 5. Start your model provider

**Ollama (local):**

```bash
ollama pull qwen3.5:9b
```

**NVIDIA API:** set `NET_AGENT_NVIDIA_API_KEY` in your `.env`; no local service required.

**OpenAI:** set `NET_AGENT_PROVIDER=openai` and `NET_AGENT_OPENAI_API_KEY` in your `.env`.

### 6. Run the first command

```bash
net-agent plan "Add VLAN 220 to access switch sw1 at HQ"
```

The `plan` command:
1. Routes the request to the `vlan` domain
2. Calls the `change_planner` agent to extract scope, intent, risk, and desired state
3. Resolves concrete target devices from inventory
4. Evaluates whether the desired state already exists, producing a `PlanDecision` of `apply`, `no_op`, or `blocked` with a structured per-device `DeviceChange` diff
5. Writes `runs/<run_id>/change_request.json` and updates `runs/<run_id>/run.json`

You can then render a candidate config artifact from that saved plan:

```bash
net-agent render runs/<run_id>/change_request.json
```

That command reads the saved `ChangeRequest`, validates it, and writes `runs/<run_id>/config_render.json`. Render is skipped if `plan_decision` is `no_op` or `blocked`.

You can then validate the rendered candidate:

```bash
net-agent validate runs/<run_id>/config_render.json
```

That writes `runs/<run_id>/validation_report.json` with a structured status, checks run, findings, and an `approved_for_execution` flag.

You can also run the post-plan stages together:

```bash
net-agent run stages runs/<run_id>/change_request.json
```

That command runs the render and validation stages in sequence and writes a `run_summary.json` artifact for the run.

For read-only questions that should not enter the change workflow:

```bash
net-agent ask "What is connected to sw1?"
net-agent topology "What is connected to sw1?"
net-agent ipam "Is 10.10.21.0/24 assigned?"
```

To inspect a run directory:

```bash
net-agent show-run <run_id>
```

Run metadata is updated stage-by-stage in `run.json`, including `current_stage`, overall `status`, `updated_at`, and a `stage_history` array.

## Example output shape

A successful planning run produces a `ChangeRequest` artifact shaped like this:

```json
{
  "meta": {
    "run_id": "run-1234abcd",
    "artifact_id": "change-request-run-1234abcd",
    "version": 1,
    "created_at": "2026-05-01T17:00:00Z",
    "created_by": "local-user"
  },
  "domain": "vlan",
  "scope": {
    "site": "HQ",
    "region": null,
    "device_names": ["sw1"],
    "device_roles": ["access-switch"]
  },
  "target_scope": "device",
  "resolved_targets": [
    {
      "name": "sw1",
      "site": "HQ",
      "role": "access-switch",
      "platform": "mist",
      "primary_ip": "10.0.0.10/24",
      "vendor": "juniper"
    }
  ],
  "requested_change": {
    "summary": "Add VLAN 220 to sw1 at HQ",
    "business_reason": null,
    "requested_by": "local-user",
    "maintenance_window": null,
    "intent": "Add VLAN 220 to access switch sw1 at HQ",
    "constraints": [],
    "desired_state": {
      "operations": [
        {
          "object_type": "vlan",
          "operation": "ensure_present",
          "attributes": { "vlan_id": 220, "name": "220" }
        }
      ]
    }
  },
  "risk": "low",
  "assumptions": ["sw1 is the correct target device"],
  "dependencies": [],
  "rollback_plan": {
    "summary": "Rollback 1 operation(s) across 1 device(s): sw1.",
    "trigger_conditions": ["Validation or post-change connectivity checks fail."],
    "rollback_steps": ["[sw1] Remove VLAN 220 from sw1."],
    "structured_rollback_steps": [
      {
        "order": 1,
        "object_type": "vlan",
        "operation": "remove",
        "target_device": "sw1",
        "attributes": { "vlan_id": 220 },
        "description": "Remove VLAN 220 from sw1."
      }
    ]
  },
  "plan_decision": {
    "decision": "apply",
    "reason": "VLAN 220 must be created on sw1.",
    "diff": [
      {
        "device": "sw1",
        "domain": "vlan",
        "changes": {
          "operations": [
            {
              "change_type": "vlan",
              "op": "create",
              "vlan_id": 220,
              "name": "220",
              "status": "apply",
              "reason": "VLAN 220 does not exist on sw1."
            }
          ]
        }
      }
    ]
  }
}
```

The exact values will vary by model, but the top-level schema remains stable because the agent uses a typed output model. The `plan_decision` is always set deterministically by the orchestration layer, not by the LLM.

## Key source files

- `main.py` — CLI entry point via Typer; orchestrates the plan/render/validate flow
- `orchestration/read_only_answer.py` — deterministic direct-answer path for read-only capabilities
- `agents/agent_factory.py` — resolves the configured model provider (Ollama/NVIDIA/OpenAI) and builds PydanticAI agents
- `agents/change_planner.py` — LLM agent that extracts scope, intent, risk, and desired state from a natural-language request
- `agents/config_render_agent.py` — PydanticAI render agent with domain-specific YAML context loading and snippet validation
- `orchestration/intent_router.py` — deterministically routes plain English to a network domain (`vlan`, `acl`, `routing`, `wireless`)
- `orchestration/domain_loader.py` — merges core terms and domain-specific YAML glossaries into a unified agent context
- `orchestration/desired_state_normalizer.py` — normalizes planner `desired_state` into structured operations and defaults unnamed VLANs to `str(vlan_id)`
- `orchestration/build_render.py` — translates an approved `ChangeRequest` diff into a typed `RenderRequest` (`VlanRenderPayload`)
- `orchestration/rollback_builder.py` — deterministically constructs ordered `structured_rollback_steps` from the forward diff
- `orchestration/platform_constraints.py` — validates planned diffs against platform-specific constraints
- `orchestration/coordinator.py` — `StageCoordinator` that sequences render, validate, and execution plan stages and produces a `run_summary`
- `orchestration/stream_utils.py` — spinner utility for long-running agent calls
- `tools/inventory_tools.py` — `resolve_from_scope` resolves target devices from inventory authoritatively
- `tools/topology_tools.py` — deterministic topology lookups from inventory snapshots
- `tools/ipam_tools.py` — read-only IPAM lookups backed by adapter data
- `tools/evaluation.py` — `evaluate_intent_state` evaluates VLAN, trunk, and SVI intent against current device state to produce a `PlanDecision`
- `tools/vlan_state.py` — pure helpers (`vlan_exists`, `trunk_allows_vlan`, `access_vlan_matches`, `compute_vlan_diff`)
- `tools/validation_tools.py` — validates a `ConfigRender` into a `ValidationReport` (including consistency, candidate headers, and optional Terraform preflight checks)
- `adapters/backends/` — backend adapters and vendor strategies (`direct_api.py`, `terraform.py`, `api_operations.py`, `cli_snippets.py`)
- `adapters/mock_inventory_adapter.py` — synthetic inventory snapshot for local development
- `adapters/netbox_adapter.py` — optional read-only REST adapter (enabled via `NET_AGENT_INVENTORY_SOURCE=netbox`)
- `config.py` — loads configuration from environment variables and `.env`
- `services/run_store.py` — persists and updates run metadata including stage history
- `services/artifact_store.py` — persists typed Pydantic models as JSON artifacts
- `services/run_progress_reporter.py` — updates run state and emits progress messages
- `models/` — all typed artifact contracts (`ChangeRequest`, `PlannedChange`, `PlanDecision`, `ConfigRender`, `ValidationReport`, `ExecutionPlan`, `InventorySnapshot`)

## Running tests

```bash
ruff check .
python -m pytest -q
```

## Safety boundaries

The current project stays inside these boundaries:

- no production credentials,
- no live device access,
- no config push capability,
- no autonomous remediation,
- no broad shell execution,
- no company-sensitive data in prompts or fixtures.

Network changes carry operational risk. The value of this prototype is proving workflow correctness, not autonomy.

## Recommended next steps

A sensible build order for the next few chunks:

1. Extend `evaluate_intent_state` and deterministic backend adapters to support ACL, routing, and wireless domains beyond VLAN
2. Expand NetBox inventory and IPAM read-only context integration for multi-device and site-wide changes
3. Add artifact indexes or human-readable markdown summaries per run beyond JSON files alone
4. Add richer policy and approval hooks for multi-stage workflows
5. Keep live device execution disabled until all upstream planning, rendering, and validation stages are thoroughly battle-tested

## Troubleshooting

### The CLI says `net-agent` is not found

Make sure the virtual environment is activated and that `uv sync --extras dev` completed successfully.

### The model call fails

**Ollama:** Check that the Ollama service is running and that the configured model exists locally. Run `ollama list` and confirm the model name matches `NET_AGENT_OLLAMA_MODEL`.

**NVIDIA:** Confirm `NET_AGENT_NVIDIA_API_KEY` is set and valid. The provider auto-selects NVIDIA when the key is present.

### The output is invalid or inconsistent

Smaller local models may vary in quality. This is expected in the prototype phase. The typed schema helps because invalid output is caught at the application boundary instead of silently flowing through the system.

### The plan is blocked with "unsupported evaluation domain"

Only the `vlan` domain has a live `evaluate_intent_state` implementation. Requests routed to `acl`, `routing`, or `wireless` will currently produce a `blocked` decision at the evaluation step.

### The agent invents devices

That is one reason inventory-grounded target resolution exists. Tighten prompts and rely on tool-grounded data rather than free-form assumptions in future iterations.

## Notes on future integrations

The repository includes adapter modules for NetBox (read-only REST), Nornir, and NAPALM. NetBox is the only live-integration adapter currently wired up. The safer sequence is to keep using mock data first, then introduce read-only integrations, then later consider any execution path behind explicit approvals and scope controls.

## Development philosophy

The project is being built in small chunks on purpose:

- keep each step easy to review,
- keep each change small enough to survive interruptions,
- and validate one layer at a time.

That approach is especially useful for agent systems because it separates model quality problems from architecture problems early.
