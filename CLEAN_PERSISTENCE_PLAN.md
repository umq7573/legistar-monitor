# Clean Persistence Strategy Implementation Plan

## Overview
Complete redesign of the state persistence mechanism to ensure:
- Main branch contains only code (no data files)
- gh-pages branch serves as both website host AND persistent database
- Clean, fresh start with no legacy data migration
- Bulletproof state persistence across GitHub Action runs

## Current Issues to Fix
1. **Path Inconsistency**: Workflow saves to `docs/data/` but restores from `data/`
2. **Data Migration Code**: Unnecessary normalization and compatibility code
3. **AttributeError**: Missing null checks for corrupted data entries
4. **Schema Assumptions**: Code assumes certain data structure consistency

## Clean Architecture

### Branch Responsibilities
- **main**: Source code only, `.gitignore` includes `data/`
- **gh-pages**: Generated website + persistent state database

### File Structure on gh-pages
```
gh-pages/
├── index.html                          # Generated website (root level for GitHub Pages)
├── .nojekyll                           # GitHub Pages configuration
├── assets/                             # Website static assets
└── data/                               # Persistent state (not served publicly)
    ├── seen_events.json                # Main persistent state database
    └── processed_events_for_web.json   # Generated web-ready data
```

### Workflow Persistence Mechanism
1. **Restore**: `git checkout gh-pages -- data/seen_events.json || echo '{}' > data/seen_events.json`
2. **Execute**: Run scripts with restored state
3. **Stage**: Copy both data files to deployment staging
4. **Deploy**: Deploy everything (website + data) to gh-pages for next run

## Code Changes Required

### 1. Remove Migration/Defensive Code
- Remove string normalization in `load_seen_events()`
- Remove compatibility assumptions
- Remove defensive null checks added for corrupted data
- Assume clean data structure from fresh start

### 2. Simplify Data Loading
```python
def load_seen_events():
    """Load previously seen events from history file."""
    if not os.path.exists(HISTORY_FILE):
        logger.info(f"No history file found at {HISTORY_FILE}, starting fresh.")
        return {}
    
    try:
        with open(HISTORY_FILE, 'r') as f:
            data = json.load(f)
        logger.info(f"Loaded {len(data)} events from history.")
        return data
    except Exception as e:
        logger.error(f"Error loading history file {HISTORY_FILE}: {e}. Starting fresh.")
        return {}
```

### 3. Fix GitHub Actions Workflow
**Current Problem:**
```yaml
# Restore from: data/seen_events.json
git checkout gh-pages -- data/seen_events.json

# But save to: docs/data/seen_events.json (wrong path!)
cp data/seen_events.json docs/data/seen_events.json
```

**Clean Solution:**
```yaml
- name: Restore persistent state from gh-pages
  run: |
    mkdir -p data
    git fetch origin gh-pages:gh-pages || echo "No gh-pages branch found"
    git checkout gh-pages -- data/seen_events.json || echo '{}' > data/seen_events.json

- name: Stage all files for deployment  
  run: |
    mkdir -p docs/data
    cp data/seen_events.json docs/data/seen_events.json
    cp data/processed_events_for_web.json docs/data/processed_events_for_web.json

- name: Deploy everything to gh-pages
  uses: JamesIves/github-pages-deploy-action@4.1.4
  with:
    branch: gh-pages
    folder: docs
    clean: true
```

### 4. Update .gitignore
Ensure main branch stays clean:
```
data/
docs/index.html
config.json
```

## Implementation Steps

### Phase 1: Clean State Reset
1. Reset gh-pages to have clean empty `data/seen_events.json: {}`
2. Remove all data files from main branch
3. Update .gitignore to exclude data files

### Phase 2: Code Cleanup  
1. Remove data normalization code
2. Remove null checks for corrupted data (since starting fresh)
3. Simplify data loading logic
4. Keep only the AttributeError fix for ongoing robustness

### Phase 3: Workflow Fix
1. Fix path consistency in GitHub Actions
2. Ensure proper staging of data files alongside website
3. Test with manual workflow run

### Phase 4: Verification
1. Confirm main branch contains no data files
2. Confirm workflow runs without state loss
3. Confirm repeated runs work correctly

## Benefits of This Approach
- ✅ Main branch stays perpetually clean
- ✅ No manual data syncing required
- ✅ gh-pages serves dual purpose (website + database)
- ✅ Bulletproof state persistence
- ✅ No legacy data migration complexity
- ✅ Clear separation of concerns

## Testing Strategy
1. Create clean test branch from main
2. Reset gh-pages to clean state
3. Run workflow multiple times
4. Verify state persistence across runs
5. Verify no data leakage to main branch 