
┌──────────────────────────────────────────────────────────────────────────┐
│                         Operator / Network Engineer                      │
│     CLI | Web UI | Chat UI | Ticket trigger | Change request API       │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         Network Harness Control Plane                    │
│                                                                          │
│  ┌────────────────────────┐   ┌───────────────────────────────────────┐  │
│  │ Run Coordinator        │   │ Policy / Approval Engine             │  │
│  │ - workflow stages      │◄──┤ - device scope limits                │  │
│  │ - retries/timeouts     │   │ - command allowlists                 │  │
│  │ - maintenance windows  │   │ - approval for push/commit/deploy    │  │
│  └────────────┬───────────┘   └───────────────────────────────────────┘  │
│               │                                                          │
│               ▼                                                          │
│  ┌────────────────────────┐   ┌───────────────────────────────────────┐  │
│  │ Agent Router           │   │ Trace / Audit / Evidence Store       │  │
│  │ - select specialist    │──►│ - prompts, tool calls, handoffs      │  │
│  │ - filter context       │   │ - pre/post checks, diffs, approvals  │  │
│  └────────────┬───────────┘   └───────────────────────────────────────┘  │
│               │                                                          │
│               ▼                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │ Artifact Registry                                                 │  │
│  │ change_request.json | inventory.json | intended_state.json        │  │
│  │ config_render.json | validation_report.json | rollback_plan.json  │  │
│  │ execution_plan.json | incident_summary.json                       │  │
│  └────────────┬───────────────────────────────────────────────────────┘  │
│               │                                                          │
└───────────────┼──────────────────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                      Network Specialist Agent Layer                      │
│                                                                          │
│  Topology / Inventory Agent ─► Change Planner ─► Design / Policy Agent  │
│                                              │                           │
│                                              ▼                           │
│                                   Config Render Agent                    │
│                                              │                           │
│                                              ▼                           │
│                                   Validation / Compliance Agent          │
│                                              │                           │
│                         ┌────────────────────┴────────────────────┐      │
│                         ▼                                         ▼      │
│                  Execution Agent                          Incident Agent  │
│                         │                                                │
│                         ▼                                                │
│                  Verification Agent                                      │
└──────────────────────────────────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                              Network Tool Layer                          │
│ Nornir/NAPALM/Netmiko/Scrapli | source-of-truth APIs | config diff      │
│ command runner | validation tests | topology lookup | ticketing | logs  │
└──────────────────────────────────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         Infra / Data Boundaries                          │
│  Source of truth | lab/sandbox | device fleet | telemetry/log stores    │
│  Git-backed config repo | approval records | secrets boundary           │
└──────────────────────────────────────────────────────────────────────────┘
