#!/usr/bin/env python3
import os
import json
import logging
from datetime import datetime
import sys
import argparse
import shutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('web_page_generator')

# Constants
DATA_DIR = "data"
CATEGORIZED_EVENTS_FILE = os.path.join(DATA_DIR, "categorized_events.json")
SUMMARY_FILE = os.path.join(DATA_DIR, "changes_summary.json")
NEW_EVENTS_FILE = os.path.join(DATA_DIR, "new_events.json")
WEB_DIR = "docs"  # GitHub Pages serves from docs/ folder by default
INDEX_HTML = os.path.join(WEB_DIR, "index.html")

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

def format_date(date_str):
    """Format a date string for display"""
    if not date_str:
        return "Not scheduled yet"
    
    try:
        date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return date_obj.strftime("%A, %B %d, %Y")
    except:
        return date_str

def generate_html_page(events_data, summary_data=None, page_title="NYC Legistar Hearing Monitor"):
    """Generate an HTML page from the events data"""
    # If we have categorized data, use that format
    categorized = isinstance(events_data, dict) and any(k in events_data for k in ['new_with_dates', 'new_without_dates', 'rescheduled', 'date_confirmed'])
    
    # Start building the HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page_title}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            padding: 20px;
            max-width: 1200px;
            margin: 0 auto;
        }}
        .event-card {{
            margin-bottom: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        .card-new {{
            border-left: 5px solid #28a745;
        }}
        .card-new-no-date {{
            border-left: 5px solid #ffc107;
        }}
        .card-rescheduled {{
            border-left: 5px solid #6f42c1;
        }}
        .card-date-confirmed {{
            border-left: 5px solid #007bff;
        }}
        .last-updated {{
            font-style: italic;
            color: #666;
            font-size: 14px;
        }}
        .section-header {{
            margin-top: 30px;
            margin-bottom: 15px;
            padding-bottom: 5px;
            border-bottom: 2px solid #eee;
        }}
        .event-meta {{
            font-size: 14px;
            color: #666;
        }}
        .no-events {{
            font-style: italic;
            color: #666;
            padding: 15px;
        }}
        .column-container {{
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
        }}
        .column {{
            flex: 1;
            min-width: 250px;
            border-radius: 8px;
            padding: 10px;
            background-color: #f8f9fa;
        }}
    </style>
</head>
<body>
    <div class="container-fluid">
        <h1 class="mb-4">{page_title}</h1>
        <p class="last-updated">Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
"""

    # Add summary information if available
    if summary_data:
        html += f"""
        <div class="card mb-4">
            <div class="card-header bg-primary text-white">
                <h2 class="h5 mb-0">Summary</h2>
            </div>
            <div class="card-body">
                <div class="row">
                    <div class="col-md-3">
                        <p><strong>Total changes:</strong> {summary_data.get('total', 0)}</p>
                    </div>
                    <div class="col-md-3">
                        <p><strong>New events with dates:</strong> {summary_data.get('new_with_dates', 0)}</p>
                    </div>
                    <div class="col-md-3">
                        <p><strong>New events without dates:</strong> {summary_data.get('new_without_dates', 0)}</p>
                    </div>
                    <div class="col-md-3">
                        <p><strong>Rescheduled events:</strong> {summary_data.get('rescheduled', 0)}</p>
                    </div>
                    <div class="col-md-3">
                        <p><strong>Date confirmations:</strong> {summary_data.get('date_confirmed', 0)}</p>
                    </div>
                </div>
            </div>
        </div>
"""

    # Display events in columns based on category
    if categorized:
        html += """
        <div class="column-container">
"""
        # Column 1: New events with dates
        html += """
            <div class="column">
                <h2 class="h4 mb-3 text-success">New Events</h2>
"""
        if events_data.get('new_with_dates'):
            for event in events_data['new_with_dates']:
                html += f"""
                <div class="card event-card card-new mb-3">
                    <div class="card-body">
                        <h3 class="h5 card-title">{event['body']}</h3>
                        <p><strong>Date:</strong> {format_date(event.get('date'))}</p>
                        <p><strong>Time:</strong> {event.get('time', 'TBD')}</p>
                        <p><strong>Location:</strong> {event.get('location', 'TBD')}</p>
                        <div class="event-meta">
                            <p class="mb-0">ID: {event['id']}</p>
                            {f'<p class="mb-0"><a href="{event["agenda_url"]}" target="_blank">View Agenda</a></p>' if event.get('agenda_url') and event['agenda_url'] != "No agenda available yet" else '<p class="mb-0">Agenda not yet available</p>'}
                        </div>
                    </div>
                </div>
"""
        else:
            html += '<p class="no-events">No new events with dates</p>'
        html += """
            </div>
"""

        # Column 2: New events without dates
        html += """
            <div class="column">
                <h2 class="h4 mb-3 text-warning">New Events (No Date)</h2>
"""
        if events_data.get('new_without_dates'):
            for event in events_data['new_without_dates']:
                html += f"""
                <div class="card event-card card-new-no-date mb-3">
                    <div class="card-body">
                        <h3 class="h5 card-title">{event['body']}</h3>
                        <p><strong>Date:</strong> Not scheduled yet</p>
                        <div class="event-meta">
                            <p class="mb-0">ID: {event['id']}</p>
                        </div>
                    </div>
                </div>
"""
        else:
            html += '<p class="no-events">No new events without dates</p>'
        html += """
            </div>
"""

        # Column 3: Rescheduled events
        html += """
            <div class="column">
                <h2 class="h4 mb-3 text-purple">Rescheduled</h2>
"""
        if events_data.get('rescheduled'):
            for event in events_data['rescheduled']:
                html += f"""
                <div class="card event-card card-rescheduled mb-3">
                    <div class="card-body">
                        <h3 class="h5 card-title">{event['body']}</h3>
                        <p><strong>New Date:</strong> {format_date(event.get('date'))}</p>
                        <p><strong>Time:</strong> {event.get('time', 'TBD')}</p>
                        <p><strong>Location:</strong> {event.get('location', 'TBD')}</p>
                        <div class="event-meta">
                            <p class="mb-0">ID: {event['id']}</p>
                            {f'<p class="mb-0"><a href="{event["agenda_url"]}" target="_blank">View Agenda</a></p>' if event.get('agenda_url') and event['agenda_url'] != "No agenda available yet" else '<p class="mb-0">Agenda not yet available</p>'}
                        </div>
                    </div>
                </div>
"""
        else:
            html += '<p class="no-events">No rescheduled events</p>'
        html += """
            </div>
"""

        # Column 4: Date confirmations
        html += """
            <div class="column">
                <h2 class="h4 mb-3 text-primary">Date Confirmed</h2>
"""
        if events_data.get('date_confirmed'):
            for event in events_data['date_confirmed']:
                html += f"""
                <div class="card event-card card-date-confirmed mb-3">
                    <div class="card-body">
                        <h3 class="h5 card-title">{event['body']}</h3>
                        <p><strong>Date:</strong> {format_date(event.get('date'))}</p>
                        <p><strong>Time:</strong> {event.get('time', 'TBD')}</p>
                        <p><strong>Location:</strong> {event.get('location', 'TBD')}</p>
                        <div class="event-meta">
                            <p class="mb-0">ID: {event['id']}</p>
                            {f'<p class="mb-0"><a href="{event["agenda_url"]}" target="_blank">View Agenda</a></p>' if event.get('agenda_url') and event['agenda_url'] != "No agenda available yet" else '<p class="mb-0">Agenda not yet available</p>'}
                        </div>
                    </div>
                </div>
"""
        else:
            html += '<p class="no-events">No date confirmations</p>'
        html += """
            </div>
        </div>
"""
    
    # If we don't have categorized data, just show a list of all events
    else:
        html += """
        <div class="row">
            <div class="col-12">
                <h2 class="section-header">All Changes</h2>
"""
        if events_data:
            for event in events_data:
                card_class = "card-new"
                if event.get('change_type'):
                    if event['change_type'] == 'new_without_date':
                        card_class = "card-new-no-date"
                    elif event['change_type'] == 'rescheduled':
                        card_class = "card-rescheduled"
                    elif event['change_type'] == 'date_confirmed':
                        card_class = "card-date-confirmed"
                
                html += f"""
                <div class="card event-card {card_class} mb-3">
                    <div class="card-body">
                        <h3 class="h5 card-title">{event['body']}</h3>
                        <p><strong>Date:</strong> {format_date(event.get('date'))}</p>
                        <p><strong>Time:</strong> {event.get('time', 'TBD')}</p>
                        <p><strong>Location:</strong> {event.get('location', 'TBD')}</p>
                        <div class="event-meta">
                            <p class="mb-0">ID: {event['id']}</p>
                            {f'<p class="mb-0"><a href="{event["agenda_url"]}" target="_blank">View Agenda</a></p>' if event.get('agenda_url') and event['agenda_url'] != "No agenda available yet" else '<p class="mb-0">Agenda not yet available</p>'}
                        </div>
                    </div>
                </div>
"""
        else:
            html += '<p class="no-events">No events found</p>'
        html += """
            </div>
        </div>
"""

    # Close out the HTML
    html += """
        <footer class="mt-5 pt-3 border-top text-center text-muted">
            <p>NYC Legistar Hearing Monitor - <a href="https://github.com/your-username/legistar" target="_blank">GitHub Repository</a></p>
        </footer>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""
    
    return html

def setup_web_directory():
    """Set up the web directory structure"""
    # Create web directory if it doesn't exist
    os.makedirs(WEB_DIR, exist_ok=True)
    
    # Create assets directory for CSS, JS, etc.
    assets_dir = os.path.join(WEB_DIR, "assets")
    os.makedirs(assets_dir, exist_ok=True)
    
    logger.info(f"Web directory structure created at {WEB_DIR}")

def generate_web_page():
    """Generate the static web page"""
    setup_web_directory()
    
    # Try to load categorized data first
    events_data = load_categorized_events()
    summary_data = load_summary()
    
    # If no categorized data, fall back to regular event list
    if not events_data:
        events_data = load_new_events()
        logger.info("Using legacy event data format")
    else:
        logger.info("Using categorized event data format")
    
    # Generate the HTML
    html = generate_html_page(events_data, summary_data)
    
    # Write the HTML to the index file
    with open(INDEX_HTML, 'w') as f:
        f.write(html)
    
    logger.info(f"Static web page generated at {INDEX_HTML}")
    
    return True

def main():
    """Main function to generate the static web page"""
    parser = argparse.ArgumentParser(description='Generate a static web page for GitHub Pages')
    parser.add_argument('--title', help='Page title', default="NYC Legistar Hearing Monitor")
    args = parser.parse_args()
    
    logger.info("Starting web page generation")
    
    try:
        generate_web_page()
        logger.info("Web page generation completed successfully")
        return 0
    except Exception as e:
        logger.error(f"Error generating web page: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 