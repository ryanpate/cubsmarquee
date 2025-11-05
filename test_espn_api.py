#!/usr/bin/env python3
"""Test script to explore ESPN API structure"""

import requests
import json


def fetch_bears_schedule():
    """Fetch Bears schedule from ESPN API"""
    url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/chi/schedule"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        # Save full response to file for inspection
        with open('bears_api_full.json', 'w') as f:
            json.dump(data, f, indent=2)
        print("✓ Full API response saved to bears_api_full.json")

        # Find today's or most recent game
        events = data.get('events', [])

        if not events:
            print("No events found")
            return

        print(f"\n{'='*80}")
        print(f"Found {len(events)} events in schedule")
        print(f"{'='*80}\n")

        # Look at the first event (most recent)
        event = events[0]

        print("EVENT STRUCTURE:")
        print(f"  Event ID: {event.get('id')}")
        print(f"  Name: {event.get('name')}")
        print(f"  Date: {event.get('date')}")
        print(
            f"  Status: {event.get('status', {}).get('type', {}).get('name')}")
        print()

        # Get competition
        competition = event['competitions'][0]

        print("COMPETITION STRUCTURE:")
        print(f"  Competition keys: {list(competition.keys())}")
        print()

        # Check for scores in different locations
        print("SEARCHING FOR SCORES IN COMPETITION OBJECT:")

        # Check if there's a 'competitors' array
        competitors = competition.get('competitors', [])
        print(f"  Number of competitors: {len(competitors)}")

        for i, comp in enumerate(competitors):
            print(f"\n  Competitor {i}:")
            print(
                f"    Team: {comp.get('team', {}).get('displayName', 'Unknown')}")
            print(f"    Home/Away: {comp.get('homeAway')}")
            print(f"    Keys available: {list(comp.keys())}")
            print(f"    Score in competitor: {comp.get('score')}")

            # Check if score is nested elsewhere
            if 'score' in comp:
                print(f"    Score object type: {type(comp['score'])}")
                if isinstance(comp['score'], dict):
                    print(f"    Score object contents: {comp['score']}")

        # Check for scores at competition level
        print("\n  SCORES AT COMPETITION LEVEL:")
        if 'competitors' in competition:
            for comp in competition['competitors']:
                team_name = comp.get('team', {}).get('abbreviation', 'Unknown')
                score = comp.get('score', 'NOT FOUND')
                print(f"    {team_name}: {score}")

        # Check for status details
        print("\n  STATUS DETAILS:")
        status = competition.get('status', {})
        print(f"    Type: {status.get('type', {})}")
        print(f"    Clock: {status.get('clock')}")
        print(f"    Display clock: {status.get('displayClock')}")
        print(f"    Period: {status.get('period')}")

        # Check if there's a 'situation' object (often contains live game data)
        if 'situation' in competition:
            print("\n  SITUATION OBJECT FOUND:")
            situation = competition['situation']
            print(f"    Keys: {list(situation.keys())}")
            print(f"    Situation data: {json.dumps(situation, indent=4)}")

        # Save just the first event for detailed inspection
        with open('bears_api_event.json', 'w') as f:
            json.dump(event, f, indent=2)
        print("\n✓ First event saved to bears_api_event.json")

        # Save just the competition for detailed inspection
        with open('bears_api_competition.json', 'w') as f:
            json.dump(competition, f, indent=2)
        print("✓ Competition data saved to bears_api_competition.json")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    fetch_bears_schedule()
    print("\n" + "="*80)
    print("Check the generated JSON files for full structure details:")
    print("  - bears_api_full.json (complete response)")
    print("  - bears_api_event.json (first event)")
    print("  - bears_api_competition.json (competition details)")
    print("="*80)
