import logging
import time
from typing import TypedDict

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from config import get_settings
from services.llm_service import SYSTEM_PROMPT, get_llm
from tools import knowledge_tool, rag_tool
from tools.knowledge_tool import knowledge_search, remember_fact
from tools.ocr_tool import image_ocr
from tools.rag_tool import rag_search
from tools.sql_tool import sql_query

log = logging.getLogger("agentic_rag.agent")

TOOLS = [rag_search, image_ocr, sql_query, knowledge_search, remember_fact]

_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT + "\n\n{context_note}"),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ]
)

_executors: dict[str | None, AgentExecutor] = {}


def get_executor(model: str | None = None) -> AgentExecutor:
    """One executor per model, built on first use and reused after."""
    if model not in _executors:
        s = get_settings()
        agent = create_tool_calling_agent(get_llm(model), TOOLS, _prompt)
        _executors[model] = AgentExecutor(
            agent=agent,
            tools=TOOLS,
            return_intermediate_steps=True,
            max_iterations=s.agent_max_iterations,
            # a model that loops on bad tool args must not hang the request
            max_execution_time=s.agent_timeout_seconds,
            handle_parsing_errors=True,
        )
    return _executors[model]


class ToolCall(TypedDict):
    tool: str
    duration_ms: int


class AgentResult(TypedDict):
    answer: str
    tool_used: str | None
    tools_used: list[str]
    tool_calls: list[ToolCall]
    sources: list[rag_tool.Citation]
    duration_ms: int


def to_messages(history: list) -> list:
    out = []
    for h in history:
        if h.role == "user":
            out.append(HumanMessage(content=h.message))
        elif h.role == "assistant":
            out.append(AIMessage(content=h.message))
    return out


def run_agent(
    message: str,
    history: list,
    last_image: str | None = None,
    model: str | None = None,
    session_id: str | None = None,
) -> AgentResult:
    note = (
        f"User BARU SAJA mengunggah gambar '{last_image}' pada sesi ini. "
        "Bila pertanyaan user bisa dijawab dari isi gambar itu - termasuk "
        "pertanyaan singkat atau ambigu seperti 'berapa totalnya?' - panggil "
        "image_ocr dengan image_path tersebut lebih dulu, jangan balik bertanya."
        if last_image
        else "Belum ada gambar yang diunggah pada sesi ini."
    )
    rag_tool.reset_sources()
    # Which session a proposed fact came from is ours to decide, not the model's.
    knowledge_tool.set_session(session_id)
    started = time.perf_counter()
    result = get_executor(model).invoke(
        {"input": message, "chat_history": to_messages(history), "context_note": note}
    )
    duration_ms = int((time.perf_counter() - started) * 1000)

    steps = result.get("intermediate_steps", [])
    tools_used = [action.tool for action, _ in steps]
    # Per-call duration is not exposed by AgentExecutor; the total is, so record
    # the tool sequence and the run total rather than inventing per-tool numbers.
    calls: list[ToolCall] = [ToolCall(tool=t, duration_ms=-1) for t in tools_used]

    log.info(
        "agent run model=%s tools=%s duration_ms=%d sources=%d",
        model or "default",
        ",".join(tools_used) or "-",
        duration_ms,
        len(rag_tool.get_sources()),
    )

    return AgentResult(
        answer=result["output"],
        # tool_used keeps the README's single-value contract; tools_used is the
        # complete sequence, which is what an audit trail actually needs.
        tool_used=tools_used[-1] if tools_used else None,
        tools_used=tools_used,
        tool_calls=calls,
        sources=rag_tool.get_sources(),
        duration_ms=duration_ms,
    )
