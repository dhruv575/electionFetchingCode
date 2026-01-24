"""
Step 2: Create senate_collated.csv from fetched events.
Fetches price histories and creates collated format.
"""

import json
import pandas as pd
import requests
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional


def parse_datetime(dt_str: str) -> Optional[datetime]:
    """Parse a datetime string to datetime object with timezone."""
    if not dt_str or pd.isna(dt_str):
        return None
    try:
        dt_str = str(dt_str)
        if dt_str.endswith('Z'):
            dt_str = dt_str.replace('Z', '+00:00')
        if '+00' in dt_str and not '+00:' in dt_str:
            dt_str = dt_str.replace('+00', '+00:00')
        return datetime.fromisoformat(dt_str)
    except Exception as e:
        print(f"Error parsing datetime '{dt_str}': {e}")
        return None


def fetch_7day_price_history(clob_token_id: str, reference_date: datetime, start_date: datetime = None) -> Dict[int, float]:
    """Fetch price history for 7 days before reference date."""
    if reference_date.tzinfo is None:
        reference_date = reference_date.replace(tzinfo=timezone.utc)

    if start_date and start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)

    api_start = (reference_date - timedelta(days=8)).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
    api_end = (reference_date - timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0, tzinfo=timezone.utc)

    start_ts = int(api_start.timestamp())
    end_ts = int(api_end.timestamp())

    url = (
        f"https://clob.polymarket.com/prices-history?"
        f"fidelity=1440&market={clob_token_id}&startTs={start_ts}&endTs={end_ts}"
    )

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        history = data.get('history', [])
        if not history:
            return {}

        result = {}

        for days_before in range(7, 0, -1):
            target_time = (reference_date - timedelta(days=days_before)).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
            target_ts = int(target_time.timestamp())

            if start_date and target_time < start_date:
                continue

            closest = None
            min_diff = float('inf')

            for entry in history:
                diff = abs(entry['t'] - target_ts)
                if diff < min_diff and diff < 7200:
                    min_diff = diff
                    closest = entry

            if closest is None:
                for entry in sorted(history, key=lambda x: x['t'], reverse=True):
                    if entry['t'] <= target_ts:
                        closest = entry
                        break

            if closest:
                result[days_before] = closest['p']

        return result

    except requests.RequestException as e:
        print(f"Error fetching price history: {e}")
        return {}


def get_clob_id(clob_token_ids) -> Optional[str]:
    """Extract the first CLOB token ID."""
    if not clob_token_ids:
        return None
    try:
        if isinstance(clob_token_ids, str):
            clob_ids = json.loads(clob_token_ids)
        elif isinstance(clob_token_ids, list):
            clob_ids = clob_token_ids
        else:
            return None
        return clob_ids[0] if clob_ids else None
    except:
        return None


def process_market(market: dict, side: str, reference_date: datetime) -> dict:
    """Process a market and fetch its price history."""
    clob_id = get_clob_id(market.get('clobTokenIds'))
    start_date = parse_datetime(market.get('startDate'))

    prices = {}
    if clob_id and reference_date:
        prices = fetch_7day_price_history(clob_id, reference_date, start_date)
        time.sleep(0.15)

    # Determine if Yes won based on outcome prices
    outcome_prices = market.get('outcomePrices', [])
    if isinstance(outcome_prices, str):
        try:
            outcome_prices = json.loads(outcome_prices)
        except:
            outcome_prices = []

    yes_won = None
    if outcome_prices and len(outcome_prices) >= 2:
        try:
            if float(outcome_prices[0]) >= 0.99:
                yes_won = True
            elif float(outcome_prices[1]) >= 0.99:
                yes_won = False
        except:
            pass

    # Calculate correctness
    correct_at_7d = None
    correct_at_1d = None
    if yes_won is not None:
        if 7 in prices:
            correct_at_7d = (prices[7] > 0.5) == yes_won
        if 1 in prices:
            correct_at_1d = (prices[1] > 0.5) == yes_won

    return {
        'id': market.get('id'),
        'question': market.get('question'),
        'slug': market.get('slug'),
        'description': market.get('description', ''),
        'outcomes': str(market.get('outcomes', [])),
        'outcomePrices': str(outcome_prices),
        'volume': float(market.get('volume', 0) or 0),
        'liquidity': market.get('liquidity', 0),
        'startDate': market.get('startDate'),
        'endDate': market.get('endDate'),
        'closedTime': market.get('closedTime'),
        'resolutionSource': market.get('resolutionSource'),
        'tag_ids': '',
        'tag_labels': str(market.get('tags', [])),
        'clobTokenIds': str(market.get('clobTokenIds', [])),
        'side': side,
        'probability7d': prices.get(7),
        'probability6d': prices.get(6),
        'probability5d': prices.get(5),
        'probability4d': prices.get(4),
        'probability3d': prices.get(3),
        'probability2d': prices.get(2),
        'probability1d': prices.get(1),
        'correct_at_7d': correct_at_7d,
        'correct_at_1d': correct_at_1d,
        'yes_won': yes_won,
    }


def create_collated_row(name: str, d_market: dict, r_market: dict) -> dict:
    """Create a row in collated_elections format."""

    # Calculate combined d_prob values
    d_probs = {}
    for days in range(7, 0, -1):
        d_prob = d_market.get(f'probability{days}d')
        r_prob = r_market.get(f'probability{days}d')

        if d_prob is not None and r_prob is not None:
            d_probs[days] = (d_prob + (1 - r_prob)) / 2
        elif d_prob is not None:
            d_probs[days] = d_prob
        elif r_prob is not None:
            d_probs[days] = 1 - r_prob
        else:
            d_probs[days] = None

    # Determine winner (D won if D market Yes won)
    d_won = d_market.get('yes_won', False) == True

    row = {
        'name': name,
        'type': 'pair',
        'combined_volume': d_market.get('volume', 0) + r_market.get('volume', 0),
        'd_prob_7d': d_probs.get(7),
        'd_prob_6d': d_probs.get(6),
        'd_prob_5d': d_probs.get(5),
        'd_prob_4d': d_probs.get(4),
        'd_prob_3d': d_probs.get(3),
        'd_prob_2d': d_probs.get(2),
        'd_prob_1d': d_probs.get(1),
        'd_won': d_won,
    }

    # Add d_market columns
    for key, value in d_market.items():
        if key != 'yes_won':
            row[f'd_market_{key}'] = value

    # Add r_market columns
    for key, value in r_market.items():
        if key != 'yes_won':
            row[f'r_market_{key}'] = value

    return row


def main():
    print("=" * 60)
    print("Creating senate_collated.csv")
    print("=" * 60)

    # Load raw events
    with open('senate_events_raw.json', 'r') as f:
        events = json.load(f)

    print(f"\nLoaded {len(events)} events")

    rows = []

    for event in events:
        state = event['state']
        d_market_raw = event['d_market']
        r_market_raw = event['r_market']

        if not d_market_raw or not r_market_raw:
            print(f"  SKIP {state}: Missing D or R market")
            continue

        # Get reference date from D market (use closedTime or endDate)
        ref_date = parse_datetime(d_market_raw.get('closedTime') or d_market_raw.get('endDate'))

        print(f"\n{state}:")

        # Process markets
        d_processed = process_market(d_market_raw, 'D', ref_date)
        print(f"  D: 7d={d_processed.get('probability7d')}, 1d={d_processed.get('probability1d')}, won={d_processed.get('yes_won')}")

        r_processed = process_market(r_market_raw, 'R', ref_date)
        print(f"  R: 7d={r_processed.get('probability7d')}, 1d={r_processed.get('probability1d')}, won={r_processed.get('yes_won')}")

        # Create name following convention
        name = f"Who will win {state} in the US Senate Election?"

        row = create_collated_row(name, d_processed, r_processed)
        rows.append(row)

        print(f"  -> d_prob_7d={row['d_prob_7d']:.3f}, d_prob_1d={row['d_prob_1d']:.3f}, d_won={row['d_won']}")

    # Create DataFrame
    df = pd.DataFrame(rows)

    # Save
    df.to_csv('senate_collated.csv', index=False)

    print("\n" + "=" * 60)
    print(f"Saved {len(rows)} markets to senate_collated.csv")
    print("=" * 60)

    # Preview
    print("\nPreview:")
    print(df[['name', 'd_prob_7d', 'd_prob_1d', 'd_won', 'combined_volume']].to_string())


if __name__ == '__main__':
    main()
