# Permissions model

A concrete permissions model is critical here because execution risk is high.
This table maps the network roles to the tool-layer privileges we defined in the previous section.

Execution-oriented permissions are intentionally constrained in this repository’s current prototype, where execution is disabled by default and review artifacts are the primary endpoint.

| Role                    | Read inventory | Read device state | Render config | Execute commands             | Push config             | Notes                                                                                |
| ----------------------- | -------------- | ----------------- | ------------- | ---------------------------- | ----------------------- | ------------------------------------------------------------------------------------ |
| **Inventory agent**     | Yes (permit)   | Limited (permit)  | No            | No                           | No                      | Can query inventory and limited status, but cannot change topology or configuration. |
| **Change planner**      | Yes (pydantic) | Limited (permit)  | No            | No                           | No                      | Analyzes intent and proposes changes, but cannot execute.                            |
| **Design/policy agent** | Yes (pydantic) | Optional          | No            | No                           | No                      | Validates designs against policy; can “see” more state if needed for validation.     |
| **Config render agent** | Yes (ollama)   | Yes               | Yes (ollama)  | No                           | No                      | Reads live state to render or validate, but does not execute changes.                |
| **Validation agent**    | Yes (pydantic) | Yes               | Review only   | Limited (pre/post checks)    | No                      | Can run pre and post change checks, but not arbitrary commands or config pushes.     |
| **Execution agent**     | Yes            | Yes               | No            | Yes (approval required)      | Yes (approval required) | Can run approved commands and push approved configs.                                 |
| **Incident agent**      | Yes            | Yes               | Optional      | Optional (approval required) | No                      | Can run limited commands during incident triage if approved.                         |

## Source-of-truth write gates

Inventory, IPAM, and topology adapters now expose future write method
signatures, but all implementations remain disabled by default.

Every write path must satisfy **all** of the following before any real
implementation is allowed to run:

1. Explicit configuration enablement for the specific write capability:
   - `NET_AGENT_ENABLE_INVENTORY_WRITES=true`
   - `NET_AGENT_ENABLE_IPAM_WRITES=true`
   - `NET_AGENT_ENABLE_TOPOLOGY_WRITES=true`
2. An approved policy artifact reference (`approved_artifact_id`).
3. An explicit capability grant for the matching write type.
4. Reviewed evidence references captured alongside the approval.

If any requirement is missing, the policy layer raises `PolicyDenied`.
If all requirements are present, the current adapter stubs still raise
`NotImplementedError` until a later milestone deliberately enables a
concrete write backend.

### Approval and evidence requirements by write type

| Write type | Required config flag | Required capability grant | Minimum approval artifact | Minimum evidence |
| ---------- | -------------------- | ------------------------- | ------------------------- | ---------------- |
| Inventory source-of-truth update | `NET_AGENT_ENABLE_INVENTORY_WRITES` | `inventory_write` | Approved artifact ID authorizing the inventory mutation | Evidence refs showing the reviewed inventory delta and upstream planning context |
| IPAM reservation/update | `NET_AGENT_ENABLE_IPAM_WRITES` | `ipam_write` | Approved artifact ID authorizing the IPAM mutation | Evidence refs showing the reviewed prefix/address allocation context |
| Topology source-of-truth update | `NET_AGENT_ENABLE_TOPOLOGY_WRITES` | `topology_write` | Approved artifact ID authorizing the topology mutation | Evidence refs showing the reviewed topology plan or delta |

Read-only and discovery paths remain restricted to their existing
non-mutating tool allowlists. Reserved write tool names are explicitly
blocked in the tool registry so write capability is not exposed through
`ask`, topology discovery, IPAM lookup, or other read-only flows.
