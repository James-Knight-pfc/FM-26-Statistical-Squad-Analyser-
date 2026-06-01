# Football Manager Squad Analysis

A Python script that rates your Football Manager squad using real match statistics exported from the game, giving each player a score across four categories: Defending, Pressing, Possession, and Attacking.

## How it works

Rather than using FM's built-in attribute ratings, this tool analyses actual in-game performance data — what players did on the pitch, not their potential. Each stat is scaled between 0 and 10 within your squad (best player in the squad for that stat = 10, worst = 0) and then weighted to produce four category scores. These are blended into a position-aware overall rating.

### Category weights (per position)

Tuple order: **(Defense, Pressing, Possession, Attacking)**

| Position | Defense | Pressing | Possession | Attacking |
|----------|---------|----------|------------|-----------|
| CB       | 0.60    | 0.10     | 0.25       | 0.05      |
| FB       | 0.35    | 0.20     | 0.35       | 0.10      |
| MID      | 0.20    | 0.20     | 0.35       | 0.25      |
| FWD      | 0.00    | 0.15     | 0.35       | 0.50      |

### Stat weightings

Individual stat weights for each category are loaded from `Stat_Weightings.xlsx`, so you can adjust them without touching the code. Key design choices:

- **Defense** — built around possession won, interceptions, and tackles rather than clearances
- **Pressing** — pressures completed and possession won, with weight given to pressures attempted to reward high-intensity teams
- **Possession** — pass accuracy is heavily weighted; a penalty is applied for possession lost
- **Attacking** — focused on xG per 90 (converted from the raw xG export) as the primary measure, supported by assists, chances created, and conversion rate

## Setup

### Requirements

```
pip install pandas numpy openpyxl
```

### Export your squad from FM26

> 📺 [How to print screen in Football Manager](https://www.youtube.com/watch?v=NugiVa5xpIY)

1. In FM26, load the `Stats.fmf` view file (included in this repo) — this sets up the exact columns the script expects
2. Follow the tutorial above to export your squad screen as a CSV
3. The exported file can be fed directly into the script — rename it to `player_export.csv` and place it in the same folder

### Files needed in the same folder

```
Squad_Stats_Analysis.py
Stat_Weightings.xlsx
player_export.csv
```

### Run

```bash
python Squad_Stats_Analysis.py
```

## Customising the weightings

Open `Stat_Weightings.xlsx` and edit the weighting values in any of the four category columns. Weights should sum to 1.0 per category (negative weights are supported — `Poss Lost/90` uses -0.15 as a penalty). Save the file, close it, and re-run the script.

## Notes

- Players must have played more than 5% of the squad's maximum minutes to be included — this filters out players with too small a sample size
- `xG/90` is computed from the raw `xG` export column divided by minutes played
- Goalkeepers are excluded from the outfield ratings
- Squad view required for upload included in the repository as stats.fmf

## Development

Built with assistance from [Claude](https://claude.ai) (Anthropic). The stat selection, weightings, position logic, and overall design decisions were made by the author — Claude was used as a coding and reasoning tool throughout the development process.

## Example Output
![Example Output](Example%20of%20Analysed%20Squad.png)
