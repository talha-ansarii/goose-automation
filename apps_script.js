var LEADS_HEADERS = [
  "ProfileID",
  "Name",
  "Headline",
  "Location",
  "Status",
  "LastContactAt",
  "LastActionType",
  "LastActionResult",
  "Notes"
];

var TASK_DEFINITION_HEADERS = [
  "TaskKey",
  "TaskName",
  "Description",
  "Instructions",
  "Toolset",
  "InputSchemaHint",
  "RequiresApproval",
  "Enabled"
];

var TASK_RUN_HEADERS = [
  "RunID",
  "TaskKey",
  "InputPayload",
  "Status",
  "ApprovalStatus",
  "CreatedAt",
  "StartedAt",
  "FinishedAt",
  "Summary",
  "Error",
  "RequestedBy"
];

var TASK_ACTION_HEADERS = [
  "ActionID",
  "RunID",
  "EntityID",
  "ActionType",
  "Content",
  "DraftStatus",
  "ExecutionStatus",
  "ExecutionError",
  "CreatedAt",
  "ExecutedAt"
];

function doPost(e) {
  try {
    var data = JSON.parse((e.postData && e.postData.contents) || "{}");
    var method = data.method;
    var ss = SpreadsheetApp.getActiveSpreadsheet();

    ensureSheet(ss, "Leads", LEADS_HEADERS);
    ensureSheet(ss, "TaskDefinitions", TASK_DEFINITION_HEADERS);
    ensureSheet(ss, "TaskRuns", TASK_RUN_HEADERS);
    ensureSheet(ss, "TaskActions", TASK_ACTION_HEADERS);

    if (method === "get_leads_by_status") {
      return jsonResponse(listLeadsByStatus(ss, data.status));
    }

    if (method === "update_lead_status") {
      return jsonResponse(updateLeadStatus(ss, data.profile_id, data.new_status));
    }

    if (method === "list_task_definitions") {
      return jsonResponse(listTaskDefinitions(ss, data.enabled_only));
    }

    if (method === "create_task_run") {
      return jsonResponse(createTaskRun(ss, data.task_key, data.input_payload, data.requested_by));
    }

    if (method === "list_task_runs") {
      return jsonResponse(listTaskRuns(ss, data.status, data.approval_status));
    }

    if (method === "list_runnable_task_runs") {
      return jsonResponse(listRunnableTaskRuns(ss));
    }

    if (method === "get_task_run") {
      return jsonResponse(getTaskRun(ss, data.run_id));
    }

    if (method === "start_task_run") {
      return jsonResponse(startTaskRun(ss, data.run_id));
    }

    if (method === "complete_task_run") {
      return jsonResponse(completeTaskRun(ss, data.run_id, data.summary));
    }

    if (method === "fail_task_run") {
      return jsonResponse(failTaskRun(ss, data.run_id, data.error));
    }

    if (method === "create_task_action") {
      return jsonResponse(createTaskAction(ss, data.run_id, data.entity_id, data.action_type, data.content));
    }

    if (method === "list_task_actions") {
      return jsonResponse(listTaskActions(ss, data.run_id, data.draft_status, data.execution_status));
    }

    if (method === "approve_task_run") {
      return jsonResponse(approveTaskRun(ss, data.run_id));
    }

    if (method === "reject_task_run") {
      return jsonResponse(rejectTaskRun(ss, data.run_id));
    }

    if (method === "approve_task_actions") {
      return jsonResponse(approveTaskActions(ss, data.run_id, data.action_ids));
    }

    if (method === "mark_task_action_result") {
      return jsonResponse(markTaskActionResult(ss, data.action_id, data.execution_status, data.error_message));
    }

    throw new Error("Method not recognized: " + method);
  } catch (error) {
    return errorResponse(String(error));
  }
}

function ensureSheet(ss, sheetName, headers) {
  var sheet = ss.getSheetByName(sheetName);
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
  }
  if (sheet.getLastRow() === 0) {
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    return sheet;
  }
  var existingHeaders = sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), headers.length)).getValues()[0];
  if (!headersMatch(existingHeaders.slice(0, headers.length), headers)) {
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  }
  return sheet;
}

function headersMatch(currentHeaders, expectedHeaders) {
  if (currentHeaders.length !== expectedHeaders.length) {
    return false;
  }
  for (var i = 0; i < expectedHeaders.length; i++) {
    if (String(currentHeaders[i]) !== String(expectedHeaders[i])) {
      return false;
    }
  }
  return true;
}

function getSheetRecords(sheet) {
  var values = sheet.getDataRange().getValues();
  if (values.length < 2) {
    return [];
  }
  var headers = values[0];
  var rows = [];
  for (var i = 1; i < values.length; i++) {
    var row = {};
    for (var j = 0; j < headers.length; j++) {
      row[headers[j]] = values[i][j];
    }
    row.__rowNumber = i + 1;
    rows.push(row);
  }
  return rows;
}

function appendRecord(sheet, headers, record) {
  var row = [];
  for (var i = 0; i < headers.length; i++) {
    row.push(record[headers[i]] || "");
  }
  sheet.appendRow(row);
  record.__rowNumber = sheet.getLastRow();
  return record;
}

function updateRecord(sheet, headers, rowNumber, updates) {
  for (var i = 0; i < headers.length; i++) {
    var key = headers[i];
    if (updates.hasOwnProperty(key)) {
      sheet.getRange(rowNumber, i + 1).setValue(updates[key]);
    }
  }
}

function normalizeBool(value) {
  var normalized = String(value).toLowerCase();
  return normalized === "true" || normalized === "1" || normalized === "yes";
}

function isoNow() {
  return new Date().toISOString();
}

function listLeadsByStatus(ss, status) {
  var sheet = ss.getSheetByName("Leads");
  var rows = getSheetRecords(sheet);
  var results = [];
  for (var i = 0; i < rows.length; i++) {
    if (String(rows[i].Status) === String(status)) {
      results.push(stripInternalKeys(rows[i]));
    }
  }
  return results;
}

function updateLeadStatus(ss, profileId, newStatus) {
  var sheet = ss.getSheetByName("Leads");
  var rows = getSheetRecords(sheet);
  for (var i = 0; i < rows.length; i++) {
    if (String(rows[i].ProfileID) === String(profileId)) {
      updateRecord(sheet, LEADS_HEADERS, rows[i].__rowNumber, {
        Status: newStatus,
        LastContactAt: isoNow(),
        LastActionResult: newStatus
      });
      return { message: "Lead updated", profile_id: profileId, status: newStatus };
    }
  }
  throw new Error("ProfileID not found: " + profileId);
}

function listTaskDefinitions(ss, enabledOnly) {
  var sheet = ss.getSheetByName("TaskDefinitions");
  var rows = getSheetRecords(sheet);
  var results = [];
  for (var i = 0; i < rows.length; i++) {
    if (normalizeBool(enabledOnly) && !normalizeBool(rows[i].Enabled)) {
      continue;
    }
    results.push(stripInternalKeys(rows[i]));
  }
  return results;
}

function listTaskRuns(ss, status, approvalStatus) {
  var sheet = ss.getSheetByName("TaskRuns");
  var rows = getSheetRecords(sheet);
  var results = [];
  for (var i = 0; i < rows.length; i++) {
    if (status && String(rows[i].Status) !== String(status)) {
      continue;
    }
    if (approvalStatus && String(rows[i].ApprovalStatus) !== String(approvalStatus)) {
      continue;
    }
    results.push(enrichTaskRun(ss, rows[i]));
  }
  return results;
}

function listRunnableTaskRuns(ss) {
  var rows = listTaskRuns(ss, "Queued", "");
  var results = [];
  for (var i = 0; i < rows.length; i++) {
    var approvalStatus = String(rows[i].ApprovalStatus);
    if ((approvalStatus === "Approved" || approvalStatus === "NotNeeded") && normalizeBool(rows[i].TaskDefinition.Enabled)) {
      results.push(rows[i]);
    }
  }
  return results;
}

function getTaskRun(ss, runId) {
  var sheet = ss.getSheetByName("TaskRuns");
  var rows = getSheetRecords(sheet);
  for (var i = 0; i < rows.length; i++) {
    if (String(rows[i].RunID) === String(runId)) {
      return enrichTaskRun(ss, rows[i]);
    }
  }
  throw new Error("RunID not found: " + runId);
}

function getTaskDefinitionByKey(ss, taskKey) {
  var sheet = ss.getSheetByName("TaskDefinitions");
  var rows = getSheetRecords(sheet);
  for (var i = 0; i < rows.length; i++) {
    if (String(rows[i].TaskKey) === String(taskKey)) {
      return rows[i];
    }
  }
  throw new Error("Task definition not found for TaskKey: " + taskKey);
}

function createTaskRun(ss, taskKey, inputPayload, requestedBy) {
  var taskDefinition = getTaskDefinitionByKey(ss, taskKey);
  if (!normalizeBool(taskDefinition.Enabled)) {
    throw new Error("Task definition is disabled: " + taskKey);
  }

  var run = {
    RunID: Utilities.getUuid(),
    TaskKey: taskKey,
    InputPayload: inputPayload || "{}",
    Status: "Queued",
    ApprovalStatus: normalizeBool(taskDefinition.RequiresApproval) ? "Pending" : "NotNeeded",
    CreatedAt: isoNow(),
    StartedAt: "",
    FinishedAt: "",
    Summary: "",
    Error: "",
    RequestedBy: requestedBy || "system"
  };

  appendRecord(ss.getSheetByName("TaskRuns"), TASK_RUN_HEADERS, run);
  return enrichTaskRun(ss, run);
}

function startTaskRun(ss, runId) {
  var sheet = ss.getSheetByName("TaskRuns");
  var rows = getSheetRecords(sheet);
  for (var i = 0; i < rows.length; i++) {
    if (String(rows[i].RunID) !== String(runId)) {
      continue;
    }
    if (String(rows[i].Status) !== "Queued") {
      throw new Error("Run is not queued: " + runId);
    }
    if (String(rows[i].ApprovalStatus) !== "Approved" && String(rows[i].ApprovalStatus) !== "NotNeeded") {
      throw new Error("Run is not approved: " + runId);
    }
    updateRecord(sheet, TASK_RUN_HEADERS, rows[i].__rowNumber, {
      Status: "Running",
      StartedAt: isoNow(),
      Error: ""
    });
    return getTaskRun(ss, runId);
  }
  throw new Error("RunID not found: " + runId);
}

function completeTaskRun(ss, runId, summary) {
  var sheet = ss.getSheetByName("TaskRuns");
  var rows = getSheetRecords(sheet);
  for (var i = 0; i < rows.length; i++) {
    if (String(rows[i].RunID) === String(runId)) {
      updateRecord(sheet, TASK_RUN_HEADERS, rows[i].__rowNumber, {
        Status: "Completed",
        FinishedAt: isoNow(),
        Summary: summary || "",
        Error: ""
      });
      return getTaskRun(ss, runId);
    }
  }
  throw new Error("RunID not found: " + runId);
}

function failTaskRun(ss, runId, errorMessage) {
  var sheet = ss.getSheetByName("TaskRuns");
  var rows = getSheetRecords(sheet);
  for (var i = 0; i < rows.length; i++) {
    if (String(rows[i].RunID) === String(runId)) {
      updateRecord(sheet, TASK_RUN_HEADERS, rows[i].__rowNumber, {
        Status: "Failed",
        FinishedAt: isoNow(),
        Error: errorMessage || "Unknown error"
      });
      return getTaskRun(ss, runId);
    }
  }
  throw new Error("RunID not found: " + runId);
}

function createTaskAction(ss, runId, entityId, actionType, content) {
  getTaskRun(ss, runId);
  var action = {
    ActionID: Utilities.getUuid(),
    RunID: runId,
    EntityID: entityId || "",
    ActionType: String(actionType || "").toUpperCase(),
    Content: content || "",
    DraftStatus: "Draft",
    ExecutionStatus: "Pending",
    ExecutionError: "",
    CreatedAt: isoNow(),
    ExecutedAt: ""
  };

  appendRecord(ss.getSheetByName("TaskActions"), TASK_ACTION_HEADERS, action);
  return stripInternalKeys(action);
}

function listTaskActions(ss, runId, draftStatus, executionStatus) {
  var sheet = ss.getSheetByName("TaskActions");
  var rows = getSheetRecords(sheet);
  var results = [];
  for (var i = 0; i < rows.length; i++) {
    if (String(rows[i].RunID) !== String(runId)) {
      continue;
    }
    if (draftStatus && String(rows[i].DraftStatus) !== String(draftStatus)) {
      continue;
    }
    if (executionStatus && String(rows[i].ExecutionStatus) !== String(executionStatus)) {
      continue;
    }
    results.push(stripInternalKeys(rows[i]));
  }
  return results;
}

function getTaskActionById(ss, actionId) {
  var sheet = ss.getSheetByName("TaskActions");
  var rows = getSheetRecords(sheet);
  for (var i = 0; i < rows.length; i++) {
    if (String(rows[i].ActionID) === String(actionId)) {
      return stripInternalKeys(rows[i]);
    }
  }
  throw new Error("ActionID not found: " + actionId);
}

function approveTaskRun(ss, runId) {
  var sheet = ss.getSheetByName("TaskRuns");
  var rows = getSheetRecords(sheet);
  for (var i = 0; i < rows.length; i++) {
    if (String(rows[i].RunID) === String(runId)) {
      updateRecord(sheet, TASK_RUN_HEADERS, rows[i].__rowNumber, {
        ApprovalStatus: "Approved"
      });
      approveTaskActions(ss, runId, "");
      return getTaskRun(ss, runId);
    }
  }
  throw new Error("RunID not found: " + runId);
}

function rejectTaskRun(ss, runId) {
  var sheet = ss.getSheetByName("TaskRuns");
  var rows = getSheetRecords(sheet);
  for (var i = 0; i < rows.length; i++) {
    if (String(rows[i].RunID) === String(runId)) {
      updateRecord(sheet, TASK_RUN_HEADERS, rows[i].__rowNumber, {
        ApprovalStatus: "Rejected"
      });
      setTaskActionDraftStatus(ss, function(action) {
        return String(action.RunID) === String(runId) && String(action.DraftStatus) === "Draft";
      }, "Rejected");
      return getTaskRun(ss, runId);
    }
  }
  throw new Error("RunID not found: " + runId);
}

function approveTaskActions(ss, runId, actionIds) {
  var actionIdLookup = {};
  var updated = 0;
  if (actionIds) {
    var splitIds = String(actionIds).split(",");
    for (var i = 0; i < splitIds.length; i++) {
      actionIdLookup[String(splitIds[i]).trim()] = true;
    }
  }

  updated = setTaskActionDraftStatus(ss, function(action) {
    if (runId) {
      return String(action.RunID) === String(runId) && String(action.DraftStatus) === "Draft";
    }
    return !!actionIdLookup[String(action.ActionID)] && String(action.DraftStatus) === "Draft";
  }, "Approved");

  return { updated_count: updated };
}

function setTaskActionDraftStatus(ss, predicate, nextStatus) {
  var sheet = ss.getSheetByName("TaskActions");
  var rows = getSheetRecords(sheet);
  var updated = 0;
  for (var i = 0; i < rows.length; i++) {
    if (predicate(rows[i])) {
      updateRecord(sheet, TASK_ACTION_HEADERS, rows[i].__rowNumber, {
        DraftStatus: nextStatus
      });
      updated++;
    }
  }
  return updated;
}

function markTaskActionResult(ss, actionId, executionStatus, errorMessage) {
  var sheet = ss.getSheetByName("TaskActions");
  var rows = getSheetRecords(sheet);
  for (var i = 0; i < rows.length; i++) {
    if (String(rows[i].ActionID) === String(actionId)) {
      updateRecord(sheet, TASK_ACTION_HEADERS, rows[i].__rowNumber, {
        ExecutionStatus: executionStatus,
        ExecutionError: errorMessage || "",
        ExecutedAt: executionStatus === "Pending" ? "" : isoNow()
      });
      return getTaskActionById(ss, actionId);
    }
  }
  throw new Error("ActionID not found: " + actionId);
}

function enrichTaskRun(ss, run) {
  var enriched = stripInternalKeys(run);
  enriched.TaskDefinition = stripInternalKeys(getTaskDefinitionByKey(ss, run.TaskKey));
  return enriched;
}

function stripInternalKeys(record) {
  var clean = {};
  for (var key in record) {
    if (record.hasOwnProperty(key) && key.indexOf("__") !== 0) {
      clean[key] = record[key];
    }
  }
  return clean;
}

function jsonResponse(data) {
  return ContentService
    .createTextOutput(JSON.stringify({ ok: true, data: data, error: null }))
    .setMimeType(ContentService.MimeType.JSON);
}

function errorResponse(message) {
  return ContentService
    .createTextOutput(JSON.stringify({ ok: false, data: null, error: message }))
    .setMimeType(ContentService.MimeType.JSON);
}
