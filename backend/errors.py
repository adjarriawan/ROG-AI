"""Client-facing error messages.

Raw exception text used to be interpolated straight into HTTP responses and
into tool output read by the LLM. Postgres errors carry column names, types,
and sometimes row data; driver errors carry connection strings. The detail
belongs in the log, keyed by request id - not in the response.
"""

import logging

from observability.context import current_request_id

log = logging.getLogger("agentic_rag.errors")


def safe_detail(public_message: str, exc: BaseException, where: str) -> str:
    """Log the real cause, return something safe to show.

    The request id is included so a support request can be tied back to the
    exact log line without the user ever seeing the internals.
    """
    log.exception("%s failed: %s", where, type(exc).__name__)
    return f"{public_message} (ref: {current_request_id()})"


def tool_error(public_message: str, exc: BaseException, where: str) -> str:
    """Same, for text handed back to the model.

    Anything returned here enters the LLM context and may be echoed to the
    user, so it must not carry schema or driver detail either.
    """
    log.exception("%s failed: %s", where, type(exc).__name__)
    return public_message
