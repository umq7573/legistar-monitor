#!/usr/bin/env python3
import os
import json
import logging
from datetime import datetime, timedelta
import difflib # Added for comment similarity
from legistar_api import LegistarAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('hearing_checker')

# Constants & Configuration Defaults
DATA_DIR = "data"
HISTORY_FILE = os.path.join(DATA_DIR, "seen_events.json")
OUTPUT_EVENTS_FILE = os.path.join(DATA_DIR, "processed_events_for_web.json") # New output file for generate_web_page.py
CONFIG_FILE = "config.json" # Expects config.json in the root directory

# Default values, can be overridden by config.json
DEFAULT_LOOKBACK_DAYS = 365
DEFAULT_DEFERRED_MATCH_GRACE_PERIOD_DAYS = 60

# Global config dictionary
APP_CONFIG = {}

def load_app_config():
    global APP_CONFIG
    config_defaults = {
        "lookback_days": DEFAULT_LOOKBACK_DAYS,
        "deferred_match_grace_period_days": DEFAULT_DEFERRED_MATCH_GRACE_PERIOD_DAYS,
        # "deferred_match_comment_similarity_threshold": DEFAULT_DEFERRED_MATCH_COMMENT_SIMILARITY_THRESHOLD, # No longer used
        # Add other future configurations here
    }
    
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                user_config = json.load(f)
                # Merge user_config with defaults, user_config takes precedence
                APP_CONFIG = {**config_defaults, **user_config.get('hearing_monitor_settings', {})}
                logger.info(f"Loaded hearing monitor settings from {CONFIG_FILE}")
        else:
            APP_CONFIG = config_defaults
            logger.info(f"No user config found at {CONFIG_FILE}, using default hearing monitor settings.")
    except Exception as e:
        logger.error(f"Error loading hearing monitor settings from {CONFIG_FILE}: {e}. Using defaults.")
        APP_CONFIG = config_defaults

    # Ensure essential keys are present
    for key, default_value in config_defaults.items():
        APP_CONFIG.setdefault(key, default_value)
    
    logger.info(f"Application config: {APP_CONFIG}")

def load_seen_events():
    """Load previously seen events from history file, migrating old formats if necessary."""
    if not os.path.exists(HISTORY_FILE):
        logger.info(f"No history file found at {HISTORY_FILE}, starting fresh.")
        return {}
    
    try:
        with open(HISTORY_FILE, 'r') as f:
            raw_data = json.load(f)
    except Exception as e:
        logger.error(f"Error loading or parsing history file {HISTORY_FILE}: {e}. Starting fresh.")
        return {}

    migrated_data = {}
    current_time_iso = datetime.now().isoformat()

    for event_key, entry_value in raw_data.items():
        # New format has 'event_data' and 'current_status' as top-level keys in entry_value.
        if "event_data" not in entry_value or "current_status" not in entry_value:
            logger.warning(f"Old format entry found for key '{event_key}', attempting migration.")
            
            actual_event_id_str = str(entry_value.get("event_id", event_key))
            
            # Construct a mock API event object from old entry data
            mock_event_api_obj = {
                # EventId in API is int. Keys in our DB are strings.
                "EventId": None, # Will be populated from actual_event_id_str
                "EventBodyName": entry_value.get("body"),
                "EventDate": entry_value.get("date"), # ISO string or None
                "EventTime": entry_value.get("time"), # String like "10:00 AM" or None
                "EventLocation": entry_value.get("location"),
                "EventAgendaFile": entry_value.get("agenda_url"), # Old field name
                "EventComment": entry_value.get("EventComment"), # Might not exist in very old format
                "EventAgendaStatusName": None # Cannot reliably get this from old simple status
            }
            try:
                mock_event_api_obj["EventId"] = int(actual_event_id_str)
            except ValueError:
                logger.error(f"Could not convert event_id '{actual_event_id_str}' to int for mock_event_api_obj. This event might not be processed correctly if API data is missing.")
                # Keep it as None or handle as error, but EventId is crucial.
                # For now, let it be None if conversion fails, new data from API should overwrite if event still exists.


            mock_event_api_obj_cleaned = {k: v for k, v in mock_event_api_obj.items() if v is not None}
            if mock_event_api_obj["EventId"] is None and "EventId" in mock_event_api_obj_cleaned:
                 del mock_event_api_obj_cleaned["EventId"] # Don't include a None EventId

            first_seen_timestamp = entry_value.get("first_seen", current_time_iso)
            # Use last_updated for other timestamps, as it's the most recent info from old format
            last_meaningful_update_timestamp = entry_value.get("last_updated", first_seen_timestamp)

            new_migrated_entry = {
                "event_data": mock_event_api_obj_cleaned,
                "first_seen_timestamp": first_seen_timestamp,
                "last_seen_timestamp": last_meaningful_update_timestamp, # When it was last seen/updated in old system
                "last_processed_timestamp": current_time_iso, # Mark as processed now during migration
                "last_significant_change_timestamp": last_meaningful_update_timestamp,
                "current_status": "active", # Default for migrated entries, will be re-evaluated
                "original_event_details_if_rescheduled": None,
                "rescheduled_event_details_if_deferred": None,
                "processing_tags": ['migrated_from_old_format']
            }
            migrated_data[actual_event_id_str] = new_migrated_entry
            logger.info(f"Migrated old entry for Event ID {actual_event_id_str} to new format.")
        else:
            # It's already in the new format, ensure key is string.
            migrated_data[str(event_key)] = entry_value 
            
    logger.info(f"Loaded {len(migrated_data)} events from history, with migration if needed.")
    return migrated_data

def save_seen_events(seen_events):
    """Save seen events to history file"""
    os.makedirs(DATA_DIR, exist_ok=True)
    
    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(seen_events, f, indent=2)
        logger.info(f"Saved {len(seen_events)} events to history file")
    except Exception as e:
        logger.error(f"Error saving history file: {e}")

def fetch_events_from_api(api):
    """Fetch events from the Legistar API based on configured lookback."""
    today = datetime.now()
    start_date = (today - timedelta(days=APP_CONFIG['lookback_days']))
    
    # End date is None for open-ended future query
    logger.info(f"Fetching events from {start_date.date()} to indefinite future.")
    
    # The get_events method in LegistarAPI now handles pagination and takes page_size via 'top'
    events = api.get_events(
        top=1000,  # Page size for API calls, LegistarAPI handles full pagination
        date_range=(start_date, None) # None as end_date for open-ended future
    )
    
    if not events:
        logger.warning("No events found from API for the given date range.")
        return []
    
    logger.info(f"Fetched {len(events)} total events from API.")
    return events

def initialize_seen_event_entry(event_obj, current_time_iso):
    """Creates a new entry for seen_events.json based on the new data model."""
    return {
        "event_data": event_obj,
        "first_seen_timestamp": current_time_iso,
        "last_seen_timestamp": current_time_iso,
        "last_processed_timestamp": current_time_iso,
        "last_significant_change_timestamp": current_time_iso,
        "current_status": "active", # Initial status for a new event
        "original_event_details_if_rescheduled": None,
        "rescheduled_event_details_if_deferred": None,
        "processing_tags": [], # Internal tags for this run, e.g. ['newly_added', 'became_deferred']
        "last_alert_type": "new", # Default for a brand new entry
        "last_alert_timestamp": current_time_iso # Timestamp of this initial "new" alert
    }

def get_event_datetime(event_data):
    """Safely parses EventDate and EventTime into a datetime object."""
    event_date_str = event_data.get('EventDate')
    event_time_str = event_data.get('EventTime')
    if not event_date_str:
        return None
    
    # Remove time part from EventDate if present (e.g., 'T00:00:00')
    event_date_str = event_date_str.split('T')[0]
    
    if not event_time_str: # If no time, use start of day
        try:
            return datetime.strptime(event_date_str, '%Y-%m-%d')
        except ValueError:
            return None # Invalid date format

    try:
        # Combine date and time. Handle various time formats if necessary.
        # Assuming time is like "10:00 AM" or "1:00 PM"
        dt_str = f"{event_date_str} {event_time_str}"
        return datetime.strptime(dt_str, '%Y-%m-%d %I:%M %p')
    except ValueError:
        # Fallback if time format is different or unparseable with combined string
        try:
            return datetime.strptime(event_date_str, '%Y-%m-%d') # Date only
        except ValueError:
            return None

def check_significant_event_data_change(current_api_event, stored_event_data_from_db):
    """Checks for significant changes between current API event data and stored data."""
    fields_to_check = ['EventDate', 'EventTime', 'EventLocation', 'EventBodyName', 'EventAgendaStatusName', 'EventComment']
    for field in fields_to_check:
        if current_api_event.get(field) != stored_event_data_from_db.get(field):
            #logger.debug(f"Significant change for EventId {current_api_event.get('EventId')}: Field '{field}' changed from '{stored_event_data_from_db.get(field)}' to '{current_api_event.get(field)}'")
            return True
    return False

def string_similarity(s1, s2):
    """Calculates similarity ratio between two strings."""
    s1 = s1 or ""
    s2 = s2 or ""
    return difflib.SequenceMatcher(None, s1, s2).ratio()

def process_event_changes(api_events, seen_events_db):
    logger.info("Starting processing of event changes...")
    current_run_iso_time = datetime.now().isoformat()
    
    processed_event_ids_this_run = set()
    newly_added_event_ids = []
    newly_deferred_event_ids = [] 
    newly_rescheduled_pairs = [] 

    # Pass 1: Update existing events and identify new ones / newly deferred
    for current_event_obj in api_events:
        event_id = str(current_event_obj['EventId'])
        processed_event_ids_this_run.add(event_id)
        
        if event_id not in seen_events_db:
            seen_events_db[event_id] = initialize_seen_event_entry(current_event_obj, current_run_iso_time)
            # last_alert_type and last_alert_timestamp are set by initialize_seen_event_entry for new events
            seen_events_db[event_id]["processing_tags"].append('newly_added')
            newly_added_event_ids.append(event_id)
            logger.info(f"New event added: ID {event_id} - {current_event_obj.get('EventBodyName')}")
        else:
            stored_entry = seen_events_db[event_id]
            stored_entry["last_seen_timestamp"] = current_run_iso_time 
            stored_entry["processing_tags"] = [] # Reset for current run

            significant_data_change_occurred = check_significant_event_data_change(current_event_obj, stored_entry["event_data"])
            if significant_data_change_occurred:
                logger.info(f"Significant change detected for EventId {event_id}")
                stored_entry["event_data"] = current_event_obj 
                stored_entry["last_significant_change_timestamp"] = current_run_iso_time
                stored_entry["processing_tags"].append('data_changed')
                # Note: Simple data changes on active events don't currently update last_alert_type/timestamp
                # unless it leads to a status change below.

            current_api_status = current_event_obj.get('EventAgendaStatusName')
            stored_status = stored_entry["current_status"]

            if stored_status == "active" and current_api_status == "Deferred":
                logger.info(f"Event ID {event_id} status changed from active to Deferred.")
                stored_entry["current_status"] = "deferred_pending_match"
                stored_entry["last_significant_change_timestamp"] = current_run_iso_time
                stored_entry["last_alert_type"] = "deferred_initial"
                stored_entry["last_alert_timestamp"] = current_run_iso_time
                stored_entry["processing_tags"].append('became_deferred')
                newly_deferred_event_ids.append(event_id)
            elif stored_status == "deferred_pending_match" and current_api_status != "Deferred":
                logger.info(f"Event ID {event_id} was deferred_pending_match, but API status is now '{current_api_status}'. Reverting to active.")
                stored_entry["current_status"] = "active"
                stored_entry["last_significant_change_timestamp"] = current_run_iso_time
                # This reversion might be considered a new "active" alert or just a data correction.
                # For now, let's assume it will be picked up if it qualifies as "new" again due to date changes, or if it was the target of a deferral.
                # If it was simply reverted, it may not create a new explicit alert beyond data_changed.
                stored_entry["last_alert_type"] = "data_changed_reverted_deferral" # Or a more generic type
                stored_entry["last_alert_timestamp"] = current_run_iso_time
                stored_entry["processing_tags"].append('data_changed') 
                stored_entry["processing_tags"].append('reverted_from_deferred')
            elif significant_data_change_occurred and stored_status == "active":
                 # If it was active and had significant data changes (but not status to Deferred)
                 # We could also give this its own alert type, e.g., "active_data_updated"
                 # stored_entry["last_alert_type"] = "active_data_updated"
                 # stored_entry["last_alert_timestamp"] = current_run_iso_time
                 pass # For now, simple data changes on active events don't generate a new separate alert for 7/30 day lists by default

            stored_entry["last_processed_timestamp"] = current_run_iso_time

    # Pass 2: Attempt to match deferred events to newly added events
    newly_added_events_this_run_entries = [seen_events_db[eid] for eid in newly_added_event_ids]
    deferred_events_pending_match = { eid: entry for eid, entry in seen_events_db.items() if entry["current_status"] == "deferred_pending_match"}
    logger.info(f"Attempting to match {len(deferred_events_pending_match)} deferred events with {len(newly_added_events_this_run_entries)} newly added events.")
    newly_added_events_this_run_entries.sort(key=lambda x: get_event_datetime(x['event_data']) or datetime.max)

    for def_id, def_entry in deferred_events_pending_match.items():
        def_event_data = def_entry["event_data"]
        def_event_dt = get_event_datetime(def_event_data)

        potential_matches = []
        for new_event_entry in newly_added_events_this_run_entries:
            new_event_id = str(new_event_entry['event_data']['EventId'])
            if new_event_id == def_id: continue # Cannot match with itself

            new_event_data = new_event_entry['event_data']
            new_event_dt = get_event_datetime(new_event_data)

            if not new_event_dt or not def_event_dt or new_event_dt < def_event_dt:
                continue # New event must have a date and be on or after the deferred event's date

            # Heuristic: Body name must be identical
            if def_event_data.get("EventBodyName") != new_event_data.get("EventBodyName"):
                continue
            
            # Heuristic: EventComment must be identical (if both exist)
            # If one has a comment and the other doesn't, they don't match. If both null, they match on comment.
            def_comment = def_event_data.get("EventComment")
            new_comment = new_event_data.get("EventComment")
            if def_comment != new_comment:
                continue

            # If all heuristics pass, it's a potential match
            potential_matches.append(new_event_entry)
        
        # Select the best match (earliest valid new date)
        if potential_matches:
            # Already sorted by date, so the first one is the best by date.
            best_match_entry = potential_matches[0]
            best_match_id = str(best_match_entry['event_data']['EventId'])
            
            logger.info(f"Matched deferred Event ID {def_id} to new Event ID {best_match_id}")
            def_entry["current_status"] = "deferred_rescheduled"
            def_entry["rescheduled_event_details_if_deferred"] = {
                "original_event_id": def_id,
                "new_event_id": best_match_id,
                "new_date": best_match_entry["event_data"].get("EventDate"),
                "new_time": best_match_entry["event_data"].get("EventTime"),
                "match_timestamp": current_run_iso_time
            }
            def_entry["last_significant_change_timestamp"] = current_run_iso_time
            def_entry["last_alert_type"] = "deferred_rescheduled"
            def_entry["last_alert_timestamp"] = current_run_iso_time
            def_entry["processing_tags"].append('became_rescheduled_match_found_for_original')

            best_match_entry["original_event_details_if_rescheduled"] = {
                "original_event_id": def_id,
                "original_date": def_event_data.get("EventDate"),
                "original_time": def_event_data.get("EventTime"),
                "match_timestamp": current_run_iso_time
            }
            # If the target was also newly_added this run, its initial last_alert_type was "new". 
            # We update it to reflect it's primarily a reschedule target now.
            if 'newly_added' in best_match_entry.get("processing_tags", []):
                best_match_entry["last_alert_type"] = "rescheduled_as_new"
                best_match_entry["last_alert_timestamp"] = best_match_entry['first_seen_timestamp'] # Alert is from when it was first seen
            
            best_match_entry["processing_tags"].append('newly_added_as_reschedule_target')
            best_match_entry["last_significant_change_timestamp"] = current_run_iso_time # Also a significant change for the target

            newly_rescheduled_pairs.append((def_id, best_match_id))
            
            # Remove from newly_added_event_ids if it was consumed as a reschedule target,
            # so it doesn't also appear as a simple "new" event in some contexts if we only use that list.
            # However, its 'newly_added' tag will persist on the entry itself.
            if best_match_id in newly_added_event_ids:
                 # We don't remove it from newly_added_event_ids because it *is* new, just also a reschedule.
                 # generate_output_for_webpage will use processing_tags to differentiate.
                 pass

    # Pass 3: Handle old deferred events that didn't find a match - check grace period
    grace_period_delta = timedelta(days=APP_CONFIG.get('deferred_match_grace_period_days', DEFAULT_DEFERRED_MATCH_GRACE_PERIOD_DAYS))
    current_datetime = datetime.now()

    for event_id, entry in seen_events_db.items():
        if entry["current_status"] == "deferred_pending_match":
            last_change_dt = datetime.fromisoformat(entry["last_significant_change_timestamp"])
            if current_datetime - last_change_dt > grace_period_delta:
                logger.info(f"Event ID {event_id} (deferred_pending_match) exceeded grace period. Moving to deferred_nomatch.")
                entry["current_status"] = "deferred_nomatch"
                entry["last_significant_change_timestamp"] = current_run_iso_time
                entry["last_alert_type"] = "deferred_nomatch"
                entry["last_alert_timestamp"] = current_run_iso_time
                entry["processing_tags"].append('became_nomatch')

    # Output counts for GitHub Action summary
    # These counts are based on what happened *this run*
    newly_added_pure_count = 0
    for nid in newly_added_event_ids:
        if not seen_events_db[nid].get("original_event_details_if_rescheduled"): # if it's not a target of a reschedule
            newly_added_pure_count +=1

    print(f"::set-output name=total_updates::{len(newly_added_event_ids) + len(newly_deferred_event_ids) + len(newly_rescheduled_pairs)}") # Simplistic sum for now
    print(f"::set-output name=newly_added_count::{newly_added_pure_count}")
    print(f"::set-output name=newly_deferred_count::{len(newly_deferred_event_ids)}") # Events that became deferred_pending_match this run
    print(f"::set-output name=newly_rescheduled_count::{len(newly_rescheduled_pairs)}") # Pairs matched this run
    
    logger.info(f"Finished processing event changes. Total unique events processed in API feed: {len(processed_event_ids_this_run)}")
    logger.info(f"DB size: {len(seen_events_db)}")
    logger.info(f"Newly added (and not a reschedule target immediately): {newly_added_pure_count}")
    logger.info(f"Became deferred this run: {len(newly_deferred_event_ids)}")
    logger.info(f"Matched as reschedules this run: {len(newly_rescheduled_pairs)}")

    return seen_events_db, newly_added_event_ids, newly_deferred_event_ids, newly_rescheduled_pairs


def generate_output_for_webpage(seen_events_db, newly_added_ids_this_run, newly_deferred_ids_this_run, newly_rescheduled_pairs_this_run):
    logger.info("Generating output for web page...")

    today_date = datetime.now().date()
    seven_days_ago_dt = datetime.now() - timedelta(days=7)
    thirty_days_ago_dt = datetime.now() - timedelta(days=30)
    min_datetime_for_sort = datetime.min

    # --- 1. Upcoming Hearings List ---
    upcoming_hearings_list = []
    for entry_id, entry in seen_events_db.items():
        status = entry['current_status']
        if status == 'active':
            event_dt_obj = get_event_datetime(entry['event_data'])
            if event_dt_obj and event_dt_obj.date() >= today_date:
                upcoming_hearings_list.append(entry)
    upcoming_hearings_list.sort(key=lambda x: (get_event_datetime(x['event_data']) or min_datetime_for_sort))
    logger.info(f"Generated upcoming_hearings_list with {len(upcoming_hearings_list)} events.")

    # --- Helper for creating wrapped updates ---
    def create_wrapped_update(update_item_dict, alert_timestamp_iso_str, event_data_for_event_date):
        event_dt = get_event_datetime(event_data_for_event_date)
        return {
            "item": update_item_dict,
            "alert_dt_iso": alert_timestamp_iso_str,
            "event_dt_for_sort": event_dt if event_dt else min_datetime_for_sort
        }

    # --- 2. Updates Since Last Run ---
    updates_since_last_run_wrapped = []
    
    for event_id in newly_added_ids_this_run:
        entry = seen_events_db[event_id]
        event_dt = get_event_datetime(entry['event_data'])
        # If it was also a reschedule target, its last_alert_type would be 'rescheduled_as_new'
        # Otherwise, it's 'new'
        alert_type_for_item = entry.get('last_alert_type', 'new') 
        if alert_type_for_item == 'rescheduled_as_new' or alert_type_for_item == 'new':
            if event_dt and event_dt.date() >= today_date:
                item_dict = {"type": alert_type_for_item, "data": entry}
                updates_since_last_run_wrapped.append(create_wrapped_update(item_dict, entry['last_alert_timestamp'], entry['event_data']))
    
    for event_id in newly_deferred_ids_this_run: # Became deferred_pending_match this run
        entry = seen_events_db[event_id]
        item_dict = {"type": "deferred_initial", "data": entry} # Corresponds to last_alert_type "deferred_initial"
        updates_since_last_run_wrapped.append(create_wrapped_update(item_dict, entry['last_alert_timestamp'], entry['event_data']))

    for original_id, _ in newly_rescheduled_pairs_this_run: # Original event became deferred_rescheduled this run
        original_entry = seen_events_db[original_id]
        item_dict = {"type": "deferred_rescheduled", "data": original_entry} # Corresponds to last_alert_type "deferred_rescheduled"
        updates_since_last_run_wrapped.append(create_wrapped_update(item_dict, original_entry['last_alert_timestamp'], original_entry['event_data']))
    
    for entry_id, entry in seen_events_db.items():
        if 'became_nomatch' in entry.get('processing_tags', []) and entry['current_status'] == 'deferred_nomatch':
            # This indicates it transitioned to nomatch this run
            item_dict = {"type": "deferred_nomatch", "data": entry} # Corresponds to last_alert_type "deferred_nomatch"
            updates_since_last_run_wrapped.append(create_wrapped_update(item_dict, entry['last_alert_timestamp'], entry['event_data']))
            
    updates_since_last_run_wrapped.sort(key=lambda x: (datetime.fromisoformat(x['alert_dt_iso']), x['event_dt_for_sort']), reverse=True)
    updates_since_last_run = [w['item'] for w in updates_since_last_run_wrapped]
    logger.info(f"Generated updates_since_last_run with {len(updates_since_last_run)} items.")

    # --- 3. Updates Last 7 Days & Last 30 Days ---
    updates_last_7_days_wrapped = []
    updates_last_30_days_wrapped = []

    for entry_id, entry in seen_events_db.items():
        alert_type = entry.get('last_alert_type')
        alert_timestamp_iso = entry.get('last_alert_timestamp')
        event_data = entry['event_data']

        if not alert_type or not alert_timestamp_iso:
            continue # Should not happen if initialized and processed correctly

        # Apply date filter for specific alert types (new, rescheduled_as_new)
        if alert_type in ["new", "rescheduled_as_new"]:
            event_dt = get_event_datetime(event_data)
            if not (event_dt and event_dt.date() >= today_date):
                continue # Skip if past date for these types
        
        alert_dt_obj = datetime.fromisoformat(alert_timestamp_iso)
        current_update_item_dict = {"type": alert_type, "data": entry} # Use the definitive alert_type
        wrapped_update = create_wrapped_update(current_update_item_dict, alert_timestamp_iso, event_data)

        if alert_dt_obj >= thirty_days_ago_dt:
            updates_last_30_days_wrapped.append(wrapped_update)
            if alert_dt_obj >= seven_days_ago_dt:
                updates_last_7_days_wrapped.append(wrapped_update)

    updates_last_7_days_wrapped.sort(key=lambda x: (datetime.fromisoformat(x['alert_dt_iso']), x['event_dt_for_sort']), reverse=True)
    updates_last_7_days = [w['item'] for w in updates_last_7_days_wrapped]
    logger.info(f"Generated updates_last_7_days with {len(updates_last_7_days)} items.")

    updates_last_30_days_wrapped.sort(key=lambda x: (datetime.fromisoformat(x['alert_dt_iso']), x['event_dt_for_sort']), reverse=True)
    updates_last_30_days = [w['item'] for w in updates_last_30_days_wrapped]
    logger.info(f"Generated updates_last_30_days with {len(updates_last_30_days)} items.")
    
    output_data = {
        "generation_timestamp": datetime.now().isoformat(),
        "upcoming_hearings": upcoming_hearings_list,
        "updates_since_last_run": updates_since_last_run,
        "updates_last_7_days": updates_last_7_days,
        "updates_last_30_days": updates_last_30_days,
    }
    return output_data


def main():
    """Main function to check for new hearings and process changes."""
    logger.info("Starting hearing check run...")
    load_app_config() # Load configuration first
    
    api = LegistarAPI(config_file=CONFIG_FILE) # API client uses its own config for client/token
    
    seen_events = load_seen_events()
    logger.info(f"Loaded {len(seen_events)} previously seen events.")
    
    fetched_api_events = fetch_events_from_api(api)
    
    if not fetched_api_events:
        logger.warning("No events fetched from API. Skipping further processing.")
        # Still save current seen_events state if it was loaded, to update timestamps if any logic ran before this check
        save_seen_events(seen_events) 
        # Potentially write an empty structure or a message for the webpage
        processed_data_for_web = {
            "updates_since_last_run": [], "updates_last_7_days": [], "updates_last_30_days": [],
            "upcoming_hearings": [], "generation_timestamp": datetime.now().isoformat(), "error": "No events fetched from API."
        }
        with open(OUTPUT_EVENTS_FILE, 'w') as f_out:
            json.dump(processed_data_for_web, f_out, indent=2)
        logger.info(f"Wrote empty/error state to {OUTPUT_EVENTS_FILE}")
        return

    updated_seen_events_db, newly_added_ids, newly_deferred_ids, newly_rescheduled_pairs = \
        process_event_changes(fetched_api_events, seen_events)
    
    save_seen_events(updated_seen_events_db)
    logger.info(f"Saved {len(updated_seen_events_db)} events to history file.")
    
    # Prepare data for the webpage
    processed_data_for_web = generate_output_for_webpage(
        updated_seen_events_db, 
        newly_added_ids, 
        newly_deferred_ids, 
        newly_rescheduled_pairs
    )
    
    with open(OUTPUT_EVENTS_FILE, 'w') as f_out:
        json.dump(processed_data_for_web, f_out, indent=2)
    logger.info(f"Successfully wrote processed event data to {OUTPUT_EVENTS_FILE}")

    # Output for GitHub Actions summary (can be refined)
    total_updates = len(processed_data_for_web['updates_since_last_run'])
    logger.info(f"Total items for 'Updates since last run': {total_updates}")
    if 'GITHUB_OUTPUT' in os.environ:
        with open(os.environ['GITHUB_OUTPUT'], 'a') as h:
            print(f'total_updates={total_updates}', file=h)
            print(f'newly_added_count={len(newly_added_ids)}', file=h)
            print(f'newly_deferred_count={len(newly_deferred_ids)}', file=h)
            print(f'newly_rescheduled_count={len(newly_rescheduled_pairs)}', file=h)

if __name__ == "__main__":
    main() 