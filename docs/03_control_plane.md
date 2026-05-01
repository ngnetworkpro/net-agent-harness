# Control plane responsibilities

The control plane stays almost identical to the product-planning version, but the policies become much stricter because the blast radius is higher.
[OpenAI’s docs](https://openai.github.io/openai-agents-python/guardrails/) emphasize guardrails for input and output safety, while [PydanticAI](https://pydantic.dev/docs/ai/api/pydantic-ai/tools/) includes support for tool calls that require approval or deferred execution.

## Run coordinator

The Run Coordinator owns the state machine for network workflows.
It should know whether the current run is discovery, planning, rendering, validation, approval pending, execution, or verification.

**Responsibilities:**

1. Start and track change or incident runs.
2. Enforce maintenance-window rules and retry limits.
3. Pause automatically for human approval before execution.
4. Resume with approved scope only.
5. Stop the run if validation evidence is missing.

## Policy and approval engine

This is the [safety core](https://www.permit.io/blog/ai-agents-access-control-with-pydantic-ai).
It decides what an agent may read, what it may render, and what it may execute.

**Responsibilities:**

1. Limit device scope by site, vendor, or maintenance window.
2. Restrict live execution tools to approved operators and approved runs.
3. Maintain command allowlists and deny dangerous patterns.
4. Require rollback plan before any config push.
5. Require post-change verification before closure.

## Trace and evidence store

In networking, evidence is not optional. [OpenAI Agents SDK](https://github.com/openai/openai-agents-python/blob/main/docs/tracing.md) tracing is valuable because it captures generations, tool calls, handoffs, guardrails, and custom events, while your harness should also store command results, diffs, and pre/post validation outputs.

**Responsibilities:**

1. Store every artifact revision.
2. Record command output, config diff, and validation results.
3. Link actions to user, run, device scope, and approval event.
4. Preserve incident notes and resolution steps.
5. Support audit and postmortem review.

## Specialist agents

The network variant mostly changes the domain agents and their artifacts. [Handoffs](https://openai.github.io/openai-agents-python/handoffs/) are useful here because discovery, planning, rendering, validation, and incident handling often need different context and different tool permissions.

### Topology and inventory agent

This agent builds the initial fact base from source-of-truth systems and device discovery. It should usually be read-only.

**Responsibilities:**

1. Pull inventory, interface, topology, and site facts.
2. Normalize vendor-specific data into a common schema.
3. Identify relevant devices for the requested change.
4. Produce inventory.json and topology_snapshot.json.
5. Flag missing or conflicting source-of-truth data.

### Change planner

This agent turns a requested change into an executable plan. [Structured outputs](https://ollama.com/blog/structured-outputs) are especially important here because you want predictable fields like scope, assumptions, risk, and rollback prerequisites.

**Responsibilities:**

1. Parse the requested network change.
2. Identify impacted devices, services, and dependencies.
3. Generate change_request.json and execution_plan.json.
4. Define checkpoints, maintenance-window requirements, and rollback triggers.
5. Ask for clarification when risk is too high or scope is ambiguous.

### Design and policy agent

This agent validates whether the planned change aligns with architecture and policy. It is the network equivalent of the architect role.

**Responsibilities:**

1. Check design against segmentation, routing, security, and naming policy.
2. Compare proposed state against intended-state standards.
3. Generate intended_state.json.
4. Identify policy exceptions that need approval.
5. Recommend safer patterns when possible.

### Config render agent

This is the network equivalent of the coding agent. It should render or prepare configuration, not necessarily push it.

**Responsibilities:**

1. Generate config snippets or full rendered configs from approved intent.
2. Scope output by vendor, platform, role, and device.
3. Produce config_render.json.
4. Include rollback or inverse-change data where possible.
5. Stop if inventory facts are incomplete or inconsistent.

### Validation and compliance agent

This agent is one of the highest-value parts of the system because it can check intent, rendered config, and live state before execution.
PydanticAI’s validated outputs are a natural fit for producing structured findings.

**Responsibilities:**

1. Compare rendered config against policy and intent.
2. Run linting, template validation, and pre-check rules.
3. Produce validation_report.json.
4. Mark issues by severity and remediation requirement.
5. Block execution if required checks fail.

### Execution agent

This agent should be heavily constrained and often disabled in early versions.
It is where policy and approval controls matter most.

**Responsibilities:**

1. Execute only approved commands or config pushes.
2. Operate only on approved devices in approved windows.
3. Capture raw command output and change results.
4. Abort on policy violation or unexpected state.
5. Hand off immediately to verification after execution.

### Verification agent

This agent confirms the network is in the intended post-change state.

**Responsibilities:**

1. Run post-check commands and health validations.
2. Compare actual state to intended state.
3. Generate evidence of success or rollback requirement.
4. Produce updated validation_report.json or closure artifact.
5. Escalate to incident flow if something broke.

### Incident agent

This agent can share the same stack but follows a different path from change planning. It is useful for triage, summarization, and rollback recommendation.

**Responsibilities:**

1. Summarize logs, alerts, and device facts into incident_summary.json.
2. Suggest likely fault domains and next checks.
3. Correlate a recent change to symptoms when possible.
4. Produce recommended remediation options.
5. Hand off to execution only with approval.
