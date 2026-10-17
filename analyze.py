#!/usr/bin/env python3
"""
analyze.py — Results Parser & Statistical Analyzer
====================================================
Reads all iperf3 JSON files from results/, parses key metrics, computes
Jain's Fairness Index for the fairness scenario, and outputs:
  - results/summary.csv  (machine-readable)
  - Markdown table to stdout

Metrics extracted per experiment:
  • avg_throughput_mbps   — mean bits_per_second over all intervals
  • end_throughput_mbps   — throughput from iperf3 'end' summary block
  • total_bytes_mb        — total bytes transferred
  • retransmissions       — total TCP retransmit count
  • jfi                   — Jain's Fairness Index (fairness scenario only)

Usage:
    python3 analyze.py [--results-dir results] [--output results/summary.csv]
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

RESULTS_DIR = Path('results')
OUTPUT_CSV   = RESULTS_DIR / 'summary.csv'

# Canonical scenario ordering for display
SCENARIO_ORDER = ['baseline', 'loss_1', 'loss_5', 'high_rtt',
                  'small_buffer', 'fairness']


# ---------------------------------------------------------------------------
# Jain's Fairness Index
# ---------------------------------------------------------------------------

def jains_fairness_index(throughputs: list[float]) -> float:
    """
    Compute Jain's Fairness Index.

    J(x) = (Σxᵢ)² / (n · Σxᵢ²)

    Returns a value in (0, 1].  1.0 = perfectly fair.
    Returns NaN for empty or all-zero inputs.
    """
    filtered = [x for x in throughputs if x > 0]
    n = len(filtered)
    if n == 0:
        return float('nan')
    sum_x  = sum(filtered)
    sum_x2 = sum(x ** 2 for x in filtered)
    if sum_x2 == 0:
        return float('nan')
    return (sum_x ** 2) / (n * sum_x2)


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------

def parse_iperf3_json(filepath: Path) -> dict | None:
    """
    Parse a single iperf3 JSON file and return a flat metrics dict.

    Returns None if the file is an error stub or cannot be parsed.
    """
    try:
        with open(filepath) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [WARN] Cannot read {filepath.name}: {e}", file=sys.stderr)
        return None

    # Skip error stubs created by run_tests.py
    if data.get('_error') or 'error' in data and '_meta' in data and len(data) == 3:
        print(f"  [SKIP] {filepath.name} is an error stub.", file=sys.stderr)
        return None

    # ── Extract metadata ────────────────────────────────────────────────
    meta     = data.get('_meta', {})
    scenario = meta.get('scenario', _infer_scenario(filepath.stem))
    algo     = meta.get('algorithm', _infer_algo(filepath.stem))

    # Special case: fairness_summary.json
    if filepath.stem == 'fairness_summary':
        return _parse_fairness_summary(data)

    # ── Parse iperf3 'end' block ────────────────────────────────────────
    end = data.get('end', {})
    sum_sent = end.get('sum_sent', {})

    end_bps   = sum_sent.get('bits_per_second', 0.0)
    end_bytes  = sum_sent.get('bytes', 0)
    retransmits = sum_sent.get('retransmits', 0)

    # ── Parse intervals for average throughput ──────────────────────────
    intervals = data.get('intervals', [])
    interval_bps = []
    for iv in intervals:
        streams = iv.get('streams', [])
        if not streams:
            # Try 'sum' key (iperf3 -P > 1 mode)
            s = iv.get('sum', {})
            bps = s.get('bits_per_second', 0)
        else:
            # Sum across parallel streams
            bps = sum(s.get('bits_per_second', 0) for s in streams)
        if bps > 0:
            interval_bps.append(bps)

    avg_bps = sum(interval_bps) / len(interval_bps) if interval_bps else end_bps

    return {
        'scenario':            scenario,
        'algorithm':           algo,
        'avg_throughput_mbps': round(avg_bps / 1e6, 4),
        'end_throughput_mbps': round(end_bps / 1e6, 4),
        'total_bytes_mb':      round(end_bytes / 1e6, 4),
        'retransmissions':     int(retransmits),
        'jfi':                 float('nan'),   # filled in fairness post-processing
        'num_intervals':       len(interval_bps),
    }


def _parse_fairness_summary(data: dict) -> dict:
    """Parse the special fairness_summary.json file."""
    return {
        'scenario':            'fairness',
        'algorithm':           'cubic+bbr',
        'avg_throughput_mbps': round(
            (data.get('cubic_throughput_bps', 0) +
             data.get('bbr_throughput_bps', 0)) / 2 / 1e6, 4),
        'end_throughput_mbps': float('nan'),
        'total_bytes_mb':      float('nan'),
        'retransmissions':     0,
        'jfi':                 round(data.get('jains_fairness_index', float('nan')), 6),
        'num_intervals':       0,
    }


def _infer_scenario(stem: str) -> str:
    """Infer scenario from filename stem when _meta is missing."""
    for s in SCENARIO_ORDER:
        if s in stem:
            return s
    return 'unknown'


def _infer_algo(stem: str) -> str:
    """Infer algorithm from filename stem when _meta is missing."""
    for a in ['reno', 'cubic', 'bbr']:
        if a in stem:
            return a
    return 'unknown'


# ---------------------------------------------------------------------------
# Main analysis pipeline
# ---------------------------------------------------------------------------

def load_results(results_dir: Path) -> pd.DataFrame:
    """Load all JSON result files and return a combined DataFrame."""
    rows = []
    json_files = sorted(results_dir.glob('*.json'))
    if not json_files:
        print(f"No JSON files found in {results_dir.resolve()}", file=sys.stderr)
        return pd.DataFrame()

    print(f"\nLoading {len(json_files)} result file(s) from {results_dir.resolve()}/")
    for jf in json_files:
        print(f"  → {jf.name}")
        parsed = parse_iperf3_json(jf)
        if parsed is not None:
            rows.append(parsed)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    return df


def compute_fairness(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute and annotate Jain's Fairness Index for the fairness scenario.

    For each (scenario, algorithm) pair in the fairness scenario,
    groups by scenario and calculates JFI across all algorithm throughputs.
    """
    if df.empty:
        return df

    # Individual fairness rows (cubic_fairness.json, bbr_fairness.json)
    fair_mask = df['scenario'] == 'fairness'
    fair_df   = df[fair_mask & (df['algorithm'] != 'cubic+bbr')]

    if not fair_df.empty:
        throughputs = fair_df['avg_throughput_mbps'].tolist()
        jfi = jains_fairness_index(throughputs)
        # Annotate each fairness row with JFI
        df.loc[fair_mask & (df['algorithm'] != 'cubic+bbr'), 'jfi'] = round(jfi, 6)

    return df


def format_markdown_table(df: pd.DataFrame) -> str:
    """Render the summary DataFrame as a Markdown table."""
    if df.empty:
        return "*(no data)*"

    # Select display columns
    display_cols = [
        'scenario', 'algorithm',
        'avg_throughput_mbps', 'end_throughput_mbps',
        'total_bytes_mb', 'retransmissions', 'jfi'
    ]
    # Only keep columns that exist
    display_cols = [c for c in display_cols if c in df.columns]
    display_df = df[display_cols].copy()

    # Sort by scenario order then algorithm
    scenario_cat = pd.Categorical(
        display_df['scenario'],
        categories=SCENARIO_ORDER + ['unknown'],
        ordered=True
    )
    display_df = display_df.assign(scenario_cat=scenario_cat)
    display_df = display_df.sort_values(['scenario_cat', 'algorithm'])
    display_df = display_df.drop(columns=['scenario_cat'])

    # Rename columns for display
    display_df.columns = [c.replace('_', ' ').title() for c in display_df.columns]

    # Build Markdown
    header  = '| ' + ' | '.join(display_df.columns) + ' |'
    divider = '| ' + ' | '.join(['---'] * len(display_df.columns)) + ' |'
    rows_md = []
    for _, row in display_df.iterrows():
        cells = []
        for v in row:
            if isinstance(v, float):
                cells.append('—' if pd.isna(v) else f'{v:.4f}')
            else:
                cells.append(str(v))
        rows_md.append('| ' + ' | '.join(cells) + ' |')

    return '\n'.join([header, divider] + rows_md)


def format_ascii_table(df: pd.DataFrame) -> str:
    """Render the summary DataFrame as an ASCII box table."""
    if df.empty:
        return "(no data)"

    display_cols = [
        'scenario', 'algorithm',
        'avg_throughput_mbps', 'retransmissions', 'jfi'
    ]
    display_cols = [c for c in display_cols if c in df.columns]
    display_df = df[display_cols].copy()

    # Sort
    scenario_cat = pd.Categorical(
        display_df['scenario'],
        categories=SCENARIO_ORDER + ['unknown'],
        ordered=True
    )
    display_df = display_df.assign(sc=scenario_cat)
    display_df = display_df.sort_values(['sc', 'algorithm']).drop(columns=['sc'])

    col_headers = ['Scenario', 'Algorithm', 'Avg Mbps', 'Retransmits', "Jain's FI"]
    rows_str = []
    for _, row in display_df.iterrows():
        r = []
        for v in row:
            if isinstance(v, float):
                r.append('—' if pd.isna(v) else f'{v:.4f}')
            else:
                r.append(str(v))
        rows_str.append(r)

    # Compute column widths
    all_rows = [col_headers] + rows_str
    widths = [max(len(r[i]) for r in all_rows) for i in range(len(col_headers))]

    sep   = '+' + '+'.join('-' * (w + 2) for w in widths) + '+'
    def fmt_row(cells):
        return '|' + '|'.join(f' {c:{w}} ' for c, w in zip(cells, widths)) + '|'

    lines = [sep, fmt_row(col_headers), sep]
    for r in rows_str:
        lines.append(fmt_row(r))
    lines.append(sep)
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Analyze TCP benchmark results')
    parser.add_argument('--results-dir', type=Path, default=RESULTS_DIR,
                        help='Directory containing iperf3 JSON files')
    parser.add_argument('--output', type=Path, default=OUTPUT_CSV,
                        help='Path for output CSV file')
    args = parser.parse_args()

    results_dir = args.results_dir
    output_path = args.output

    if not results_dir.exists():
        sys.exit(f"ERROR: Results directory '{results_dir}' does not exist. "
                 f"Run run_tests.py first.")

    # ── Load ────────────────────────────────────────────────────────────────
    df = load_results(results_dir)
    if df.empty:
        sys.exit("ERROR: No parseable results found.")

    # ── Compute JFI ─────────────────────────────────────────────────────────
    df = compute_fairness(df)

    # ── Save CSV ─────────────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"\nSummary CSV saved: {output_path.resolve()}")

    # ── Print tables ─────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  TCP CONGESTION CONTROL BENCHMARK — RESULTS SUMMARY")
    print("=" * 70 + "\n")

    ascii_table = format_ascii_table(df)
    print(ascii_table)

    print("\n\n── Markdown Table ─────────────────────────────────────────────────")
    md_table = format_markdown_table(df)
    print(md_table)

    # ── Save Markdown report ─────────────────────────────────────────────────
    md_path = results_dir / 'summary_table.md'
    with open(md_path, 'w') as f:
        f.write("# TCP Congestion Control Benchmark — Results\n\n")
        f.write(md_table + '\n')
    print(f"\nMarkdown table saved: {md_path.resolve()}")

    # ── Key insights ─────────────────────────────────────────────────────────
    if not df.empty:
        print("\n── Key Insights ───────────────────────────────────────────────────")
        try:
            # Best performer per scenario
            numeric_df = df[df['avg_throughput_mbps'].notna() &
                            (df['algorithm'] != 'cubic+bbr')]
            if not numeric_df.empty:
                best = (numeric_df.groupby('scenario')['avg_throughput_mbps']
                        .idxmax())
                for sc, idx in best.items():
                    row = df.loc[idx]
                    print(f"  {sc:<15}: best = {row['algorithm']:<6} "
                          f"({row['avg_throughput_mbps']:.2f} Mbps)")
        except Exception:
            pass

        # Fairness
        fair_row = df[df['algorithm'] == 'cubic+bbr']
        if not fair_row.empty:
            jfi_val = fair_row['jfi'].iloc[0]
            if not pd.isna(jfi_val):
                label = ('near-perfect' if jfi_val > 0.95 else
                         'good'         if jfi_val > 0.8  else
                         'moderate'     if jfi_val > 0.6  else 'poor')
                print(f"  {'fairness':<15}: Jain's FI = {jfi_val:.4f} ({label})")

    print()


if __name__ == '__main__':
    main()
