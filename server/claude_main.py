import json
import os
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    ThinkingBlock,
    TextBlock,
    ToolUseBlock,
    ResultMessage,
)

app = FastAPI()

agent_client = None
agent_options = None


@app.on_event("startup")
async def startup():
    global agent_client, agent_options
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://127.0.0.1:49983/envs", timeout=5.0)
            if response.status_code == 200:
                env_vars = response.json()
                for key, value in env_vars.items():
                    os.environ[key] = value
            else:
                pass
    except Exception as e:
        pass

    agent_options = ClaudeAgentOptions(
        # System prompt - using Claude Code preset
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            # Optional: append custom instructions
            # "append": "\n\nAdditional custom instructions here..."
        },
        # Load settings from .claude/ directory to enable skills
        # "project" loads .claude/settings.json and discovers skills in .claude/skills/
        setting_sources=["project"],
        # Enable ALL tools
        allowed_tools=[
            "Bash",  # Execute shell commands
            "Read",  # Read files
            "Write",  # Write new files
            "Edit",  # Edit existing files
            "MultiEdit",  # Edit multiple files at once
            "Glob",  # Find files by pattern
            "GrepTool",  # Search file contents
            "WebSearch",  # Search the web
            "WebFetch",  # Fetch web content
            "Skill",  # Use skills from .claude/skills/
            "TodoWrite",  # Create todo lists
            "TodoEdit",  # Edit todo lists
            "Task",  # Launch subagents
        ],
        # Working directory - where Claude operates
        cwd="/workspace",
        # Permission mode - auto-accept file edits for automation
        permission_mode="acceptEdits",
        # Max conversation turns before stopping
        max_turns=30,
    )

    agent_client = ClaudeSDKClient(options=agent_options)
    await agent_client.__aenter__()  # Initialize the session


@app.on_event("shutdown")
async def shutdown():
    global agent_client
    if agent_client:
        await agent_client.__aexit__(None, None, None)  # Properly close the session


@app.get("/health")
async def health():
    """
    Health check that verifies Claude Agent SDK is initialized.
    """
    if agent_client is not None:
        return {"status": "ok", "agent": "ready"}
    else:
        return {"status": "starting", "agent": "initializing"}


class TaskRequest(BaseModel):
    task: str
    context: list[dict] = []
    files: list[str] = []


@app.post("/execute_task")
async def execute_task(request: TaskRequest):
    """
    Execute task by CC inside dedicated microvm
    """
    global agent_client

    print(f"[CLAUDE-SERVER] 🔔 New task: {request.task[:50]}...", flush=True)

    if not agent_client:
        raise HTTPException(500, "Agent not initialized")

    context_parts = []

    if request.context:
        context_parts.append("Context from previous work:")
        for msg in request.context:
            context_parts.append(f"  {msg['role']}: {msg['content']}")

    if request.files:
        context_parts.append(
            f"\nFiles available in /workspace/: {', '.join(request.files)}"
        )

    context_str = "\n".join(context_parts)

    full_query = f"{context_str}\n\n{request.task}" if context_str else request.task

    async def stream_response():
        try:
            await agent_client.query(full_query)

            async for message in agent_client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            yield f"{block.text}\n".encode()
                        elif isinstance(block, ThinkingBlock):
                            yield f"{block.thinking}\n".encode()
                        elif isinstance(block, ToolUseBlock):
                            yield f"🔧 Tool: {block.name}\n".encode()
                            yield f"   Input: {json.dumps(block.input)}\n".encode()

                elif isinstance(message, ResultMessage):
                    yield f"\n✅ Complete (turns: {message.num_turns})\n".encode()

        except Exception as e:
            yield f"Error: {str(e)}\n".encode()

    return StreamingResponse(stream_response(), media_type="text/plain")
