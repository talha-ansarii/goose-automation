import unittest

from agent_skills import _normalize_tool_inputs
from neocfo_core import (
    MAX_INVITE_NOTE_LENGTH,
    UnipileClient,
    parse_json_payload,
    resolve_instructions_text,
    validate_action,
)
from neocfo_workflows import create_follow_on_run_for_approval
from task_dispatcher import select_run


class FakeSheets:
    def __init__(self, run=None, runnable=None):
        self._run = run or {}
        self._runnable = runnable or []

    def get_task_run(self, run_id):
        return dict(self._run, RunID=run_id)

    def list_runnable_task_runs(self):
        return list(self._runnable)


class FakeBridgeSheets:
    def __init__(self):
        self.approved = []
        self.created = []

    def approve_task_run(self, run_id):
        self.approved.append(run_id)
        return {"RunID": run_id}

    def create_task_run(self, task_key, input_payload, requested_by):
        self.created.append((task_key, input_payload, requested_by))
        return {"RunID": "executor-run-1", "TaskKey": task_key}

    def get_task_run(self, run_id):
        return {"RunID": run_id, "TaskKey": "linkedin_outreach_executor", "Status": "Queued"}


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class FakeUnipileHTTP:
    base_url = "https://example.com"
    default_headers = {"X-API-KEY": "token"}

    def request(self, method, path, **kwargs):
        return FakeResponse(
            {
                "items": [
                    {"id": "1", "name": "Alice", "headline": "CFO", "location": "India"},
                    {"id": "2", "name": "Bob", "headline": "Head of Finance", "location": "India"},
                ]
            }
        )


class ValidationTests(unittest.TestCase):
    def test_invite_length_over_limit_is_rejected(self):
        note = "x" * (MAX_INVITE_NOTE_LENGTH + 1)
        self.assertIn("exceeds", validate_action("INVITE", "profile-1", note))

    def test_missing_entity_id_is_rejected(self):
        self.assertEqual("Entity identifier is required.", validate_action("MESSAGE", "", "hello"))

    def test_invalid_payload_raises(self):
        with self.assertRaises(ValueError):
            parse_json_payload('["not","an","object"]')

    def test_prompt_reference_resolves(self):
        prompt = resolve_instructions_text("prompt://linkedin_outreach_planner.md")
        self.assertIn("create_task_action", prompt)

    def test_search_linkedin_accepts_string_target_count(self):
        client = UnipileClient()
        client.http = FakeUnipileHTTP()
        client._account_id = "account-1"
        results = client.search_linkedin("CFO", "India", target_count="1")
        self.assertEqual(1, len(results))

    def test_tool_input_normalizer_handles_stringified_list_args(self):
        params = _normalize_tool_inputs(
            ["keywords", "location", "target_count"],
            args='["CFO", "India", 10]',
            kwargs="{}",
        )
        self.assertEqual("CFO", params["keywords"])
        self.assertEqual("India", params["location"])
        self.assertEqual(10, params["target_count"])

    def test_tool_input_normalizer_handles_stringified_kwargs(self):
        params = _normalize_tool_inputs(
            ["keywords", "location", "target_count"],
            args="[]",
            kwargs='{"keywords":"CFO","location":"India","target_count":5}',
        )
        self.assertEqual("CFO", params["keywords"])
        self.assertEqual("India", params["location"])
        self.assertEqual(5, params["target_count"])

    def test_tool_input_normalizer_preserves_message_alias(self):
        params = _normalize_tool_inputs(
            ["summary_text"],
            args="[]",
            kwargs='{"message":"hello admin"}',
        )
        self.assertEqual("hello admin", params["message"])


class DispatcherSelectionTests(unittest.TestCase):
    def test_specific_run_must_be_queued(self):
        sheets = FakeSheets(run={"Status": "Completed", "ApprovalStatus": "Approved"})
        with self.assertRaises(ValueError):
            select_run(sheets, "run-1")

    def test_specific_run_must_be_approved(self):
        sheets = FakeSheets(run={"Status": "Queued", "ApprovalStatus": "Pending"})
        with self.assertRaises(ValueError):
            select_run(sheets, "run-2")

    def test_selects_oldest_runnable_run(self):
        sheets = FakeSheets(
            runnable=[
                {"RunID": "newer", "TaskKey": "a", "CreatedAt": "2026-04-15T11:00:00Z"},
                {"RunID": "older", "TaskKey": "b", "CreatedAt": "2026-04-15T10:00:00Z"},
            ]
        )
        selected = select_run(sheets)
        self.assertEqual("older", selected["RunID"])


class ApprovalBridgeTests(unittest.TestCase):
    def test_completed_planner_creates_executor_run(self):
        fake_sheets = FakeBridgeSheets()
        planner_run = {"RunID": "planner-1", "TaskKey": "linkedin_outreach_planner", "Status": "Completed"}
        follow_on = create_follow_on_run_for_approval(fake_sheets, planner_run, requested_by="telegram:admin-1")
        self.assertEqual("executor-run-1", follow_on["RunID"])
        self.assertEqual(["planner-1", "executor-run-1"], fake_sheets.approved)
        self.assertEqual("linkedin_outreach_executor", fake_sheets.created[0][0])


if __name__ == "__main__":
    unittest.main()
