import os
import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Load environment variables
load_dotenv()

UNIPILE_DSN = os.getenv("UNIPILE_DSN")
UNIPILE_TOKEN = os.getenv("UNIPILE_ACCESS_TOKEN")
# If the DSN contains .com, don't append it again
UNIPILE_URL = f"https://{UNIPILE_DSN}/api/v1" if (UNIPILE_DSN and ".com" in UNIPILE_DSN) else (f"https://{UNIPILE_DSN}.unipile.com/api/v1" if UNIPILE_DSN else "")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")

# Initialize MCP Server
mcp = FastMCP("NeoCFOSkills")

# --- UNIPILE API TOOLS ---

@mcp.tool()
def search_linkedin(keywords: str, location: str) -> str:
    """Searches for LinkedIn profiles via Unipile."""
    headers = {"X-API-KEY": UNIPILE_TOKEN, "Accept": "application/json"}
    try:
        # 1. Dynamically fetch the LinkedIn Account ID from Unipile
        acc_resp = requests.get(f"{UNIPILE_URL}/accounts", headers=headers)
        acc_resp.raise_for_status()
        accounts = acc_resp.json().get("items", [])
        account_id = None
        for acc in accounts:
            if acc.get("type") == "LINKEDIN":
                account_id = acc.get("id")
                break
        if not account_id:
            return "Error: No LinkedIn account connected to Unipile."

        # 2. Use the "Search from URL" method to bypass complex nested JSON schemas
        # URL encode spaces by replacing them with %20, though requests handles raw string formatting reasonably well
        from urllib.parse import quote
        query = quote(f"{keywords} {location}")
        payload = {"url": f"https://www.linkedin.com/search/results/people/?keywords={query}"}
        
        response = requests.post(
            f"{UNIPILE_URL}/linkedin/search", 
            headers=headers, 
            params={"account_id": account_id},
            json=payload
        )
        response.raise_for_status()
        
        # 3. Streamline the response to only essential fields so we don't blow up the LLM context window
        items = response.json().get("items", [])
        results = []
        for item in items:
            # Drop anonymous/private profiles that lack a usable ID or Name
            if item.get("id") and item.get("name") and "LinkedIn Member" not in item.get("name"):
                results.append({
                    "id": item["id"], 
                    "name": item["name"], 
                    "headline": item.get("headline", ""),
                    "location": item.get("location", "")
                })
        return str(results)
    except Exception as e:
        return f"Error connecting to Unipile: {str(e)}"

@mcp.tool()
def send_connection_request(profile_id: str, note: str) -> str:
    """Sends a LinkedIn connection request."""
    headers = {"X-API-KEY": UNIPILE_TOKEN, "Accept": "application/json"}
    try:
        acc_resp = requests.get(f"{UNIPILE_URL}/accounts", headers=headers)
        acc_resp.raise_for_status()
        account_id = next((acc["id"] for acc in acc_resp.json().get("items", []) if acc.get("type") == "LINKEDIN"), None)
        if not account_id: return "Error: No LinkedIn account connected."

        payload = {"account_id": account_id, "provider_id": profile_id, "message": note}
        response = requests.post(f"{UNIPILE_URL}/users/invite", headers=headers, json=payload)
        response.raise_for_status()
        return "Connection request successful."
    except Exception as e:
        return f"Error connecting to Unipile: {str(e)}"

@mcp.tool()
def send_linkedin_message(profile_id: str, text: str) -> str:
    """Sends a message to a LinkedIn profile."""
    headers = {"X-API-KEY": UNIPILE_TOKEN, "Accept": "application/json"}
    try:
        acc_resp = requests.get(f"{UNIPILE_URL}/accounts", headers=headers)
        acc_resp.raise_for_status()
        account_id = next((acc["id"] for acc in acc_resp.json().get("items", []) if acc.get("type") == "LINKEDIN"), None)
        if not account_id: return "Error: No LinkedIn account connected."

        payload = {"account_id": account_id, "attendees_ids": profile_id, "text": text}
        response = requests.post(f"{UNIPILE_URL}/chats", headers=headers, json=payload)
        response.raise_for_status()
        return "Message sent successfully."
    except Exception as e:
        return f"Error connecting to Unipile: {str(e)}"

# --- GOOGLE SHEETS TOOLS (APPS SCRIPT VERSION) ---

APPS_SCRIPT_URL = os.getenv("GOOGLE_APPS_SCRIPT_URL")

@mcp.tool()
def get_leads_by_status(status: str) -> str:
    """Fetches leads from the CRM that match a specific status."""
    if not APPS_SCRIPT_URL: return "Google Apps Script URL not configured."
    try:
        payload = {"method": "get_leads_by_status", "status": status}
        response = requests.post(APPS_SCRIPT_URL, json=payload, allow_redirects=True)
        response.raise_for_status()
        return str(response.json())
    except Exception as e:
        return f"Error accessing Google Sheets via App Script: {str(e)}"

@mcp.tool()
def draft_pending_action(profile_id: str, action_type: str, content: str) -> str:
    """Drafts an action to the Pending Approvals tab without executing it."""
    if not APPS_SCRIPT_URL: return "Google Apps Script URL not configured."
    try:
        payload = {
            "method": "draft_pending_action", 
            "profile_id": profile_id, 
            "action_type": action_type, 
            "content": content
        }
        response = requests.post(APPS_SCRIPT_URL, json=payload, allow_redirects=True)
        response.raise_for_status()
        return response.text
    except Exception as e:
        return f"Error writing to Sheets via App Script: {str(e)}"

@mcp.tool()
def update_lead_status(profile_id: str, new_status: str) -> str:
    """Updates the status of a specific lead in the main CRM tab."""
    if not APPS_SCRIPT_URL: return "Google Apps Script URL not configured."
    try:
        payload = {
            "method": "update_lead_status", 
            "profile_id": profile_id, 
            "new_status": new_status
        }
        response = requests.post(APPS_SCRIPT_URL, json=payload, allow_redirects=True)
        response.raise_for_status()
        return response.text
    except Exception as e:
        return f"Error updating Sheets via App Script: {str(e)}"

# --- TELEGRAM NOTIFICATION ---

@mcp.tool()
def notify_human_for_approval(summary_text: str) -> str:
    """Sends a Telegram notification to the Admin."""
    if not TELEGRAM_TOKEN or not TELEGRAM_ADMIN_ID:
        return "Telegram not configured in environment variables."
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_ADMIN_ID, "text": summary_text}
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return "Human notified successfully."
    except Exception as e:
        return f"Failed to notify human: {str(e)}"

if __name__ == "__main__":
    # Run the MCP server over stdio
    mcp.run()
