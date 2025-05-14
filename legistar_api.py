#!/usr/bin/env python3
import requests
import json
import os
import argparse
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode

class LegistarAPI:
    def __init__(self, client="nyc", token=None, config_file=None):
        """
        Initialize the Legistar API client
        
        Args:
            client (str): Client identifier (e.g., "nyc" for New York City)
            token (str): API token for authentication
            config_file (str): Path to config file containing client and token
        """
        # Load config from file if provided
        if config_file and os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    if 'client' in config and not client:
                        client = config['client']
                    if 'token' in config and not token:
                        token = config['token']
            except Exception as e:
                print(f"Error loading config file: {e}")

        self.client = client
        self.token = token
        self.base_url = f"https://webapi.legistar.com/v1/{client}"
    
    def get(self, endpoint, params=None):
        """
        Make a GET request to the Legistar API
        
        Args:
            endpoint (str): API endpoint to query
            params (dict): Query parameters
            
        Returns:
            dict or list: JSON response from the API
        """
        url = f"{self.base_url}/{endpoint}"
        
        # Prepare parameters
        query_params = {}
        if params:
            query_params.update(params)
        
        # Add token if provided
        if self.token:
            query_params['token'] = self.token
        
        # Build full URL with parameters
        if query_params:
            query_string = urlencode(query_params, quote_via=quote)
            url = f"{url}?{query_string}"
        
        print(f"Fetching: {url}")
        response = requests.get(url)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error {response.status_code}: {response.text}")
            return None
    
    def save_to_file(self, data, filename, directory="data"):
        """Save data to a JSON file"""
        os.makedirs(directory, exist_ok=True)
        filepath = os.path.join(directory, filename)
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"Data saved to {filepath}")
        return filepath
    
    # Matter-related methods
    def get_matters(self, top=10, skip=0, **filters):
        """
        Get matters with pagination and optional filters
        
        Args:
            top (int): Number of records to return
            skip (int): Number of records to skip
            **filters: Additional filter parameters
            
        Returns:
            list: List of matters
        """
        params = {
            '$top': top,
            '$skip': skip
        }
        
        # Build filter string if filters are provided
        if filters:
            filter_parts = []
            for key, value in filters.items():
                if key.startswith('date_'):
                    # Handle date filters
                    field = key[5:]  # Remove 'date_' prefix
                    operator = 'ge' if 'from' in field else 'lt'
                    field = field.replace('_from', '').replace('_to', '')
                    date_str = value.isoformat().split('T')[0]
                    filter_parts.append(f"{field} {operator} datetime'{date_str}'")
                else:
                    # Handle other filters
                    operator = 'eq'
                    filter_parts.append(f"{key} {operator} {value}")
            
            params['$filter'] = ' and '.join(filter_parts)
        
        return self.get('matters', params)
    
    def get_matter(self, matter_id):
        """Get details for a specific matter"""
        return self.get(f"matters/{matter_id}")
    
    def get_matter_attachments(self, matter_id):
        """Get attachments for a specific matter"""
        return self.get(f"matters/{matter_id}/attachments")
    
    def get_matter_histories(self, matter_id):
        """Get history for a specific matter"""
        return self.get(f"matters/{matter_id}/histories")
    
    def get_matter_sponsors(self, matter_id):
        """Get sponsors for a specific matter"""
        return self.get(f"matters/{matter_id}/sponsors")
    
    # Event-related methods
    def get_events(self, top=10, skip=0, **filters):
        """
        Get events with pagination and optional filters
        
        Args:
            top (int): Number of records to return
            skip (int): Number of records to skip
            **filters: Additional filter parameters
            
        Returns:
            list: List of events
        """
        params = {
            '$top': top,
            '$skip': skip
        }
        
        # Build filter string if filters are provided
        if filters:
            filter_parts = []
            for key, value in filters.items():
                if key == 'date_range':
                    # Handle date range filter
                    start_date, end_date = value
                    start_date_str = start_date.isoformat().split('T')[0]
                    end_date_str = end_date.isoformat().split('T')[0]
                    filter_parts.append(f"EventDate ge datetime'{start_date_str}' and EventDate lt datetime'{end_date_str}'")
                elif key.startswith('date_'):
                    # Handle date filters
                    field = key[5:]  # Remove 'date_' prefix
                    operator = 'ge' if 'from' in field else 'lt'
                    field = field.replace('_from', '').replace('_to', '')
                    date_str = value.isoformat().split('T')[0]
                    filter_parts.append(f"{field} {operator} datetime'{date_str}'")
                else:
                    # Handle other filters
                    operator = 'eq'
                    filter_parts.append(f"{key} {operator} {value}")
            
            params['$filter'] = ' and '.join(filter_parts)
        
        return self.get('events', params)
    
    def get_event(self, event_id):
        """Get details for a specific event"""
        return self.get(f"events/{event_id}")
    
    def get_event_items(self, event_id):
        """Get agenda items for a specific event"""
        return self.get(f"events/{event_id}/eventitems")
    
    # Body-related methods
    def get_bodies(self, top=50, skip=0, active_only=True):
        """Get bodies/committees"""
        params = {
            '$top': top,
            '$skip': skip
        }
        
        if active_only:
            params['$filter'] = 'BodyActiveFlag eq 1'
        
        return self.get('bodies', params)
    
    def get_body(self, body_id):
        """Get details for a specific body"""
        return self.get(f"bodies/{body_id}")
    
    # Person-related methods
    def get_persons(self, top=50, skip=0, active_only=True):
        """Get persons"""
        params = {
            '$top': top,
            '$skip': skip
        }
        
        if active_only:
            params['$filter'] = 'PersonActiveFlag eq 1'
        
        return self.get('persons', params)
    
    def get_person(self, person_id):
        """Get details for a specific person"""
        return self.get(f"persons/{person_id}")
    
    # Reference data methods
    def get_matter_types(self):
        """Get all matter types"""
        return self.get('mattertypes')
    
    def get_matter_statuses(self):
        """Get all matter statuses"""
        return self.get('matterstatuses')
    
    def get_body_types(self):
        """Get all body types"""
        return self.get('bodytypes')


def main():
    """Command-line interface for the Legistar API client"""
    parser = argparse.ArgumentParser(description='Legistar API Client')
    
    # Global arguments
    parser.add_argument('--client', help='Client identifier (default from config.json or "nyc")')
    parser.add_argument('--token', help='API token (default from config.json)')
    parser.add_argument('--config', default='config.json', help='Path to config file (default: config.json)')
    parser.add_argument('--output', '-o', help='Output file path')
    
    # Create subparsers for each command
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Matters command
    matters_parser = subparsers.add_parser('matters', help='Get matters/legislation')
    matters_parser.add_argument('--top', type=int, default=10, help='Number of records to return')
    matters_parser.add_argument('--skip', type=int, default=0, help='Number of records to skip')
    matters_parser.add_argument('--type', type=int, help='Filter by matter type ID')
    matters_parser.add_argument('--status', type=int, help='Filter by matter status ID')
    matters_parser.add_argument('--since', help='Filter matters introduced since date (YYYY-MM-DD)')
    
    # Matter detail command
    matter_parser = subparsers.add_parser('matter', help='Get matter details')
    matter_parser.add_argument('id', type=int, help='Matter ID')
    
    # Matter history command
    matter_history_parser = subparsers.add_parser('matter-history', help='Get matter history')
    matter_history_parser.add_argument('id', type=int, help='Matter ID')
    
    # Matter sponsors command
    matter_sponsors_parser = subparsers.add_parser('matter-sponsors', help='Get matter sponsors')
    matter_sponsors_parser.add_argument('id', type=int, help='Matter ID')
    
    # Events command
    events_parser = subparsers.add_parser('events', help='Get events/meetings')
    events_parser.add_argument('--top', type=int, default=10, help='Number of records to return')
    events_parser.add_argument('--skip', type=int, default=0, help='Number of records to skip')
    events_parser.add_argument('--body', type=int, help='Filter by body ID')
    events_parser.add_argument('--start', help='Start date (YYYY-MM-DD)')
    events_parser.add_argument('--end', help='End date (YYYY-MM-DD)')
    
    # Event items command
    event_items_parser = subparsers.add_parser('event-items', help='Get event items')
    event_items_parser.add_argument('id', type=int, help='Event ID')
    
    # Bodies command
    bodies_parser = subparsers.add_parser('bodies', help='Get bodies/committees')
    bodies_parser.add_argument('--top', type=int, default=50, help='Number of records to return')
    bodies_parser.add_argument('--skip', type=int, default=0, help='Number of records to skip')
    bodies_parser.add_argument('--all', action='store_true', help='Include inactive bodies')
    
    # Reference data commands
    subparsers.add_parser('matter-types', help='Get matter types')
    subparsers.add_parser('matter-statuses', help='Get matter statuses')
    subparsers.add_parser('body-types', help='Get body types')
    
    args = parser.parse_args()
    
    # Create API client
    api = LegistarAPI(client=args.client, token=args.token, config_file=args.config)
    
    # Execute command
    result = None
    
    if args.command == 'matters':
        filters = {}
        if args.type:
            filters['MatterTypeId'] = args.type
        if args.status:
            filters['MatterStatusId'] = args.status
        if args.since:
            filters['date_MatterIntroDate_from'] = datetime.strptime(args.since, '%Y-%m-%d')
        
        result = api.get_matters(top=args.top, skip=args.skip, **filters)
    
    elif args.command == 'matter':
        result = api.get_matter(args.id)
    
    elif args.command == 'matter-history':
        result = api.get_matter_histories(args.id)
    
    elif args.command == 'matter-sponsors':
        result = api.get_matter_sponsors(args.id)
    
    elif args.command == 'events':
        filters = {}
        if args.body:
            filters['EventBodyId'] = args.body
        if args.start and args.end:
            start_date = datetime.strptime(args.start, '%Y-%m-%d')
            end_date = datetime.strptime(args.end, '%Y-%m-%d')
            filters['date_range'] = (start_date, end_date)
        
        result = api.get_events(top=args.top, skip=args.skip, **filters)
    
    elif args.command == 'event-items':
        result = api.get_event_items(args.id)
    
    elif args.command == 'bodies':
        result = api.get_bodies(top=args.top, skip=args.skip, active_only=not args.all)
    
    elif args.command == 'matter-types':
        result = api.get_matter_types()
    
    elif args.command == 'matter-statuses':
        result = api.get_matter_statuses()
    
    elif args.command == 'body-types':
        result = api.get_body_types()
    
    # Print or save results
    if result:
        if args.output:
            api.save_to_file(result, args.output)
        else:
            print(json.dumps(result, indent=2))
    elif args.command is None:
        parser.print_help()


if __name__ == '__main__':
    main() 