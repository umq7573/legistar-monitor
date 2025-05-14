# Legistar API Documentation

This document provides an overview of the Legistar Web API based on exploration of the NYC client.

## API Base URL

```
https://webapi.legistar.com/v1/{client}
```

Where `{client}` is the client identifier (e.g., "nyc" for New York City).

## Authentication

Some endpoints require authentication using an API token:

```
https://webapi.legistar.com/v1/{client}/{endpoint}?token={your_token}
```

## Main Resources

The Legistar API provides access to the following main resources:

### 1. Matters (Legislation)

Matters represent legislation items like bills, resolutions, etc.

**Endpoint**: `/matters`

**Key fields**:
- `MatterId`: Unique identifier
- `MatterFile`: File code (e.g., "Int 0760-2022")
- `MatterName`: Short name/title
- `MatterTitle`: Full title/description
- `MatterTypeId`: Type of matter (references MatterTypes)
- `MatterTypeName`: Name of the matter type
- `MatterStatusId`: Current status (references MatterStatuses)
- `MatterStatusName`: Name of the current status
- `MatterBodyId`: The body responsible for the matter
- `MatterBodyName`: Name of the responsible body
- `MatterIntroDate`: Date introduced
- `MatterPassedDate`: Date passed (if applicable)
- `MatterEnactmentDate`: Date enacted (if applicable)
- `MatterEnactmentNumber`: Enactment number (if applicable)
- `MatterVersion`: Version indicator ("*" or letter like "A")

**Related endpoints**:
- `/matters/{id}`: Get details for a specific matter
- `/matters/{id}/attachments`: Get attachments for a matter
- `/matters/{id}/histories`: Get history/timeline of actions for a matter
- `/matters/{id}/sponsors`: Get sponsors of a matter

### 2. Events (Meetings)

Events represent meetings like committee hearings, votes, etc.

**Endpoint**: `/events`

**Key fields**:
- `EventId`: Unique identifier
- `EventBodyId`: The body holding the meeting
- `EventBodyName`: Name of the body
- `EventDate`: Date of the event
- `EventTime`: Time of the event
- `EventLocation`: Location of the event
- `EventAgendaStatusId`: Status of the agenda
- `EventAgendaStatusName`: Name of the agenda status
- `EventMinutesStatusId`: Status of the minutes
- `EventMinutesStatusName`: Name of minutes status
- `EventAgendaFile`: URL to agenda file (PDF)
- `EventMinutesFile`: URL to minutes file (PDF)
- `EventVideoPath`: URL to video recording (if available)

**Related endpoints**:
- `/events/{id}`: Get details for a specific event
- `/events/{id}/eventitems`: Get agenda items for an event

### 3. EventItems (Agenda Items)

EventItems represent items discussed/voted on at events.

**Endpoint**: `/events/{eventId}/eventitems`

**Key fields**:
- `EventItemId`: Unique identifier
- `EventItemEventId`: The event this item belongs to
- `EventItemAgendaSequence`: Order in agenda
- `EventItemMinutesSequence`: Order in minutes
- `EventItemActionId`: Action taken
- `EventItemActionName`: Name of action taken
- `EventItemPassedFlag`: Whether item passed (0=no, 1=yes, null=n/a)
- `EventItemPassedFlagName`: Text representation of passed status
- `EventItemTitle`: Title of the item
- `EventItemMatterId`: Associated matter (if any)
- `EventItemMatterFile`: File code of associated matter
- `EventItemMatterName`: Name of associated matter
- `EventItemMatterType`: Type of associated matter
- `EventItemMatterStatus`: Current status of associated matter

**Related endpoints**:
- `/eventitems/{id}/votes`: Get votes for an event item

### 4. Bodies (Committees, etc.)

Bodies represent committees, subcommittees, and other organizational groups.

**Endpoint**: `/bodies`

**Key fields**:
- `BodyId`: Unique identifier
- `BodyName`: Name of the body
- `BodyTypeId`: Type of body
- `BodyTypeName`: Name of the body type
- `BodyDescription`: Description of the body's function
- `BodyMeetFlag`: Whether the body meets (1=yes, 0=no)
- `BodyActiveFlag`: Whether the body is active (1=yes, 0=no)
- `BodyContactNameId`: ID of contact person
- `BodyContactFullName`: Name of contact person
- `BodyContactPhone`: Phone number of contact
- `BodyContactEmail`: Email of contact
- `BodyNumberOfMembers`: Number of members in the body

### 5. Persons

Persons represent council members, officials, etc.

**Endpoint**: `/persons`

**Key fields**:
- `PersonId`: Unique identifier
- `PersonFirstName`: First name
- `PersonLastName`: Last name
- `PersonFullName`: Full name
- `PersonActiveFlag`: Whether person is active (1=yes, 0=no)
- `PersonPhone`: Phone number
- `PersonEmail`: Email address
- `PersonAddress1`: Primary address

## Supporting Entities

### Matter Types

Lists the different types of matters (legislation)

**Endpoint**: `/mattertypes`

Common types include:
- Introduction (bills)
- Resolution
- Land Use Application
- Communication
- Oversight
- Mayor's Message

### Matter Statuses

Lists the different statuses a matter can have

**Endpoint**: `/matterstatuses`

Common statuses include:
- Introduced
- Committee
- Adopted
- Enacted
- Filed
- Withdrawn
- Vetoed

### Body Types

Lists the different types of bodies

**Endpoint**: `/bodytypes`

Common types include:
- Primary Legislative Body
- Committee
- Subcommittee
- Mayor
- Department

## ODATA Query Parameters

The API supports ODATA query parameters for filtering, sorting, and pagination:

### Pagination

```
?$top=10&$skip=0  // First 10 items
?$top=10&$skip=10 // Next 10 items
```

### Filtering

```
// Filter by date range
?$filter=EventDate+ge+datetime%272023-01-01%27+and+EventDate+lt+datetime%272023-12-31%27

// Filter by multiple conditions
?$filter=MatterTypeId eq 2 and MatterStatusId eq 35 and MatterIntroDate ge datetime'2022-01-01'
```

### Text Search

Full text searching may have limited support (the `contains` function didn't work in testing).

## Example Workflows

### 1. Finding and tracking a piece of legislation

1. Search for matters with specific filters
2. Get the matter details by ID
3. Get the matter history to see timeline of actions
4. Get matter sponsors to see who introduced it
5. Get matter attachments to see related documents

### 2. Finding meetings and votes on a specific topic

1. Search for events within a date range
2. Get event details
3. Get event items to see what was discussed/voted on
4. For relevant event items, get votes to see how officials voted

## Notes and Limitations

1. API responses are limited to 1000 items per request.
2. The `contains` function does not seem to work for text searching.
3. Date filtering needs special formatting: `datetime'2023-01-01'`
4. Some endpoints may return 404 if they don't exist for the client (e.g., `/eventitems` for NYC).
5. Some fields like MatterEXText1-11 and MatterEXDate1-10 are client-specific extended fields. 