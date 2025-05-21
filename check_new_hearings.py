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
DEFAULT_DEFERRED_MATCH_COMMENT_SIMILARITY_THRESHOLD = 0.85

# Global config dictionary
APP_CONFIG = {}

def load_app_config():
    global APP_CONFIG
    config_defaults = {
        "lookback_days": DEFAULT_LOOKBACK_DAYS,
        "deferred_match_grace_period_days": DEFAULT_DEFERRED_MATCH_GRACE_PERIOD_DAYS,
        "deferred_match_comment_similarity_threshold": DEFAULT_DEFERRED_MATCH_COMMENT_SIMILARITY_THRESHOLD,
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
    """Load previously seen events from history file"""
    if not os.path.exists(HISTORY_FILE):
        logger.info(f"No history file found at {HISTORY_FILE}")
        return {}
    
    try:
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading history file: {e}")
        return {}

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
        "processing_tags": [] # Internal tags for this run, e.g. ['newly_added', 'became_deferred']
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
    
    # Make a deep copy of seen_events_db for modifications if needed, or update in place carefully
    # For now, assume direct modification of seen_events_db objects is acceptable.
    
    processed_event_ids_this_run = set()
    newly_added_event_ids = []
    newly_deferred_event_ids = [] # Store IDs of events that became deferred this run
    # Store (deferred_event_id, new_event_id) for events matched as reschedules
    newly_rescheduled_pairs = [] 

    # Pass 1: Update existing events and identify new ones / newly deferred
    for current_event_obj in api_events:
        event_id = str(current_event_obj['EventId'])
        processed_event_ids_this_run.add(event_id)
        
        if event_id not in seen_events_db:
            seen_events_db[event_id] = initialize_seen_event_entry(current_event_obj, current_run_iso_time)
            seen_events_db[event_id]["processing_tags"].append('newly_added')
            newly_added_event_ids.append(event_id)
            logger.info(f"New event added: ID {event_id} - {current_event_obj.get('EventBodyName')}")
        else:
            stored_entry = seen_events_db[event_id]
            stored_entry["last_seen_timestamp"] = current_run_iso_time # Update last seen for all existing
            stored_entry["processing_tags"] = [] # Reset for current run

            if check_significant_event_data_change(current_event_obj, stored_entry["event_data"]):
                logger.info(f"Significant change detected for EventId {event_id}")
                stored_entry["event_data"] = current_event_obj # Update to latest API data
                stored_entry["last_significant_change_timestamp"] = current_run_iso_time
                stored_entry["processing_tags"].append('data_changed')

            # Check for transition to "Deferred"
            # Only transition if it was previously active and not already some form of deferred/rescheduled
            if current_event_obj.get('EventAgendaStatusName') == 'Deferred' and \
               stored_entry["current_status"] == 'active':
                stored_entry["current_status"] = 'deferred_pending_match'
                # Reset any previous reschedule links as it's now deferred again
                stored_entry["original_event_details_if_rescheduled"] = None 
                stored_entry["rescheduled_event_details_if_deferred"] = None
                stored_entry["last_significant_change_timestamp"] = current_run_iso_time
                stored_entry["processing_tags"].append('became_deferred')
                newly_deferred_event_ids.append(event_id)
                logger.info(f"Event ID {event_id} became deferred.")
            
            # If an event was deferred_pending_match and is now NOT deferred, it becomes active again (rare?)
            elif current_event_obj.get('EventAgendaStatusName') != 'Deferred' and \
                 stored_entry["current_status"] == 'deferred_pending_match':
                 logger.info(f"Event ID {event_id} was deferred_pending_match, now not Deferred. Resetting to active.")
                 stored_entry["current_status"] = 'active'
                 stored_entry["last_significant_change_timestamp"] = current_run_iso_time
                 stored_entry["processing_tags"].append('became_active_from_pending_deferral')

            stored_entry["last_processed_timestamp"] = current_run_iso_time

    # Pass 2: Attempt to match newly_added_event_ids with deferred_pending_match events
    # Filter to only truly new events (not just changed ones that were already known)
    potential_reschedules_from_new = [eid for eid in newly_added_event_ids if seen_events_db[eid]["first_seen_timestamp"] == current_run_iso_time]
    
    deferred_pending_ids = [eid for eid, entry in seen_events_db.items() if entry["current_status"] == 'deferred_pending_match']
    
    for deferred_id in deferred_pending_ids:
        deferred_entry = seen_events_db[deferred_id]
        deferred_event_data = deferred_entry["event_data"]
        deferred_datetime = get_event_datetime(deferred_event_data)
        if not deferred_datetime: continue

        best_match_score = 0
        best_match_id = None

        for new_event_id in potential_reschedules_from_new:
            if new_event_id == deferred_id: continue # Cannot match to itself
            
            new_event_entry = seen_events_db[new_event_id]
            # Ensure it hasn't already been linked as a reschedule of something else
            if new_event_entry["original_event_details_if_rescheduled"]: continue 

            new_event_data = new_event_entry["event_data"]
            new_datetime = get_event_datetime(new_event_data)
            if not new_datetime: continue

            if new_datetime <= deferred_datetime: continue # Reschedule must be later
            if (new_datetime - deferred_datetime).days > APP_CONFIG["deferred_match_grace_period_days"]: continue
            if new_event_data.get('EventBodyName') != deferred_event_data.get('EventBodyName'): continue
            
            comment_sim = string_similarity(new_event_data.get('EventComment'), deferred_event_data.get('EventComment'))
            if comment_sim >= APP_CONFIG["deferred_match_comment_similarity_threshold"]:
                # Could add more scoring factors here, like time difference
                if comment_sim > best_match_score: # Simple best match for now
                    best_match_score = comment_sim
                    best_match_id = new_event_id
        
        if best_match_id:
            logger.info(f"Matched deferred Event ID {deferred_id} to new Event ID {best_match_id} as reschedule.")
            new_event_entry = seen_events_db[best_match_id]

            deferred_entry["current_status"] = 'deferred_rescheduled'
            deferred_entry["rescheduled_event_details_if_deferred"] = {
                "new_event_id": best_match_id,
                "new_date": new_event_entry["event_data"].get('EventDate'),
                "new_time": new_event_entry["event_data"].get('EventTime')
            }
            deferred_entry["last_significant_change_timestamp"] = current_run_iso_time
            deferred_entry["processing_tags"].append('matched_as_deferred_to_new')

            new_event_entry["original_event_details_if_rescheduled"] = {
                "deferred_event_id": deferred_id,
                "original_date": deferred_event_data.get('EventDate'),
                "original_time": deferred_event_data.get('EventTime')
            }
            new_event_entry["last_significant_change_timestamp"] = current_run_iso_time
            new_event_entry["processing_tags"].append('matched_as_reschedule_of_deferred')
            
            newly_rescheduled_pairs.append((deferred_id, best_match_id))
            # Remove from newly_added_event_ids if it was there, as it's now a 'reschedule' type of new
            if best_match_id in newly_added_event_ids: newly_added_event_ids.remove(best_match_id)
            if best_match_id in potential_reschedules_from_new : potential_reschedules_from_new.remove(best_match_id)

    # Pass 3: Handle old deferred events that found no match
    deferred_grace_period_delta = timedelta(days=APP_CONFIG["deferred_match_grace_period_days"])
    for event_id, entry in seen_events_db.items():
        if entry["current_status"] == 'deferred_pending_match':
            event_date_obj = get_event_datetime(entry["event_data"])
            if event_date_obj and (datetime.now() > event_date_obj + deferred_grace_period_delta):
                logger.info(f"Event ID {event_id} (deferred on {event_date_obj.date()}) passed grace period with no match. Marking deferred_nomatch.")
                entry["current_status"] = 'deferred_nomatch'
                entry["last_significant_change_timestamp"] = current_run_iso_time
                entry["processing_tags"].append('became_deferred_nomatch')

        # Update last_processed for all entries touched or considered in this run
        if event_id in processed_event_ids_this_run or entry["processing_tags"]: 
             entry["last_processed_timestamp"] = current_run_iso_time

    logger.info("Finished processing event changes.")
    # `seen_events_db` is now updated.
    # The lists `newly_added_event_ids`, `newly_deferred_event_ids`, `newly_rescheduled_pairs` 
    # can be used to generate summaries or specific lists for the webpage "Updates" section.
    return seen_events_db, newly_added_event_ids, newly_deferred_event_ids, newly_rescheduled_pairs


def generate_output_for_webpage(seen_events_db, newly_added_ids, newly_deferred_ids, newly_rescheduled_pairs):
    """Prepares the data in the format expected by generate_web_page.py."""
    # This will create two main lists: one for "Updates" and one for "All Upcoming Hearings"
    # And apply user_facing_tags for the webpage logic.
    
    now_iso = datetime.now().isoformat()
    last_week_iso = (datetime.now() - timedelta(days=7)).isoformat()
    last_month_iso = (datetime.now() - timedelta(days=30)).isoformat()

    updates_since_last_run = [] # For 'new since last update'
    updates_last_7_days = []
    updates_last_30_days = []

    all_upcoming_hearings = [] # For the main paginated panel

    # Populate `user_facing_tags` and build lists
    for event_id, entry in seen_events_db.items():
        entry["user_facing_tags"] = [] # Reset for this generation
        is_newly_added_this_run = event_id in newly_added_ids and entry["first_seen_timestamp"] == entry["last_processed_timestamp"]
        is_newly_deferred_this_run = event_id in newly_deferred_ids and 'became_deferred' in entry["processing_tags"]
        
        # Determine if it's part of a reschedule pair for "Updates" section
        is_rescheduled_new_part = any(pair[1] == event_id for pair in newly_rescheduled_pairs)
        is_rescheduled_deferred_part = any(pair[0] == event_id for pair in newly_rescheduled_pairs)

        # --- Logic for "Updates" Column (based on last_significant_change_timestamp) ---
        changed_this_run = entry["last_significant_change_timestamp"] == entry["last_processed_timestamp"]
        
        update_item = None
        if is_newly_added_this_run:
            update_item = {"type": "new", "event_id": event_id, "data": entry}
            entry["user_facing_tags"].append("new")
        elif is_rescheduled_new_part: # The new event that IS the reschedule
            update_item = {"type": "rescheduled_new", "event_id": event_id, "data": entry}
            entry["user_facing_tags"].append("rescheduled")
        elif is_rescheduled_deferred_part and entry["current_status"] == 'deferred_rescheduled': # The original event that WAS deferred and now matched
             update_item = {"type": "rescheduled_original_deferred", "event_id": event_id, "data": entry}
             # No specific tag for upcoming, its status and links handle it
        elif is_newly_deferred_this_run and entry["current_status"] == 'deferred_pending_match':
            update_item = {"type": "deferred_pending", "event_id": event_id, "data": entry}
            # No specific tag for upcoming, its status handles it
        elif changed_this_run and entry["current_status"] == 'deferred_nomatch' and 'became_deferred_nomatch' in entry["processing_tags"]:
            update_item = {"type": "deferred_nomatch", "event_id": event_id, "data": entry}

        if update_item:
            updates_since_last_run.append(update_item)
            if entry["last_significant_change_timestamp"] >= last_week_iso:
                updates_last_7_days.append(update_item)
            if entry["last_significant_change_timestamp"] >= last_month_iso:
                updates_last_30_days.append(update_item)
        
        # --- Logic for "Upcoming Hearings" Main Panel ---
        # Include active events, or deferred events that are pending/no_match (to show their original slot)
        # or events that are the *new* part of a reschedule. Avoid double-listing the *original* deferred event if it was rescheduled.
        if entry["current_status"] == 'active':
            all_upcoming_hearings.append(entry) 
            if is_newly_added_this_run and not entry["original_event_details_if_rescheduled"] : entry["user_facing_tags"].append("new_hearing_tag") # Tag for upcoming panel
            if entry["original_event_details_if_rescheduled"]: entry["user_facing_tags"].append("rescheduled_hearing_tag")
        
        elif entry["current_status"] in ['deferred_pending_match', 'deferred_nomatch']:
            all_upcoming_hearings.append(entry)
            entry["user_facing_tags"].append("deferred_hearing_tag")
        
        # No need to add 'deferred_rescheduled' (original event) to upcoming; its rescheduled counterpart is 'active' and has the link.

    # Sort upcoming hearings by date, then by EventBodyName
    all_upcoming_hearings.sort(key=lambda x: (get_event_datetime(x["event_data"]) or datetime.max, x["event_data"].get("EventBodyName", "")))

    return {
        "updates_since_last_run": updates_since_last_run,
        "updates_last_7_days": updates_last_7_days,
        "updates_last_30_days": updates_last_30_days,
        "upcoming_hearings": all_upcoming_hearings,
        "generation_timestamp": now_iso
    }


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