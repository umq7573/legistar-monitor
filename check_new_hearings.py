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

# Global config dictionary
APP_CONFIG = {}

def load_app_config():
    global APP_CONFIG
    config_defaults = {
        "lookback_days": DEFAULT_LOOKBACK_DAYS,
        # "deferred_match_grace_period_days": DEFAULT_DEFERRED_MATCH_GRACE_PERIOD_DAYS, # Removed
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
    """Load previously seen events from history file."""
    if not os.path.exists(HISTORY_FILE):
        logger.info(f"No history file found at {HISTORY_FILE}, starting fresh.")
        return {}
    
    try:
        with open(HISTORY_FILE, 'r') as f:
            data = json.load(f)
        logger.info(f"Loaded {len(data)} events from history.")
        return data
    except Exception as e:
        logger.error(f"Error loading history file {HISTORY_FILE}: {e}. Starting fresh.")
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

def extract_topic_from_items(event_items):
    """Extracts a meeting topic from event items."""
    if not event_items:
        return None

    # Sort items by agenda sequence (lowest first), None/null sequences last
    event_items.sort(key=lambda x: x.get("EventItemAgendaSequence") if x.get("EventItemAgendaSequence") is not None else float('inf'))
    
    if not event_items: # Should not happen if original list was not empty, but as a safeguard
        return None

    primary_item = event_items[0]
    
    topic = primary_item.get("EventItemMatterName")
    if topic and topic.strip():
        return topic.strip()
    
    # Fallback to EventItemTitle if EventItemMatterName is not available or empty
    topic = primary_item.get("EventItemTitle")
    if topic and topic.strip():
        # Clean up common boilerplate or excessive newlines if needed from title
        topic_lines = [line.strip() for line in topic.strip().splitlines() if line.strip()]
        # Heuristic: if the first line looks like a header (e.g. all caps) and there are other lines,
        # prefer the first line. Otherwise, join a few lines. This is a simple heuristic.
        if topic_lines:
            if len(topic_lines) > 1 and topic_lines[0].isupper() and any(c.islower() for c in topic_lines[0]): # Mix of upper/lower suggests not a pure title
                 return topic_lines[0] # Take first line if it's descriptive
            return " ".join(topic_lines[:3]) # Join first few lines, or just the first if only one
        return None # Should not happen if topic.strip() was true

    return "Meeting details to be determined" # Final fallback

def fetch_events_from_api(api):
    """Fetch events from the Legistar API based on configured lookback."""
    today = datetime.now()
    start_date = (today - timedelta(days=APP_CONFIG['lookback_days']))
    
    logger.info(f"Fetching events from {start_date.date()} to indefinite future.")
    
    api_events = api.get_events(
        top=1000, # Page size for API calls, LegistarAPI handles full pagination
        date_range=(start_date, None) # None as end_date for open-ended future
    )
    
    if not api_events:
        logger.warning("No events found from API for the given date range.")
        return []
    
    logger.info(f"Fetched {len(api_events)} raw events from API.")
    return api_events

def initialize_seen_event_entry(event_obj, current_time_iso):
    """Creates a new entry for seen_events.json based on the new data model."""
    return {
        "event_data": event_obj,
        "first_seen_timestamp": current_time_iso,
        "last_seen_timestamp": current_time_iso,
        "last_processed_timestamp": current_time_iso,
        "last_significant_change_timestamp": current_time_iso, # For a new event, this is its creation time
        "current_status": "active", # Initial status for a new event
        "original_event_details_if_rescheduled": None,
        "rescheduled_event_details_if_deferred": None,
        "processing_tags": [], # Internal tags for this run, e.g. ['newly_added', 'became_deferred']
        "last_alert_type": "new", # Per plan: "new" for any event first added
        "last_alert_timestamp": current_time_iso # Per plan: set to first_seen_timestamp
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

def process_event_changes(api_events, seen_events_db, api):
    logger.info("Starting processing of event changes...")
    current_run_iso_time = datetime.now().isoformat()
    
    processed_event_ids_this_run = set()
    # These lists are for the "since_last_run" updates.
    newly_added_event_ids_this_run = [] 
    newly_deferred_event_ids_this_run = []
    # This list will store tuples of (original_deferred_event_id, new_rescheduled_event_id)
    # It helps in generating annotations later.
    newly_rescheduled_pairs_this_run = []


    # Pass 1: Update existing events and identify new ones / newly deferred
    for current_event_obj in api_events:
        event_id = str(current_event_obj['EventId'])
        processed_event_ids_this_run.add(event_id)
        
        is_deferred_api = current_event_obj.get("EventAgendaStatusName") == "Deferred"

        if event_id not in seen_events_db:
            seen_events_db[event_id] = initialize_seen_event_entry(current_event_obj, current_run_iso_time)
            # last_alert_type and last_alert_timestamp are set by initialize_seen_event_entry
            seen_events_db[event_id]["processing_tags"].append('newly_added')
            newly_added_event_ids_this_run.append(event_id)
            logger.info(f"New event added: ID {event_id} - {current_event_obj.get('EventBodyName')}")

            # Fetch and store SyntheticMeetingTopic for this NEW event
            try:
                event_items = api.get_event_items(int(event_id)) # EventId for API is int
                topic = extract_topic_from_items(event_items)
                seen_events_db[event_id]["event_data"]["SyntheticMeetingTopic"] = topic
                logger.info(f"Fetched topic for new event {event_id}: '{topic}'")
            except Exception as e:
                logger.error(f"Error fetching or processing event items for new EventId {event_id}: {e}")
                seen_events_db[event_id]["event_data"]["SyntheticMeetingTopic"] = "Error retrieving topic"

            # If a new event is ALREADY deferred when first seen (unlikely, but handle)
            if is_deferred_api:
                stored_entry = seen_events_db[event_id]
                stored_entry["current_status"] = "deferred_pending_match"
                stored_entry["last_alert_type"] = "deferred" # Override from 'new' if born deferred
                stored_entry["last_alert_timestamp"] = current_run_iso_time # Timestamp of deferral
                stored_entry["last_significant_change_timestamp"] = current_run_iso_time
                stored_entry["processing_tags"].append('became_deferred_on_first_seen')
                newly_deferred_event_ids_this_run.append(event_id) # Also treat as newly deferred for "since last run"
                logger.info(f"Event ID {event_id} was 'Deferred' on first sight. Marked as 'deferred_pending_match'.")

        else:
            stored_entry = seen_events_db[event_id]
            stored_entry["last_seen_timestamp"] = current_run_iso_time 
            stored_entry["processing_tags"] = [] # Reset for current run

            significant_data_change_occurred = check_significant_event_data_change(current_event_obj, stored_entry["event_data"])
            
            previous_status = stored_entry["current_status"]
            status_changed_to_deferred_this_run = False

            if significant_data_change_occurred:
                logger.info(f"Significant change detected for EventId {event_id}")
                # Before updating event_data, check if it's a deferral change
                if is_deferred_api and previous_status == "active":
                    logger.info(f"EventId {event_id} status changed to Deferred.")
                    stored_entry["current_status"] = "deferred_pending_match"
                    stored_entry["last_alert_type"] = "deferred" # Set alert type to deferred
                    stored_entry["last_alert_timestamp"] = current_run_iso_time # Timestamp of this deferral
                    stored_entry["processing_tags"].append('became_deferred')
                    newly_deferred_event_ids_this_run.append(event_id)
                    status_changed_to_deferred_this_run = True
                elif not is_deferred_api and previous_status.startswith("deferred_"):
                    logger.info(f"EventId {event_id} was {previous_status}, now active (e.g. 'Final'). EventData: {current_event_obj}")
                    stored_entry["current_status"] = "active"
                    # IMPORTANT: If a deferred event becomes active again (e.g. due to API correction or status reverting to Final/Adjourned)
                    # We do NOT change its last_alert_type or last_alert_timestamp. It was deferred, that alert stands.
                    # If it's a NEW date, it will be treated like any other data change.
                    # The 'Upcoming Hearings' will show its current active state.
                    # The 'Updates' list will still show its 'deferred' alert based on its original deferral timestamp.
                    stored_entry["processing_tags"].append('deferral_reverted_to_active')

                stored_entry["event_data"] = current_event_obj 
                stored_entry["last_significant_change_timestamp"] = current_run_iso_time
                if not status_changed_to_deferred_this_run : # Avoid double-tagging if already tagged as deferred
                     stored_entry["processing_tags"].append('data_changed')
            
            # If not a significant data change, but status in API is Deferred and we have it as active
            # This can happen if only EventAgendaStatusName changed.
            elif is_deferred_api and stored_entry["current_status"] == "active":
                logger.info(f"EventId {event_id} status (only) changed to Deferred.")
                stored_entry["current_status"] = "deferred_pending_match"
                stored_entry["last_alert_type"] = "deferred" # Set alert type to deferred
                stored_entry["last_alert_timestamp"] = current_run_iso_time # Timestamp of this deferral
                stored_entry["event_data"]["EventAgendaStatusName"] = "Deferred" # Ensure this is updated
                stored_entry["last_significant_change_timestamp"] = current_run_iso_time
                stored_entry["processing_tags"].append('became_deferred')
                newly_deferred_event_ids_this_run.append(event_id)

            # Mark as processed for this run
            stored_entry["last_processed_timestamp"] = current_run_iso_time

    # Pass 2: Process deferred events - attempt to match them
    # Build lists of potential new events and currently deferred events
    potential_new_reschedule_targets = []
    deferred_events_awaiting_match = []

    # Define the cutoff for considering deferred events for matching
    thirty_days_ago_dt = datetime.now() - timedelta(days=30) 

    for event_id, entry in seen_events_db.items():
        # Only consider events seen or updated this run OR already in a deferred_pending_match state
        # Note: An event must have been processed in Pass 1 (last_processed_timestamp == current_run_iso_time)
        # OR be an existing 'deferred_pending_match' event from a previous run to be considered here.
        if entry["last_processed_timestamp"] == current_run_iso_time or entry["current_status"] == "deferred_pending_match":
            if entry["current_status"] == "active" and 'newly_added' in entry["processing_tags"]:
                 # Check if it has a date; events without date cannot be targets
                if entry["event_data"].get("EventDate"):
                    potential_new_reschedule_targets.append(entry)
            elif entry["current_status"] == "deferred_pending_match":
                try:
                    # Ensure last_alert_timestamp is valid and parse it
                    last_alert_ts_str = entry.get("last_alert_timestamp")
                    if not last_alert_ts_str:
                        logger.warning(f"EventId {event_id} is 'deferred_pending_match' but has no last_alert_timestamp. Skipping match attempt.")
                        continue
                    
                    last_alert_dt = datetime.fromisoformat(last_alert_ts_str.replace('Z', '+00:00'))
                    
                    if last_alert_dt >= thirty_days_ago_dt:
                        deferred_events_awaiting_match.append(entry)
                    else:
                        # Log that we are no longer attempting to match this old deferred event.
                        # Its status remains 'deferred_pending_match', it just won't be actively matched
                        # and will naturally fall off "Updates" lists due to its age.
                        logger.info(f"EventId {event_id} (deferred on {last_alert_dt.date()}) is older than 30 days. No longer attempting to match.")
                except ValueError:
                    logger.error(f"Could not parse last_alert_timestamp: {entry.get('last_alert_timestamp')} for event {event_id} while checking match eligibility. Skipping.")
    
    # Sort potential new events by their datetime (earliest first)
    potential_new_reschedule_targets.sort(key=lambda x: get_event_datetime(x["event_data"]) or datetime.max)

    logger.info(f"Attempting to match {len(deferred_events_awaiting_match)} deferred events with {len(potential_new_reschedule_targets)} potential new reschedule targets.")

    matched_new_event_ids = set() # To ensure a new event is not matched to multiple deferred ones

    for deferred_entry in deferred_events_awaiting_match:
        deferred_event_id = str(deferred_entry["event_data"]["EventId"])
        best_match_found = None
        
        deferred_event_dt = get_event_datetime(deferred_entry["event_data"])
        if not deferred_event_dt: # Should not happen if it was 'active' then 'deferred'
            logger.warning(f"Deferred event {deferred_event_id} has no valid original datetime. Skipping match attempt.")
            continue

        for new_event_entry in potential_new_reschedule_targets:
            new_event_id = str(new_event_entry["event_data"]["EventId"])
            if new_event_id == deferred_event_id: # Cannot be rescheduled to itself
                continue
            if new_event_id in matched_new_event_ids: # Already used as a match
                continue

            # Basic Heuristics for matching:
            # 1. Must be the same EventBodyName
            if new_event_entry["event_data"].get("EventBodyName") != deferred_entry["event_data"].get("EventBodyName"):
                continue

            # 2. New event's date must be after the deferred event's date
            new_event_dt = get_event_datetime(new_event_entry["event_data"])
            if not new_event_dt or new_event_dt <= deferred_event_dt:
                continue
            
            # 3. EventComment must be identical (if both exist) or new one can be empty if old one was too.
            #    If one has a comment and the other doesn't, they are not a match.
            old_comment = (deferred_entry["event_data"].get("EventComment") or "").strip()
            new_comment = (new_event_entry["event_data"].get("EventComment") or "").strip()
            if old_comment != new_comment:
                continue
            
            # If multiple new events could match, we prefer the one with the earliest valid date.
            # potential_new_reschedule_targets is already sorted by date.
            best_match_found = new_event_entry
            break # Found the best match for this deferred_entry

        if best_match_found:
            matched_new_event_id = str(best_match_found["event_data"]["EventId"])
            logger.info(f"EventId {deferred_event_id} (deferred) matched with new EventId {matched_new_event_id}.")
            
            # Update the original deferred event
            deferred_entry["current_status"] = "deferred_rescheduled_internal" # Internal status
            deferred_entry["rescheduled_event_details_if_deferred"] = {
                "matched_event_id": matched_new_event_id,
                "new_date": best_match_found["event_data"].get("EventDate"),
                "new_time": best_match_found["event_data"].get("EventTime"),
                "new_location": best_match_found["event_data"].get("EventLocation"),
                "match_timestamp": current_run_iso_time
            }
            # CRITICAL: deferred_entry's last_alert_type and last_alert_timestamp DO NOT CHANGE.
            deferred_entry["processing_tags"].append('became_rescheduled_match_found_for_original')
            deferred_entry["last_significant_change_timestamp"] = current_run_iso_time


            # Update the new event that is the reschedule target
            best_match_found["original_event_details_if_rescheduled"] = {
                "original_event_id": deferred_event_id,
                "original_date": deferred_entry["event_data"].get("EventDate"),
                "original_time": deferred_entry["event_data"].get("EventTime"),
                "original_status_when_deferred": "Deferred", 
                "match_timestamp": current_run_iso_time
            }
            best_match_found["processing_tags"].append('newly_added_as_reschedule_target')
            # CRITICAL: best_match_found's last_alert_type ("new") and last_alert_timestamp (its first_seen) DO NOT CHANGE.
            
            newly_rescheduled_pairs_this_run.append({
                "deferred_event_id": deferred_event_id,
                "rescheduled_to_event_id": matched_new_event_id,
                "deferred_event_data_at_deferral": deferred_entry["event_data"], # For context in updates
                "rescheduled_event_data": best_match_found["event_data"] # For context
            })
            matched_new_event_ids.add(matched_new_event_id)
        # else: # No match found for this deferred_entry in this run.
            # Grace period logic removed. A deferred event will remain deferred_pending_match indefinitely if no match is found.
            # Its visibility in "Updates" is solely determined by its last_alert_timestamp.
            # logger.info(f"EventId {deferred_event_id} (deferred) did not find a match this run. Remains 'deferred_pending_match'.")

    # Pass 3: Mark events not seen in this API pull as 'archived' if they were 'active'
    # This is less critical now that we have a large lookback, but good for hygiene.
    # Or, if they were 'deferred_pending_match' or 'deferred_rescheduled_internal' and suddenly disappear from API,
    # it's an anomaly. For now, we don't change their status aggressively based on absence alone,
    # as they might reappear. The grace period handles 'deferred_pending_match'.
    # 'deferred_rescheduled_internal' implies a match was made; the new event is now the active one.
    # If the *original* deferred event disappears, its 'deferred_rescheduled_internal' status is still informative.

    for event_id, entry in seen_events_db.items():
        if event_id not in processed_event_ids_this_run:
            # This event was in our DB but not in the latest API pull
            if entry["current_status"] == "active":
                # Consider if this should change status or just be noted.
                # For now, if it's active and disappears, it's unusual. Log it.
                # entry["current_status"] = "archived_vanished_while_active" 
                # entry["last_significant_change_timestamp"] = current_run_iso_time
                entry["processing_tags"].append('vanished_from_api_while_active')
                logger.warning(f"EventId {event_id} was 'active' but not found in current API pull (within lookback). Status not changed, tagged.")
            elif entry["current_status"] == "deferred_pending_match":
                # If it's pending match and vanishes, it's similar to grace period expiry, but faster.
                # The grace period logic based on last_alert_timestamp should handle this eventually.
                # For now, just tag it.
                entry["processing_tags"].append('vanished_from_api_while_deferred_pending')
                logger.warning(f"EventId {event_id} was 'deferred_pending_match' but not found in current API pull. Tagged.")


    logger.info(f"Processed {len(processed_event_ids_this_run)} events from API data.")
    logger.info(f"Found {len(newly_added_event_ids_this_run)} newly added events this run.")
    logger.info(f"Found {len(newly_deferred_event_ids_this_run)} events newly deferred this run.")
    logger.info(f"Found {len(newly_rescheduled_pairs_this_run)} newly rescheduled pairs this run.")

    return seen_events_db, newly_added_event_ids_this_run, newly_deferred_event_ids_this_run, newly_rescheduled_pairs_this_run


def generate_output_for_webpage(seen_events_db, newly_added_ids_this_run, newly_deferred_ids_this_run, newly_rescheduled_pairs_this_run):
    """
    Generates the structured data for `processed_events_for_web.json`.
    The 'type' field in the output maps to `last_alert_type` from `seen_events_db`
    for 7/30 day lists. For "since_last_run", it's determined by the specific lists passed in.
    """
    logger.info("Generating output for web page...")
    
    all_upcoming_hearings = []
    updates_since_last_run = []
    updates_last_7_days = []
    updates_last_30_days = []

    today_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    current_run_iso_time = datetime.now().isoformat() # For comparing timestamps

    # Helper to create a consistent "wrapped" update item structure
    # This is mostly for the "updates_since_last_run" list
    def create_wrapped_update_for_last_run(entry_id, type_for_last_run):
        entry = seen_events_db[entry_id]
        # For "since_last_run", the effective alert timestamp is 'now' or when the event happened this run.
        # For 'newly_added', last_alert_timestamp is its first_seen.
        # For 'newly_deferred', last_alert_timestamp is when it became deferred.
        return {
            "type": type_for_last_run, # "new" or "deferred" for "since_last_run" items
            "alert_timestamp": entry["last_alert_timestamp"], # This is the key for sorting and filtering
            "data": entry 
        }

    # 1. Populate "Updates - Since Last Run"
    # These are events that became "new" or "deferred" *during this specific run*.
    for event_id in newly_added_ids_this_run:
        entry = seen_events_db[event_id]
        # If it was added and immediately identified as a reschedule target, its last_alert_type is "new".
        # If it was added and immediately identified as deferred (e.g. API shows "Deferred" on first sight),
        # its last_alert_type will be "deferred".
        # The `type_for_last_run` should reflect the primary alert this causes.
        alert_type_for_this_update = entry["last_alert_type"] # Should be "new" or "deferred" (if born deferred)
        updates_since_last_run.append(create_wrapped_update_for_last_run(event_id, alert_type_for_this_update))
        
    for event_id in newly_deferred_ids_this_run:
        entry = seen_events_db[event_id]
        # If an event was ALREADY in newly_added_ids_this_run (i.e. born deferred), don't add it again.
        # The 'newly_added_ids_this_run' loop already picked it up with last_alert_type="deferred".
        if event_id not in newly_added_ids_this_run:
             updates_since_last_run.append(create_wrapped_update_for_last_run(event_id, "deferred"))


    # Sort "Updates - Since Last Run" by alert timestamp (desc), then by EventDate (desc)
    updates_since_last_run.sort(key=lambda x: (
        x["alert_timestamp"], 
        get_event_datetime(x["data"]["event_data"]) or datetime.min
    ), reverse=True)


    # 2. Populate "Upcoming Hearings" and "Updates - Last 7/30 Days"
    for event_id, entry in seen_events_db.items():
        event_data = entry.get("event_data", {})
        event_dt = get_event_datetime(event_data)

        # UPCOMING HEARINGS
        # Must be 'active' and occur today or in the future.
        if entry.get("current_status") == "active":
            if event_dt and event_dt >= today_dt:
                # Add user_facing_tags for the "Upcoming Hearings" cards
                tags = []
                if entry.get("last_alert_type") == "new" and \
                   (datetime.fromisoformat(entry.get("last_alert_timestamp", "1970-01-01T00:00:00Z")) > (datetime.now() - timedelta(days=2))): # Approx last 48h
                    tags.append("new_hearing_tag")
                
                if entry.get("original_event_details_if_rescheduled"):
                    tags.append("rescheduled_hearing_tag")
                
                # Deferred tags for 'upcoming' only if it was deferred and then reverted to active with a new date
                # This is complex. For now, simpler: only 'new' and 'rescheduled' tags on active upcoming.
                # If it was 'deferred_rescheduled_internal', it's not 'active'.

                entry_for_web = entry.copy() # Avoid modifying the main db entry
                entry_for_web["user_facing_tags"] = tags
                all_upcoming_hearings.append(entry_for_web)

        # UPDATES - LAST 7/30 DAYS (based on last_alert_timestamp)
        last_alert_type = entry.get("last_alert_type") # "new" or "deferred"
        last_alert_ts_str = entry.get("last_alert_timestamp")

        if last_alert_type and last_alert_ts_str:
            try:
                last_alert_dt = datetime.fromisoformat(last_alert_ts_str.replace('Z', '+00:00'))
            except ValueError:
                logger.error(f"Could not parse last_alert_timestamp: {last_alert_ts_str} for event {event_id}")
                continue

            update_item = {
                "type": last_alert_type, # Directly use "new" or "deferred"
                "alert_timestamp": last_alert_ts_str,
                "data": entry
            }

            # Filter for "new" type: must be future or today dated for 7/30 day lists
            # For "deferred" type, it's always included regardless of its original date, as the alert is about the deferral itself.
            include_in_7_30_day_updates = False
            if last_alert_type == "new":
                if event_dt and event_dt >= today_dt:
                    include_in_7_30_day_updates = True
            elif last_alert_type == "deferred":
                include_in_7_30_day_updates = True


            if include_in_7_30_day_updates:
                if datetime.now() - last_alert_dt <= timedelta(days=7):
                    updates_last_7_days.append(update_item)
                if datetime.now() - last_alert_dt <= timedelta(days=30):
                    updates_last_30_days.append(update_item)

    # Sort Upcoming Hearings by date (ascending)
    all_upcoming_hearings.sort(key=lambda x: get_event_datetime(x["event_data"]) or datetime.max)

    # Sort 7/30 day updates by alert_timestamp (desc), then by EventDate (desc)
    key_func_sort_updates = lambda x: (
        x["alert_timestamp"], 
        get_event_datetime(x["data"]["event_data"]) or datetime.min
    )
    updates_last_7_days.sort(key=key_func_sort_updates, reverse=True)
    updates_last_30_days.sort(key=key_func_sort_updates, reverse=True)


    logger.info(f"Generated {len(all_upcoming_hearings)} upcoming hearings.")
    logger.info(f"Generated {len(updates_since_last_run)} updates since last run.")
    logger.info(f"Generated {len(updates_last_7_days)} updates for last 7 days.")
    logger.info(f"Generated {len(updates_last_30_days)} updates for last 30 days.")

    return {
        "generation_timestamp": current_run_iso_time,
        "upcoming_hearings": all_upcoming_hearings,
        "updates_since_last_run": updates_since_last_run,
        "updates_last_7_days": updates_last_7_days,
        "updates_last_30_days": updates_last_30_days,
        # metadata about the source of these updates for traceability if needed
        "source_newly_added_ids_count": len(newly_added_ids_this_run),
        "source_newly_deferred_ids_count": len(newly_deferred_ids_this_run),
        "source_newly_rescheduled_pairs_count": len(newly_rescheduled_pairs_this_run)
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
        process_event_changes(fetched_api_events, seen_events, api)
    
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