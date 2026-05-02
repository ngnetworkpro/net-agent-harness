from rich.console import Console

console = Console()

async def run_agent_with_spinner(
    agent,
    prompt,
    deps=None,
    model_settings=None,
    message="Initializing planner...",
):
    with console.status(message) as status:
        async for event in agent.run_stream_events(
            prompt,
            deps=deps,
            model_settings=model_settings,
        ):
            event_type = type(event).__name__

            if event_type == "PartStartEvent":
                part = getattr(event, "part", None)
                if part is not None and type(part).__name__ == "ToolCallPart":
                    tool_name = getattr(part, "tool_name", "tool")
                    status.update(f"Executing tool: {tool_name}...")

            elif event_type == "FunctionToolCallEvent":
                tool_name = getattr(event, "tool_name", "tool")
                status.update(f"Executing tool: {tool_name}...")

            elif event_type == "FunctionToolResultEvent":
                tool_name = getattr(event, "tool_name", "tool")
                status.update(f"Completed tool: {tool_name}...")

            elif event_type == "AgentRunResultEvent":
                status.update("Synthesizing final response...")
                return event.result.output

        raise RuntimeError("Agent run completed without a final result event.")