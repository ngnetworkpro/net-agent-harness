# net-agent-harness

Personal lab project for a network-engineering agent harness focused on safe, structured change planning.

This repository is intentionally designed as a **personal prototype first**. The initial goal is to prove the harness shape, artifact contracts, and local-model workflow before connecting to any real network systems. The first version is read-mostly and uses mock inventory data by default.[web:18][web:26][web:55]

## Current scope

The starter version currently does six things:
- Accepts a plain-English network change request
- Converts it into a structured `ChangeRequest` artifact
- Supports a mock inventory lookup tool for grounding
- Supports an optional read-only NetBox-backed inventory adapter
- Renders a candidate `ConfigRender` artifact from a saved change request
- Validates that rendered candidate config into a `ValidationReport` artifact
- Stops before any execution against live infrastructure[web:61][web:44][web:56][web:26]

That keeps the project aligned with a safe prototype path while still exercising the important architecture decisions: typed outputs, tool calling, local model use, and narrow workflow stages.[web:18][web:26][web:55]

## Why this exists

The longer-term idea is a harness that could support network-engineering workflows such as:
- change planning,
- inventory/topology discovery,
- config rendering,
- validation and compliance checks,
- incident summarization,
- and, much later, tightly controlled execution.

The initial repo does **not** attempt all of that yet. It starts with one small vertical slice so the workflow can be tested end to end before the system grows more complex.[web:18][web:82]

## Initial architecture

The repo follows an artifact-first structure:
- `models/` defines the schemas the system relies on
- `agents/` contains focused agent implementations
- `tools/` contains narrow, typed functions the agent may call
- `adapters/` isolates integrations such as Ollama or future NetBox/Nornir/NAPALM clients
- `orchestration/` is reserved for the run coordinator and stage machine
- `policies/` is reserved for approvals, scope checks, and future guardrails[web:18][web:61][web:67]

This layout is intended to keep orchestration and policy in application code rather than hiding critical behavior inside prompts alone.[web:18][web:82]

## Starter contents

The current starter includes:
- `pyproject.toml` with the base dependencies and CLI entry point
- a minimal `change_planner` agent using PydanticAI
- typed models for `ChangeRequest`, `InventorySnapshot`, `ConfigRender`, and `ValidationReport`
- a mock inventory adapter returning a small sample device set
- a CLI command for generating a structured plan artifact
- placeholder packages for future stages and integrations[web:18][web:26][web:61]

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
│       ├── adapters/
│       ├── models/
│       ├── orchestration/
│       ├── policies/
│       ├── services/
│       ├── tools/
│       └── prompts/
├── tests/
├── data/
└── runs/
```

## Requirements

Recommended local environment:
- Python 3.11+
- Ollama installed and running locally
- at least one local model available for structured generation[web:55][web:44]

The starter project currently defaults to `llama3.1:8b` in configuration, but that can be changed later depending on what runs best on your machine.[web:55]

## Getting started

### 1. Extract the project

Unpack the starter archive wherever you keep local projects.

### 2. Create a virtual environment

On macOS or Linux:

```bash
uv venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
uv sync --extras dev
```

This installs the package in editable mode, plus the optional development tools declared in `pyproject.toml`.

### 4. Start Ollama

Make sure Ollama is installed and the local service is running. Ollama supports structured outputs and local model inference, which is why it is a good fit for this prototype.[web:55][web:44]

### 5. Pull a local model

Example:

```bash
ollama pull llama3.1:8b
```

If you want to use a different model, create a local `.env` file from `.env.example` and change `NET_AGENT_OLLAMA_MODEL`. The starter now uses Pydantic Settings to load configuration from environment variables and `.env` automatically.

### 6. Run the first command

```bash
net-agent plan "Add VLAN 220 to access switch sw1 at HQ"
```

If the agent run succeeds, it should print the run ID, the persisted artifact path, and a JSON representation of a `ChangeRequest` artifact. That output is validated against the declared Pydantic model before it is returned, and the run metadata plus artifact are written under `runs/<run_id>/`.[web:26][web:18][web:107]

You can then render a candidate config artifact from that saved plan:

```bash
net-agent render runs/<run_id>/change_request.json
```

That command reads the saved `ChangeRequest`, validates it, and writes `runs/<run_id>/config_render.json`.[web:26][web:56]

You can then validate the rendered candidate:

```bash
net-agent validate runs/<run_id>/config_render.json
```

That writes `runs/<run_id>/validation_report.json` with a structured status, checks run, findings, and an `approved_for_execution` flag.[web:26]

You can also run the post-plan stages together:

```bash
net-agent run stages runs/<run_id>/change_request.json
```

That command runs the render and validation stages in sequence and writes a `run_summary.json` artifact for the run. Typer supports command groups and nested subcommands cleanly, which makes this a good point to introduce a small stage runner.[web:121][web:124]

Run metadata is now also updated stage-by-stage in `run.json`, including `current_stage`, overall `status`, `updated_at`, and a `stage_history` array. That makes each run directory more useful for debugging and later observability work.[web:107][web:111]

## Example output shape

A successful planning run should resemble this shape:

```json
{
  "meta": {
    "run_id": "run-1234abcd",
    "artifact_id": "change-001",
    "version": 1,
    "created_at": "2026-04-22T17:00:00Z",
    "created_by": "change_planner"
  },
  "scope": {
    "site": "HQ",
    "region": null,
    "device_names": ["sw1"],
    "device_roles": ["access-switch"]
  },
  "requested_change": {
    "summary": "Add VLAN 220 to sw1 at HQ",
    "business_reason": null,
    "requested_by": "local-user",
    "maintenance_window": null,
    "intent": "Add VLAN 220 to access switch sw1 at HQ",
    "constraints": []
  },
  "risk": "low",
  "assumptions": ["sw1 is the correct target device"],
  "dependencies": [],
  "rollback_plan": {
    "summary": "Remove VLAN 220 if validation fails",
    "trigger_conditions": ["post-change validation failure"],
    "rollback_steps": ["remove VLAN 220 from the target switch"]
  }
}
```

The exact values will vary by model, but the top-level schema should remain stable because the agent uses a typed output model.[web:26][web:44]

## What the starter actually does

At the moment, the project is intentionally simple:

When `NET_AGENT_INVENTORY_SOURCE=netbox`, inventory lookups go through the adapter interface and call the NetBox device endpoint using query parameters such as `site`, `name`, and `limit`. NetBox documents token auth for the REST API and supports filtering list endpoints via query parameters.[web:143][web:150]

The adapter now also supports read-only device-context expansion by calling the device, interface, and IP address endpoints. In practice, that means the harness can fetch a matched device plus interface and IP context without introducing any write operations.[web:143][web:163]
- `main.py` exposes the CLI via Typer and persists run output
- `change_planner.py` defines the first planning agent
- `config_render_agent.py` reserves the next agent stage for model-backed rendering
- `inventory_tools.py` exposes a mock inventory tool
- `config_tools.py` contains a deterministic stub renderer for candidate config output
- `mock_inventory_adapter.py` returns a tiny synthetic inventory snapshot
- `netbox_adapter.py` provides an optional read-only REST adapter for NetBox-backed inventory lookups
- `inventory_tools.py` can now return either a simple device list or a richer device-context view with interfaces and IP addresses
- `config.py` loads configuration from environment variables and `.env`
- `services/run_store.py` and `services/artifact_store.py` persist run metadata and artifacts
- the models under `models/` define the artifact contracts[web:18][web:61][web:107][web:56]

This is enough to validate the basic local-agent loop:
1. receive a request,
2. call a tool if needed,
3. return a structured `ChangeRequest`,
4. convert that artifact into a candidate `ConfigRender`,
5. validate the render into a structured `ValidationReport`,
6. keep the system safe by avoiding live execution.[web:18][web:26][web:55][web:56]

## Running tests

The starter includes a few light tests for models and mock inventory behavior.

Run them with:

```bash
pytest
```

These tests are intentionally minimal. They exist mainly to confirm that the initial models and adapters load correctly before more behavior is added.

## Safety boundaries for v0

The current project should remain inside these boundaries:
- no production credentials,
- no live device access,
- no config push capability,
- no autonomous remediation,
- no broad shell execution,
- no company-sensitive data in prompts or fixtures.

This is important because network changes carry operational risk, and the value of the first prototype is proving workflow correctness rather than proving autonomy.[web:55][web:67]

## Recommended next steps

A sensible build order for the next few chunks is:
1. Replace the deterministic `config_render` stub with a model-backed render flow
2. Replace the deterministic validation function with richer validation logic and checks
3. Add planner/renderer use of richer device-context lookups when the request implies interface-level work
4. Add artifact indexes or summaries per run beyond JSON files alone
5. Add richer policy and approval hooks
6. Keep execution disabled until the earlier stages are reliable[web:18][web:26][web:67]

## Troubleshooting

### The CLI says `net-agent` is not found

Make sure the virtual environment is activated and that `pip install -e .[dev]` completed successfully.

### The model call fails

Check that Ollama is running and that the configured model exists locally. If needed, run `ollama list` and confirm the configured model name is present.[web:55]

### The output is invalid or inconsistent

Smaller local models may vary in quality. This is expected in the prototype phase. The typed schema still helps because invalid output is caught at the application boundary instead of silently flowing through the system.[web:26][web:44]

### The agent invents devices

That is one reason the inventory tool exists. The next iterations should tighten prompts and rely more heavily on tool-grounded data rather than free-form assumptions.[web:61][web:18]

## Notes on future integrations

The repository already includes placeholder adapter modules for systems such as NetBox, Nornir, and NAPALM, but they are intentionally empty in the starter. The safer sequence is to keep using mock data first, then introduce read-only integrations, then later consider any execution path behind explicit approvals and scope controls.[web:67][web:18]

## Development philosophy

The project is being built in small chunks on purpose:
- keep each step easy to review,
- keep each change small enough to survive interruptions,
- and validate one layer at a time.

That approach is especially useful for agent systems because it separates model quality problems from architecture problems early.[web:18][web:82]
