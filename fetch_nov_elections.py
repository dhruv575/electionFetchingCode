"""
Fetch November Elections markets from Polymarket Gamma API.
Filters by tag_id=102786, excludes tag ids 264 and 189.
Saves results to CSV.
"""

import requests
import pandas as pd
import json
import time
from typing import List, Dict

# Tags to exclude by ID
EXCLUDED_TAG_IDS = {264, 189}

def fetch_nov_elections_markets(limit: int = 250) -> List[Dict]:
    """
    Fetch closed November Elections markets from Polymarket Gamma API.

    Args:
        limit: Maximum number of markets to fetch per request

    Returns:
        List of market dictionaries
    """
    all_markets = []
    offset = 0

    while True:
        url = (
            f"https://gamma-api.polymarket.com/markets?"
            f"tag_id=102786"
            f"&include_tag=true"
            f"&closed=true"
            f"&ascending=true"
            f"&limit={limit}"
            f"&offset={offset}"
        )

        print(f"Fetching markets with offset={offset}...")

        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            markets = response.json()

            if not markets:
                print(f"No more markets found at offset {offset}")
                break

            print(f"  Retrieved {len(markets)} markets")
            all_markets.extend(markets)
            offset += limit

            # Rate limiting
            time.sleep(0.3)

        except requests.RequestException as e:
            print(f"Error fetching markets: {e}")
            break

    print(f"\nTotal markets fetched: {len(all_markets)}")
    return all_markets


def filter_by_excluded_tags(markets: List[Dict]) -> List[Dict]:
    """
    Filter out markets that have any of the excluded tag IDs.

    Args:
        markets: List of market dictionaries

    Returns:
        Filtered list of markets
    """
    filtered = []

    for market in markets:
        tags = market.get('tags', [])
        tag_ids = set()

        for tag in tags:
            if isinstance(tag, dict):
                tag_id = tag.get('id')
                if tag_id is not None:
                    try:
                        tag_ids.add(int(tag_id))
                    except (ValueError, TypeError):
                        pass

        # Check if any excluded tag is present
        if not tag_ids.intersection(EXCLUDED_TAG_IDS):
            filtered.append(market)

    removed = len(markets) - len(filtered)
    print(f"Filtered out {removed} markets with excluded tag IDs {EXCLUDED_TAG_IDS}")
    print(f"Remaining markets: {len(filtered)}")

    return filtered


def extract_tag_info(tags: List) -> Dict:
    """Extract tag IDs and labels from tags list."""
    tag_ids = []
    tag_labels = []

    for tag in tags:
        if isinstance(tag, dict):
            tag_id = tag.get('id')
            tag_label = tag.get('label', '')
            if tag_id is not None:
                tag_ids.append(str(tag_id))
                tag_labels.append(tag_label)

    return {
        'tag_ids': tag_ids,
        'tag_labels': tag_labels
    }


def markets_to_dataframe(markets: List[Dict]) -> pd.DataFrame:
    """
    Convert list of market dictionaries to a pandas DataFrame.

    Args:
        markets: List of market dictionaries

    Returns:
        DataFrame with market information
    """
    records = []

    for market in markets:
        tags = market.get('tags', [])
        tag_info = extract_tag_info(tags)

        # Parse outcomes and outcome prices
        outcomes = market.get('outcomes', [])
        outcome_prices = market.get('outcomePrices', [])

        # Try to parse JSON strings if needed
        if isinstance(outcomes, str):
            try:
                outcomes = json.loads(outcomes)
            except:
                outcomes = []

        if isinstance(outcome_prices, str):
            try:
                outcome_prices = json.loads(outcome_prices)
            except:
                outcome_prices = []

        records.append({
            'id': market.get('id'),
            'question': market.get('question'),
            'slug': market.get('slug'),
            'description': market.get('description', ''),
            'outcomes': json.dumps(outcomes) if outcomes else '[]',
            'outcomePrices': json.dumps(outcome_prices) if outcome_prices else '[]',
            'volume': market.get('volumeNum', 0),
            'liquidity': market.get('liquidityNum', 0),
            'startDate': market.get('startDate'),
            'endDate': market.get('endDate'),
            'closedTime': market.get('closedTime'),
            'resolutionSource': market.get('resolutionSource', ''),
            'tag_ids': json.dumps(tag_info['tag_ids']),
            'tag_labels': json.dumps(tag_info['tag_labels']),
            'clobTokenIds': market.get('clobTokenIds', '[]'),
        })

    return pd.DataFrame(records)


def main():
    print("=" * 60)
    print("Fetching November Elections Markets from Polymarket")
    print("=" * 60)

    # Fetch markets
    markets = fetch_nov_elections_markets(limit=250)

    if not markets:
        print("No markets found!")
        return

    # Filter out excluded tags
    filtered_markets = filter_by_excluded_tags(markets)

    if not filtered_markets:
        print("No markets remaining after filtering!")
        return

    # Convert to DataFrame
    df = markets_to_dataframe(filtered_markets)

    # Sort by volume descending
    df = df.sort_values('volume', ascending=False).reset_index(drop=True)

    # Save to CSV
    output_path = "nov_elections_markets.csv"
    df.to_csv(output_path, index=False)

    print("\n" + "=" * 60)
    print(f"Saved {len(df)} markets to {output_path}")
    print("=" * 60)

    # Print summary
    print(f"\nSummary:")
    print(f"  Total markets: {len(df)}")
    print(f"  Total volume: ${df['volume'].sum():,.2f}")
    print(f"\nSample markets:")
    for _, row in df.head(5).iterrows():
        print(f"  - {row['question'][:70]}...")


if __name__ == "__main__":
    main()
