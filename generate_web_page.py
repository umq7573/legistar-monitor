#!/usr/bin/env python3
import os
import json
import logging
from datetime import datetime
import argparse
import math

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('web_page_generator')

# Constants
DATA_DIR = "data"
PROCESSED_EVENTS_FILE = os.path.join(DATA_DIR, "processed_events_for_web.json")
WEB_DIR = "docs"
INDEX_HTML = os.path.join(WEB_DIR, "index.html")
ITEMS_PER_PAGE = 25

def format_display_date(date_str, include_time=True):
    """Format an ISO date string (or part of it) for display."""
    if not date_str:
        return "TBD"
    try:
        # Handle full ISO datetime strings and date-only strings
        dt_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00')) if 'T' in date_str else datetime.strptime(date_str, '%Y-%m-%d')
        if include_time:
            return dt_obj.strftime("%A, %B %d, %Y at %I:%M %p")
        else:
            return dt_obj.strftime("%A, %B %d, %Y")
    except ValueError:
        # Fallback for unexpected date formats or if only time is present (though time usually accompanies date)
        return date_str

def get_event_time_display(time_str):
    if not time_str:
        return "Time TBD"
    try:
        # Assuming time_str is like "10:00 AM"
        dt_obj = datetime.strptime(time_str, '%I:%M %p')
        return dt_obj.strftime('%I:%M %p')
    except ValueError:
        return time_str # Return as is if format is unexpected

def generate_event_card(event_entry, is_update_card=False):
    """Generates HTML for a single event card."""
    event_data = event_entry.get("event_data", {})
    tags = event_entry.get("user_facing_tags", [])
    
    card_html = '<div class="card event-card mb-3">'
    card_html += '<div class="card-body">'
    
    # Title
    card_html += f'<h5 class="card-title">{event_data.get("EventBodyName", "N/A")}</h5>'

    # Tags for upcoming hearings
    if not is_update_card and tags:
        tag_html = ""
        if "new_hearing_tag" in tags:
            tag_html += '<span class="badge bg-success me-1">NEW</span>'
        if "rescheduled_hearing_tag" in tags and event_entry.get("original_event_details_if_rescheduled"):
            orig_details = event_entry["original_event_details_if_rescheduled"]
            orig_date_disp = format_display_date(orig_details.get("original_date"), include_time=False)
            orig_time_disp = get_event_time_display(orig_details.get("original_time"))
            tag_html += f'<span class="badge bg-info me-1">RESCHEDULED (was {orig_date_disp} {orig_time_disp})</span>'
        if "deferred_hearing_tag" in tags: # For deferred_pending_match or deferred_nomatch
            tag_html += '<span class="badge bg-warning me-1">DEFERRED</span>'
        if tag_html:
            card_html += f'<p class="card-text small">{tag_html}</p>'

    # Date and Time
    event_date = event_data.get("EventDate")
    event_time = event_data.get("EventTime")

    if event_entry.get("current_status") in ["deferred_pending_match", "deferred_nomatch"] :
        original_date_display = format_display_date(event_date, include_time=False)
        original_time_display = get_event_time_display(event_time)
        card_html += f'<p class="card-text"><strong>Original Date:</strong> <del>{original_date_display}</del> {original_time_display}</p>'
        if event_entry["current_status"] == "deferred_pending_match":
            card_html += '<p class="card-text"><em>Reschedule: Awaiting information</em></p>'
        elif event_entry["current_status"] == "deferred_nomatch":
            card_html += '<p class="card-text"><em>Reschedule: None found after grace period</em></p>'
    else: # Active events or the new part of a reschedule
        date_display = format_display_date(event_date, include_time=False)
        time_display = get_event_time_display(event_time)
        card_html += f'<p class="card-text"><strong>Date:</strong> {date_display}</p>'
        card_html += f'<p class="card-text"><strong>Time:</strong> {time_display}</p>'

    # Location
    card_html += f'<p class="card-text"><strong>Location:</strong> {event_data.get("EventLocation", "TBD")}</p>'
    
    # Comment
    comment = event_data.get("EventComment")
    if comment:
        card_html += f'<p class="card-text fst-italic"><small>Comment: {comment}</small></p>'
        
    # Agenda Link
    agenda_file = event_data.get("EventAgendaFile")
    if agenda_file:
        card_html += f'<p class="card-text"><a href="{agenda_file}" target="_blank" class="btn btn-sm btn-outline-primary">View Agenda</a></p>'
    else:
        card_html += '<p class="card-text"><small>Agenda not yet available</small></p>'
        
    card_html += "</div></div>"
    return card_html

def generate_update_item_html(update_item):
    """Generates HTML for an item in the 'Updates' column."""
    item_type = update_item.get("type")
    entry = update_item.get("data", {})
    event_data = entry.get("event_data", {})
    html = '<div class="card event-card mb-3">'
    html += '<div class="card-body">'
    
    body_name = event_data.get("EventBodyName", "N/A")
    original_date_disp = format_display_date(event_data.get("EventDate"), include_time=False)
    original_time_disp = get_event_time_display(event_data.get("EventTime"))

    if item_type == "new":
        html += f'<h5 class="card-title text-success">NEW: {body_name}</h5>'
        html += f'<p class="card-text"><strong>Date:</strong> {original_date_disp}</p>'
        html += f'<p class="card-text"><strong>Time:</strong> {original_time_disp}</p>'
    elif item_type == "deferred_pending":
        html += f'<h5 class="card-title text-warning">DEFERRED: {body_name}</h5>'
        html += f'<p class="card-text">Original: {original_date_disp} {original_time_disp}</p>'
        html += '<p class="card-text"><em>Reschedule: Awaiting information</em></p>'
    elif item_type == "deferred_nomatch":
        html += f'<h5 class="card-title text-secondary">DEFERRED (No Match): {body_name}</h5>'
        html += f'<p class="card-text">Original: {original_date_disp} {original_time_disp}</p>'
        html += '<p class="card-text"><em>Reschedule: None found after grace period</em></p>'
    elif item_type == "rescheduled_original_deferred": # The original event that was deferred
        rescheduled_details = entry.get("rescheduled_event_details_if_deferred", {})
        new_date_disp = format_display_date(rescheduled_details.get("new_date"), include_time=False)
        new_time_disp = get_event_time_display(rescheduled_details.get("new_time"))
        html += f'<h5 class="card-title text-info">DEFERRED & RESCHEDULED: {body_name}</h5>'
        html += f'<p class="card-text"><del>Original: {original_date_disp} {original_time_disp}</del></p>'
        html += f'<p class="card-text"><strong>New Date: {new_date_disp} {new_time_disp}</strong> (See Upcoming Hearings)</p>'
    elif item_type == "rescheduled_new": # The new event that is the reschedule
        original_details = entry.get("original_event_details_if_rescheduled", {})
        orig_def_date_disp = format_display_date(original_details.get("original_date"), include_time=False)
        orig_def_time_disp = get_event_time_display(original_details.get("original_time"))
        html += f'<h5 class="card-title text-primary">RESCHEDULED EVENT: {body_name}</h5>'
        html += f'<p class="card-text"><strong>Date: {original_date_disp}</strong></p>'
        html += f'<p class="card-text"><strong>Time: {original_time_disp}</strong></p>'
        html += f'<p class="card-text"><small>(Rescheduled from {orig_def_date_disp} {orig_def_time_disp})</small></p>'
    
    # Common details like location, agenda for all update types if relevant
    location = event_data.get("EventLocation")
    if location:
        html += f'<p class="card-text"><small>Location: {location}</small></p>'
    agenda_file = event_data.get("EventAgendaFile")
    if agenda_file:
        html += f'<p class="card-text"><a href="{agenda_file}" target="_blank" class="btn btn-sm btn-outline-secondary mt-1">View Agenda</a></p>'
        
    html += "</div></div>"
    return html

def generate_pagination_html(current_page, total_pages, base_url="index.html"):
    if total_pages <= 1:
        return ""

    html = '<nav aria-label="Page navigation"><ul class="pagination justify-content-center">'
    
    # Previous button
    if current_page > 1:
        html += f'<li class="page-item"><a class="page-link" href="{base_url}?page={current_page - 1}">Previous</a></li>'
    else:
        html += '<li class="page-item disabled"><span class="page-link">Previous</span></li>'
        
    # Page numbers (simplified: show current, +/- a few, first, last)
    # For a more complex pagination, you'd calculate ranges
    # This is a basic version
    start_page = max(1, current_page - 2)
    end_page = min(total_pages, current_page + 2)

    if start_page > 1:
        html += f'<li class="page-item"><a class="page-link" href="{base_url}?page=1">1</a></li>'
        if start_page > 2:
             html += '<li class="page-item disabled"><span class="page-link">...</span></li>'
    
    for i in range(start_page, end_page + 1):
        active_class = "active" if i == current_page else ""
        html += f'<li class="page-item {active_class}"><a class="page-link" href="{base_url}?page={i}">{i}</a></li>'
        
    if end_page < total_pages:
        if end_page < total_pages - 1:
            html += '<li class="page-item disabled"><span class="page-link">...</span></li>'
        html += f'<li class="page-item"><a class="page-link" href="{base_url}?page={total_pages}">{total_pages}</a></li>'

    # Next button
    if current_page < total_pages:
        html += f'<li class="page-item"><a class="page-link" href="{base_url}?page={current_page + 1}">Next</a></li>'
    else:
        html += '<li class="page-item disabled"><span class="page-link">Next</span></li>'
        
    html += "</ul></nav>"
    return html

def generate_html_page_content(processed_data, page_title="NYC Legistar Hearing Monitor", current_page=1):
    """Generates the main HTML structure for the page."""
    
    generation_timestamp = processed_data.get("generation_timestamp", datetime.now().isoformat())
    generation_date_display = format_display_date(generation_timestamp)

    # For now, default to "updates_since_last_run" for the Updates column
    # Client-side filtering for dropdown can be added later.
    updates_to_display = processed_data.get("updates_since_last_run", [])
    
    upcoming_hearings_all = processed_data.get("upcoming_hearings", [])
    total_upcoming = len(upcoming_hearings_all)
    total_pages = math.ceil(total_upcoming / ITEMS_PER_PAGE)
    
    # Paginate upcoming_hearings
    start_index = (current_page - 1) * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    upcoming_hearings_paginated = upcoming_hearings_all[start_index:end_index]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page_title}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding-top: 20px; }}
        .container-main {{ max-width: 1400px; }}
        .updates-column {{ max-height: 90vh; overflow-y: auto; }}
        .event-card {{ border-left-width: 5px; border-left-style: solid; }}
        /* Specific card border colors can be added if desired, or use badges primarily */
        .card-title small {{ font-size: 0.8rem; color: #6c757d; }}
        del {{ color: #dc3545; }} /* Strikethrough for deferred dates */
    </style>
</head>
<body>
    <div class="container container-main">
        <div class="d-flex justify-content-between align-items-center mb-4">
            <h1>{page_title}</h1>
            <p class="text-muted mb-0">Last updated: {generation_date_display}</p>
        </div>

        <div class="row">
            <!-- Updates Column (Left) -->
            <div class="col-md-4 updates-column">
                <h4>Updates</h4>
                <div class="mb-3">
                    <select class="form-select" id="updates-filter" disabled> <!-- Dropdown disabled for now -->
                        <option selected>Since last update</option>
                        <option>Last 7 days</option>
                        <option>Last 30 days</option>
                    </select>
                </div>
                <div id="updates-content">
"""
    if updates_to_display:
        for item in updates_to_display:
            html += generate_update_item_html(item)
    else:
        html += '<p class="text-muted">No updates since last check.</p>'
    
    html += """
                </div> <!-- /updates-content -->
            </div> <!-- /col-md-4 updates-column -->

                        <!-- Upcoming Hearings Column (Right) -->
            <div class="col-md-8">
                <h4>Upcoming Hearings ({total_upcoming} total)</h4>
                <div id="upcoming-hearings-content">
"""
    if upcoming_hearings_paginated:
        for event_entry in upcoming_hearings_paginated:
            html += generate_event_card(event_entry)
    elif upcoming_hearings_all: # Paginated is empty but all is not (means invalid page number)
        html += '<p>No hearings on this page. Try a different page number.</p>'
    else:
        html += '<p class="text-muted">No upcoming hearings found.</p>'
    
    html += """
                </div> <!-- /upcoming-hearings-content -->
"""
    # Pagination
    html += generate_pagination_html(current_page, total_pages)

    html += """
            </div> <!-- /col-md-8 -->
        </div> <!-- /row -->
    </div> <!-- /container -->

    <script>
        // Basic script to handle page parameter for pagination (server-side for now)
        // More advanced JS could handle client-side filtering for updates if needed.
        // document.getElementById('updates-filter').addEventListener('change', function() {
        //     console.log('Filter changed to: ' + this.value);
        //     // Add logic to reload/filter updates content here
        // });
    </script>
</body>
</html>
"""
    return html

def main():
    parser = argparse.ArgumentParser(description="Generate a static HTML page for Legistar hearings.")
    parser.add_argument("--title", default="NYC Legistar Hearing Monitor", help="Title for the HTML page.")
    # Page argument for pagination - this assumes each page is a separate HTML file or handled by query param
    # For GitHub Pages, if we want index.html?page=2, a serverless function or client-side routing is better.
    # For simple static generation, we could generate multiple files like index.html, page2.html, etc.
    # Or, more simply, just show the first page and rely on future JS for full pagination.
    # For this iteration, we'll assume `index.html` shows page 1. A query param would be for future enhancement.
    # Let's add a --page argument to simulate this, default to 1.
    parser.add_argument("--page", type=int, default=1, help="Page number for upcoming hearings pagination.")


    args = parser.parse_args()
    
    logger.info("Starting webpage generation...")

    if not os.path.exists(PROCESSED_EVENTS_FILE):
        logger.error(f"Processed events file not found: {PROCESSED_EVENTS_FILE}")
        # Create a basic error page
        error_html = f"<html><body><h1>Error</h1><p>Processed data file not found. Cannot generate page.</p><p>Last attempted update: {datetime.now().isoformat()}</p></body></html>"
        os.makedirs(WEB_DIR, exist_ok=True)
        with open(INDEX_HTML, 'w') as f:
            f.write(error_html)
        logger.info(f"Generated error page at {INDEX_HTML}")
        return

    try:
        with open(PROCESSED_EVENTS_FILE, 'r') as f:
            processed_data = json.load(f)
    except Exception as e:
        logger.error(f"Error loading processed events data: {e}")
        error_html = f"<html><body><h1>Error</h1><p>Could not load processed data: {e}</p><p>Last attempted update: {datetime.now().isoformat()}</p></body></html>"
        os.makedirs(WEB_DIR, exist_ok=True)
        with open(INDEX_HTML, 'w') as f:
            f.write(error_html)
        logger.info(f"Generated error page due to data load failure at {INDEX_HTML}")
        return

    # Handle error state from check_new_hearings.py if present
    if "error" in processed_data:
        logger.warning(f"Data file indicates an error from previous step: {processed_data['error']}")
        error_html = f"<html><body><h1>Warning</h1><p>There was an issue fetching or processing hearing data: {processed_data['error']}</p><p>Timestamp: {processed_data.get('generation_timestamp', datetime.now().isoformat())}</p></body></html>"
        os.makedirs(WEB_DIR, exist_ok=True)
        with open(INDEX_HTML, 'w') as f:
            f.write(error_html)
        logger.info(f"Generated warning page at {INDEX_HTML} due to upstream error.")
        return

    final_html = generate_html_page_content(processed_data, page_title=args.title, current_page=args.page)
    
    os.makedirs(WEB_DIR, exist_ok=True)
    with open(INDEX_HTML, 'w', encoding='utf-8') as f:
        f.write(final_html)
    
    logger.info(f"Successfully generated webpage at {INDEX_HTML} (Page {args.page})")

if __name__ == "__main__":
    main() 