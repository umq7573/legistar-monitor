#!/usr/bin/env python3
import os
import subprocess
import json
import logging
from datetime import datetime
import shutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('test_runner')

def setup_test_environment():
    """Set up the test environment"""
    # Create a clean data directory for testing
    if os.path.exists('data/test'):
        shutil.rmtree('data/test')
    
    os.makedirs('data/test', exist_ok=True)
    
    # Create a backup of the real seen_events.json if it exists
    if os.path.exists('data/seen_events.json'):
        logger.info("Backing up existing seen_events.json")
        shutil.copy('data/seen_events.json', 'data/seen_events.json.bak')
    
    # Create an empty seen_events.json for testing
    if not os.path.exists('data/seen_events.json'):
        with open('data/seen_events.json', 'w') as f:
            json.dump({}, f)
    
    # Initialize notification config if it doesn't exist
    if not os.path.exists('notification_config.json'):
        logger.info("Initializing notification config")
        subprocess.run(['python', 'notify_new_hearings.py', '--init'], check=True)
    
    logger.info("Test environment set up")

def teardown_test_environment():
    """Clean up after testing"""
    # Restore the original seen_events.json if it existed
    if os.path.exists('data/seen_events.json.bak'):
        logger.info("Restoring original seen_events.json")
        shutil.copy('data/seen_events.json.bak', 'data/seen_events.json')
        os.remove('data/seen_events.json.bak')
    
    # Clean up test directory
    if os.path.exists('data/test'):
        shutil.rmtree('data/test')
    
    logger.info("Test environment cleaned up")

def run_check_hearings():
    """Run the check_hearings.py script"""
    logger.info("Running check_hearings.py")
    
    try:
        result = subprocess.run(
            ['python', 'check_new_hearings.py'], 
            capture_output=True, 
            text=True, 
            check=True
        )
        logger.info(f"check_hearings.py output:\n{result.stdout}")
        
        # Extract the metrics from the output
        metrics = {
            'total_changes': 0,
            'new_with_dates': 0,
            'new_without_dates': 0,
            'rescheduled': 0,
            'date_confirmed': 0
        }
        
        for line in result.stdout.split('\n'):
            if line.startswith('::set-output name='):
                parts = line.split('::')
                if len(parts) >= 3:
                    name_part = parts[1].split('=')[1]
                    value = parts[2]
                    if name_part in metrics:
                        metrics[name_part] = int(value)
        
        return metrics
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running check_hearings.py: {e}")
        logger.error(f"Stdout: {e.stdout}")
        logger.error(f"Stderr: {e.stderr}")
        return {'total_changes': 0}

def run_notify_hearings(method=None, summary_only=False):
    """Run the notify_new_hearings.py script"""
    logger.info("Running notify_new_hearings.py")
    
    cmd = ['python', 'notify_new_hearings.py']
    if method:
        cmd.extend(['--method', method])
    if summary_only:
        cmd.append('--summary-only')
    
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            check=True
        )
        logger.info(f"notify_new_hearings.py output:\n{result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error running notify_new_hearings.py: {e}")
        logger.error(f"Stdout: {e.stdout}")
        logger.error(f"Stderr: {e.stderr}")
        return False

def check_output_files():
    """Check if output files were created"""
    files_to_check = [
        'data/new_events.json',
        'data/categorized_events.json',
        'data/changes_summary.json',
        'data/notification_text.txt',
        'data/notification_html.html'
    ]
    
    results = {}
    
    for file_path in files_to_check:
        if os.path.exists(file_path):
            logger.info(f"{os.path.basename(file_path)} was created")
            
            try:
                if file_path.endswith('.json'):
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            logger.info(f"{os.path.basename(file_path)} contains {len(data)} items")
                        elif isinstance(data, dict):
                            logger.info(f"{os.path.basename(file_path)} contains keys: {', '.join(data.keys())}")
                        results[os.path.basename(file_path)] = data
                else:
                    with open(file_path, 'r') as f:
                        content = f.read()
                        content_preview = content[:100] + '...' if len(content) > 100 else content
                        logger.info(f"{os.path.basename(file_path)} content preview: {content_preview}")
            except Exception as e:
                logger.error(f"Error reading {file_path}: {e}")
        else:
            logger.info(f"{os.path.basename(file_path)} was NOT created")
    
    return results

def main():
    """Main test function"""
    logger.info("Starting test run")
    
    try:
        # Set up test environment
        setup_test_environment()
        
        # Run check_hearings.py
        metrics = run_check_hearings()
        logger.info(f"Hearing check metrics: {metrics}")
        
        # Run notify_hearings.py if there are changes
        if metrics['total_changes'] > 0:
            logger.info(f"Found {metrics['total_changes']} changes, running notification")
            
            # Test different notification methods
            logger.info("Testing file notification (default)")
            run_notify_hearings()
            
            logger.info("Testing summary-only notification")
            run_notify_hearings(summary_only=True)
        else:
            logger.info("No changes found")
        
        # Check if files were created
        output_files = check_output_files()
        
        # Print a summary of the detected changes if available
        if 'changes_summary.json' in output_files:
            summary = output_files['changes_summary.json']
            logger.info("\n=== CHANGE SUMMARY ===")
            logger.info(f"Total changes: {summary.get('total', 0)}")
            logger.info(f"New events with dates: {summary.get('new_with_dates', 0)}")
            logger.info(f"New events without dates: {summary.get('new_without_dates', 0)}")
            logger.info(f"Rescheduled events: {summary.get('rescheduled', 0)}")
            logger.info(f"Events with newly confirmed dates: {summary.get('date_confirmed', 0)}")
        
        logger.info("Test run completed successfully")
        return 0
    
    except Exception as e:
        logger.error(f"Error during test run: {e}")
        return 1
    
    finally:
        # Clean up test environment
        teardown_test_environment()

if __name__ == "__main__":
    exit(main()) 