#!/usr/bin/env python3
import os
import json
import logging
from datetime import datetime
import argparse
import math
from urllib.parse import parse_qs # For parsing query params if we were in a web server context

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
        # Try parsing as "10:00 AM" format first
        dt_obj = datetime.strptime(time_str, '%I:%M %p')
        return dt_obj.strftime('%I:%M %p')
    except ValueError:
        try:
            # Try parsing as "10:00:00" format (24-hour)
            dt_obj = datetime.strptime(time_str, '%H:%M:%S')
            return dt_obj.strftime('%I:%M %p')
        except ValueError:
            try:
                # Try parsing as "10:00" format (24-hour without seconds)
                dt_obj = datetime.strptime(time_str, '%H:%M')
                return dt_obj.strftime('%I:%M %p')
            except ValueError:
                return time_str # Return as is if format is unexpected

def generate_event_card(event_entry, is_update_card=False):
    """Generates HTML for a single event card."""
    event_data = event_entry.get("event_data", {})
    tags = event_entry.get("user_facing_tags", [])
    
    card_html = '<div class="card event-card mb-3">'
    card_html += '<div class="card-body">'
    
    # Header section with committee name and agenda button side by side
    card_html += '<div class="card-header-flex">'
    card_html += f'<h5 class="card-title">{event_data.get("EventBodyName", "N/A")}</h5>'
    
    # Agenda button (moved to header)
    agenda_file = event_data.get("EventAgendaFile")
    if agenda_file:
        card_html += f'<a href="{agenda_file}" target="_blank" class="btn btn-sm btn-outline-primary agenda-btn">View Agenda</a>'
    card_html += '</div>'
    
    # Subtitle (Synthetic Meeting Topic) - only if available
    meeting_topic = event_data.get("SyntheticMeetingTopic")
    if meeting_topic:
        card_html += f'<h6 class="card-subtitle mb-2 text-muted">{meeting_topic}</h6>'

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
        if "deferred_hearing_tag" in tags:
            tag_html += '<span class="badge bg-warning me-1">DEFERRED</span>'
        if tag_html:
            card_html += f'<p class="card-text small">{tag_html}</p>'

    # Date, Time and Location in one responsive flex row
    event_date = event_data.get("EventDate")
    event_time = event_data.get("EventTime")
    event_location = event_data.get("EventLocation", "TBD")

    if event_entry.get("current_status") in ["deferred_pending_match", "deferred_nomatch"]:
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
        
        # Use flexbox for date, time, location with automatic wrapping
        card_html += '<div class="card-details-flex">'
        card_html += f'<p class="detail-item"><strong>Date:</strong> {date_display}</p>'
        card_html += f'<p class="detail-item"><strong>Time:</strong> {time_display}</p>'
        card_html += f'<p class="detail-item"><strong>Location:</strong> {event_location}</p>'
        card_html += '</div>'
    
    # Comment
    comment = event_data.get("EventComment")
    if comment:
        card_html += f'<p class="card-text fst-italic"><small>Comment: {comment}</small></p>'
    
    card_html += "</div></div>"
    return card_html

def generate_update_item_html(update_item):
    """Generates HTML for an item in the 'Updates' column based on simplified alert types."""
    item_type = update_item.get("type") # This will be "new" or "deferred"
    entry = update_item.get("data", {})
    event_data = entry.get("event_data", {})
    html = '<div class="card event-card mb-3">'
    html += '<div class="card-body">'
    
    body_name = event_data.get("EventBodyName", "N/A")
    meeting_topic = event_data.get("SyntheticMeetingTopic")
    
    original_event_details = entry.get("original_event_details_if_rescheduled")
    rescheduled_details_for_deferred = entry.get("rescheduled_event_details_if_deferred")
    
    agenda_file = event_data.get("EventAgendaFile")
    
    # Header section with committee name and agenda button
    html += '<div class="card-header-flex">'
    if item_type == "new":
        html += f'<h5 class="card-title text-success">NEW: {body_name}</h5>'
    elif item_type == "deferred":
        html += f'<h5 class="card-title text-warning">DEFERRED: {body_name}</h5>'
    else:
        html += f'<h5 class="card-title text-muted">UPDATE ({item_type}): {body_name}</h5>'
    
    # Agenda button
    if agenda_file:
        html += f'<a href="{agenda_file}" target="_blank" class="btn btn-sm btn-outline-secondary agenda-btn">View Agenda</a>'
    html += '</div>'
    
    # Meeting topic subtitle
    if meeting_topic:
        html += f'<h6 class="card-subtitle mb-2 text-muted">{meeting_topic}</h6>'
    
    if item_type == "new":
        current_event_date_disp = format_display_date(event_data.get("EventDate"), include_time=False)
        current_event_time_disp = get_event_time_display(event_data.get("EventTime"))
        event_location = event_data.get("EventLocation", "TBD")
        
        # Use flexbox for details
        html += '<div class="card-details-flex">'
        html += f'<p class="detail-item"><strong>Date:</strong> {current_event_date_disp}</p>'
        html += f'<p class="detail-item"><strong>Time:</strong> {current_event_time_disp}</p>'
        html += f'<p class="detail-item"><strong>Location:</strong> {event_location}</p>'
        html += '</div>'
        
        if original_event_details: # This "new" event is a reschedule of a previous one
            orig_date_disp = format_display_date(original_event_details.get("original_date"), include_time=False)
            orig_time_disp = get_event_time_display(original_event_details.get("original_time"))
            html += f'<p class="card-text fst-italic"><small>(Rescheduled from {orig_date_disp} {orig_time_disp})</small></p>'

    elif item_type == "deferred":
        original_date_disp = format_display_date(event_data.get("EventDate"), include_time=False)
        original_time_disp = get_event_time_display(event_data.get("EventTime"))
        html += f'<p class="card-text">Original Date: <del>{original_date_disp} {original_time_disp}</del></p>'

        if rescheduled_details_for_deferred: # This deferred event has been rescheduled
            new_date_disp = format_display_date(rescheduled_details_for_deferred.get("new_date"), include_time=False)
            new_time_disp = get_event_time_display(rescheduled_details_for_deferred.get("new_time"))
            html += f'<p class="card-text"><strong>Rescheduled to: {new_date_disp} {new_time_disp}</strong></p>'
        else: # Still deferred, awaiting reschedule or no match found after grace period
            html += '<p class="card-text"><em>Reschedule: Awaiting information</em></p>'
    else:
        # Fallback for any unexpected item_type, though this shouldn't happen with the new logic.
        current_event_date_disp = format_display_date(event_data.get("EventDate"), include_time=False)
        current_event_time_disp = get_event_time_display(event_data.get("EventTime"))
        html += f'<p class="card-text">Date: {current_event_date_disp} {current_event_time_disp}</p>'

    # Comment if exists
    comment = event_data.get("EventComment")
    if comment:
        html += f'<p class="card-text fst-italic small">{comment}</p>'
        
    html += "</div></div>"
    return html

def generate_pagination_html(current_page, total_pages):
    if total_pages <= 1:
        return ""

    html = '<nav aria-label="Page navigation"><ul class="pagination justify-content-center">'
    
    # Previous button
    if current_page > 1:
        html += f'<li class="page-item"><a class="page-link" href="index.html?page={current_page - 1}">Previous</a></li>'
    else:
        html += '<li class="page-item disabled"><span class="page-link">Previous</span></li>'
        
    # Page numbers (simplified: show current, +/- a few, first, last)
    start_page = max(1, current_page - 2)
    end_page = min(total_pages, current_page + 2)

    if start_page > 1:
        html += f'<li class="page-item"><a class="page-link" href="index.html?page=1">1</a></li>'
        if start_page > 2:
             html += '<li class="page-item disabled"><span class="page-link">...</span></li>'
    
    for i in range(start_page, end_page + 1):
        active_class = "active" if i == current_page else ""
        html += f'<li class="page-item {active_class}"><a class="page-link" href="index.html?page={i}">{i}</a></li>'
        
    if end_page < total_pages:
        if end_page < total_pages - 1:
            html += '<li class="page-item disabled"><span class="page-link">...</span></li>'
        html += f'<li class="page-item"><a class="page-link" href="index.html?page={total_pages}">{total_pages}</a></li>'

    # Next button
    if current_page < total_pages:
        html += f'<li class="page-item"><a class="page-link" href="index.html?page={current_page + 1}">Next</a></li>'
    else:
        html += '<li class="page-item disabled"><span class="page-link">Next</span></li>'
        
    html += "</ul></nav>"
    return html

def generate_html_page_content(processed_data, page_title="NYC Legistar Hearing Monitor", current_page=1, updates_filter_value="since_last_run"):
    """Generates the main HTML structure for the page."""
    
    generation_timestamp = processed_data.get("generation_timestamp", datetime.now().isoformat())
    generation_date_display = format_display_date(generation_timestamp)

    # Select which updates list to display based on the filter value
    if updates_filter_value == "last_7_days":
        updates_to_display = processed_data.get("updates_last_7_days", [])
        selected_filter_option_7 = "selected"
        selected_filter_option_30 = ""
        selected_filter_option_last_run = ""
    elif updates_filter_value == "last_30_days":
        updates_to_display = processed_data.get("updates_last_30_days", [])
        selected_filter_option_7 = ""
        selected_filter_option_30 = "selected"
        selected_filter_option_last_run = ""
    else: # Default to "since_last_run"
        updates_to_display = processed_data.get("updates_since_last_run", [])
        selected_filter_option_7 = ""
        selected_filter_option_30 = ""
        selected_filter_option_last_run = "selected"

    upcoming_hearings_all = processed_data.get("upcoming_hearings", [])
    total_upcoming = len(upcoming_hearings_all)
    total_pages = math.ceil(total_upcoming / ITEMS_PER_PAGE)
    
    # Paginate upcoming_hearings
    start_index = (current_page - 1) * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    upcoming_hearings_paginated = upcoming_hearings_all[start_index:end_index]

    # Create the CSS styles as a separate string to avoid f-string parsing issues
    css_styles = """
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding-top: 20px; }
        .container-main { max-width: 1400px; }
        .updates-column { max-height: 90vh; overflow-y: auto; position: sticky; top: 20px; }
        .event-card { border-left-width: 5px; border-left-style: solid; }
        .card-title small { font-size: 0.8rem; color: #6c757d; }
        del { color: #dc3545; }
        
        /* New styles for improved card layout */
        .card-header-flex { 
            display: flex; 
            justify-content: space-between; 
            align-items: flex-start;
            margin-bottom: 8px;
        }
        .card-header-flex .card-title { 
            margin-bottom: 0; 
            margin-right: 8px;
            flex: 1;
        }
        .card-subtitle {
            margin-top: 0.25rem !important;
            margin-bottom: 0.75rem !important;
        }
        .card-details-flex {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin-bottom: 8px;
        }
        .card-details-flex .detail-item {
            margin: 0;
            white-space: nowrap;
        }
        .agenda-btn {
            white-space: nowrap;
            flex-shrink: 0;
        }
    """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{page_title}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>{css_styles}</style>
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
                    <select class="form-select" id="updates-filter">
                        <option value="since_last_run" {selected_filter_option_last_run}>Since last update</option>
                        <option value="last_7_days" {selected_filter_option_7}>Last 7 days</option>
                        <option value="last_30_days" {selected_filter_option_30}>Last 30 days</option>
                    </select>
                </div>
                <div id="updates-content">
"""
    if updates_to_display:
        for item in updates_to_display:
            html += generate_update_item_html(item)
    else:
        html += '                    <p class="text-muted">No updates for selected period.</p>'

    html += """
                </div> <!-- /updates-content -->
            </div> <!-- /col-md-4 updates-column -->

            <!-- Upcoming Hearings Column (Right) -->
            <div class="col-md-8">
                <h4>Upcoming Hearings (""" + f"{total_upcoming} total" + """)</h4>
                <div id="upcoming-hearings-content">
"""
    if upcoming_hearings_paginated:
        for event_entry in upcoming_hearings_paginated:
            html += generate_event_card(event_entry)
    elif upcoming_hearings_all:
        html += '                    <p>No hearings on this page. Try a different page number.</p>'
    else:
        html += '                    <p class="text-muted">No upcoming hearings found.</p>'

    html += """
                </div> <!-- /upcoming-hearings-content -->
"""
    html += generate_pagination_html(current_page, total_pages) # Simpler call, JS will add filter

    html += """
            </div> <!-- /col-md-8 -->
        </div> <!-- /row -->
    </div> <!-- /container -->

    <script>
        document.addEventListener('DOMContentLoaded', function() {
            const filterSelect = document.getElementById('updates-filter');
            const paginationLinks = document.querySelectorAll('.pagination .page-link');
            
            // Set filter dropdown from URL query parameter on page load
            const urlParams = new URLSearchParams(window.location.search);
            const currentFilter = urlParams.get('updates_filter');
            if (currentFilter) {
                filterSelect.value = currentFilter;
            }

            filterSelect.addEventListener('change', function() {
                const selectedValue = this.value;
                // Reload the page with the new filter query parameter, keeping other params like 'page' if they exist
                urlParams.set('updates_filter', selectedValue);
                // When changing filter, reset to page 1 of updates
                urlParams.delete('page'); 
                window.location.search = urlParams.toString();
            });

            // Ensure pagination links carry the current filter
            paginationLinks.forEach(link => {
                link.addEventListener('click', function(e) {
                    e.preventDefault();
                    const pageUrl = new URL(link.href);
                    const pageNumber = pageUrl.searchParams.get('page');
                    
                    const currentUrlParams = new URLSearchParams(window.location.search);
                    if (pageNumber) {
                        currentUrlParams.set('page', pageNumber);
                    } else {
                         // Link might not have a page number if it's a non-functional link (e.g. '...')
                        currentUrlParams.delete('page'); // Or handle as appropriate
                    }
                    // Keep the existing filter if present
                    const filterValue = filterSelect.value;
                     if (filterValue) {
                        currentUrlParams.set('updates_filter', filterValue);
                    }

                    window.location.search = currentUrlParams.toString();
                });
            });
        });
    </script>
</body>
</html>
"""
    return html

def main():
    parser = argparse.ArgumentParser(description="Generate a static HTML page for Legistar hearings.")
    parser.add_argument("--title", default="NYC Legistar Hearing Monitor", help="Title for the HTML page.")
    parser.add_argument("--page", type=int, default=1, help="Page number for upcoming hearings pagination.")
    parser.add_argument("--updates-filter", 
                        choices=["since_last_run", "last_7_days", "last_30_days"],
                        default="since_last_run", 
                        help="Which set of updates to display by default.")
    args = parser.parse_args()
    
    logger.info("Starting webpage generation...")

    if not os.path.exists(PROCESSED_EVENTS_FILE):
        logger.error(f"Processed events file not found: {PROCESSED_EVENTS_FILE}")
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

    if "error" in processed_data:
        logger.warning(f"Data file indicates an error from previous step: {processed_data['error']}")
        error_html = f"<html><body><h1>Warning</h1><p>There was an issue fetching or processing hearing data: {processed_data['error']}</p><p>Timestamp: {processed_data.get('generation_timestamp', datetime.now().isoformat())}</p></body></html>"
        os.makedirs(WEB_DIR, exist_ok=True)
        with open(INDEX_HTML, 'w') as f:
            f.write(error_html)
        logger.info(f"Generated warning page at {INDEX_HTML} due to upstream error.")
        return

    final_html = generate_html_page_content(
        processed_data, 
        page_title=args.title, 
        current_page=args.page,
        updates_filter_value=args.updates_filter
    )
    
    # For a true query param driven site, the GitHub action would need to be smarter or run a small server.
    # For now, the GH Action will always generate index.html with default filters.
    # The JS allows users to change it, and the URL will reflect it for bookmarking/sharing if served appropriately.
    # If different pages per filter are desired (e.g. index_last_7_days.html), main() would need to handle that.

    os.makedirs(WEB_DIR, exist_ok=True)
    with open(INDEX_HTML, 'w', encoding='utf-8') as f:
        f.write(final_html)
    
    logger.info(f"Successfully generated webpage at {INDEX_HTML} (Page {args.page}, Updates: {args.updates_filter})")

if __name__ == "__main__":
    main() 