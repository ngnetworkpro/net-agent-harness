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

---

## Resource lifecycle states

Topology records and IPAM allocations carry an explicit `lifecycle_state` field
so they can be tracked from initial planning through post-activation verification.

| State       | Meaning                                                                                  |
|-------------|------------------------------------------------------------------------------------------|
| `current`   | Reflects what is actually deployed right now.                                            |
| `intended`  | Desired end-state expressed as policy-level intent; not yet a concrete diff.             |
| `planned`   | Change has been modelled and diffed; not yet approved. IPAM allocations reserved for a planned change also sit here. |
| `approved`  | Change has passed an approval gate; not yet applied.                                     |
| `applied`   | Change has been pushed to the device; not yet verified.                                  |
| `verified`  | Applied change confirmed to match intent. Terminal state.                                |

### Allowed transitions

```
current  ──► planned
intended ──► planned
planned  ──► approved
planned  ──► current   (abandoned / rejected)
approved ──► applied
applied  ──► verified
applied  ──► current   (verification skipped)
```

`verified` is a terminal state; no further transitions are permitted.

### Workflow read/write access

| Workflow / stage      | Read states     | Write state(s)                      |
|-----------------------|-----------------|-------------------------------------|
| discovery / read-only | any             | none                                |
| plan                  | current, intended | planned                           |
| approval gate         | planned         | approved                            |
| execute               | approved        | applied                             |
| review                | applied         | verified, current (skip-verify)     |

