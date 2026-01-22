"""
Process all_elections_labeled.csv:
1. Deduplicate by market id
2. Fetch 7-day price history
3. Add correct_at_7d and correct_at_1d columns
"""

import pandas as pd
import requests
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from tqdm import tqdm

DEBUG = True


def parse_datetime(dt_str: str) -> Optional[datetime]:
    """Parse a datetime string to datetime object with timezone."""
    if not dt_str or pd.isna(dt_str):
        return None
    try:
        dt_str = str(dt_str)
        if dt_str.endswith('Z'):
            dt_str = dt_str.replace('Z', '+00:00')
        # Handle format like "2024-11-06 15:17:41+00"
        if '+00' in dt_str and not '+00:' in dt_str:
            dt_str = dt_str.replace('+00', '+00:00')
        return datetime.fromisoformat(dt_str)
    except Exception as e:
        if DEBUG:
            print(f"Error parsing datetime '{dt_str}': {e}")
        return None


def fetch_7day_price_history(clob_token_id: str, reference_date: datetime, start_date: datetime = None) -> Dict[int, float]:
    """
    Fetch price history for 7 days before reference date using a single API call.
    Returns daily prices (one per day) for days 7 through 1 before reference date.

    Args:
        clob_token_id: The CLOB token ID for the market outcome
        reference_date: The reference date (earlier of closedTime and endDate)
        start_date: When the market was created (to avoid looking for data before it existed)

    Returns:
        Dictionary mapping days before (7, 6, 5, 4, 3, 2, 1) to prices
    """
    # Ensure we're working in UTC/GMT
    if reference_date.tzinfo is None:
        reference_date = reference_date.replace(tzinfo=timezone.utc)

    if start_date and start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)

    # Set bounds to capture 7 days of data at 00:00 GMT
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

            # Skip if this is before the market was created
            if start_date and target_time < start_date:
                continue

            # Find the price entry that matches this timestamp
            closest = None
            min_diff = float('inf')

            for entry in history:
                diff = abs(entry['t'] - target_ts)
                if diff < min_diff and diff < 7200:  # Within 2 hours
                    min_diff = diff
                    closest = entry

            # Fallback: if no close match, find the most recent price BEFORE the target
            if closest is None:
                for entry in sorted(history, key=lambda x: x['t'], reverse=True):
                    if entry['t'] <= target_ts:
                        closest = entry
                        break

            if closest:
                result[days_before] = closest['p']

        return result

    except requests.RequestException as e:
        if DEBUG:
            print(f"Error fetching price history for {clob_token_id}: {e}")
        return {}


def get_reference_date(row) -> Optional[datetime]:
    """Get the earlier of closedTime and endDate as the reference date."""
    end_date = parse_datetime(row.get('endDate'))
    closed_time = parse_datetime(row.get('closedTime'))

    if end_date is None:
        return closed_time
    if closed_time is None:
        return end_date
    return min(end_date, closed_time)


def get_clob_id(clob_token_ids_str: str) -> Optional[str]:
    """Extract the first CLOB token ID from the JSON string."""
    if not clob_token_ids_str or pd.isna(clob_token_ids_str):
        return None
    try:
        clob_ids = json.loads(clob_token_ids_str)
        return clob_ids[0] if clob_ids else None
    except:
        return None


def get_outcome_result(outcome_prices_str: str) -> Optional[bool]:
    """
    Determine if 'Yes' outcome won.
    Returns True if Yes won, False if No won, None if undetermined.
    """
    if not outcome_prices_str or pd.isna(outcome_prices_str):
        return None
    try:
        prices = json.loads(outcome_prices_str)
        float_prices = [float(p) for p in prices]

        # Check if definitively resolved
        if float_prices[0] >= 0.99:
            return True  # Yes won
        elif float_prices[1] >= 0.99:
            return False  # No won
        return None
    except:
        return None


def calculate_correctness(probability: float, yes_won: bool, side: str) -> Optional[bool]:
    """
    Calculate if the market prediction was correct at a given probability.

    Args:
        probability: The probability of 'Yes' at that time
        yes_won: Whether 'Yes' outcome won
        side: 'R' or 'D' - which party 'Yes' represents

    Returns:
        True if market correctly predicted, False otherwise, None if can't determine
    """
    if probability is None or yes_won is None or pd.isna(probability):
        return None

    # Market predicted Yes if probability > 0.5
    market_predicted_yes = probability > 0.5

    # Correct if prediction matches outcome
    return market_predicted_yes == yes_won


def main():
    print("=" * 60)
    print("Processing Elections Data")
    print("=" * 60)

    # Load data
    input_path = "all_elections_labeled.csv"
    df = pd.read_csv(input_path)
    print(f"Loaded {len(df)} rows from {input_path}")

    # Deduplicate by id
    original_count = len(df)
    df = df.drop_duplicates(subset=['id'], keep='first').reset_index(drop=True)
    print(f"After deduplication: {len(df)} rows ({original_count - len(df)} duplicates removed)")

    # Extract CLOB IDs
    df['clobID'] = df['clobTokenIds'].apply(get_clob_id)

    # Get outcome results
    df['yes_won'] = df['outcomePrices'].apply(get_outcome_result)

    # Initialize probability columns
    for days in range(7, 0, -1):
        df[f'probability{days}d'] = None

    # Fetch price history for each market
    print("\nFetching 7-day price history...")
    for idx, row in tqdm(df.iterrows(), total=len(df), desc="Fetching prices"):
        clob_id = row['clobID']
        if not clob_id:
            continue

        reference_date = get_reference_date(row)
        start_date = parse_datetime(row.get('startDate'))

        if reference_date is None:
            continue

        prices = fetch_7day_price_history(clob_id, reference_date, start_date)

        for days_before, price in prices.items():
            df.at[idx, f'probability{days_before}d'] = price

        # Rate limiting
        time.sleep(0.1)

    # Calculate correctness columns
    print("\nCalculating correctness...")

    def calc_correct_at(row, days):
        prob = row.get(f'probability{days}d')
        yes_won = row.get('yes_won')
        side = row.get('side')
        return calculate_correctness(prob, yes_won, side)

    df['correct_at_7d'] = df.apply(lambda row: calc_correct_at(row, 7), axis=1)
    df['correct_at_1d'] = df.apply(lambda row: calc_correct_at(row, 1), axis=1)

    # Clean up temporary columns
    df = df.drop(columns=['clobID', 'yes_won'], errors='ignore')

    # Save results
    output_path = "all_elections_processed.csv"
    df.to_csv(output_path, index=False)

    print("\n" + "=" * 60)
    print(f"Saved {len(df)} markets to {output_path}")
    print("=" * 60)

    # Print summary statistics
    print("\nSummary:")
    print(f"  Total markets: {len(df)}")

    prob_7d_count = df['probability7d'].notna().sum()
    prob_1d_count = df['probability1d'].notna().sum()
    print(f"  Markets with 7d price: {prob_7d_count}")
    print(f"  Markets with 1d price: {prob_1d_count}")

    correct_7d = df['correct_at_7d'].sum() if df['correct_at_7d'].notna().any() else 0
    total_7d = df['correct_at_7d'].notna().sum()
    correct_1d = df['correct_at_1d'].sum() if df['correct_at_1d'].notna().any() else 0
    total_1d = df['correct_at_1d'].notna().sum()

    if total_7d > 0:
        print(f"  Correct at 7d: {correct_7d}/{total_7d} ({100*correct_7d/total_7d:.1f}%)")
    if total_1d > 0:
        print(f"  Correct at 1d: {correct_1d}/{total_1d} ({100*correct_1d/total_1d:.1f}%)")

    # Breakdown by side
    for side in ['R', 'D']:
        side_df = df[df['side'] == side]
        if len(side_df) > 0:
            correct_7d_side = side_df['correct_at_7d'].sum() if side_df['correct_at_7d'].notna().any() else 0
            total_7d_side = side_df['correct_at_7d'].notna().sum()
            correct_1d_side = side_df['correct_at_1d'].sum() if side_df['correct_at_1d'].notna().any() else 0
            total_1d_side = side_df['correct_at_1d'].notna().sum()

            print(f"\n  Side {side}:")
            print(f"    Markets: {len(side_df)}")
            if total_7d_side > 0:
                print(f"    Correct at 7d: {correct_7d_side}/{total_7d_side} ({100*correct_7d_side/total_7d_side:.1f}%)")
            if total_1d_side > 0:
                print(f"    Correct at 1d: {correct_1d_side}/{total_1d_side} ({100*correct_1d_side/total_1d_side:.1f}%)")


if __name__ == "__main__":
    main()
