# Main flow

The cleanest network workflow is staged rather than fully autonomous. That lets you make read-only discovery the default, require explicit approval before execution, and preserve evidence at each step.

A concrete lifecycle looks like this:

```
Change request or incident
│
▼
Inventory / topology discovery
│
▼
Change planning or incident triage
│
▼
Design / policy review
│
▼
Config render or remediation proposal
│
▼
Validation / compliance checks
│
▼
Human approval gate
│
├── reject -> revise plan/render
│
▼
Execution on bounded device scope
│
▼
Post-change verification
│
▼
Evidence package + closure notes

```

That model maps very naturally to structured outputs and approved tool execution, which is why this stack is a good fit for network work.
