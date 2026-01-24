# Election Market Data Collection Pipeline

This repository contains scripts to collect and process US election prediction market data from Polymarket, ultimately producing a collated dataset that pairs Democrat and Republican markets for bias analysis.

## Prerequisites

```bash
pip install pandas requests tqdm
```

## Pipeline Overview

```
Step 1: Fetch Markets    →    Step 2: Label D/R    →    Step 3: Process    →    Step 4: Collate
   (3 scripts)                  (manual)                (1 script)              (manual)
```

## Step 1: Fetch Election Markets

Run the three fetch scripts to collect closed election markets from Polymarket's Gamma API:

```bash
python fetch_us_elections.py      # US Elections (tag_id=1101)
python fetch_nov_elections.py     # November Elections (tag_id=102786)
python fetch_states_elections.py  # State Elections (tag_id=100164)
```

Each script:
- Fetches closed markets with the specified tag
- Excludes certain tags to avoid duplicates (e.g., states script excludes US and Nov election tags)
- Outputs a CSV with market metadata: `id`, `question`, `slug`, `outcomes`, `outcomePrices`, `volume`, `clobTokenIds`, etc.

**Outputs:**
- `us_elections_markets.csv`
- `nov_elections_markets.csv`
- `states_elections_markets.csv`

## Step 2: Label Markets (Manual)

For each market, manually add a `side` column indicating which party the "Yes" outcome favors:

| side | Meaning | Example Market |
|------|---------|----------------|
| `D`  | Democrat | "Will Kamala Harris win the 2024 US Presidential Election?" |
| `R`  | Republican | "Will Donald Trump win the 2024 US Presidential Election?" |

Save the labeled files as:
- `us_elections_labeled.csv`
- `nov_elections_labeled.csv`
- `states_elections_labeled.csv`

Then combine all labeled files into a single `all_elections_labeled.csv`:

```python
import pandas as pd

dfs = [
    pd.read_csv('us_elections_labeled.csv'),
    pd.read_csv('nov_elections_labeled.csv'),
    pd.read_csv('states_elections_labeled.csv')
]
combined = pd.concat(dfs, ignore_index=True)
combined.to_csv('all_elections_labeled.csv', index=False)
```

## Step 3: Process Elections Data

Run the processing script to fetch historical price data and calculate prediction correctness:

```bash
python process_elections.py
```

This script:
1. Deduplicates markets by ID
2. Fetches 7-day price history from Polymarket's CLOB API (daily prices at 00:00 GMT)
3. Adds probability columns: `probability7d`, `probability6d`, ..., `probability1d`
4. Calculates `correct_at_7d` and `correct_at_1d` (whether the market correctly predicted the winner)

**Input:** `all_elections_labeled.csv`
**Output:** `all_elections_processed.csv`

## Step 4: Collate D/R Market Pairs (Manual)

Create `collated_elections.csv` by pairing complementary Democrat and Republican markets that ask about the same election outcome.

### Collation Rules

1. **Paired markets** (`type=pair`): Match D and R markets about the same event
   - Example: "Will Kamala win?" (D) + "Will Trump win?" (R) → "Who will win the 2024 US Presidential Election?"

2. **Single markets** (`type=single`): Markets without a complementary pair
   - Example: "Senate control after 2024 election?" (only D market exists)

### Output Schema

The collated CSV normalizes everything to Democrat probability:

| Column | Description |
|--------|-------------|
| `name` | Descriptive name for the election event |
| `type` | `pair` or `single` |
| `combined_volume` | Sum of D and R market volumes |
| `d_prob_7d` ... `d_prob_1d` | Democrat win probability (7 days to 1 day before close) |
| `d_won` | `TRUE` if Democrat won, `FALSE` if Republican won |
| `d_market_*` | All columns from the D-side market |
| `r_market_*` | All columns from the R-side market (empty for `single` type) |

### Probability Calculation for Pairs

For paired markets, calculate `d_prob_*` as the average:

```
d_prob_Xd = (d_market_probabilityXd + (1 - r_market_probabilityXd)) / 2
```

This averages the D market's "Yes" probability with the R market's implied "No" probability.

---

## Alternative: Fetch Senate Elections from Event URLs

For Senate elections (and other events organized as Polymarket "events" rather than individual markets), use the event-based fetching approach.

### Step 1: Create Event URL List

Create `senate.txt` with one Polymarket event URL per line:

```
https://polymarket.com/event/washington-us-senate-election-winner
https://polymarket.com/event/texas-us-senate-election-winner
https://polymarket.com/event/maryland-us-senate-election-winner
...
```

### Step 2: Fetch Events

Run the fetch script to retrieve event data and identify D/R submarkets:

```bash
python fetch_senate_events.py
```

This script:
1. Extracts the event slug from each URL
2. Calls the Gamma API events endpoint: `https://gamma-api.polymarket.com/events?slug={slug}`
3. Identifies Democrat and Republican markets by searching for "democrat"/"republican" in the market slug
4. Saves raw event data to `senate_events_raw.json`

**Input:** `senate.txt`
**Output:** `senate_events_raw.json`

### Step 3: Create Collated CSV

Run the collation script to fetch price histories and create the final CSV:

```bash
python create_senate_collated.py
```

This script:
1. Loads events from `senate_events_raw.json`
2. Fetches 7-day price history for each D and R market
3. Calculates combined `d_prob_*` values using the averaging formula
4. Determines winner based on outcome prices
5. Creates `senate_collated.csv` in the same format as `collated_elections.csv`

**Input:** `senate_events_raw.json`
**Output:** `senate_collated.csv`

### Naming Convention

Senate election names follow the pattern:
```
Who will win {State} in the US Senate Election?
```

Examples:
- "Who will win Washington in the US Senate Election?"
- "Who will win Texas in the US Senate Election?"

---

## Output Files

| File | Description |
|------|-------------|
| `*_markets.csv` | Raw market data from Polymarket API |
| `*_labeled.csv` | Markets with manual D/R labels |
| `all_elections_labeled.csv` | Combined labeled markets |
| `all_elections_processed.csv` | Markets with 7-day price history |
| `collated_elections.csv` | Final paired dataset for analysis (80 markets) |
| `senate.txt` | List of Senate election event URLs |
| `senate_events_raw.json` | Raw event data from Gamma API |
| `senate_collated.csv` | Senate elections in collated format |

## API Reference

- **Gamma API** (market metadata): `https://gamma-api.polymarket.com/markets`
- **Gamma API** (event data): `https://gamma-api.polymarket.com/events?slug={slug}`
- **CLOB API** (price history): `https://clob.polymarket.com/prices-history`

## Rate Limiting

The scripts include built-in rate limiting (0.1-0.3s delays between requests). If you encounter rate limit errors, increase the `time.sleep()` values.

## Current Dataset

The `collated_elections.csv` contains 80 markets:
- 77 paired markets (both D and R)
- 3 single markets (D only)
- 32 Democrat wins, 48 Republican wins
- Total volume: ~$3.2B
