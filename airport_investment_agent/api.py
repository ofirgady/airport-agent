import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent

from agents import RawResponsesStreamEvent, Runner

from airport_investment_agent.agent import airport_agent
from airport_investment_agent.utils import get_session, log_run, read_runs
from airport_investment_agent.models import ChatRequest, RunLogEntry, ToolInfo

app = FastAPI(title="Airport Investment Intelligence Agent")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    session = get_session(request.session_id)
    try:
        result = Runner.run_streamed(airport_agent, request.message, session=session)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    started = time.monotonic()

    async def event_source():
        try:
            async for event in result.stream_events():
                if isinstance(event, RawResponsesStreamEvent) and isinstance(
                    event.data, ResponseTextDeltaEvent
                ):
                    yield f"data: {event.data.delta}\n\n"
        except Exception as error:
            yield f"event: error\ndata: {error}\n\n"
            return

        log_run(
            request.session_id,
            request.message,
            result.new_items,
            result.final_output,
            usage=result.context_wrapper.usage,
            latency_seconds=time.monotonic() - started,
        )

    return StreamingResponse(event_source(), media_type="text/event-stream")


@app.get("/tools", response_model=list[ToolInfo])
async def list_tools() -> list[ToolInfo]:
    # airport_agent.tools is typed as the SDK's full Tool union, most of
    # which (hosted tools like WebSearchTool) have no .description -- every
    # tool actually in ALL_TOOLS is a FunctionTool today, but getattr keeps
    # this correct if a hosted tool is ever added directly.
    return [
        ToolInfo(name=tool.name, description=getattr(tool, "description", None))
        for tool in airport_agent.tools
    ]


@app.get("/runs", response_model=list[RunLogEntry])
async def list_runs() -> list[RunLogEntry]:
    return [RunLogEntry(**entry) for entry in read_runs()]