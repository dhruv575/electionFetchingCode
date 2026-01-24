"""
Step 1: Fetch Senate election events from Polymarket and identify D/R markets.
"""

import requests
import time
import json

def fetch_event(slug: str) -> dict:
    """Fetch event data from Polymarket Gamma API."""
    url = f'https://gamma-api.polymarket.com/events?slug={slug}'
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        if data and len(data) > 0:
            return data[0]
        return None
    except Exception as e:
        print(f"Error fetching {slug}: {e}")
        return None


def main():
    # Read URLs from senate.txt
    with open('senate.txt', 'r') as f:
        urls = [line.strip() for line in f if line.strip()]

    print(f"Found {len(urls)} event URLs\n")
    print("=" * 80)

    results = []

    for url in urls:
        # Extract slug from URL
        slug = url.split('/event/')[-1]

        event = fetch_event(slug)
        if not event:
            print(f"FAILED: {slug}")
            continue

        # Extract state name from slug
        state = slug.replace('-us-senate-election-winner', '').replace('-', ' ').title()

        markets = event.get('markets', [])

        # Find D and R markets
        d_market = None
        r_market = None

        for m in markets:
            market_slug = m.get('slug', '')
            if 'democrat' in market_slug.lower():
                d_market = m
            elif 'republican' in market_slug.lower():
                r_market = m

        print(f"\n{state}")
        print(f"  Event: {event.get('title')}")

        if d_market:
            print(f"  D: {d_market.get('slug')}")
        else:
            print(f"  D: NOT FOUND")

        if r_market:
            print(f"  R: {r_market.get('slug')}")
        else:
            print(f"  R: NOT FOUND")

        results.append({
            'state': state,
            'event_slug': slug,
            'event_title': event.get('title'),
            'd_market': d_market,
            'r_market': r_market,
        })

        time.sleep(0.2)

    # Save results for step 2
    with open('senate_events_raw.json', 'w') as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 80)
    print(f"\nSaved {len(results)} events to senate_events_raw.json")
    print("\nSummary:")
    print(f"  Events with both D and R: {sum(1 for r in results if r['d_market'] and r['r_market'])}")
    print(f"  Events missing D: {sum(1 for r in results if not r['d_market'])}")
    print(f"  Events missing R: {sum(1 for r in results if not r['r_market'])}")


if __name__ == '__main__':
    main()
