#!/usr/bin/env python3
import requests
import json
from urllib.parse import quote

# API token
token = "Uvxb0j9syjm3aI8h46DhQvnX5skN4aSUL0x_Ee3ty9M.ew0KICAiVmVyc2lvbiI6IDEsDQogICJOYW1lIjogIk5ZQyByZWFkIHRva2VuIDIwMTcxMDI2IiwNCiAgIkRhdGUiOiAiMjAxNy0xMC0yNlQxNjoyNjo1Mi42ODM0MDYtMDU6MDAiLA0KICAiV3JpdGUiOiBmYWxzZQ0KfQ"

# Base URL
client = "nyc" # Based on token being "NYC read token"
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
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"Data saved to {filename}")

def explore_endpoint(endpoint, params=None, filename=None):
    """Explore an endpoint and save results to a file"""
    data = fetch_endpoint(endpoint, params)
    if data:
        if filename:
            save_to_file(filename, data)
        else:
            save_to_file(f"{endpoint.replace('/', '_')}.json", data)
    return data

# Explore available endpoints
print("== Exploring Legistar API ==")

# 1. Check matters endpoint with pagination
explore_endpoint("matters", "$top=10&$skip=0", "matters_page1.json")

# 2. Check events endpoint with date filtering
date_filter = "$filter=EventDate+ge+datetime%272023-01-01%27+and+EventDate+lt+datetime%272023-12-31%27"
explore_endpoint("events", date_filter, "events_2023.json")

# 3. Explore bodies endpoint
explore_endpoint("bodies", "$top=50", "bodies.json")

# 4. Explore persons endpoint (council members, etc.)
explore_endpoint("persons", "$top=50", "persons.json")

# 5. Get recent votes
explore_endpoint("eventitems", "$top=10&$skip=0", "eventitems.json")

print("Initial exploration complete. Check the output files for results.") 