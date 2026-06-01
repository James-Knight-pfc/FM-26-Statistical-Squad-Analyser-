import pandas as pd
import numpy as np
import re
from pathlib import Path
 
DEFAULT_CSV      = "player_export.csv"
WEIGHTINGS_XLSX  = "Stat_Weightings.xlsx"
MIN_MINS_PCT     = 0.05   # player must have played >5% of squad's max minutes
 
 
# ── Load data ─────────────────────────────────────────────────────────────────
def load_data(csv_file: str) -> pd.DataFrame:
    path = Path(csv_file)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path.resolve()}")
    return pd.read_csv(path, sep=';')
 
 
def load_weightings(xlsx_file: str) -> dict[str, dict[str, float]]:
    """Read the four weighting columns from the Excel sheet.
    Returns a dict: {'Defense': {stat: weight, ...}, 'Possession': ..., ...}
    Negative weights are preserved (used to penalise stats like Poss Lost/90).
    """
    path = Path(xlsx_file)
    if not path.exists():
        raise FileNotFoundError(f"Weightings file not found: {path.resolve()}")
 
    df = pd.read_excel(path)
 
    # Column layout: stat | Defense | (gap) | (gap) | Possession | (gap) | (gap) | (gap) | Attacking | (gap) | (gap) | Pressing
    col_map = {
        'Defense':    (df.columns[0], df.columns[1]),
        'Possession': (df.columns[4], df.columns[5]),
        'Attacking':  (df.columns[8], df.columns[9]),
        'Pressing':   (df.columns[11], df.columns[12]),
    }
 
    result = {}
    for category, (stat_col, weight_col) in col_map.items():
        weights = {}
        for _, row in df.iterrows():
            stat   = str(row[stat_col]).strip()
            weight = row[weight_col]
            if stat and stat != 'nan' and pd.notna(weight) and weight != 0:
                weights[stat] = float(weight)
        result[category] = weights
 
    return result
 
 
# ── Data cleaning ─────────────────────────────────────────────────────────────
def parse_apps(val) -> int:
    s = str(val).strip()
    if '(' in s:
        left  = s.split('(')[0].strip()
        right = s.split('(')[1].replace(')', '').strip()
        return (int(left) if left.isdigit() else 0) + (int(right) if right.isdigit() else 0)
    try:
        return int(s)
    except ValueError:
        return 0
 
 
def clean_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip()
 
    # Strip % signs from percentage columns
    pct_cols = ['Pas %', 'Conv %', 'Shot %', 'OP-Cr %', 'Tck R', 'Hdr %']
    for col in pct_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace('%', '').str.strip(),
                errors='coerce'
            ).fillna(0)
 
    # Appearances → Total Mins
    apps_col = next(
        (c for c in df.columns if c.strip().lower() in ('appearances', 'apps', 'ap')), None
    )
    if apps_col is None:
        print("Available columns:", df.columns.tolist())
        raise KeyError("Could not find Appearances column")
 
    df['Total Apps'] = df[apps_col].apply(parse_apps)
    df['Mins/Gm']    = pd.to_numeric(df['Mins/Gm'], errors='coerce').fillna(0)
    df['Total Mins'] = df['Mins/Gm'] * df['Total Apps']
 
    # Minutes filter
    max_mins      = df['Total Mins'].max()
    min_threshold = max_mins * MIN_MINS_PCT
    df = df[df['Total Mins'] >= min_threshold].copy()
    df = df[df['Rating'].astype(str).str.strip() != '-'].copy()
 
    # Coerce all stat columns to numeric
    stat_cols = [
        'Ps C/90', 'Pas %', 'Goals', 'xG', 'ShT/90', 'Conv %', 'Shot %',
        'Asts/90', 'Pr passes/90', 'KP/90', 'OP-KP/90', 'Ch C/90',
        'Drb/90', 'Dist/90', 'Sprints/90',
        'Pres C/90', 'Pres A/90', 'Tck/90', 'K Tck/90',
        'Blk/90', 'Hdrs W/90', 'Hdr %',
        'Int/90', 'Poss Won/90', 'Poss Lost/90',
        'Clr/90', 'Shts Blckd/90', 'Ps A/90',
    ]
    for col in stat_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
 
    # Derived stats
    df['xG/90'] = (df['xG'] / (df['Total Mins'] / 90)).fillna(0)
 
    df['Rating'] = pd.to_numeric(df['Rating'], errors='coerce')
 
    return df, min_threshold, max_mins
 
 
# ── Scoring ───────────────────────────────────────────────────────────────────
def pct_score(series: pd.Series) -> pd.Series:
    """Scale within squad, 0–10. Best in squad = 10, worst = 0."""
    min_val = series.min()
    max_val = series.max()
    if max_val == min_val:
        return pd.Series(5.0, index=series.index)
    return (series - min_val) / (max_val - min_val) * 10
 
 
def score_category(df: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """
    Compute a weighted percentile score for a category.
    Positive weights: higher stat = better.
    Negative weights: higher stat = worse (percentile is inverted).
    """
    score = pd.Series(0.0, index=df.index)
    for stat, weight in weights.items():
        if stat not in df.columns:
            continue
        if weight > 0:
            score += pct_score(df[stat]) * weight
        else:
            # Invert: more of this stat is bad, so flip the percentile
            score += (10 - pct_score(df[stat])) * abs(weight)
    return score
 
 
# ── Position classification ───────────────────────────────────────────────────
def classify_pos_group(row) -> str:
    picked = str(row.get('Picked', '')).strip()
    pos_str = picked if (picked and picked != '-' and not re.match(r'S\d+', picked)) \
              else str(row.get('Position', ''))
 
    p = pos_str.split(',')[0].strip().lower()
    if 'gk' in p:                          return 'GK'
    if 'wb' in p:                          return 'FB'
    if p.startswith('dm'):                 return 'MID'
    if p.startswith('d') and 'wb' not in p:
        m = re.search(r'\(([^)]+)\)', p)
        if m: return 'CB' if 'c' in m.group(1).lower() else 'FB'
        return 'CB'
    if 'am' in p or 'st' in p:            return 'FWD'
    if re.search(r'\bm\s*[\(/]\s*[rl]', p): return 'FWD'
    if 'm' in p:                           return 'MID'
    return 'OTHER'
 
 
# ── Overall: position-weighted blend of all four scores ───────────────────────
# Tuple order: (Defense, Pressing, Possession, Attacking)
overall_weights = {
    'CB':  (0.6, 0.1, 0.25, 0.05),
    'FB':  (0.35, 0.20, 0.35, 0.10),
    'MID': (0.20, 0.20, 0.35, 0.25),
    'FWD': (0.0, 0.15, 0.35, 0.50),
}
 
def weighted_overall(row) -> float:
    w = overall_weights.get(row['Group'], (0.25, 0.25, 0.25, 0.25))
    return round(
        row['Defensive'] * w[0] +
        row['Pressing']  * w[1] +
        row['Possession'] * w[2] +
        row['Attacking'] * w[3],
        2
    )
 
 
# ── Main ──────────────────────────────────────────────────────────────────────
df_raw          = load_data(DEFAULT_CSV)
weightings      = load_weightings(WEIGHTINGS_XLSX)
df, min_threshold, max_mins = clean_df(df_raw)
 
df['Defensive']  = score_category(df, weightings['Defense']).round(2)
df['Pressing']   = score_category(df, weightings['Pressing']).round(2)
df['Possession'] = score_category(df, weightings['Possession']).round(2)
df['Attacking']  = score_category(df, weightings['Attacking']).round(2)
 
df['Group']   = df.apply(classify_pos_group, axis=1)
df['Overall'] = df.apply(weighted_overall, axis=1)
 
# ── Print ─────────────────────────────────────────────────────────────────────
HEADER  = (f"  {'Player':<22} {'Position':<22} {'Mins':>5}  {'FM':>4}  "
           f"{'DEF':>5}  {'PRESS':>5}  {'POSS':>5}  {'ATT':>5}  {'OVR':>5}")
DIVIDER = f"  {'-'*90}"
 
print(f"\n{'='*94}")
print(f"  PLAYER RATINGS  —  min. {min_threshold:.0f} mins played  ({max_mins:.0f} max in squad)")
print(f"  Scores: 10 = best in squad, 5 = squad average")
print(f"{'='*94}")
 
for group, label in [
    ('CB',  '🔵  CENTRE BACKS'),
    ('FB',  '🟡  FULL BACKS'),
    ('MID', '🟢  MIDFIELDERS'),
    ('FWD', '🔴  FORWARDS & WINGERS'),
]:
    subset = df[df['Group'] == group].sort_values('Overall', ascending=False)
    if subset.empty:
        continue
    print(f"\n  {label}")
    print(HEADER)
    print(DIVIDER)
    for _, p in subset.iterrows():
        fm_str = f"{p['Rating']:.2f}" if pd.notna(p['Rating']) else '  —  '
        print(
            f"  {p['Player']:<22} {str(p['Position'])[:22]:<22} {int(p['Total Mins']):>5}  "
            f"{fm_str:>4}  {p['Defensive']:>5.2f}  {p['Pressing']:>5.2f}  "
            f"{p['Possession']:>5.2f}  {p['Attacking']:>5.2f}  {p['Overall']:>5.2f}"
        )
 
print(f"\n{'='*94}\n")
 