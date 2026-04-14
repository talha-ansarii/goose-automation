import logging
import ast
import json
from typing import Any, Dict, List

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - fallback for local tests without MCP installed
    class FastMCP:  # type: ignore[override]
        def __init__(self, _name: str) -> None:
            self.name = _name

        def tool(self):
            def decorator(func):
                return func

            return decorator

        def run(self) -> None:
            raise RuntimeError("FastMCP is not installed.")

from neocfo_core import SheetsClient, TelegramNotifier, UnipileClient, build_response

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s %(message)s", level=logging.INFO)
LOGGER = logging.getLogger(__name__)

mcp = FastMCP("NeoCFOSkills")
unipile = UnipileClient()
sheets = SheetsClient()
telegram = TelegramNotifier()


def tool_guard(fn):
    def wrapped(*args, **kwargs):
        try:
            data = fn(*args, **kwargs)
            return build_response(True, data=data)
        except Exception as exc:  # pragma: no cover - exercised via tool callers
            LOGGER.exception("Tool %s failed", fn.__name__)
            return build_response(False, error=str(exc))

    wrapped.__name__ = fn.__name__
    wrapped.__doc__ = fn.__doc__
    return wrapped


def _decode_loose(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list, int, float, bool)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text in {"", "{}", "[]", "null", '""', "''"}:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        if "=" in text:
            parts = [part.strip() for part in text.split(",") if part.strip()]
            parsed: Dict[str, Any] = {}
            for part in parts:
                if "=" not in part:
                    continue
                key, raw_val = part.split("=", 1)
                key = key.strip()
                raw_val = raw_val.strip()
                try:
                    parsed[key] = ast.literal_eval(raw_val)
                except Exception:
                    parsed[key] = raw_val.strip("\"'")
            if parsed:
                return parsed
        return text
    return value


def _normalize_tool_inputs(
    positional_names: List[str],
    args: Any = None,
    kwargs: Any = None,
    **named: Any,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {}

    decoded_kwargs = _decode_loose(kwargs)
    if isinstance(decoded_kwargs, dict):
        result.update(decoded_kwargs)

    decoded_args = _decode_loose(args)
    if isinstance(decoded_args, dict):
        result.update(decoded_args)
    elif isinstance(decoded_args, list):
        for idx, name in enumerate(positional_names):
            if idx < len(decoded_args):
                result[name] = decoded_args[idx]
    elif decoded_args is not None and positional_names:
        if len(positional_names) == 1:
            result[positional_names[0]] = decoded_args
        else:
            pieces = [piece.strip() for piece in str(decoded_args).split(",")]
            if len(pieces) >= len(positional_names):
                for idx, name in enumerate(positional_names):
                    result[name] = pieces[idx]

    for key, value in named.items():
        decoded_value = _decode_loose(value)
        if decoded_value is None:
            continue
        if key == "kwargs" and isinstance(decoded_value, dict):
            result.update(decoded_value)
            continue
        if key == "args":
            continue
        if isinstance(decoded_value, dict) and key in positional_names:
            result.update(decoded_value)
            continue
        result[key] = decoded_value

    return result


@mcp.tool()
@tool_guard
def list_task_definitions(enabled_only: Any = "true", args: Any = None, kwargs: Any = None) -> object:
    """Lists registered task definitions."""
    params = _normalize_tool_inputs(["enabled_only"], args=args, kwargs=kwargs, enabled_only=enabled_only)
    return sheets.list_task_definitions(enabled_only=params.get("enabled_only", True))


@mcp.tool()
@tool_guard
def create_task_run(task_key: str, input_payload: str = "{}", requested_by: str = "system") -> object:
    """Creates a task run with queued or approval-pending state."""
    return sheets.create_task_run(task_key=task_key, input_payload=input_payload, requested_by=requested_by)


@mcp.tool()
@tool_guard
def list_runnable_task_runs() -> object:
    """Lists queued task runs that are approved or do not need approval."""
    return sheets.list_runnable_task_runs()


@mcp.tool()
@tool_guard
def list_task_runs(status: Any = "", approval_status: Any = "", args: Any = None, kwargs: Any = None) -> object:
    """Lists task runs by optional status filters."""
    params = _normalize_tool_inputs(
        ["status", "approval_status"],
        args=args,
        kwargs=kwargs,
        status=status,
        approval_status=approval_status,
    )
    normalized_status = str(params.get("status", "")).strip()
    if normalized_status.lower() == "queued":
        normalized_status = "Queued"
    return sheets.list_task_runs(
        status=normalized_status,
        approval_status=str(params.get("approval_status", "")).strip(),
    )


@mcp.tool()
@tool_guard
def get_task_run(run_id: Any = "", args: Any = None, kwargs: Any = None) -> object:
    """Fetches one task run with task definition details."""
    params = _normalize_tool_inputs(["run_id"], args=args, kwargs=kwargs, run_id=run_id)
    return sheets.get_task_run(run_id=str(params.get("run_id", "")).strip())


@mcp.tool()
@tool_guard
def start_task_run(run_id: str) -> object:
    """Moves a queued task run to running."""
    return sheets.start_task_run(run_id=run_id)


@mcp.tool()
@tool_guard
def complete_task_run(run_id: str, summary: str) -> object:
    """Marks a task run as completed."""
    return sheets.complete_task_run(run_id=run_id, summary=summary)


@mcp.tool()
@tool_guard
def fail_task_run(run_id: str, error: str) -> object:
    """Marks a task run as failed."""
    return sheets.fail_task_run(run_id=run_id, error=error)


@mcp.tool()
@tool_guard
def approve_task_run(run_id: str) -> object:
    """Approves one task run and all of its draft actions."""
    return sheets.approve_task_run(run_id=run_id)


@mcp.tool()
@tool_guard
def reject_task_run(run_id: str) -> object:
    """Rejects one task run and all of its draft actions."""
    return sheets.reject_task_run(run_id=run_id)


@mcp.tool()
@tool_guard
def create_task_action(
    run_id: Any = "",
    entity_id: Any = "",
    action_type: Any = "",
    content: Any = "",
    args: Any = None,
    kwargs: Any = None,
) -> object:
    """Creates one task action linked to a task run."""
    params = _normalize_tool_inputs(
        ["run_id", "entity_id", "action_type", "content"],
        args=args,
        kwargs=kwargs,
        run_id=run_id,
        entity_id=entity_id,
        action_type=action_type,
        content=content,
    )
    return sheets.create_task_action(
        run_id=str(params.get("run_id", "")).strip(),
        entity_id=str(params.get("entity_id", "")).strip(),
        action_type=str(params.get("action_type", "")).strip(),
        content=str(params.get("content", "")).strip(),
    )


@mcp.tool()
@tool_guard
def list_task_actions(
    run_id: Any = "",
    draft_status: Any = "",
    execution_status: Any = "",
    args: Any = None,
    kwargs: Any = None,
) -> object:
    """Lists task actions for one run."""
    params = _normalize_tool_inputs(
        ["run_id", "draft_status", "execution_status"],
        args=args,
        kwargs=kwargs,
        run_id=run_id,
        draft_status=draft_status,
        execution_status=execution_status,
    )
    return sheets.list_task_actions(
        run_id=str(params.get("run_id", "")).strip(),
        draft_status=str(params.get("draft_status", "")).strip(),
        execution_status=str(params.get("execution_status", "")).strip(),
    )


@mcp.tool()
@tool_guard
def approve_task_actions(run_id: str = "", action_ids: str = "") -> object:
    """Approves draft actions for one run or explicit action ids."""
    return sheets.approve_task_actions(run_id=run_id, action_ids=action_ids)


@mcp.tool()
@tool_guard
def mark_task_action_result(
    action_id: Any = "",
    execution_status: Any = "",
    error_message: Any = "",
    args: Any = None,
    kwargs: Any = None,
) -> object:
    """Marks a task action execution result."""
    params = _normalize_tool_inputs(
        ["action_id", "execution_status", "error_message"],
        args=args,
        kwargs=kwargs,
        action_id=action_id,
        execution_status=execution_status,
        error_message=error_message,
    )
    return sheets.mark_task_action_result(
        action_id=str(params.get("action_id", "")).strip(),
        execution_status=str(params.get("execution_status", "")).strip(),
        error_message=str(params.get("error_message", "")).strip(),
    )


@mcp.tool()
@tool_guard
def search_linkedin(
    keywords: Any = "",
    location: Any = "",
    target_count: Any = 10,
    args: Any = None,
    kwargs: Any = None,
) -> object:
    """Searches LinkedIn profiles via Unipile."""
    params = _normalize_tool_inputs(
        ["keywords", "location", "target_count"],
        args=args,
        kwargs=kwargs,
        keywords=keywords,
        location=location,
        target_count=target_count,
    )
    return unipile.search_linkedin(
        keywords=str(params.get("keywords", "")).strip(),
        location=str(params.get("location", "")).strip(),
        target_count=params.get("target_count", 10),
    )


@mcp.tool()
@tool_guard
def send_connection_request(profile_id: Any = "", note: Any = "", args: Any = None, kwargs: Any = None) -> object:
    """Sends a LinkedIn connection request after validation."""
    params = _normalize_tool_inputs(["profile_id", "note"], args=args, kwargs=kwargs, profile_id=profile_id, note=note)
    unipile.send_connection_request(
        profile_id=str(params.get("profile_id", "")).strip(),
        note=str(params.get("note", "")).strip(),
    )
    return {"message": "Connection request successful."}


@mcp.tool()
@tool_guard
def send_linkedin_message(profile_id: Any = "", text: Any = "", args: Any = None, kwargs: Any = None) -> object:
    """Sends a LinkedIn message after validation."""
    params = _normalize_tool_inputs(["profile_id", "text"], args=args, kwargs=kwargs, profile_id=profile_id, text=text)
    unipile.send_linkedin_message(
        profile_id=str(params.get("profile_id", "")).strip(),
        text=str(params.get("text", "")).strip(),
    )
    return {"message": "Message sent successfully."}


@mcp.tool()
@tool_guard
def get_leads_by_status(status: Any = "", args: Any = None, kwargs: Any = None) -> object:
    """Fetches leads from the CRM by status."""
    params = _normalize_tool_inputs(["status"], args=args, kwargs=kwargs, status=status)
    return sheets.get_leads_by_status(status=str(params.get("status", "")).strip())


@mcp.tool()
@tool_guard
def update_lead_status(profile_id: Any = "", new_status: Any = "", args: Any = None, kwargs: Any = None) -> object:
    """Updates a lead status in the CRM sheet."""
    params = _normalize_tool_inputs(
        ["profile_id", "new_status"],
        args=args,
        kwargs=kwargs,
        profile_id=profile_id,
        new_status=new_status,
    )
    return sheets.update_lead_status(
        profile_id=str(params.get("profile_id", "")).strip(),
        new_status=str(params.get("new_status", "")).strip(),
    )


@mcp.tool()
@tool_guard
def notify_human_for_approval(summary_text: Any = "", args: Any = None, kwargs: Any = None) -> object:
    """Sends a Telegram notification to the configured admin."""
    params = _normalize_tool_inputs(["summary_text"], args=args, kwargs=kwargs, summary_text=summary_text)
    message = params.get("summary_text")
    if not message:
        message = params.get("message")
    if not message:
        message = params.get("text")
    return telegram.send_admin_message(str(message or "").strip())


if __name__ == "__main__":
    mcp.run()
