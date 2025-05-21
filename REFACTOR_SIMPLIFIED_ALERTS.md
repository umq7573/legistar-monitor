# Refactor Plan (Revised): Simplified Alert Tracking & Display

**Goal:**
Refine the alert system to primarily feature two distinct user-facing alert types ("New" and "Deferred") in the "Updates" section. Additional information regarding rescheduling will supplement these alerts rather than creating new alert categories or resetting alert timestamps. Simplify the internal state management and data model for `last_alert_type` and `last_alert_timestamp`.

**Core Principles:**
1.  **Two Main Visual Alerts in "Updates":** "New Hearing" and "Deferred Hearing."
2.  **Rescheduling as Supplemental Info:**
    *   A "New Hearing" alert can be annotated if it's a reschedule of a previous event.
    *   A "Deferred Hearing" alert can be annotated with its new date if rescheduled, or indicate it's awaiting reschedule information.
3.  **Alert Timestamps:**
    *   The timestamp determining an alert's inclusion in "Updates since last run," "Last 7 days," or "Last 30 days" is set when the primary alert condition occurs (event first seen as new, or event first seen as deferred).
    *   Successfully rescheduling a deferred event updates its information but does *not* make it a "new" alert for the original deferred item or reset its alert timestamp.
4.  **No "No Match" as a New Alert Type:** A deferred hearing that isn't rescheduled and whose original "deferred" alert timestamp ages out of the filter window will simply no longer appear in those update lists. There's no new alert for it "not being found" after its initial deferral notification period.

**Proposed Changes:**

1.  **Refine `last_alert_type` and `last_alert_timestamp` in `seen_events.json`:**
    *   **`last_alert_type` values:**
        *   `"new"`: For any event when it's first added to `seen_events.json`.
        *   `"deferred"`: When an existing event's `EventAgendaStatusName` changes to "Deferred."
    *   **`last_alert_timestamp`:**
        *   For `last_alert_type = "new"`: Set to `first_seen_timestamp`.
        *   For `last_alert_type = "deferred"`: Set to `last_significant_change_timestamp` (i.e., when it became deferred).

2.  **Modify `process_event_changes()` in `check_new_hearings.py`:**
    *   **Initialization (`initialize_seen_event_entry`)**: 
        *   Set `last_alert_type = "new"`.
        *   Set `last_alert_timestamp = current_time_iso` (which is `first_seen_timestamp`).
    *   **Event Becomes Deferred**:
        *   When `current_status` changes from `active` to `deferred_pending_match` (internal status):
            *   Set `last_alert_type = "deferred"`.
            *   Set `last_alert_timestamp = current_run_iso_time` (which also updates `last_significant_change_timestamp`).
    *   **Deferred Event is Matched to a Reschedule**:
        *   For the *original deferred event*:
            *   Update its `rescheduled_event_details_if_deferred` field.
            *   Its `last_alert_type` remains `"deferred"`.
            *   Its `last_alert_timestamp` (from when it first became deferred) **does not change**.
            *   Its `current_status` (internal tracking) changes to `deferred_rescheduled_internal` (or similar, e.g., `deferred_matched`).
        *   For the *new event that is the reschedule target*:
            *   It will have been added with `last_alert_type = "new"` and `last_alert_timestamp = its first_seen_timestamp`.
            *   Its `original_event_details_if_rescheduled` field is populated. This information is used by the card generator to annotate it as a reschedule.
    *   **"No Match" for Deferred Events (Internal Grace Period Expiry)**:
        *   The internal `current_status` can transition from `deferred_pending_match` to `deferred_nomatch_internal` after a grace period to stop actively trying to match it.
        *   This transition **does not** update `last_alert_type` or `last_alert_timestamp` of the original deferred event and does not generate a new entry in any "Updates" list based on this transition.

3.  **Modify `generate_output_for_webpage()` in `check_new_hearings.py`:**
    *   **Updates - Since Last Run**:
        *   Identify newly added events (these get `item_dict_type="new"`). Their alert timestamp is `last_alert_timestamp` (which is `first_seen_timestamp`).
        *   Identify events that became "deferred" *this run* (these get `item_dict_type="deferred"`). Their alert timestamp is `last_alert_timestamp` (when they became deferred).
    *   **Updates - Last 7/30 Days**:
        *   Iterate `seen_events_db`.
        *   Use `entry['last_alert_type']` directly as `item_dict["type"]`.
        *   Use `entry['last_alert_timestamp']` to filter by the 7/30 day window.
        *   Apply the future/today date filter for items where `item_dict["type"]="new"`.
        *   Sort using `last_alert_timestamp`.

4.  **Modify `generate_update_item_html()` in `generate_web_page.py`:**
    *   This function will now primarily handle `item_type="new"` and `item_type="deferred"`.
    *   **For `item_type="new"`**:
        *   Display as "NEW: [Committee Name]".
        *   Check if `entry['original_event_details_if_rescheduled']` exists. If so, add the note "(Rescheduled from [original date/time])".
    *   **For `item_type="deferred"`**:
        *   Display as "DEFERRED: [Committee Name]". Show original date/time (struck through).
        *   Check if `entry['rescheduled_event_details_if_deferred']` exists.
            *   If yes: Display "Rescheduled to: [new date/time]".
            *   If no (i.e., still `deferred_pending_match` or `deferred_nomatch_internal`): Display "Reschedule: Awaiting information".
    *   Remove or consolidate other specific `item_type` handling like `deferred_initial`, `deferred_nomatch` (as a primary type), `deferred_rescheduled`, `rescheduled_as_new` if these are now just annotations or internal states.

**Benefits of this Revision:**
*   Directly implements the "two main alert types" requirement.
*   Simplifies the `last_alert_type` states in `seen_events.json`.
*   Prevents "no match" internal state changes from creating new user-facing alerts or extending visibility in update lists beyond the original deferral alert.
*   Makes the logic for when an alert's timestamp is set more consistent and tied to the primary event trigger (genuinely new, or genuinely became deferred). 