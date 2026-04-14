import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 20
MAX_HTTP_RETRIES = 2
SUPPORTED_ACTION_TYPES = {"INVITE", "MESSAGE"}
MAX_INVITE_NOTE_LENGTH = 190

TASK_RUN_STATUSES = {"Queued", "Running", "Completed", "Failed", "Cancelled"}
TASK_RUN_APPROVAL_STATUSES = {"NotNeeded", "Pending", "Approved", "Rejected"}
TASK_ACTION_DRAFT_STATUSES = {"Draft", "Approved", "Rejected"}
TASK_ACTION_EXECUTION_STATUSES = {"Pending", "Success", "Failed", "Skipped"}


def build_response(ok: bool, data: Any = None, error: Optional[str] = None) -> str:
    return json.dumps({"ok": ok, "data": data, "error": error}, ensure_ascii=True)


def normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_json_payload(input_payload: str) -> Dict[str, Any]:
    if not input_payload:
        return {}
    try:
        parsed = json.loads(input_payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Input payload must be valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Input payload must decode to a JSON object.")
    return parsed


def validate_action(action_type: str, entity_id: str, content: str) -> Optional[str]:
    normalized_type = (action_type or "").strip().upper()
    if normalized_type not in SUPPORTED_ACTION_TYPES:
        return f"Unsupported action type: {action_type}"
    if not (entity_id or "").strip():
        return "Entity identifier is required."
    if normalized_type == "INVITE" and len((content or "").strip()) > MAX_INVITE_NOTE_LENGTH:
        return f"Invite content exceeds {MAX_INVITE_NOTE_LENGTH} characters."
    if not (content or "").strip():
        return "Content is required."
    return None


class HTTPService:
    def __init__(
        self,
        base_url: str = "",
        default_headers: Optional[Dict[str, str]] = None,
        timeout: int = REQUEST_TIMEOUT_SECONDS,
        retries: int = MAX_HTTP_RETRIES,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_headers = default_headers or {}
        self.timeout = timeout
        self.retries = retries
        self.session = requests.Session()

    def request(self, method: str, path: str = "", **kwargs: Any) -> requests.Response:
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        headers = dict(self.default_headers)
        headers.update(kwargs.pop("headers", {}))

        last_error: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    timeout=kwargs.pop("timeout", self.timeout),
                    **kwargs,
                )
                if response.status_code >= 500 and attempt < self.retries:
                    LOGGER.warning("Retrying %s %s after server error %s", method, url, response.status_code)
                    time.sleep(1 + attempt)
                    continue
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_error = exc
                retriable = isinstance(exc, (requests.Timeout, requests.ConnectionError))
                if retriable and attempt < self.retries:
                    LOGGER.warning("Retrying %s %s after transport error: %s", method, url, exc)
                    time.sleep(1 + attempt)
                    continue
                break
        assert last_error is not None
        raise last_error


class UnipileClient:
    def __init__(self) -> None:
        dsn = os.getenv("UNIPILE_DSN", "")
        token = os.getenv("UNIPILE_ACCESS_TOKEN", "")
        if dsn and ".com" in dsn:
            base_url = f"https://{dsn}/api/v1"
        elif dsn:
            base_url = f"https://{dsn}.unipile.com/api/v1"
        else:
            base_url = ""
        self.http = HTTPService(base_url=base_url, default_headers={"X-API-KEY": token, "Accept": "application/json"})
        self._account_id: Optional[str] = None

    def configured(self) -> bool:
        return bool(self.http.base_url and self.http.default_headers.get("X-API-KEY"))

    def _get_account_id(self) -> str:
        if self._account_id:
            return self._account_id
        response = self.http.request("GET", "/accounts")
        accounts = response.json().get("items", [])
        account_id = next((acc["id"] for acc in accounts if acc.get("type") == "LINKEDIN"), None)
        if not account_id:
            raise ValueError("No LinkedIn account connected to Unipile.")
        self._account_id = account_id
        return account_id

    def search_linkedin(self, keywords: str, location: str, target_count: int = 10) -> List[Dict[str, str]]:
        if not self.configured():
            raise ValueError("Unipile is not configured.")
        from urllib.parse import quote

        try:
            normalized_target_count = int(target_count)
        except (TypeError, ValueError):
            normalized_target_count = 10

        query = quote(f"{keywords} {location}".strip())
        payload = {"url": f"https://www.linkedin.com/search/results/people/?keywords={query}"}
        response = self.http.request(
            "POST",
            "/linkedin/search",
            params={"account_id": self._get_account_id()},
            json=payload,
        )
        items = response.json().get("items", [])
        results: List[Dict[str, str]] = []
        for item in items:
            if item.get("id") and item.get("name") and "LinkedIn Member" not in item.get("name", ""):
                results.append(
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "headline": item.get("headline", ""),
                        "location": item.get("location", ""),
                    }
                )
        if normalized_target_count > 0:
            return results[:normalized_target_count]
        return results

    def send_connection_request(self, profile_id: str, note: str) -> None:
        error = validate_action("INVITE", profile_id, note)
        if error:
            raise ValueError(error)
        payload = {"account_id": self._get_account_id(), "provider_id": profile_id, "message": note}
        self.http.request("POST", "/users/invite", json=payload)

    def send_linkedin_message(self, profile_id: str, text: str) -> None:
        error = validate_action("MESSAGE", profile_id, text)
        if error:
            raise ValueError(error)
        payload = {"account_id": self._get_account_id(), "attendees_ids": profile_id, "text": text}
        self.http.request("POST", "/chats", json=payload)


class SheetsClient:
    def __init__(self) -> None:
        apps_script_url = os.getenv("GOOGLE_APPS_SCRIPT_URL", "")
        self.http = HTTPService(base_url="", default_headers={"Accept": "application/json"})
        self.apps_script_url = apps_script_url

    def configured(self) -> bool:
        return bool(self.apps_script_url)

    def call(self, method_name: str, **payload: Any) -> Any:
        if not self.configured():
            raise ValueError("Google Apps Script URL is not configured.")
        body = {"method": method_name}
        body.update(payload)
        response = self.http.request("POST", self.apps_script_url, json=body, allow_redirects=True)
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            data = response.json()
        else:
            text = response.text.strip()
            data = json.loads(text) if text.startswith("{") or text.startswith("[") else {"message": text}

        if isinstance(data, dict) and data.get("ok") is False:
            raise ValueError(data.get("error") or f"Apps Script call failed: {method_name}")
        return data.get("data") if isinstance(data, dict) and "data" in data else data

    def list_task_definitions(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        return self.call("list_task_definitions", enabled_only=enabled_only)

    def create_task_run(self, task_key: str, input_payload: str, requested_by: str) -> Dict[str, Any]:
        parse_json_payload(input_payload)
        return self.call("create_task_run", task_key=task_key, input_payload=input_payload, requested_by=requested_by)

    def list_runnable_task_runs(self) -> List[Dict[str, Any]]:
        return self.call("list_runnable_task_runs")

    def get_task_run(self, run_id: str) -> Dict[str, Any]:
        return self.call("get_task_run", run_id=run_id)

    def list_task_runs(self, status: str = "", approval_status: str = "") -> List[Dict[str, Any]]:
        return self.call("list_task_runs", status=status, approval_status=approval_status)

    def start_task_run(self, run_id: str) -> Dict[str, Any]:
        return self.call("start_task_run", run_id=run_id)

    def complete_task_run(self, run_id: str, summary: str) -> Dict[str, Any]:
        return self.call("complete_task_run", run_id=run_id, summary=summary)

    def fail_task_run(self, run_id: str, error: str) -> Dict[str, Any]:
        return self.call("fail_task_run", run_id=run_id, error=error)

    def approve_task_run(self, run_id: str) -> Dict[str, Any]:
        return self.call("approve_task_run", run_id=run_id)

    def reject_task_run(self, run_id: str) -> Dict[str, Any]:
        return self.call("reject_task_run", run_id=run_id)

    def create_task_action(self, run_id: str, entity_id: str, action_type: str, content: str) -> Dict[str, Any]:
        error = validate_action(action_type, entity_id, content)
        if error:
            raise ValueError(error)
        return self.call(
            "create_task_action",
            run_id=run_id,
            entity_id=entity_id,
            action_type=action_type.upper(),
            content=content,
        )

    def list_task_actions(
        self,
        run_id: str,
        draft_status: str = "",
        execution_status: str = "",
    ) -> List[Dict[str, Any]]:
        return self.call(
            "list_task_actions",
            run_id=run_id,
            draft_status=draft_status,
            execution_status=execution_status,
        )

    def approve_task_actions(self, run_id: str = "", action_ids: str = "") -> Dict[str, Any]:
        return self.call("approve_task_actions", run_id=run_id, action_ids=action_ids)

    def mark_task_action_result(self, action_id: str, execution_status: str, error_message: str = "") -> Dict[str, Any]:
        if execution_status not in TASK_ACTION_EXECUTION_STATUSES:
            raise ValueError(f"Unsupported execution status: {execution_status}")
        return self.call(
            "mark_task_action_result",
            action_id=action_id,
            execution_status=execution_status,
            error_message=error_message,
        )

    def get_leads_by_status(self, status: str) -> List[Dict[str, Any]]:
        return self.call("get_leads_by_status", status=status)

    def update_lead_status(self, profile_id: str, new_status: str) -> Dict[str, Any]:
        return self.call("update_lead_status", profile_id=profile_id, new_status=new_status)


class TelegramNotifier:
    def __init__(self) -> None:
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        admin_id = os.getenv("TELEGRAM_ADMIN_ID", "")
        self.admin_id = admin_id
        self.http = HTTPService(base_url=f"https://api.telegram.org/bot{token}", default_headers={"Accept": "application/json"})

    def configured(self) -> bool:
        return bool(self.admin_id and self.http.base_url.rstrip("/").split("bot")[-1])

    def send_admin_message(self, text: str) -> Dict[str, Any]:
        if not self.configured():
            raise ValueError("Telegram is not configured.")
        response = self.http.request("POST", "/sendMessage", json={"chat_id": self.admin_id, "text": text})
        return response.json()


def resolve_instructions_text(instructions_value: str) -> str:
    if not instructions_value:
        raise ValueError("Task definition is missing instructions.")
    if instructions_value.startswith("prompt://"):
        prompt_name = instructions_value.replace("prompt://", "", 1).strip("/")
        prompt_path = Path(__file__).resolve().parent / "prompts" / prompt_name
        if not prompt_path.exists():
            raise ValueError(f"Prompt file not found: {prompt_path}")
        return prompt_path.read_text(encoding="utf-8")
    return instructions_value


def create_temp_instructions_file(run_id: str, task_key: str, instructions_text: str, input_payload: Dict[str, Any]) -> str:
    runtime_block = (
        "\n\n---\n"
        "Runtime Context\n"
        f"- Run ID: {run_id}\n"
        f"- Task Key: {task_key}\n"
        f"- Input Payload JSON: {json.dumps(input_payload, ensure_ascii=True)}\n"
        "Use the task-run and task-action tools to keep all work scoped to this run.\n"
    )
    handle = tempfile.NamedTemporaryFile(prefix=f"neocfo-{run_id}-", suffix=".md", delete=False)
    with handle:
        handle.write((instructions_text + runtime_block).encode("utf-8"))
    return handle.name
