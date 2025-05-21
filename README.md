# Legistar API Tools

This repository contains utilities for working with the Legistar Web API, which provides access to legislative data for various municipalities.

## Hearing Monitoring Utility

This repository includes a utility to automatically monitor for new and changed Legistar hearings. It's designed to run as a GitHub Action and present findings on a static webpage.

### How the Hearing Monitor Works

The core logic resides in `check_new_hearings.py` and `generate_web_page.py`, orchestrated by a GitHub Action:

1.  **Data Persistence**:
    *   The GitHub Action, when it runs, first attempts to retrieve the `data/seen_events.json` file from the `gh-pages` branch. This file acts as a database of events observed in previous runs.
    *   If not found (e.g., on the first run), a new `seen_events.json` will be created.

2.  **Event Fetching & Processing (`check_new_hearings.py`)**:
    *   Queries the Legistar API for events within a configurable lookback period (e.g., 1 year) and all future events.
    *   Compares fetched events against the data in `seen_events.json` (if it exists).
    *   **Categorizes Events**:
        *   **New Hearings**: Events not previously seen.
        *   **Deferred Hearings**: Events previously seen whose status changes to "Deferred". The system then attempts to find a matching rescheduled event.
            *   If a match is found (based on body name, exact comment match, and date proximity), it's tagged as "deferred and rescheduled."
            *   If no match is found after a grace period, it's tagged as "deferred with no match."
            *   If awaiting a match, it's "deferred pending match."
    *   Updates `seen_events.json` with the latest event states and timestamps.
    *   Generates `data/processed_events_for_web.json`, which contains structured data tailored for the webpage, including lists for "Updates" and "Upcoming Hearings."

3.  **Webpage Generation (`generate_web_page.py`)**:
    *   Reads `data/processed_events_for_web.json`.
    *   Creates `docs/index.html`, a static webpage to display the findings.

4.  **GitHub Action Workflow (`.github/workflows/check_hearings.yml`)**:
    *   Automates the above steps on a schedule (e.g., daily) or manual trigger.
    *   After the Python scripts run, the Action copies the updated `data/seen_events.json` and `data/processed_events_for_web.json` into the `docs/data/` directory.
    *   It then deploys the entire `docs` folder (containing `index.html` and `docs/data/*`) to the `gh-pages` branch. This makes the webpage live and also persists the `seen_events.json` for the next Action run.
    *   **Important**: The Action does *not* commit any changes back to the `main` branch. This keeps the `main` branch clean for development.

### Setting Up the Hearing Monitor

1.  **Configure your API token**:
    *   Add your Legistar API token as a repository secret in GitHub. Name this secret `LEGISTAR_API_TOKEN`.

2.  **Enable GitHub Pages**:
    *   In your GitHub repository settings (under "Pages"), ensure GitHub Pages is enabled and set to deploy from the `gh-pages` branch, using the `/ (root)` folder of that branch.
    *   The workflow will automatically create and populate the `gh-pages` branch.

3.  **GitHub Actions Setup**:
    *   The workflow is already configured in `.github/workflows/check_hearings.yml`.
    *   By default, it runs daily. You can also trigger it manually from the "Actions" tab in your GitHub repository.

### Static Website

The hearing monitor generates a static website with a clean, responsive design, accessible at `https://[your-username].github.io/[your-repo-name]/` (e.g., `https://umq7573.github.io/legistar-monitor/`).

The website features a two-column layout:

1.  **Updates Column (Left)**:
    *   Displays recent changes, categorized as:
        *   **NEW**: Newly announced hearings.
        *   **DEFERRED**: Hearings that were marked as "Deferred." Shows original date/time.
        *   **DEFERRED & RESCHEDULED**: Deferred hearings for which a new date has been found. Shows original and new dates/times.
        *   **DEFERRED (No Match)**: Deferred hearings for which no reschedule was identified after a grace period.
    *   Includes an interactive dropdown filter to view updates from:
        *   Since last update (default)
        *   Last 7 days
        *   Last 30 days
    *   Each update card provides event details and a link to the agenda if available.

2.  **Upcoming Hearings Column (Right)**:
    *   Lists all known upcoming hearings, sorted by date.
    *   **Pagination**: Displays a set number of hearings per page (e.g., 25).
    *   **Tags**:
        *   `NEW`: For hearings recently added.
        *   `RESCHEDULED (was ...)`: For hearings that are the result of a deferral, showing the original date/time.
        *   `DEFERRED`: For hearings that are deferred and currently have no reschedule date identified.
    *   Each hearing card shows the committee/body name, date, time, location, and agenda link.

### Testing Locally

To test the hearing monitor and website generation locally:

1.  **Create `config.json`**:
    *   In the root directory, create a `config.json` file with your API credentials:
        ```json
        {
          "client": "your_client_name", // e.g., "nyc"
          "token": "YOUR_API_TOKEN"
        }
        ```
    *   This file is listed in `.gitignore` and should not be committed.

2.  **Run the scripts**:
```bash
    # Ensure dependencies are installed (e.g., requests)
    # pip install requests

    # Run the hearing monitor to check for changes and update local data files
python check_new_hearings.py

# Generate the static website
python generate_web_page.py

# Open the generated website in your browser
open docs/index.html
```
    *   When running locally, `check_new_hearings.py` will read `data/seen_events.json` if it exists in your local `data/` directory, or create it if not. This mimics one part of the Action's state management but without fetching from `gh-pages`.

### Manual Commands for `legistar_api.py`

The `legistar_api.py` script can also be used as a general command-line tool to query the Legistar API.

```bash
# Example: Get top 10 active matters
./legistar_api.py matters --top 10 --status 35

# Example: Get events starting from a specific date
./legistar_api.py events --start 2023-01-01
```

## Files in this Repository

-   **`.github/workflows/check_hearings.yml`**: Defines the GitHub Action workflow for automated hearing checks and webpage deployment.
-   **`LEGISTAR_API_DOCUMENTATION.md`**: Comprehensive documentation of the Legistar API.
-   **`legistar_api.py`**: Python script providing both a library class (`LegistarAPI`) and a command-line interface for Legistar API interaction.
-   **`check_new_hearings.py`**: Core script that fetches hearings, processes changes, and updates state.
-   **`generate_web_page.py`**: Script that generates the `docs/index.html` static website from processed data.
-   **`config.json`** (local use only, gitignored): Configuration for `legistar_api.py` when run manually, containing API client and token. The GitHub Action uses repository secrets.
-   **`requirements.txt`**: Lists Python package dependencies.
-   **`data/`** (gitignored, except by Action on `gh-pages`):
    *   `seen_events.json`: Stores a record of all events processed. Locally, this file is read/written by `check_new_hearings.py`. The GitHub Action manages its persistence between runs by storing it on the `gh-pages` branch.
    *   `processed_events_for_web.json`: Intermediate JSON file generated by `check_new_hearings.py`, containing data structured for consumption by `generate_web_page.py`.
-   **`docs/`**:
    *   `index.html` (gitignored locally): The main static webpage generated by `generate_web_page.py`. The GitHub Action generates this and deploys it.
    *   `data/` (managed by Action on `gh-pages`): The GitHub action places copies of `seen_events.json` and `processed_events_for_web.json` here when deploying to `gh-pages`.
-   **`archive/`**: Contains older exploratory scripts and sample JSON outputs, not part of the active system.
-   **`investigations/`**: Contains scripts and notes from specific research tasks (e.g., `refactor_plan.md`).

## Getting Started (for `legistar_api.py` CLI)

1.  **Configure your API token**:
    *   Edit or create `config.json` in the root directory:
        ```json
        {
          "client": "your_client_name",
          "token": "YOUR_API_TOKEN"
        }
        ```

2.  **Run the command-line utility**:
    ```bash
   ./legistar_api.py [command] [options]
   ```

## Available Commands (`legistar_api.py`)

-   **`matters`**: Get legislation items
    ```bash
  ./legistar_api.py matters --top 10 --status 35
  ```

- **`matter`**: Get details for a specific matter
  ```
  ./legistar_api.py matter 12345
  ```

- **`matter-history`**: Get history for a specific matter
  ```
  ./legistar_api.py matter-history 12345
  ```

- **`matter-sponsors`**: Get sponsors for a specific matter
  ```
  ./legistar_api.py matter-sponsors 12345
  ```

- **`events`**: Get meetings/events
  ```
  ./legistar_api.py events --start 2023-01-01 --end 2023-12-31
  ```

- **`event-items`**: Get agenda items for a specific event
  ```
  ./legistar_api.py event-items 678
  ```

- **`bodies`**: Get committees/bodies
  ```
  ./legistar_api.py bodies --all
  ```

- **`matter-types`**: Get all matter types
  ```
  ./legistar_api.py matter-types
  ```

- **`matter-statuses`**: Get all matter statuses
  ```
  ./legistar_api.py matter-statuses
  ```

- **`body-types`**: Get all body types
  ```
  ./legistar_api.py body-types
  ```

## Saving Output

Use the `--output` option to save results to a file:

```
./legistar_api.py --output results.json matters --top 25
```

## Global Options

- **`--client`**: Client identifier (defaults to value in config.json)
- **`--token`**: API token (defaults to value in config.json)
- **`--config`**: Path to config file (default: config.json)
- **`--output`**: Save output to specified file

## Using the API in Custom Scripts

You can import the `LegistarAPI` class into your own Python scripts:

```python
from legistar_api import LegistarAPI

# Create an API client
api = LegistarAPI(client="nyc", config_file="config.json")

# Get recent legislation
matters = api.get_matters(top=5, skip=0, MatterStatusId=35)

# Process the data
for matter in matters:
    print(f"{matter['MatterFile']}: {matter['MatterName']}")
```

## Data Directory (Legacy - See "Files in this Repository" for current structure)

The `data/` directory was previously used more extensively. Currently, its primary role for local execution is to hold `seen_events.json` and the temporary `processed_events_for_web.json`. The GitHub Action workflow has a more specific way of handling these files for persistence via the `gh-pages` branch.

The `archive/` directory contains older exploratory scripts and sample JSON outputs from previous API calls, which are not part of the active monitoring system.
