import asyncio
from rich.console import Console
from pydantic_ai.messages import ToolCallPart, ModelResponsePart

console = Console()

async def run_agent_with_spinner(agent, prompt, deps=None, model_settings=None, message="Initializing planner..."):
    """
    Runs a Pydantic AI agent stream and updates a rich spinner with tool calls.
    Returns the final structured output.
    """
    with console.status(message) as status:
        async with agent.run_stream(prompt, deps=deps, model_settings=model_settings) as result:
            async for event in result.stream_events():
                event_type = type(event).__name__
                if event_type == "ModelRequest":
                    # For newer PydanticAI versions, parts are inside ModelRequest
                    if hasattr(event, "parts"):
                        for part in event.parts:
                            if type(part).__name__ == "ToolCallPart":
                                status.update(f"Executing tool: {part.tool_name}...")
                elif event_type == "ModelResponse":
                    status.update("Synthesizing final response...")
                elif event_type == "ToolCallPart":
                    # For older PydanticAI versions that yield parts directly
                    status.update(f"Executing tool: {event.tool_name}...")
                elif event_type == "ModelResponsePart":
                    status.update("Synthesizing final response...")
            
            # The stream is complete, return the final parsed data
            return await result.get_data()
