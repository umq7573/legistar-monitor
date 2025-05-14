# Legistar API Tools

This repository contains utilities for working with the Legistar Web API, which provides access to legislative data for various municipalities.

## Hearing Monitoring Utility

This repository includes a utility to automatically monitor for new hearings and send notifications. It's designed to run as a GitHub Action.

### How the Hearing Monitor Works

1. The script queries the Legistar API for upcoming events/hearings within a specified date range
2. Categorizes changes into different types:
   - New events with dates
   - New events without dates (TBD)
   - Rescheduled events (date changed)
   - Events with newly confirmed dates (previously had no date)
3. Tracks all events in a database file to identify changes over time
4. Generates a static website displaying the changes
5. Updates the database for future runs

### Setting Up the Hearing Monitor

1. **Configure your API token**:
   - Edit `config.json` to include your client identifier and API token for local testing
   - Add your API token as a repository secret in GitHub named `LEGISTAR_API_TOKEN`

2. **Enable GitHub Pages**:
   - In your GitHub repository settings, enable GitHub Pages from the `gh-pages` branch
   - The workflow will automatically create and update this branch

3. **GitHub Actions Setup**:
   - The workflow is already configured in `.github/workflows/check_hearings.yml`
   - By default, it runs daily at 8:00 AM UTC
   - You can trigger it manually from the Actions tab in GitHub

### Static Website

The hearing monitor generates a static website with a clean, responsive design that:

1. **Displays hearings in categorized columns**:
   - New events with dates (green)
   - New events without dates (yellow)
   - Rescheduled events (purple)
   - Events with newly confirmed dates (blue)

2. **Shows summary information**:
   - Total number of changes
   - Counts for each category
   - Last update timestamp

3. **Provides details for each hearing**:
   - Committee/body name
   - Date and time
   - Location
   - Links to agenda documents (when available)

The static website is automatically deployed to GitHub Pages, making it accessible at:
`https://[your-username].github.io/legistar/`

### Testing Locally

To test the hearing monitor and website generation locally:

```bash
# Run the hearing monitor to check for changes
python check_new_hearings.py

# Generate the static website
python generate_web_page.py

# Open the generated website in your browser
open docs/index.html
```

### Notification Options

This system uses web-based notifications via GitHub Pages:

- **Static Web Page**: 
  - All hearing changes are displayed on a clean, responsive webpage
  - Automatically deployed to GitHub Pages during each workflow run
  - No additional infrastructure needed (email servers, Slack, etc.)
  - Access the page at: `https://[your-username].github.io/legistar/`

The static website is organized into four columns, each representing a different category of changes, with clear color-coding:
  - Green: New events with dates
  - Yellow: New events without dates
  - Purple: Rescheduled events
  - Blue: Events with newly confirmed dates

### Manual Commands

You can also run the core scripts manually:

```bash
# Check for new hearings
python check_new_hearings.py

# Generate the static website
python generate_web_page.py

# Open the generated website in your browser
open docs/index.html
```

## Original Features

## Files in this Repository

- **`LEGISTAR_API_DOCUMENTATION.md`**: Comprehensive documentation of the Legistar API, including available endpoints, field descriptions, and example usage patterns.

- **`legistar_api.py`**: A Python utility script that provides easy command-line access to the Legistar API.

- **`check_new_hearings.py`**: The core script that monitors for changes in hearings.

- **`generate_web_page.py`**: Script that generates the static website for viewing changes.

- **`config.json`**: Configuration file for the API client. You should add your client identifier and token here.

- **`archive/`**: Contains exploratory scripts and older features no longer in active use.

## Getting Started

1. **Configure your API token**: 
   Edit `config.json` to include your client identifier and API token.

2. **Run the command-line utility**:
   ```
   ./legistar_api.py [command] [options]
   ```

## Available Commands

- **`matters`**: Get legislation items
  ```
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

## Data Directory

The `data/` directory contains JSON output from API calls. This data can be used for further analysis or as input to other applications. 