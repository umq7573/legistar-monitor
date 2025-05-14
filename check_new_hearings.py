#!/usr/bin/env python3
import os
import json
import logging
from datetime import datetime, timedelta
from legistar_api import LegistarAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('hearing_checker')

# Constants
DATA_DIR = "data"
HISTORY_FILE = os.path.join(DATA_DIR, "seen_events.json")
LOOKBACK_DAYS = 7   # How many days in the past to check
LOOKAHEAD_DAYS = 30  # How many days in the future to check

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

def fetch_upcoming_events(api):
    """Fetch upcoming events from the Legistar API"""
    today = datetime.now()
    start_date = (today - timedelta(days=LOOKBACK_DAYS))
    end_date = (today + timedelta(days=LOOKAHEAD_DAYS))
    
    logger.info(f"Fetching events from {start_date.date()} to {end_date.date()}")
    
    events = api.get_events(
        top=1000,  # Maximum records to return
        date_range=(start_date, end_date)
    )
    
    if not events:
        logger.warning("No events found")
        return []
    
    logger.info(f"Found {len(events)} events")
    return events

def categorize_event_changes(events, seen_events):
    """
    Categorize event changes into different types:
    1. New events with dates
    2. New events without dates
    3. Rescheduled events (date changed)
    4. Date confirmed events (previously no date, now has date)
    """
    new_with_dates = []
    new_without_dates = []
    rescheduled = []
    date_confirmed = []
    
    # Dictionary to look up events by ID for faster processing
    seen_events_by_id = {}
    for key, event_data in seen_events.items():
        event_id = event_data.get('event_id')
        if event_id:
            seen_events_by_id[event_id] = event_data
    
    for event in events:
        event_id = str(event['EventId'])
        event_body = event['EventBodyName']
        event_date = event['EventDate'] if event.get('EventDate') else None
        event_time = event['EventTime'] if event.get('EventTime') else None
        
        # Create a unique key for the event
        event_key = f"{event_id}_{event_body}_{event_date}"
        
        # Check if this event ID has been seen before
        if event_id in seen_events_by_id:
            # We've seen this event before
            previous_data = seen_events_by_id[event_id]
            previous_date = previous_data.get('date')
            
            # Case: Previously no date, now has date (date confirmed)
            if not previous_date and event_date:
                logger.info(f"Date confirmed for event: {event_body}")
                date_confirmed.append(event)
                
                # Update the event data
                seen_events[event_key] = {
                    'first_seen': previous_data.get('first_seen'),
                    'last_updated': datetime.now().isoformat(),
                    'event_id': event_id,
                    'body': event_body,
                    'date': event_date,
                    'time': event_time,
                    'status': 'date_confirmed',
                    'previous_date': previous_date
                }
                
                # Remove old key if it exists
                old_key = f"{event_id}_{event_body}_{previous_date}"
                if old_key in seen_events and old_key != event_key:
                    seen_events.pop(old_key)
            
            # Case: Date changed (rescheduled)
            elif previous_date and event_date and previous_date != event_date:
                logger.info(f"Event rescheduled: {event_body} from {previous_date} to {event_date}")
                rescheduled.append(event)
                
                # Update the event data
                seen_events[event_key] = {
                    'first_seen': previous_data.get('first_seen'),
                    'last_updated': datetime.now().isoformat(),
                    'event_id': event_id,
                    'body': event_body,
                    'date': event_date,
                    'time': event_time,
                    'status': 'rescheduled',
                    'previous_date': previous_date
                }
                
                # Remove old key if it exists
                old_key = f"{event_id}_{event_body}_{previous_date}"
                if old_key in seen_events and old_key != event_key:
                    seen_events.pop(old_key)
            
            # If we've seen this exact event before with this date, do nothing
            elif event_key in seen_events:
                # Just update the last seen time
                if seen_events[event_key].get('status') not in ['new', 'rescheduled', 'date_confirmed']:
                    seen_events[event_key]['status'] = 'unchanged'
                seen_events[event_key]['last_checked'] = datetime.now().isoformat()
        
        # New event
        else:
            if event_date:
                logger.info(f"New event with date found: {event_body} on {event_date}")
                new_with_dates.append(event)
                status = 'new_with_date'
            else:
                logger.info(f"New event without date found: {event_body}")
                new_without_dates.append(event)
                status = 'new_without_date'
            
            # Mark as seen for next time
            seen_events[event_key] = {
                'first_seen': datetime.now().isoformat(),
                'last_updated': datetime.now().isoformat(),
                'event_id': event_id,
                'body': event_body,
                'date': event_date,
                'time': event_time,
                'status': status
            }
    
    # Collect all changes for notification
    all_changes = {
        'new_with_dates': new_with_dates,
        'new_without_dates': new_without_dates,
        'rescheduled': rescheduled,
        'date_confirmed': date_confirmed
    }
    
    return all_changes, seen_events

def format_event_for_notification(event, change_type=None):
    """Format event details for notification"""
    formatted = {
        'id': event['EventId'],
        'body': event['EventBodyName'],
        'date': event['EventDate'] if event.get('EventDate') else None,
        'time': event['EventTime'] if event.get('EventTime') else None,
        'location': event['EventLocation'] if event.get('EventLocation') else None,
        'agenda_url': event['EventAgendaFile'] if event.get('EventAgendaFile') else "No agenda available yet",
        'change_type': change_type
    }
    
    return formatted

def main():
    """Main function to check for new hearings"""
    logger.info("Starting hearing check")
    
    # Initialize API client
    api = LegistarAPI(config_file="config.json")
    
    # Load previously seen events
    seen_events = load_seen_events()
    logger.info(f"Loaded {len(seen_events)} previously seen events")
    
    # Fetch upcoming events
    events = fetch_upcoming_events(api)
    
    # Categorize event changes
    changes, updated_seen_events = categorize_event_changes(events, seen_events)
    
    # Save updated seen events
    save_seen_events(updated_seen_events)
    
    # Format events for notification
    notification_data = []
    
    # New events with dates
    for event in changes['new_with_dates']:
        notification_data.append(format_event_for_notification(event, 'new_with_date'))
    
    # New events without dates
    for event in changes['new_without_dates']:
        notification_data.append(format_event_for_notification(event, 'new_without_date'))
    
    # Rescheduled events
    for event in changes['rescheduled']:
        notification_data.append(format_event_for_notification(event, 'rescheduled'))
    
    # Date confirmed events
    for event in changes['date_confirmed']:
        notification_data.append(format_event_for_notification(event, 'date_confirmed'))
    
    # Save the changes to files for notification system to pick up
    total_changes = len(notification_data)
    
    if total_changes > 0:
        logger.info(f"Found {total_changes} event changes for notification")
        
        # Save detailed breakdown for notification system
        changes_counts = {
            'new_with_dates': len(changes['new_with_dates']),
            'new_without_dates': len(changes['new_without_dates']),
            'rescheduled': len(changes['rescheduled']),
            'date_confirmed': len(changes['date_confirmed']),
            'total': total_changes
        }
        
        # Save categorized events for detailed processing
        categorized_changes = {
            'new_with_dates': [format_event_for_notification(e, 'new_with_date') for e in changes['new_with_dates']],
            'new_without_dates': [format_event_for_notification(e, 'new_without_date') for e in changes['new_without_dates']],
            'rescheduled': [format_event_for_notification(e, 'rescheduled') for e in changes['rescheduled']],
            'date_confirmed': [format_event_for_notification(e, 'date_confirmed') for e in changes['date_confirmed']]
        }
        
        # Save the data
        os.makedirs(DATA_DIR, exist_ok=True)
        
        # Save all changes in one file
        new_events_file = os.path.join(DATA_DIR, "new_events.json")
        with open(new_events_file, 'w') as f:
            json.dump(notification_data, f, indent=2)
        
        # Save categorized changes
        categorized_file = os.path.join(DATA_DIR, "categorized_events.json") 
        with open(categorized_file, 'w') as f:
            json.dump(categorized_changes, f, indent=2)
        
        # Save summary counts
        summary_file = os.path.join(DATA_DIR, "changes_summary.json")
        with open(summary_file, 'w') as f:
            json.dump(changes_counts, f, indent=2)
        
        # Set GitHub Actions outputs - use the new environment file approach if available
        github_output = os.environ.get('GITHUB_OUTPUT')
        if github_output:
            with open(github_output, 'a') as f:
                f.write(f"total_changes={total_changes}\n")
                f.write(f"new_with_dates={len(changes['new_with_dates'])}\n")
                f.write(f"new_without_dates={len(changes['new_without_dates'])}\n")
                f.write(f"rescheduled={len(changes['rescheduled'])}\n")
                f.write(f"date_confirmed={len(changes['date_confirmed'])}\n")
                f.write(f"new_events_file={new_events_file}\n")
        else:
            # Fallback to deprecated set-output command
            print(f"::set-output name=total_changes::{total_changes}")
            print(f"::set-output name=new_with_dates::{len(changes['new_with_dates'])}")
            print(f"::set-output name=new_without_dates::{len(changes['new_without_dates'])}")
            print(f"::set-output name=rescheduled::{len(changes['rescheduled'])}")
            print(f"::set-output name=date_confirmed::{len(changes['date_confirmed'])}")
            print(f"::set-output name=new_events_file::{new_events_file}")
    else:
        logger.info("No event changes found")
        
        # Set GitHub Actions outputs - use the new environment file approach if available
        github_output = os.environ.get('GITHUB_OUTPUT')
        if github_output:
            with open(github_output, 'a') as f:
                f.write("total_changes=0\n")
        else:
            # Fallback to deprecated set-output command
            print("::set-output name=total_changes::0")
    
    logger.info("Hearing check completed")
    return total_changes

if __name__ == "__main__":
    main() 