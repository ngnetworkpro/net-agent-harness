# Main flow

The lifecycle is staged and safety-gated, not autonomous.

## Canonical lifecycle

```
Change request
│
▼
route
│
▼
plan
│
├── no_op  -> stop with evidence
├── blocked -> stop with blocking reason
│
▼
render (apply only)
│
▼
execute (approval-gated; currently disabled by default)
│
▼
review
```

## Stage outcomes

- `route` selects a domain or fails safely when confidence is too low.
- `plan` resolves targets and chooses exactly one decision: `apply`, `no_op`, or `blocked`.
- `render` translates approved diffs into backend-specific operations with explicit backend labels.
- `execute` applies changes only when approvals and policy checks pass.
- `review` records expected versus observed outcomes, rollback conditions, and final run status.

## Practical status in this repository

- End-to-end planning and render/validation workflows are implemented.
- Execution is intentionally constrained and not part of default day-to-day runs.
