import os
from pydantic_ai import Agent, RunContext
from pydantic_ai.output import NativeOutput

from ..models.changes import PlannedChange
from ..orchestration.run_context import RunContextData
from ..tools.inventory_tools import lookup_inventory, resolve_device_target, resolve_site_targets
from ..tools.evaluation import evaluate_intent_state

from ..agents.agent_factory import build_agent

change_planner = build_agent(
    deps_type=RunContextData,
    output_type=NativeOutput(PlannedChange),
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
        "- when wording is ambiguous or conflicts with inventory configuration, return question/blocked instead of assuming "
        "4. Prefer vendor-neutral intent, not vendor-specific syntax. ",
        "5. Do not render CLI commands or API payloads. ",
        "6. Do not decide execution details unless explicitly provided by context. ",
        "7. If the request is ambiguous, return blocked with a clear reason. ",
        "8. If the request asks for something that may already be true, describe the desired end state so a later diff stage can determine no-op vs apply. ",
        "Target Resolution: ",
        "During planning, call resolve_device_target if the request names a specific device, "
        "or resolve_site_targets if the request references a site without a specific device. "
        "Use the inventory results to inform risk, assumptions, and dependency fields. "
        "Note: resolved_targets in your output will be validated and overwritten by the "
        "orchestration layer. Focus on populating scope, requested_change, risk, and "
        "plan_decision accurately. ",
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

