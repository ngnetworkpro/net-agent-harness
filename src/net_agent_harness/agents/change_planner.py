from pydantic_ai import Agent, RunContext
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.output import NativeOutput
from pydantic_ai.providers.ollama import OllamaProvider

from ..config import settings
from ..models.changes import PlannedChange
from ..orchestration.run_context import RunContextData
from ..tools.inventory_tools import lookup_inventory, resolve_device_target, resolve_site_targets
from ..tools.vlan_state import compute_vlan_diff

model = OllamaModel(
    settings.ollama_model,
    provider=OllamaProvider(base_url="http://localhost:11434/v1"),
)

change_planner = Agent(
    model,
    deps_type=RunContextData,
    output_type=NativeOutput(PlannedChange),
    retries=2,
)

@change_planner.system_prompt
def planner_system_prompt(ctx: RunContext[RunContextData]) -> str:
    """Generate the system prompt dynamically using the resolved domain context."""
    
    # Static preamble (rules of engagement)
    preamble = [
        "You are a network change planner. ",
        "Your job is to convert the user's request into a normalized, vendor-neutral change intent that can later be validated, diffed against current state, rendered for API or CLI, and optionally executed. ",
        "You must use the provided domain context and inventory context. Treat the domain context as authoritative for terminology and intent mapping. ",
        "Objectives: ",
        "1. Interpret the user's request using the provided domain glossary and intent rules. ",
        "2. Extract structured intent without inventing missing facts. ",
        "3. Distinguish between: ",
        "- desired configuration intent ",
        "- current-state questions ",
        "- unsupported or ambiguous requests ",
        "4. Prefer vendor-neutral intent, not vendor-specific syntax. ",
        "5. Do not render CLI commands or API payloads. ",
        "6. Do not decide execution details unless explicitly provided by context. ",
        "7. If the request is ambiguous, return blocked with a clear reason. ",
        "8. If the request asks for something that may already be true, describe the desired end state so a later diff stage can determine no-op vs apply. ",
        "Authoritative domain context: ",
        "{{ domain_context }}",
        "Core terms: ",
        "{{ core_terms }}",
        "Relevant examples: ",
        "{{ examples }}",
        "Inventory context: ",
        "{{ inventory_context }} ",
        "Output requirements: ",
        "Return structured output with these fields: ",
        "- decision: one of ['plan', 'blocked', 'question'] ",
        "- summary: short summary of the intended change ",
        "- domain: primary domain ",
        "- intent_type: normalized intent type ",
        "- targets: ",
        "- site ",
        "- devices ",
        "- interfaces ",
        "- scope ",
        "- desired_state: ",
        "- include only fields necessary to express the desired end state "
        "assumptions: ",
        "- list assumptions explicitly "
        "missing_information: ",
        "- list of missing details that prevent safe planning "
        "safety_notes: ",
        "- list of risks or review points "
        "reasoning: ",
        "- short explanation of how the request was interpreted from the glossary and examples "
        "Normalization rules: ",
        "- Use vendor-neutral terms such as access_vlan, native_vlan, allowed_vlans_mode, vlan_ids, svi, ip_prefix, acl_entries. ",
        "- If the request says \"put port in VLAN X\" and does not mention trunk, uplink, tagged, or allowed VLANs, interpret it as setting an access VLAN. ",
        "- If the request says \"allow\", \"permit\", or \"tag\" VLAN X on a trunk or uplink, interpret it as updating trunk allowed VLAN membership. ",
        "- If the request mentions \"native VLAN\", require or assume trunk context. ",
        "- If the request mentions \"gateway IP\", \"routed VLAN interface\", or \"SVI\", interpret it as Layer 3 VLAN interface work. ",
        "- Do not assume a VLAN exists unless inventory context confirms it. ",
        "- Do not assume all VLANs are allowed on a trunk unless inventory context confirms allowed_vlans_mode=\"all\". ",
        "- include only fields necessary to express the desired end state ",
        "assumptions: ",
        "- list assumptions explicitly ",
        "missing_information: ",
        "- list of missing details that prevent safe planning ",
        "safety_notes: ",
        "- list of risks or review points ",
        "reasoning: ",
        "- short explanation of how the request was interpreted from the glossary and examples ",
        "Normalization rules: ",
        "- Use vendor-neutral terms such as access_vlan, native_vlan, allowed_vlans_mode, vlan_ids, svi, ip_prefix, acl_entries. ",
        "- If the request says \"put port in VLAN X\" and does not mention trunk, uplink, tagged, or allowed VLANs, interpret it as setting an access VLAN. ",
        "- If the request says \"allow\", \"permit\", or \"tag\" VLAN X on a trunk or uplink, interpret it as updating trunk allowed VLAN membership. ",
        "- If the request mentions \"native VLAN\", require or assume trunk context. ",
        "- If the request mentions \"gateway IP\", \"routed VLAN interface\", or \"SVI\", interpret it as Layer 3 VLAN interface work. ",
        "- Do not assume a VLAN exists unless inventory context confirms it. ",
        "- Do not assume all VLANs are allowed on a trunk unless inventory context confirms allowed_vlans_mode=\"all\". ",    
        "User request: ",
        "{{ user_request }} "
    ]
    
    parts = [" ".join(preamble)]
    
    # Inject domain context if available
    if ctx.deps.domain_context:
        parts.append(ctx.deps.domain_context.render_prompt_block())
        
    return "\n\n".join(parts)


@change_planner.output_validator
async def _enforce_plan_decision(
    ctx: RunContext[RunContextData], output: PlannedChange
) -> PlannedChange:
    """Deterministically enforce the consequences of plan_decision.

    The LLM may produce a correct ``plan_decision`` but neglect to apply its
    implications to the rest of the output (e.g. leaving ``resolved_targets``
    populated on a no_op, or leaving ``clarifications_needed`` empty on a
    blocked decision).  This validator corrects both cases in code so the
    downstream pipeline always sees a consistent artifact.
    """
    from ..models.changes import PlanDecisionType

    if output.plan_decision is None:
        return output

    decision = output.plan_decision.decision
    reason = output.plan_decision.reason

    if decision == PlanDecisionType.NO_OP:
        # Nothing needs rendering — clear targets so ensure_renderable
        # (and any other consumers) cannot accidentally proceed.
        output.resolved_targets = []
        output.clarifications_needed = [
            f"[no_op] {reason}"
        ]

    elif decision == PlanDecisionType.BLOCKED:
        # Ensure the reason surfaces as a clarification so the CLI surfaces
        # it clearly, regardless of what the LLM put in clarifications_needed.
        blocker_note = f"[blocked] {reason}"
        if blocker_note not in output.clarifications_needed:
            output.clarifications_needed = [blocker_note] + [
                c for c in output.clarifications_needed
                if not c.startswith("[blocked]")
            ]

    return output




@change_planner.tool
async def get_inventory(ctx: RunContext[RunContextData], site: str):
    return lookup_inventory(ctx, site=site)

@change_planner.tool
async def get_site_targets(ctx: RunContext[RunContextData], site: str):
    return resolve_site_targets(ctx, site=site)


@change_planner.tool
async def get_device_target(ctx: RunContext[RunContextData], site: str | None, device_name: str):
    return resolve_device_target(ctx, site=site, device_name=device_name)


@change_planner.tool
async def evaluate_vlan_intent(
    ctx: RunContext[RunContextData],
    site: str,
    device_name: str,
    vlan_id: int,
    target_interfaces: list[str],
    mode: str = "trunk",
    vlan_name: str | None = None,
) -> dict:
    """Evaluate whether a VLAN provisioning intent is already satisfied on a device.

    Call this after resolving the target device from inventory.  The result is a
    PlanDecision dict — decision (apply | no_op | blocked), reason, and diff — that
    should be placed verbatim into plan_decision on the PlannedChange output.

    Parameters
    ----------
    site:
        Site name used to look up the device's full inventory snapshot.
    device_name:
        Exact device name as returned by the inventory tool.
    vlan_id:
        VLAN ID the request wants to provision.
    target_interfaces:
        Interface names the VLAN should be present on.
    mode:
        ``"trunk"`` (default) or ``"access"``.
    vlan_name:
        Optional human-readable VLAN label; used only in reason strings.
    """
    from ..adapters.mock_inventory_adapter import get_inventory_for_site

    snapshot = get_inventory_for_site(run_id=ctx.deps.run_id, site=site)
    device = next((d for d in snapshot.devices if d.name == device_name), None)

    if device is None:
        return {
            "decision": "blocked",
            "reason": (
                f"Device '{device_name}' was not found in the inventory snapshot "
                f"for site '{site}'. Verify the device name and site."
            ),
            "diff": {"vlans_to_create": [], "ports_to_update": []},
        }

    return compute_vlan_diff(
        intent={
            "vlan_id": vlan_id,
            "target_interfaces": target_interfaces,
            "mode": mode,
            "vlan_name": vlan_name,
        },
        current_state=device,
    )