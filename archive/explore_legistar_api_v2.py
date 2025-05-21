#!/usr/bin/env python3
import requests
import json
import os
from urllib.parse import quote

# API token
token = "Uvxb0j9syjm3aI8h46DhQvnX5skN4aSUL0x_Ee3ty9M.ew0KICAiVmVyc2lvbiI6IDEsDQogICJOYW1lIjogIk5ZQyByZWFkIHRva2VuIDIwMTcxMDI2IiwNCiAgIkRhdGUiOiAiMjAxNy0xMC0yNlQxNjoyNjo1Mi42ODM0MDYtMDU6MDAiLA0KICAiV3JpdGUiOiBmYWxzZQ0KfQ"

# Base URL
client = "nyc"  # Based on token being "NYC read token"
base_url = f"https://webapi.legistar.com/v1/{client}"

def fetch_endpoint(endpoint, params=None):
    """Fetch data from a specific endpoint"""
    url = f"{base_url}/{endpoint}"
    if params:
        url += f"?{params}"
    
    # Add token if not already in params
    if "token=" not in url:
        url += "&token=" + token if "?" in url else "?token=" + token
    
    print(f"Fetching: {url}")
    response = requests.get(url)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error {response.status_code}: {response.text}")
        return None

def save_to_file(filename, data):
    """Save API response to a file"""
    # Create 'data' directory if it doesn't exist
    os.makedirs("data", exist_ok=True)
    
    filepath = os.path.join("data", filename)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Data saved to {filepath}")

def explore_endpoint(endpoint, params=None, filename=None):
    """Explore an endpoint and save results to a file"""
    data = fetch_endpoint(endpoint, params)
    if data:
        if filename:
            save_to_file(filename, data)
        else:
            save_to_file(f"{endpoint.replace('/', '_')}.json", data)
    return data

# Explore API Structure
print("== Exploring Legistar API Structure ==")

# 1. Get matters (legislation)
print("\n1. Exploring matters (legislation)...")
matter_data = explore_endpoint("matters", "$top=5", "matters_top5.json")

if matter_data and len(matter_data) > 0:
    # 2. Get matter details for a specific matter
    matter_id = matter_data[0]["MatterId"]
    print(f"\n2. Getting details for matter ID {matter_id}...")
    explore_endpoint(f"matters/{matter_id}", None, f"matter_detail_{matter_id}.json")
    
    # 3. Get matter attachments
    print(f"\n3. Getting attachments for matter ID {matter_id}...")
    explore_endpoint(f"matters/{matter_id}/attachments", None, f"matter_attachments_{matter_id}.json")
    
    # 4. Get matter histories (actions taken on this matter)
    print(f"\n4. Getting history for matter ID {matter_id}...")
    matter_histories = explore_endpoint(f"matters/{matter_id}/histories", None, f"matter_histories_{matter_id}.json")
    
    # 5. Get matter sponsors
    print(f"\n5. Getting sponsors for matter ID {matter_id}...")
    explore_endpoint(f"matters/{matter_id}/sponsors", None, f"matter_sponsors_{matter_id}.json")

# 6. Get events (meetings)
print("\n6. Exploring events (meetings)...")
events_data = explore_endpoint("events", "$top=5", "events_top5.json")

if events_data and len(events_data) > 0:
    # 7. Get event details for a specific event
    event_id = events_data[0]["EventId"]
    print(f"\n7. Getting details for event ID {event_id}...")
    explore_endpoint(f"events/{event_id}", None, f"event_detail_{event_id}.json")
    
    # 8. Get event items (agenda items)
    print(f"\n8. Getting agenda items for event ID {event_id}...")
    event_items = explore_endpoint(f"events/{event_id}/eventitems", None, f"event_items_{event_id}.json")
    
    if event_items and len(event_items) > 0:
        # 9. Get votes for an event item
        event_item_id = event_items[0]["EventItemId"]
        print(f"\n9. Getting votes for event item ID {event_item_id}...")
        explore_endpoint(f"eventitems/{event_item_id}/votes", None, f"event_item_votes_{event_item_id}.json")

# 10. Get all bodies (committees, etc.)
print("\n10. Getting all bodies (committees, etc.)...")
explore_endpoint("bodies", "$top=50", "bodies_all.json")

# 11. Get all body types
print("\n11. Getting all body types...")
explore_endpoint("bodytypes", None, "body_types.json")

# 12. Get all matter types
print("\n12. Getting all matter types...")
explore_endpoint("mattertypes", None, "matter_types.json")

# 13. Get all matter statuses
print("\n13. Getting all matter statuses...")
explore_endpoint("matterstatuses", None, "matter_statuses.json")

# 14. Try a complex ODATA filter
print("\n14. Trying a complex ODATA filter for matters...")
filter_query = "$filter=MatterTypeId eq 2 and MatterStatusId eq 35 and MatterIntroDate ge datetime'2022-01-01'"
explore_endpoint("matters", f"{filter_query}&$top=10", "matters_filtered.json")

# 15. Search for matters by text
print("\n15. Searching for matters containing 'Housing'...")
text_search = "$filter=contains(MatterTitle,'Housing')"
explore_endpoint("matters", f"{text_search}&$top=10", "matters_housing.json")

print("\nAPI exploration complete. Check the 'data' directory for output files.") 