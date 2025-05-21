# Analysis of Event Edge Cases

This document analyzes the behavior of Deferred, Without Date, and Joint Hearings based on data from `archive/events_2023.json` and live API queries, assessing implications for the `check_new_hearings.py` script.

## 1. Deferred Hearings & Rescheduling

- **Definition (Initial Understanding)**: Events with `EventAgendaStatusName: "Deferred"`.
- **Observations (from `archive/events_2023.json`)**:
    - Deferred hearings in the sample data **still have a specific `EventDate` and `EventTime`**.
    - Example: EventId 19709 ("Subcommittee on Zoning and Franchises") on "2023-01-17T00:00:00" has status "Deferred".

- **Live API Investigation (Committee on Civil and Human Rights, June 2025)**:
    - **Scenario**: A hearing initially scheduled for June 9, 2025, was marked "Deferred" and then a hearing for the same purpose was held on June 12, 2025.
    - **API Representation**:
        - The June 9th hearing (`EventId: 21620`) remains in the API with `EventAgendaStatusName: "Deferred"` and its original date `2025-06-09`.
        - The June 12th hearing appears as a **new, distinct record** with a **different `EventId: 21629`**, `EventAgendaStatusName: "Final"`, and date `2025-06-12`.
    - **Conclusion**: In this instance, a "deferred and rescheduled" event did **not** involve the original `EventId` having its date changed. Instead, the original event was marked "Deferred," and a new event record was created for the new date.

- **Current Script Handling (`check_new_hearings.py`)**:
    - The script identifies "rescheduled" events only if the **same `EventId`** appears with a **new `EventDate`**.
    - In the live API example above:
        - `EventId: 21620` (June 9, Deferred) would be seen as a "New event" when first encountered, and then "Unchanged" in subsequent runs as long as it remains in the API with that date and status.
        - `EventId: 21629` (June 12, Final) would be seen as a separate "New event" when it appears.
    - **The script would NOT categorize this scenario as a "reschedule" of the June 9th event.** It would report two distinct events.

- **Implications & Potential Issues**: 
    - If this pattern (deferral = original entry stays as "Deferred", reschedule = new `EventId`) is common, the current script will under-report reschedules from a user's perspective.
    - Users might expect the June 12th event to be flagged as a reschedule of the June 9th event.
    - Accurately tracking such reschedules would require more complex logic to correlate different `EventId`s based on `EventBodyName`, `EventComment`, date proximity, and the "Deferred" status of a preceding event.

## 2. Hearings Without Dates

- **Definition**: Events where `EventDate` is null, empty, or a placeholder.
- **Observations (from `archive/events_2023.json`)**:
    - No examples were found. All events in this dataset had a specified `EventDate`.
- **Observations (from Live API Queries - `EventDate eq null` and broad date range fallback)**:
    - No events were returned by the API that had a null `EventDate` or a common placeholder like "0001-01-01".
- **Current Script Handling (`check_new_hearings.py`)**:
    - The script is prepared for this scenario:
        - It can categorize events as **"New events without dates"**.
        - It can categorize events as **"Events with newly confirmed dates"**.
- **Conclusion**: While the script is ready, actual events without dates appear to be extremely rare or non-existent for the NYC client in typical API responses. The corresponding categories on the webpage may seldom, if ever, be populated.

## 3. Joint Hearings

- **Definition**: A single meeting held by multiple committees/bodies simultaneously.
- **Observations**:
    - Indicated by text in the `EventComment` field (e.g., "Jointly with...", "Joint hearing...").
    - The Legistar API represents a joint hearing by creating **separate `Event` entries for each participating committee/body**. These entries typically share the same `EventDate`, `EventTime`, and `EventComment` but have distinct `EventId`s and `EventBodyName`s.
- **Current Script Handling (`check_new_hearings.py`)**:
    - The script processes each `EventId` independently.
    - A new joint hearing (e.g., of 3 committees) will be reported as 3 separate "New events with dates."
    - If a joint hearing is rescheduled (and all associated `EventId`s have their dates changed), it will be reported as 3 "Rescheduled events."
    - If a joint hearing is rescheduled via the "deferral with new EventId" pattern (see Section 1), each component of the original joint hearing would remain as "Deferred," and each component of the new joint hearing would appear as a "New event."
- **Conclusion**: The current script handles the data correctly as provided by the API. The multiple-entry display for joint hearings is a consequence of the API structure. No immediate change is critical, but the interaction with the "deferral with new EventId" rescheduling pattern is important to note.

## Summary of Event ID and Rescheduling Logic

- **EventID is Key (Current Assumption)**: The `check_new_hearings.py` script assumes `EventId` is the stable primary identifier for an event, and changes to *its* date signify a reschedule.
- **Observed API Behavior for Deferral/Reschedule**: At least in some cases, when an event is deferred and then occurs on a new date, Legistar may keep the original event record with its `EventId` and "Deferred" status, and create a *new event record with a new `EventId`* for the actual meeting date.
- **Impact**: This means our current "rescheduled" category will miss these instances. We would see the original deferred event (likely as "unchanged" after its first appearance) and a completely new event.

## Summary of Event ID and Rescheduling

- **EventID is Key**: The `EventId` is the primary identifier for an event.
- **Rescheduling Logic**: An event is "rescheduled" if its `EventDate` changes compared to the last seen `EventDate` for that same `EventId`.
- **Deferred vs. Rescheduled**:
    - If a "Deferred" event (which has an `EventDate`) gets a *new* `EventDate` in the API, it's a reschedule.
    - If a "Deferred" event has its `EventDate` *removed* (becomes null), it would be treated as a new "event without date" if the `EventId` was previously unknown with a date, or potentially an odd state if it was known *with* a date and now has no date (current logic might not explicitly handle "date removed" as a category, it would just not match the old dated entry and potentially be re-added as a new "no-date" event if the old key is removed). This particular sub-case ("date removed from existing event") needs more thought if it's common. However, the examples show deferred events *having* dates.
- **Losing an Event**: If an event (deferred or otherwise) simply stops appearing in the API query (e.g., canceled, too far in the past/future), it's no longer processed. It remains in `seen_events.json` but doesn't generate new notifications. 