function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var method = data.method;
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    
    // METHOD 1: Fetch leads based on state
    if (method === "get_leads_by_status") {
      var sheet = ss.getSheetByName("Leads");
      var dataRange = sheet.getDataRange().getValues();
      var headers = dataRange[0];
      var statusColIndex = headers.indexOf("Status");
      
      var results = [];
      for (var i = 1; i < dataRange.length; i++) {
        if (dataRange[i][statusColIndex] === data.status) {
          var rowObj = {};
          for (var j = 0; j < headers.length; j++) {
            rowObj[headers[j]] = dataRange[i][j];
          }
          results.push(rowObj);
        }
      }
      return ContentService.createTextOutput(JSON.stringify(results)).setMimeType(ContentService.MimeType.JSON);
    }
    
    // METHOD 2: Draft new profiles awaiting clearance
    if (method === "draft_pending_action") {
      var sheet = ss.getSheetByName("Leads");
      sheet.appendRow([data.profile_id, data.action_type, data.content, "Pending Approval"]);
      return ContentService.createTextOutput("Draft saved successfully").setMimeType(ContentService.MimeType.TEXT);
    }
    
    // METHOD 3: Modify specific leads
    if (method === "update_lead_status") {
      var sheet = ss.getSheetByName("Leads");
      var dataRange = sheet.getDataRange().getValues();
      var headers = dataRange[0];
      var idColIndex = headers.indexOf("ProfileID");
      var statusColIndex = headers.indexOf("Status");
      
      for (var i = 1; i < dataRange.length; i++) {
        // If string matches exactly
        if (String(dataRange[i][idColIndex]) === String(data.profile_id)) {
          // Update the cell (row and col are 1-indexed in Apps script)
          sheet.getRange(i + 1, statusColIndex + 1).setValue(data.new_status);
          return ContentService.createTextOutput("Status updated to " + data.new_status).setMimeType(ContentService.MimeType.TEXT);
        }
      }
      return ContentService.createTextOutput("ProfileID not found").setMimeType(ContentService.MimeType.TEXT);
    }
    
    return ContentService.createTextOutput("Method not recognized").setMimeType(ContentService.MimeType.TEXT);
    
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({"error": String(error)})).setMimeType(ContentService.MimeType.JSON);
  }
}
