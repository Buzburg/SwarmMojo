"""ROMS Smart Local LLM Gateway & Autonomous Cartridge Proxy.

Provides an OpenAI-compatible API endpoint (/v1/chat/completions, /v1/models):
1. Intercepts incoming user chat messages
2. Retrieves hybrid RAG context from roms.db
3. Matches and injects procedural SOP skills from skills/<name>.md (UpSkill)
4. Dynamically injects top matching tool schemas on-demand (AnyTool Smart Tool RAG)
5. Forwards each request independently; completion reuse is disabled
6. Transparent streaming to/from your local LLM (Ollama, llama.cpp, vLLM, LM Studio)

Experimental text-only proxy; individual client integrations require verification.
"""

import json
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional
import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from app.config import (
    ROMS_UPSTREAM_LLM_URL,
    ROMS_GATEWAY_PORT,
    MAX_RAG_CONTEXT_TOKENS,
    MIN_RELEVANCE_SCORE,
    SKILLS_DIR,
)
from app.rag_engine import hybrid_search
from app.prompt_builder import format_context_for_local_llm, build_grounded_system_prompt
from app.tool_rag import format_tool_search_results
from app.trajectory_recorder import start_session, record_step, finish_session

app = Starlette(debug=False)

def _find_matching_skill(query: str) -> Optional[tuple[str, str]]:
    """Identifies if a user query corresponds to an existing procedural SOP playbook in skills/."""
    if not SKILLS_DIR.exists():
        return None

    query_tokens = set(query.lower().replace("_", " ").split())
    best_skill = None
    best_overlap = 0

    for skill_file in SKILLS_DIR.glob("*.md"):
        skill_name = skill_file.stem.lower()
        skill_tokens = set(skill_name.replace("_", " ").split())
        overlap = len(query_tokens.intersection(skill_tokens))
        if overlap > best_overlap:
            best_overlap = overlap
            best_skill = skill_file

    if best_skill and best_overlap > 0:
        return best_skill.stem, best_skill.read_text(encoding="utf-8", errors="replace")
    return None


async def list_models(request: Request) -> JSONResponse:
    """Proxies /v1/models to upstream local LLM or returns ROMS default model list."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{ROMS_UPSTREAM_LLM_URL}/models")
            if resp.status_code == 200:
                return JSONResponse(resp.json())
    except Exception:
        pass

    # Fallback default models if upstream is not reachable
    return JSONResponse({
        "object": "list",
        "data": [
            {"id": "roms-smart-cartridge", "object": "model", "owned_by": "roms"},
            {"id": "llama3.2:latest", "object": "model", "owned_by": "ollama"},
        ]
    })


async def chat_completions(request: Request) -> Response:
    """Augments chat completions with ROMS knowledge, skills, and tools before sending to local LLM."""
    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    if not isinstance(body, dict):
        return JSONResponse({"error": "Expected a JSON object"}, status_code=400)
    messages = body.get("messages", [])
    if not isinstance(messages, list) or any(
        not isinstance(message, dict)
        or not isinstance(message.get("role"), str)
        or not isinstance(message.get("content"), str)
        for message in messages
    ):
        return JSONResponse({"error": "messages must contain text role/content objects"}, status_code=400)
    if "stream" in body and not isinstance(body["stream"], bool):
        return JSONResponse({"error": "stream must be a boolean"}, status_code=400)
    stream: bool = body.get("stream", False)
    session_id = str(uuid.uuid4())[:8]

    # 1. Extract the latest user query
    last_user_query = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_query = msg.get("content", "")
            break

    # Augment with knowledge, skills and tool descriptions
    if last_user_query:
        # A. Hybrid RAG
        rag_chunks = hybrid_search(
            query=last_user_query,
            limit=3,
            min_score=MIN_RELEVANCE_SCORE,
        )
        context_str = format_context_for_local_llm(
            rag_chunks,
            format_style="xml",
            max_tokens=MAX_RAG_CONTEXT_TOKENS,
        )

        # B. Matching Procedural SOP Skill
        matching_skill = _find_matching_skill(last_user_query)
        skill_str = ""
        if matching_skill:
            s_name, s_content = matching_skill
            skill_str = f"\n<active_skill_playbook name=\"{s_name}\">\n{s_content}\n</active_skill_playbook>"

        # C. Smart Tool RAG discovery (AnyTool schema injection)
        tool_schemas = format_tool_search_results(last_user_query, limit=2)
        tool_str = ""
        if "Found" in tool_schemas:
            tool_str = f"\n<available_mcp_tools>\n{tool_schemas}\n</available_mcp_tools>"

        # Combine all augmentations
        combined_augmentation = context_str + skill_str + tool_str

        if combined_augmentation.strip():
            has_system = False
            for msg in messages:
                if msg.get("role") == "system":
                    msg["content"] = build_grounded_system_prompt(msg["content"], combined_augmentation)
                    has_system = True
                    break
            if not has_system:
                grounded_prompt = build_grounded_system_prompt("", combined_augmentation)
                messages.insert(0, {"role": "system", "content": grounded_prompt})

    body["messages"] = messages
    target_url = f"{ROMS_UPSTREAM_LLM_URL}/chat/completions"

    # Start trajectory tracking
    if last_user_query:
        start_session(session_id=session_id, goal=last_user_query)

    if stream:
        async def stream_generator() -> AsyncGenerator[bytes, None]:
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    async with client.stream(
                        "POST", target_url, json=body, headers={"Content-Type": "application/json"}
                    ) as upstream_resp:
                        async for chunk in upstream_resp.aiter_bytes():
                            yield chunk
                finish_session(session_id=session_id, success=True, final_result="Streamed completion successfully")
            except Exception as e:
                err_payload = {"error": f"Upstream LLM connection error: {str(e)}"}
                yield f"data: {json.dumps(err_payload)}\n\n".encode("utf-8")
                yield b"data: [DONE]\n\n"
                finish_session(session_id=session_id, success=False, final_result=f"Stream error: {str(e)}")

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-ROMS-Session": session_id},
        )
    else:
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                upstream_resp = await client.post(
                    target_url, json=body, headers={"Content-Type": "application/json"}
                )
                if upstream_resp.status_code == 200:
                    resp_data = upstream_resp.json()
                    finish_session(session_id=session_id, success=True, final_result="Completed successfully")
                    return JSONResponse(resp_data, headers={"X-ROMS-Cache": "DISABLED", "X-ROMS-Session": session_id})

                return Response(
                    content=upstream_resp.content,
                    status_code=upstream_resp.status_code,
                    media_type="application/json",
                )
        except Exception as e:
            finish_session(session_id=session_id, success=False, final_result=f"Backend error: {str(e)}")
            return JSONResponse(
                {"error": f"Failed to connect to local LLM backend at {ROMS_UPSTREAM_LLM_URL}: {str(e)}"},
                status_code=502,
            )


async def health_check(request: Request) -> JSONResponse:
    """Health check and status endpoint."""
    from app.tools import get_system_metrics
    return JSONResponse({
        "status": "online",
        "service": "ROMS Smart Local LLM Gateway & Cartridge",
        "upstream_url": ROMS_UPSTREAM_LLM_URL,
        "completion_cache": "disabled",
        "metrics": get_system_metrics(),
    })


app.routes.extend([
    Route("/v1/models", list_models, methods=["GET"]),
    Route("/v1/chat/completions", chat_completions, methods=["POST"]),
    Route("/health", health_check, methods=["GET"]),
    Route("/", health_check, methods=["GET"]),
])


def start_gateway(port: int = ROMS_GATEWAY_PORT, host: str = "127.0.0.1"):
    """Launches the OpenAI-compatible RAG gateway."""
    import uvicorn
    from app.db import init_database
    from app.tool_rag import init_default_tool_registry
    from app.okf_loader import ingest_okf_directory
    from app.config import KNOWLEDGE_DIR
    init_database()
    init_default_tool_registry()
    ingest_okf_directory(KNOWLEDGE_DIR)
    print(f"[ROMS Gateway] Starting OpenAI-compatible Smart Cartridge on http://{host}:{port}/v1")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    start_gateway()
