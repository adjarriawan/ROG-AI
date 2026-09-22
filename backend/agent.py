from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from services.llm_service import SYSTEM_PROMPT, get_llm
from tools import rag_tool
from tools.ocr_tool import image_ocr
from tools.rag_tool import rag_search
from tools.sql_tool import sql_query

TOOLS = [rag_search, image_ocr, sql_query]

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
        agent = create_tool_calling_agent(get_llm(model), TOOLS, _prompt)
        _executors[model] = AgentExecutor(
            agent=agent,
            tools=TOOLS,
            return_intermediate_steps=True,
            max_iterations=4,
            max_execution_time=240,  # a model that loops on bad tool args must not hang the request
            handle_parsing_errors=True,
        )
    return _executors[model]


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
) -> dict:
    note = (
        f"Gambar terakhir yang diunggah user pada sesi ini: '{last_image}'. "
        "Gunakan nilai itu sebagai image_path bila user bertanya tentang gambar."
        if last_image
        else "Belum ada gambar yang diunggah pada sesi ini."
    )
    rag_tool.last_sources.clear()
    result = get_executor(model).invoke(
        {"input": message, "chat_history": to_messages(history), "context_note": note}
    )

    tools_used = [action.tool for action, _ in result.get("intermediate_steps", [])]
    return {
        "answer": result["output"],
        "tool_used": tools_used[-1] if tools_used else None,
        "sources": list(rag_tool.last_sources),
    }
