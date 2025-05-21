#!/usr/bin/env python3
import os
import json
import logging
from datetime import datetime
import sys
import argparse
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests  # For Slack notifications

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('hearing_notifier')

# Constants
DATA_DIR = "data"
NEW_EVENTS_FILE = os.path.join(DATA_DIR, "new_events.json")
CATEGORIZED_EVENTS_FILE = os.path.join(DATA_DIR, "categorized_events.json")
SUMMARY_FILE = os.path.join(DATA_DIR, "changes_summary.json")
CONFIG_FILE = "notification_config.json"

def load_config():
    """Load notification configuration"""
    if not os.path.exists(CONFIG_FILE):
        logger.warning(f"No config file found at {CONFIG_FILE}, using defaults")
        return {
            "notification_method": "file",  # Options: file, email, slack
            "email": {
                "enabled": False,
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "username": "",
                "password": "",
                "from_email": "",
                "to_emails": []
            },
            "slack": {
                "enabled": False,
                "webhook_url": "",
                "channel": "#general",
                "username": "Hearing Monitor"
            },
            "preferences": {
                "notify_new_with_dates": True,
                "notify_new_without_dates": True,
                "notify_rescheduled": True,
                "notify_date_confirmed": True,
                "send_summary_only": False
            }
        }
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config file: {e}")
        return {}

def load_summary():
    """Load summary of changes"""
    if not os.path.exists(SUMMARY_FILE):
        logger.warning(f"No summary file found at {SUMMARY_FILE}")
        return None
    
    try:
        with open(SUMMARY_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading summary file: {e}")
        return None

def load_categorized_events():
    """Load categorized events"""
    if not os.path.exists(CATEGORIZED_EVENTS_FILE):
        logger.warning(f"No categorized events file found at {CATEGORIZED_EVENTS_FILE}")
        return None
    
    try:
        with open(CATEGORIZED_EVENTS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading categorized events file: {e}")
        return None

def load_new_events():
    """Load all new events (backwards compatibility)"""
    if not os.path.exists(NEW_EVENTS_FILE):
        logger.warning(f"No new events file found at {NEW_EVENTS_FILE}")
        return []
    
    try:
        with open(NEW_EVENTS_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading new events file: {e}")
        return []

def format_summary_text(summary):
    """Format a summary of changes"""
    if not summary:
        return "No changes to report."
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    text = f"Hearing Changes Summary - {now}\n\n"
    text += f"Total changes: {summary.get('total', 0)}\n"
    text += f"New events with dates: {summary.get('new_with_dates', 0)}\n"
    text += f"New events without dates: {summary.get('new_without_dates', 0)}\n"
    text += f"Rescheduled events: {summary.get('rescheduled', 0)}\n"
    text += f"Events with newly confirmed dates: {summary.get('date_confirmed', 0)}\n"
    
    return text

def format_event_text(event, include_type=True):
    """Format a single event for text notification"""
    text = ""
    
    if include_type and event.get('change_type'):
        change_type = event['change_type']
        if change_type == 'new_with_date':
            text += "NEW EVENT: "
        elif change_type == 'new_without_date':
            text += "NEW EVENT (NO DATE): "
        elif change_type == 'rescheduled':
            text += "RESCHEDULED: "
        elif change_type == 'date_confirmed':
            text += "DATE CONFIRMED: "
    
    text += f"{event['body']}\n"
    
    if event.get('date'):
        # Parse the date from ISO format to a more readable format
        try:
            date_obj = datetime.fromisoformat(event['date'].replace('Z', '+00:00'))
            formatted_date = date_obj.strftime("%A, %B %d, %Y")
            text += f"Date: {formatted_date}\n"
        except:
            text += f"Date: {event['date']}\n"
    else:
        text += "Date: Not scheduled yet\n"
    
    if event.get('time'):
        text += f"Time: {event['time']}\n"
    
    if event.get('location'):
        text += f"Location: {event['location']}\n"
    
    if event.get('agenda_url') and event['agenda_url'] != "No agenda available yet":
        text += f"Agenda: {event['agenda_url']}\n"
    else:
        text += "Agenda: Not available yet\n"
    
    text += f"Event ID: {event['id']}\n"
    
    return text

def format_notification_text(events, categorized=False, preferences=None):
    """Format the notification text for email/message"""
    if not events:
        return "No changes to report."
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Set default preferences if not provided
    if not preferences:
        preferences = {
            "notify_new_with_dates": True,
            "notify_new_without_dates": True,
            "notify_rescheduled": True,
            "notify_date_confirmed": True,
            "send_summary_only": False
        }
    
    if categorized:
        # Create separate sections for each category
        text = f"Hearing Changes Alert - {now}\n\n"
        
        # Summary section
        total_count = 0
        summary = "SUMMARY:\n"
        
        if preferences["notify_new_with_dates"] and events.get('new_with_dates'):
            count = len(events['new_with_dates'])
            total_count += count
            summary += f"- New events with dates: {count}\n"
        
        if preferences["notify_new_without_dates"] and events.get('new_without_dates'):
            count = len(events['new_without_dates'])
            total_count += count
            summary += f"- New events without dates: {count}\n"
        
        if preferences["notify_rescheduled"] and events.get('rescheduled'):
            count = len(events['rescheduled'])
            total_count += count
            summary += f"- Rescheduled events: {count}\n"
        
        if preferences["notify_date_confirmed"] and events.get('date_confirmed'):
            count = len(events['date_confirmed'])
            total_count += count
            summary += f"- Events with newly confirmed dates: {count}\n"
        
        summary += f"\nTotal: {total_count} changes\n\n"
        text += summary
        
        # If summary only, return now
        if preferences["send_summary_only"]:
            text += "---\n"
            text += "This is an automated notification from the Legistar Hearing Monitor."
            return text
        
        # Detailed sections
        if preferences["notify_new_with_dates"] and events.get('new_with_dates'):
            text += "\n=== NEW EVENTS ===\n\n"
            for i, event in enumerate(events['new_with_dates'], 1):
                text += f"#{i}: {format_event_text(event, include_type=False)}\n"
        
        if preferences["notify_new_without_dates"] and events.get('new_without_dates'):
            text += "\n=== NEW EVENTS (NO DATE) ===\n\n"
            for i, event in enumerate(events['new_without_dates'], 1):
                text += f"#{i}: {format_event_text(event, include_type=False)}\n"
        
        if preferences["notify_rescheduled"] and events.get('rescheduled'):
            text += "\n=== RESCHEDULED EVENTS ===\n\n"
            for i, event in enumerate(events['rescheduled'], 1):
                text += f"#{i}: {format_event_text(event, include_type=False)}\n"
        
        if preferences["notify_date_confirmed"] and events.get('date_confirmed'):
            text += "\n=== EVENTS WITH NEWLY CONFIRMED DATES ===\n\n"
            for i, event in enumerate(events['date_confirmed'], 1):
                text += f"#{i}: {format_event_text(event, include_type=False)}\n"
    else:
        # Simple list of all events
        text = f"Hearing Changes Alert - {now}\n\n"
        text += f"Found {len(events)} hearing changes:\n\n"
        
        for i, event in enumerate(events, 1):
            text += f"#{i}: {format_event_text(event)}\n"
    
    text += "---\n"
    text += "This is an automated notification from the Legistar Hearing Monitor."
    
    return text

def generate_html_notification(events, categorized=False, preferences=None):
    """Generate HTML version of the notification for email"""
    if not events:
        return "<p>No changes to report.</p>"
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Set default preferences if not provided
    if not preferences:
        preferences = {
            "notify_new_with_dates": True,
            "notify_new_without_dates": True,
            "notify_rescheduled": True,
            "notify_date_confirmed": True,
            "send_summary_only": False
        }
    
    if categorized:
        # Create separate sections for each category
        html = f"<h2>Hearing Changes Alert - {now}</h2>"
        
        # Summary section
        total_count = 0
        summary = "<h3>SUMMARY</h3><ul>"
        
        if preferences["notify_new_with_dates"] and events.get('new_with_dates'):
            count = len(events['new_with_dates'])
            total_count += count
            summary += f"<li><strong>New events with dates:</strong> {count}</li>"
        
        if preferences["notify_new_without_dates"] and events.get('new_without_dates'):
            count = len(events['new_without_dates'])
            total_count += count
            summary += f"<li><strong>New events without dates:</strong> {count}</li>"
        
        if preferences["notify_rescheduled"] and events.get('rescheduled'):
            count = len(events['rescheduled'])
            total_count += count
            summary += f"<li><strong>Rescheduled events:</strong> {count}</li>"
        
        if preferences["notify_date_confirmed"] and events.get('date_confirmed'):
            count = len(events['date_confirmed'])
            total_count += count
            summary += f"<li><strong>Events with newly confirmed dates:</strong> {count}</li>"
        
        summary += f"</ul><p><strong>Total:</strong> {total_count} changes</p>"
        html += summary
        
        # If summary only, return now
        if preferences["send_summary_only"]:
            html += "<hr>"
            html += "<p><em>This is an automated notification from the Legistar Hearing Monitor.</em></p>"
            return html
        
        # Detailed sections
        if preferences["notify_new_with_dates"] and events.get('new_with_dates'):
            html += "<h3>NEW EVENTS</h3>"
            for i, event in enumerate(events['new_with_dates'], 1):
                html += format_event_html(event, i, 'new')
        
        if preferences["notify_new_without_dates"] and events.get('new_without_dates'):
            html += "<h3>NEW EVENTS (NO DATE)</h3>"
            for i, event in enumerate(events['new_without_dates'], 1):
                html += format_event_html(event, i, 'new-no-date')
        
        if preferences["notify_rescheduled"] and events.get('rescheduled'):
            html += "<h3>RESCHEDULED EVENTS</h3>"
            for i, event in enumerate(events['rescheduled'], 1):
                html += format_event_html(event, i, 'rescheduled')
        
        if preferences["notify_date_confirmed"] and events.get('date_confirmed'):
            html += "<h3>EVENTS WITH NEWLY CONFIRMED DATES</h3>"
            for i, event in enumerate(events['date_confirmed'], 1):
                html += format_event_html(event, i, 'date-confirmed')
    else:
        # Simple list of all events
        html = f"<h2>Hearing Changes Alert - {now}</h2>"
        html += f"<p>Found {len(events)} hearing changes:</p>"
        
        for i, event in enumerate(events, 1):
            html += format_event_html(event, i, event.get('change_type', 'unknown'))
    
    html += "<hr>"
    html += "<p><em>This is an automated notification from the Legistar Hearing Monitor.</em></p>"
    
    return html

def format_event_html(event, index, change_type):
    """Format a single event for HTML notification"""
    # Select background color based on change type
    bg_color = "#ffffff"  # Default white
    border_color = "#cccccc"  # Default gray
    
    if change_type == 'new' or change_type == 'new_with_date':
        bg_color = "#e6ffed"  # Light green
        border_color = "#28a745"
    elif change_type == 'new-no-date' or change_type == 'new_without_date':
        bg_color = "#fff9e6"  # Light yellow
        border_color = "#ffc107"
    elif change_type == 'rescheduled':
        bg_color = "#f1e7ff"  # Light purple
        border_color = "#6f42c1"
    elif change_type == 'date-confirmed' or change_type == 'date_confirmed':
        bg_color = "#e6f7ff"  # Light blue
        border_color = "#007bff"
    
    html = f"<div style='margin-bottom: 20px; padding: 10px; border: 1px solid {border_color}; border-left: 5px solid {border_color}; background-color: {bg_color};'>"
    html += f"<h4 style='margin-top: 0;'>#{index}: {event['body']}</h4>"
    
    if event.get('date'):
        try:
            date_obj = datetime.fromisoformat(event['date'].replace('Z', '+00:00'))
            formatted_date = date_obj.strftime("%A, %B %d, %Y")
            html += f"<p><strong>Date:</strong> {formatted_date}</p>"
        except:
            html += f"<p><strong>Date:</strong> {event['date']}</p>"
    else:
        html += "<p><strong>Date:</strong> Not scheduled yet</p>"
    
    if event.get('time'):
        html += f"<p><strong>Time:</strong> {event['time']}</p>"
    
    if event.get('location'):
        html += f"<p><strong>Location:</strong> {event['location']}</p>"
    
    if event.get('agenda_url') and event['agenda_url'] != "No agenda available yet":
        html += f"<p><strong>Agenda:</strong> <a href='{event['agenda_url']}'>View Agenda</a></p>"
    else:
        html += "<p><strong>Agenda:</strong> Not available yet</p>"
    
    html += f"<p><small>Event ID: {event['id']}</small></p>"
    html += "</div>"
    
    return html

def send_email_notification(text, html, config):
    """Send email notification"""
    email_config = config.get('email', {})
    
    if not email_config.get('enabled'):
        logger.info("Email notifications are disabled in config")
        return False
    
    smtp_server = email_config.get('smtp_server')
    smtp_port = email_config.get('smtp_port')
    username = email_config.get('username')
    password = email_config.get('password')
    from_email = email_config.get('from_email')
    to_emails = email_config.get('to_emails', [])
    
    if not (smtp_server and smtp_port and username and password and from_email and to_emails):
        logger.error("Incomplete email configuration, cannot send notification")
        return False
    
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "Legistar Hearing Monitor Alert"
        msg['From'] = from_email
        msg['To'] = ", ".join(to_emails)
        
        # Attach both plain text and HTML versions
        part1 = MIMEText(text, 'plain')
        part2 = MIMEText(html, 'html')
        msg.attach(part1)
        msg.attach(part2)
        
        # Send the email
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(username, password)
        server.sendmail(from_email, to_emails, msg.as_string())
        server.quit()
        
        logger.info(f"Email notification sent to {len(to_emails)} recipients")
        return True
    except Exception as e:
        logger.error(f"Error sending email notification: {e}")
        return False

def send_slack_notification(text, config):
    """Send Slack notification"""
    slack_config = config.get('slack', {})
    
    if not slack_config.get('enabled'):
        logger.info("Slack notifications are disabled in config")
        return False
    
    webhook_url = slack_config.get('webhook_url')
    channel = slack_config.get('channel', '#general')
    username = slack_config.get('username', 'Hearing Monitor')
    
    if not webhook_url:
        logger.error("Incomplete Slack configuration, cannot send notification")
        return False
    
    try:
        payload = {
            'text': text,
            'channel': channel,
            'username': username,
            'mrkdwn': True
        }
        
        response = requests.post(
            webhook_url,
            json=payload,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            logger.info(f"Slack notification sent to {channel}")
            return True
        else:
            logger.error(f"Error sending Slack notification: {response.status_code} {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending Slack notification: {e}")
        return False

def save_notification_to_files(text, html):
    """Save notification to files"""
    os.makedirs(DATA_DIR, exist_ok=True)
    
    with open(os.path.join(DATA_DIR, "notification_text.txt"), 'w') as f:
        f.write(text)
    
    with open(os.path.join(DATA_DIR, "notification_html.html"), 'w') as f:
        f.write(html)
    
    logger.info("Notification saved to files")
    return True

def send_notification(events, config, categorized=False):
    """Send notification through configured channels"""
    notification_method = config.get('notification_method', 'file')
    preferences = config.get('preferences', {})
    
    # Generate notification content
    text = format_notification_text(events, categorized, preferences)
    html = generate_html_notification(events, categorized, preferences)
    
    # Save to files regardless of notification method
    save_notification_to_files(text, html)
    
    # Also print to stdout for GitHub Actions logs
    print(text)
    
    # Send through configured channel
    if notification_method == 'email' or config.get('email', {}).get('enabled'):
        send_email_notification(text, html, config)
    
    if notification_method == 'slack' or config.get('slack', {}).get('enabled'):
        send_slack_notification(text, config)
    
    logger.info(f"Notifications sent via {notification_method}")
    return True

def initialize_config():
    """Initialize a default configuration file if it doesn't exist"""
    if os.path.exists(CONFIG_FILE):
        logger.info(f"Config file already exists at {CONFIG_FILE}")
        return
    
    default_config = {
        "notification_method": "file",  # Options: file, email, slack
        "email": {
            "enabled": False,
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587,
            "username": "",
            "password": "",
            "from_email": "",
            "to_emails": []
        },
        "slack": {
            "enabled": False,
            "webhook_url": "",
            "channel": "#general",
            "username": "Hearing Monitor"
        },
        "preferences": {
            "notify_new_with_dates": True,
            "notify_new_without_dates": True,
            "notify_rescheduled": True,
            "notify_date_confirmed": True,
            "send_summary_only": False
        }
    }
    
    with open(CONFIG_FILE, 'w') as f:
        json.dump(default_config, f, indent=2)
    
    logger.info(f"Created default config file at {CONFIG_FILE}")

def main():
    """Main function to send notifications about new hearings"""
    parser = argparse.ArgumentParser(description='Send notifications about hearing changes')
    parser.add_argument('--init', action='store_true', help='Initialize configuration file')
    parser.add_argument('--method', choices=['file', 'email', 'slack'], help='Notification method')
    parser.add_argument('--summary-only', action='store_true', help='Send summary notification only')
    args = parser.parse_args()
    
    # Initialize config if requested
    if args.init:
        initialize_config()
        print(f"Created default config file at {CONFIG_FILE}. Please edit it with your notification settings.")
        return 0
    
    logger.info("Starting notification process")
    
    # Load configuration
    config = load_config()
    
    # Override config with command line arguments if provided
    if args.method:
        config['notification_method'] = args.method
    
    if args.summary_only:
        config['preferences']['send_summary_only'] = True
    
    # Try to load categorized events first
    categorized_events = load_categorized_events()
    
    if categorized_events:
        # Send notification with categorized data
        logger.info("Using categorized events data")
        send_notification(categorized_events, config, categorized=True)
    else:
        # Fall back to regular events list
        events = load_new_events()
        if events:
            logger.info("Using legacy events data format")
            send_notification(events, config, categorized=False)
        else:
            # No events found
            logger.info("No events found to notify about")
            print("No events found to notify about")
    
    logger.info("Notification process completed")
    return 0

if __name__ == "__main__":
    sys.exit(main()) 