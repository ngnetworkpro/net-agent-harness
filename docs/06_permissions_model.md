# Permissions model

A concrete permissions model is critical here because execution risk is high.
This table maps the network roles to the tool-layer privileges we defined in the previous section.

| Role                    | Read inventory | Read device state | Render config | Execute commands             | Push config             | Notes                                                                                |
| ----------------------- | -------------- | ----------------- | ------------- | ---------------------------- | ----------------------- | ------------------------------------------------------------------------------------ |
| **Inventory agent**     | Yes (permit)   | Limited (permit)  | No            | No                           | No                      | Can query inventory and limited status, but cannot change topology or configuration. |
| **Change planner**      | Yes (pydantic) | Limited (permit)  | No            | No                           | No                      | Analyzes intent and proposes changes, but cannot execute.                            |
| **Design/policy agent** | Yes (pydantic) | Optional          | No            | No                           | No                      | Validates designs against policy; can “see” more state if needed for validation.     |
| **Config render agent** | Yes (ollama)   | Yes               | Yes (ollama)  | No                           | No                      | Reads live state to render or validate, but does not execute changes.                |
| **Validation agent**    | Yes (pydantic) | Yes               | Review only   | Limited (pre/post checks)    | No                      | Can run pre and post change checks, but not arbitrary commands or config pushes.     |
| **Execution agent**     | Yes            | Yes               | No            | Yes (approval required)      | Yes (approval required) | Can run approved commands and push approved configs.                                 |
| **Incident agent**      | Yes            | Yes               | Optional      | Optional (approval required) | No                      | Can run limited commands during incident triage if approved.                         |
