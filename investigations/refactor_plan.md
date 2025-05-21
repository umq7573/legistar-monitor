# Legistar Hearing Monitor - Refactor Plan

Based on investigations into API behavior (especially regarding deferred and rescheduled events), a significant refactor is proposed to improve accuracy and user experience.

## 1. Core Principles of Refactor

1.  **Accurate Reschedule Tracking**: Prioritize correctly identifying events that are deferred and then rescheduled, even if they appear with a new `EventId`.
2.  **Simplified Categories**: Remove categories for "Events without Dates" and "Date Confirmed" as primary display elements, as these appear rare in live API data.
3.  **User-Focused Display**: Create a clearer distinction between new/changed information ("Updates") and the overall schedule ("Upcoming Hearings").
4.  **Flexible Time Windows**: Allow users to define "newness" for updates and manage data scope for API queries.

## 2. Data Model Changes (`data/seen_events.json`)

Each entry in `seen_events.json` (keyed by `EventId`) will need to store more comprehensive state:

```json
{
  "EventId_12345": {
    "event_data": { ...raw event object from API... }, // Store the latest full event object
    "first_seen_timestamp": "YYYY-MM-DDTHH:MM:SSZ",    // When this EventId was first processed
    "last_seen_timestamp": "YYYY-MM-DDTHH:MM:SSZ",     // Last time this EventId was present in API results
    "last_processed_timestamp": "YYYY-MM-DDTHH:MM:SSZ",// Last time this record was updated by the script
    "last_significant_change_timestamp": "YYYY-MM-DDTHH:MM:SSZ", // When date, time, status, or linked IDs last changed
    "current_status": "active" / "deferred_pending_match" / "deferred_rescheduled" / "deferred_nomatch",
    "original_event_details_if_rescheduled": { // If current_status is 'active' AND this was a reschedule of a deferred event
        "deferred_event_id": "EventId_ABCDE",
        "original_date": "YYYY-MM-DDTHH:MM:SSZ",
        "original_time": "HH:MM AM/PM"
    },
    "rescheduled_event_details_if_deferred": { // If current_status is 'deferred_rescheduled'
        "new_event_id": "EventId_67890",
        "new_date": "YYYY-MM-DDTHH:MM:SSZ",
        "new_time": "HH:MM AM/PM"
    },
    "user_facing_tags": [] // e.g., ["new", "rescheduled", "deferred"] populated during processing for web page
  }
}
```

## 3. API Query Changes (`check_new_hearings.py` & `legistar_api.py`)

1.  **Lookback Period**:
    *   Change `LOOKBACK_DAYS` to a larger default (e.g., 365 days). Make this configurable.
    *   This defines the oldest event date to fetch.
2.  **Lookahead Period**:
    *   Remove fixed `LOOKAHEAD_DAYS`. Fetch all future events.
    *   The API query will be `EventDate ge (today - lookback_period)`.
3.  **Pagination for API Calls**:
    *   The `legistar_api.py` `get_events` (and potentially other `get_...` methods) must be updated to handle API pagination transparently if more than the `max_per_page` (e.g., 1000) items are returned. It should loop, incrementing `$skip`, until all records for the query are fetched.
    *   `check_new_hearings.py` will then receive a complete list of events within the defined date range.

## 4. `check_new_hearings.py` - Processing Logic Refactor

**Main Steps:**

1.  **Fetch Events**: Use the modified `legistar_api.py` to get all events from `(today - lookback)` to indefinite future.
2.  **Load Seen Events**: Load `data/seen_events.json`.
3.  **Initialize Change Lists**: `newly_added_events`, `newly_deferred_events`, `newly_rescheduled_events` (matched pairs).
4.  **Process Fetched Events (Iterate through API results):**
    *   For each `current_event` from API:
        *   Let `event_id = current_event['EventId']`.
        *   Mark `current_event` as `last_seen_timestamp = now`.
        *   **If `event_id` not in `seen_events`:**
            *   It's a brand new event. Add to `seen_events` with `current_status: 'active'`, `first_seen_timestamp`, `last_significant_change_timestamp`.
            *   Add to `newly_added_events`.
        *   **If `event_id` in `seen_events`:**
            *   Let `stored_event_details = seen_events[event_id]`.
            *   Compare `current_event` data (date, time, body, comment, API status like "Deferred") with `stored_event_details.event_data`.
            *   **If significant change detected (e.g., date, time, API agenda status):**
                *   Update `stored_event_details.event_data` with `current_event`.
                *   Set `last_significant_change_timestamp = now`.
                *   **If `current_event['EventAgendaStatusName'] == 'Deferred'` and `stored_event_details.current_status` was `'active'`:**
                    *   Change `stored_event_details.current_status = 'deferred_pending_match'`.
                    *   Add `stored_event_details` to `newly_deferred_events`.
                *   **If `current_event` date/time changed and `stored_event_details.current_status` was `'active'` (classic reschedule of SAME ID):**
                    *   This is now less likely given our findings but handle if it occurs.
                    *   Flag as a change, update details. Add to a "classic reschedules" list (for internal tracking, might still be presented as a type of "update").
            *   Else (no significant change to this specific event ID's direct data): No immediate action for this ID, but it's kept active.

5.  **Attempt to Match Deferred Events to New Reschedules:**
    *   Iterate through all `event_in_seen_db` where `current_status == 'deferred_pending_match'`.
    *   Iterate through all `newly_added_event` (from step 4).
    *   **Matching Heuristic**:
        *   `newly_added_event.date` > `event_in_seen_db.date`.
        *   `newly_added_event.EventBodyName` == `event_in_seen_db.EventBodyName`.
        *   High similarity in `EventComment` (e.g., Jaro-Winkler > 0.85, or specific parsing for "Jointly with...").
        *   `newly_added_event.date` is within a reasonable timeframe of `event_in_seen_db.date` (e.g., < 60 days).
    *   **If a strong match is found:**
        *   Update `event_in_seen_db`:
            *   `current_status = 'deferred_rescheduled'`
            *   `rescheduled_event_details_if_deferred = { new_event_id: newly_added_event.EventId, new_date: newly_added_event.date, ... }`
            *   `last_significant_change_timestamp = now`.
        *   Update the `newly_added_event` in `seen_events`:
            *   `current_status = 'active'` (it's an active meeting).
            *   `original_event_details_if_rescheduled = { deferred_event_id: event_in_seen_db.EventId, original_date: event_in_seen_db.date, ... }`
            *   `last_significant_change_timestamp = now`.
        *   Add the pair (`event_in_seen_db`, `newly_added_event`) to `newly_rescheduled_events_matched_pairs`.
        *   Remove `newly_added_event` from `newly_added_events` list (it's now a "reschedule," not just "new").

6.  **Handle Old Deferred Events with No Match:**
    *   Iterate through `seen_events` where `current_status == 'deferred_pending_match'`.
    *   If `event.date` is older than (today - `X` days) (e.g., `X = 30-60` days, configurable "grace period for reschedule"), change status to `deferred_nomatch`.
    *   `last_significant_change_timestamp = now`.

7.  **Prepare Data for Web Page:**
    *   This will involve creating a new JSON structure that `generate_web_page.py` can consume.
    *   **Updates List**: Based on the chosen time filter ("since last update", "last week", "last month"), select events for the "Updates" column:
        *   Events from `newly_added_events`.
        *   Original events from `newly_deferred_events` (status `deferred_pending_match` or `deferred_rescheduled`).
        *   New events that are matched reschedules (from `newly_rescheduled_events_matched_pairs`).
        *   Events whose `current_status` changed to `deferred_nomatch` recently.
    *   **Upcoming Hearings List**: All events in `seen_events` that have `current_status == 'active'` or are `deferred_rescheduled` (referring to the new event ID) or `deferred_pending_match`/`deferred_nomatch` (referring to the original deferred event). Sort by date. Include necessary tags and linked data for card display.

8.  **Save Seen Events**: Write the updated `seen_events` back to JSON.

## 5. `generate_web_page.py` - UI and Logic Changes

1.  **HTML Structure:**
    *   **Left Column ("Updates"):**
        *   Time selector dropdown: "Since last update", "Last 7 days", "Last 30 days".
        *   List of update cards:
            *   **New Hearing Card:** "NEW: [Body] - [Date] [Time]".
            *   **Deferred Hearing Card (Original Event):** "DEFERRED: [Body] - Original Date: [Date1] [Time1]".
                *   If matched: "Rescheduled to: [Date2] [Time2] (See upcoming)".
                *   If pending match: "Reschedule: Awaiting information".
                *   If no match found (original date past): "Reschedule: None found".
            *   **Rescheduled Hearing Card (New Event):** "RESCHEDULED: [Body] - New Date: [Date2] [Time2]. (Was: [Date1] [Time1])".
    *   **Right Main Panel ("Upcoming Hearings"):**
        *   Title: "Upcoming Hearings".
        *   Pagination controls (e.g., Prev | Page X of Y | Next). Display 25 items per page.
        *   List of hearing cards, sorted by date:
            *   Standard Info: Body, Date, Time, Location, Comment, Agenda Link.
            *   **Tags (visually distinct):**
                *   `[NEW]`: If this event is "new" according to the current "Updates" filter.
                *   `[DEFERRED - Original: Date1]`: If this card represents an event that is currently `deferred_pending_match` or `deferred_nomatch`. Display new date if rescheduled, or "No Reschedule Found".
                *   `[RESCHEDULED - Previously: Date1]`: If this card is an active event that was matched as a reschedule of a deferred one.

2.  **JavaScript Logic (Client-Side):**
    *   Handle time selector change for "Updates" column (likely re-filter data or fetch filtered data).
    *   Handle pagination for "Upcoming Hearings."
    *   The data passed from `check_new_hearings.py` will need to be structured to support this efficiently. It might be a single large JSON with all upcoming events and a separate JSON for "updates" filtered by different time windows, or the filtering happens client-side.

## 6. `config.json` / Script Arguments

*   Add configuration for:
    *   `lookback_days` (default 365).
    *   `deferred_match_grace_period_days` (default 30-60).
    *   `deferred_match_comment_similarity_threshold` (default ~0.85).

## 7. Open Questions / Further Considerations

*   **Performance of `seen_events.json`:** With a 1-year lookback, this file could grow large. JSON load/dump might become slow. Consider alternative storage if it becomes an issue (e.g., SQLite), though flat JSON is simple.
*   **Complexity of Matching Logic:** The deferred-to-rescheduled matching is heuristic. False positives/negatives are possible. Iterative refinement will be needed.
*   **Definition of "Last Update" for Updates Filter:** This would mean comparing the *current state* of an event in `seen_events.json` (after all processing in this run) with its state *before* this run started. This requires either keeping a copy of `seen_events.json` from the start of the run or carefully tracking changes. Simpler might be to rely on `last_significant_change_timestamp` relative to the previous run's overall timestamp.
*   **API Key / Usage**: Ensure extended queries don't hit API rate limits if any exist. The current NYC API seems generous.

This refactor is substantial but addresses the core issues found during the investigation. 