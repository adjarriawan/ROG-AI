"""Request correlation id, carried across threads via contextvars.

/chat hands work to asyncio.to_thread; a plain global would mix requests up,
exactly like the citation bug this replaced.
"""

from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def current_request_id() -> str:
    return request_id_var.get()
