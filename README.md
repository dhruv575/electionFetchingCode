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

## Output Files

| File | Description |
|------|-------------|
| `*_markets.csv` | Raw market data from Polymarket API |
| `*_labeled.csv` | Markets with manual D/R labels |
| `all_elections_labeled.csv` | Combined labeled markets |
| `all_elections_processed.csv` | Markets with 7-day price history |
| `collated_elections.csv` | Final paired dataset for analysis |

## API Reference

- **Gamma API** (market metadata): `https://gamma-api.polymarket.com/markets`
- **CLOB API** (price history): `https://clob.polymarket.com/prices-history`

## Rate Limiting

The scripts include built-in rate limiting (0.1-0.3s delays between requests). If you encounter rate limit errors, increase the `time.sleep()` values.
