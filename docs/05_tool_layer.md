# Tool layer

The tool layer is where the network version really differs.
The agents should not use raw unrestricted shell access if you can avoid it; narrow, typed tools are safer and easier to audit.
PydanticAI’s toolset and approval features are useful here because you can define exactly which calls are allowed and which ones need explicit signoff.

## Recommended tools:

- get_inventory(site|device|role)
- get_topology(device|site)
- get_running_config(device)
- render_config(intent, device_facts)
- diff_config(candidate, running)
- run_precheck(device_scope, checkset)
- run_postcheck(device_scope, checkset)
- execute_commands(device_scope, commands) — approval required
- push_config(device_scope, candidate) — approval required
- open_change_ticket(artifact_refs)
- attach_evidence(ticket_id, evidence_refs)
