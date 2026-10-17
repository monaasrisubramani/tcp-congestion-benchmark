#!/usr/bin/env python3
"""
plot_results.py — Matplotlib Visualization Generator
=====================================================
Reads results/summary.csv and raw iperf3 JSON files to produce:

  1. plots/throughput_timeseries_<scenario>.png
       Overlaid time-series lines for Reno, CUBIC, BBR per scenario.

  2. plots/throughput_bar_<scenario>.png
       Grouped bar chart comparing average throughput per algorithm.

  3. plots/throughput_bar_all.png
       Mega bar chart: all scenarios × all algorithms side by side.

  4. plots/retransmissions_bar.png
       Retransmission counts per algorithm × scenario.

  5. plots/fairness_jfi.png
       Bar chart of Jain's Fairness Index for the fairness scenario.

  6. plots/throughput_heatmap.png
       Heat-map: rows = algorithms, columns = scenarios.

Usage:
    python3 plot_results.py [--results-dir results] [--plots-dir plots]
"""

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')           # non-interactive backend (no display needed)
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Style constants
# ---------------------------------------------------------------------------

# Colour palette — distinct, publication-quality
ALGO_COLORS = {
    'reno':  '#E63946',   # vivid red
    'cubic': '#2196F3',   # material blue
    'bbr':   '#4CAF50',   # material green
}
DEFAULT_COLOR = '#9E9E9E'

SCENARIO_LABELS = {
    'baseline':     'Baseline\n(10 Mbps, 20ms)',
    'loss_1':       '1% Loss\n(10 Mbps, 20ms)',
    'loss_5':       '5% Loss\n(10 Mbps, 20ms)',
    'high_rtt':     'High RTT\n(10 Mbps, 100ms)',
    'small_buffer': 'Small Buffer\n(10 Mbps, 20ms, Q=10)',
}
SCENARIO_ORDER = ['baseline', 'loss_1', 'loss_5', 'high_rtt', 'small_buffer']

plt.rcParams.update({
    'font.family':       'DejaVu Sans',
    'font.size':         11,
    'axes.labelsize':    12,
    'axes.titlesize':    13,
    'axes.titleweight':  'bold',
    'axes.spines.top':   False,
    'axes.spines.right': False,
    'legend.framealpha': 0.85,
    'figure.dpi':        100,
})

DPI_SAVE = 300


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ensure_plots_dir(plots_dir: Path):
    plots_dir.mkdir(parents=True, exist_ok=True)


def _color(algo: str) -> str:
    return ALGO_COLORS.get(algo, DEFAULT_COLOR)


def load_interval_data(results_dir: Path) -> dict[str, dict[str, list]]:
    """
    Load per-second interval throughput data from raw JSON files.

    Returns
    -------
    dict: { scenario → { algo → [mbps_per_interval, ...] } }
    """
    data: dict[str, dict[str, list]] = {}
    for jf in sorted(results_dir.glob('*.json')):
        if 'fairness_summary' in jf.stem or 'ERROR' in jf.stem:
            continue
        try:
            with open(jf) as f:
                raw = json.load(f)
        except Exception:
            continue

        if raw.get('_error'):
            continue

        meta = raw.get('_meta', {})
        scenario = meta.get('scenario', _infer_field(jf.stem, 'scenario'))
        algo     = meta.get('algorithm', _infer_field(jf.stem, 'algo'))

        if scenario == 'fairness':
            continue   # fairness timeseries handled separately

        intervals = raw.get('intervals', [])
        ts = []
        for iv in intervals:
            streams = iv.get('streams', [])
            if streams:
                bps = sum(s.get('bits_per_second', 0) for s in streams)
            else:
                bps = iv.get('sum', {}).get('bits_per_second', 0)
            ts.append(bps / 1e6)

        if ts:
            data.setdefault(scenario, {})[algo] = ts

    return data


def load_fairness_interval_data(results_dir: Path) -> dict[str, list]:
    """Load fairness scenario interval data for cubic and bbr."""
    result = {}
    for algo in ['cubic', 'bbr']:
        jf = results_dir / f'{algo}_fairness.json'
        if not jf.exists():
            continue
        try:
            with open(jf) as f:
                raw = json.load(f)
        except Exception:
            continue
        if raw.get('_error'):
            continue
        intervals = raw.get('intervals', [])
        ts = []
        for iv in intervals:
            streams = iv.get('streams', [])
            if streams:
                bps = sum(s.get('bits_per_second', 0) for s in streams)
            else:
                bps = iv.get('sum', {}).get('bits_per_second', 0)
            ts.append(bps / 1e6)
        if ts:
            result[algo] = ts
    return result


def _infer_field(stem: str, field: str) -> str:
    if field == 'scenario':
        for s in SCENARIO_ORDER + ['fairness']:
            if s in stem:
                return s
        return 'unknown'
    if field == 'algo':
        for a in ['reno', 'cubic', 'bbr']:
            if a in stem:
                return a
        return 'unknown'
    return 'unknown'


# ---------------------------------------------------------------------------
# Plot 1 — Throughput time-series per scenario
# ---------------------------------------------------------------------------

def plot_timeseries(interval_data: dict, plots_dir: Path):
    """One overlaid line chart per scenario."""
    for scenario in SCENARIO_ORDER:
        algos_data = interval_data.get(scenario, {})
        if not algos_data:
            print(f"  [SKIP] No interval data for scenario: {scenario}")
            continue

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.set_facecolor('#f8f9fa')
        fig.patch.set_facecolor('white')

        for algo in ['reno', 'cubic', 'bbr']:
            ts = algos_data.get(algo)
            if ts is None:
                continue
            t = list(range(len(ts)))
            ax.plot(t, ts,
                    label=algo.upper(),
                    color=_color(algo),
                    linewidth=2,
                    alpha=0.9)
            # Shade area under curve lightly
            ax.fill_between(t, ts, alpha=0.08, color=_color(algo))

        ax.set_title(f'Throughput over Time — {SCENARIO_LABELS.get(scenario, scenario)}')
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('Throughput (Mbps)')
        ax.legend(loc='best')
        ax.grid(True, linestyle='--', alpha=0.5)
        ax.yaxis.set_minor_locator(mticker.AutoMinorLocator())
        ax.set_xlim(left=0)
        ax.set_ylim(bottom=0)

        out = plots_dir / f'throughput_timeseries_{scenario}.png'
        fig.tight_layout()
        fig.savefig(out, dpi=DPI_SAVE, bbox_inches='tight')
        plt.close(fig)
        print(f"  Saved: {out}")


# ---------------------------------------------------------------------------
# Plot 2 — Fairness scenario time-series
# ---------------------------------------------------------------------------

def plot_fairness_timeseries(results_dir: Path, plots_dir: Path):
    """Overlaid time-series for CUBIC and BBR in the fairness test."""
    fair_data = load_fairness_interval_data(results_dir)
    if not fair_data:
        print("  [SKIP] No fairness interval data found.")
        return

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.set_facecolor('#f8f9fa')
    fig.patch.set_facecolor('white')

    for algo, ts in fair_data.items():
        t = list(range(len(ts)))
        ax.plot(t, ts,
                label=f'{algo.upper()} (fairness test)',
                color=_color(algo),
                linewidth=2,
                alpha=0.9)
        ax.fill_between(t, ts, alpha=0.08, color=_color(algo))

    ax.set_title('Fairness Test — CUBIC vs BBR Throughput over Time')
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Throughput (Mbps)')
    ax.legend(loc='best')
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)

    out = plots_dir / 'throughput_timeseries_fairness.png'
    fig.tight_layout()
    fig.savefig(out, dpi=DPI_SAVE, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out}")


# ---------------------------------------------------------------------------
# Plot 3 — Average throughput bar charts (per scenario)
# ---------------------------------------------------------------------------

def plot_bar_per_scenario(df: pd.DataFrame, plots_dir: Path):
    """Grouped bar chart per scenario."""
    algos = [a for a in ['reno', 'cubic', 'bbr']
             if a in df['algorithm'].values]

    for scenario in SCENARIO_ORDER:
        sc_df = df[(df['scenario'] == scenario) &
                   (df['algorithm'].isin(algos))]
        if sc_df.empty:
            print(f"  [SKIP] No summary data for scenario: {scenario}")
            continue

        fig, ax = plt.subplots(figsize=(7, 5))
        ax.set_facecolor('#f8f9fa')
        fig.patch.set_facecolor('white')

        x = np.arange(len(algos))
        bars = []
        for i, algo in enumerate(algos):
            row = sc_df[sc_df['algorithm'] == algo]
            val = row['avg_throughput_mbps'].iloc[0] if not row.empty else 0
            b = ax.bar(x[i], val, width=0.5,
                       color=_color(algo), label=algo.upper(),
                       edgecolor='white', linewidth=1.2,
                       zorder=3)
            bars.append((b, val))
            # Value label on bar
            ax.text(x[i], val + 0.15, f'{val:.2f}', ha='center',
                    va='bottom', fontsize=10, fontweight='bold')

        ax.set_xticks(x)
        ax.set_xticklabels([a.upper() for a in algos])
        ax.set_title(f'Average Throughput — {SCENARIO_LABELS.get(scenario, scenario)}')
        ax.set_ylabel('Avg Throughput (Mbps)')
        ax.legend()
        ax.grid(True, axis='y', linestyle='--', alpha=0.5, zorder=0)
        ax.set_ylim(bottom=0)

        out = plots_dir / f'throughput_bar_{scenario}.png'
        fig.tight_layout()
        fig.savefig(out, dpi=DPI_SAVE, bbox_inches='tight')
        plt.close(fig)
        print(f"  Saved: {out}")


# ---------------------------------------------------------------------------
# Plot 4 — Mega grouped bar chart (all scenarios × all algorithms)
# ---------------------------------------------------------------------------

def plot_bar_all_scenarios(df: pd.DataFrame, plots_dir: Path):
    """Side-by-side grouped bars for all scenarios and algorithms."""
    algos = [a for a in ['reno', 'cubic', 'bbr']
             if a in df['algorithm'].values]
    scenarios = [s for s in SCENARIO_ORDER
                 if s in df['scenario'].values]

    if not scenarios or not algos:
        return

    n_sc   = len(scenarios)
    n_algo = len(algos)
    group_w = 0.8
    bar_w   = group_w / n_algo

    fig, ax = plt.subplots(figsize=(max(10, n_sc * 2), 6))
    ax.set_facecolor('#f8f9fa')
    fig.patch.set_facecolor('white')

    x = np.arange(n_sc)
    for j, algo in enumerate(algos):
        vals = []
        for sc in scenarios:
            row = df[(df['scenario'] == sc) & (df['algorithm'] == algo)]
            vals.append(row['avg_throughput_mbps'].iloc[0] if not row.empty else 0)

        offsets = x + (j - n_algo / 2 + 0.5) * bar_w
        ax.bar(offsets, vals, width=bar_w * 0.9,
               color=_color(algo), label=algo.upper(),
               edgecolor='white', linewidth=0.8, zorder=3)

    ax.set_xticks(x)
    sc_labels = [SCENARIO_LABELS.get(s, s) for s in scenarios]
    ax.set_xticklabels(sc_labels, fontsize=9)
    ax.set_title('Average Throughput — All Scenarios & Algorithms')
    ax.set_ylabel('Avg Throughput (Mbps)')
    ax.legend(title='Algorithm', loc='upper right')
    ax.grid(True, axis='y', linestyle='--', alpha=0.5, zorder=0)
    ax.set_ylim(bottom=0)

    out = plots_dir / 'throughput_bar_all.png'
    fig.tight_layout()
    fig.savefig(out, dpi=DPI_SAVE, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out}")


# ---------------------------------------------------------------------------
# Plot 5 — Retransmissions bar chart
# ---------------------------------------------------------------------------

def plot_retransmissions(df: pd.DataFrame, plots_dir: Path):
    """Grouped bar chart of retransmission counts."""
    algos = [a for a in ['reno', 'cubic', 'bbr']
             if a in df['algorithm'].values]
    scenarios = [s for s in SCENARIO_ORDER
                 if s in df['scenario'].values]

    if not scenarios or not algos:
        return

    n_sc   = len(scenarios)
    n_algo = len(algos)
    group_w = 0.8
    bar_w   = group_w / n_algo

    fig, ax = plt.subplots(figsize=(max(10, n_sc * 2), 5))
    ax.set_facecolor('#f8f9fa')
    fig.patch.set_facecolor('white')

    x = np.arange(n_sc)
    for j, algo in enumerate(algos):
        vals = []
        for sc in scenarios:
            row = df[(df['scenario'] == sc) & (df['algorithm'] == algo)]
            vals.append(int(row['retransmissions'].iloc[0]) if not row.empty else 0)

        offsets = x + (j - n_algo / 2 + 0.5) * bar_w
        ax.bar(offsets, vals, width=bar_w * 0.9,
               color=_color(algo), label=algo.upper(),
               edgecolor='white', linewidth=0.8, zorder=3)

    ax.set_xticks(x)
    sc_labels = [SCENARIO_LABELS.get(s, s) for s in scenarios]
    ax.set_xticklabels(sc_labels, fontsize=9)
    ax.set_title('TCP Retransmissions — All Scenarios & Algorithms')
    ax.set_ylabel('Retransmission Count')
    ax.legend(title='Algorithm', loc='upper right')
    ax.grid(True, axis='y', linestyle='--', alpha=0.5, zorder=0)
    ax.set_ylim(bottom=0)

    out = plots_dir / 'retransmissions_bar.png'
    fig.tight_layout()
    fig.savefig(out, dpi=DPI_SAVE, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out}")


# ---------------------------------------------------------------------------
# Plot 6 — Jain's Fairness Index bar chart
# ---------------------------------------------------------------------------

def plot_fairness_jfi(df: pd.DataFrame, results_dir: Path, plots_dir: Path):
    """Bar chart of Jain's FI for the fairness scenario."""

    # Try fairness_summary.json first
    summary_jfi = None
    fs_path = results_dir / 'fairness_summary.json'
    if fs_path.exists():
        try:
            with open(fs_path) as f:
                fs = json.load(f)
            summary_jfi = fs.get('jains_fairness_index', None)
        except Exception:
            pass

    # Fall back to DataFrame
    if summary_jfi is None:
        fs_row = df[df['algorithm'] == 'cubic+bbr']
        if not fs_row.empty:
            summary_jfi = fs_row['jfi'].iloc[0]

    if summary_jfi is None or (isinstance(summary_jfi, float) and
                                np.isnan(summary_jfi)):
        print("  [SKIP] No Jain's FI data found.")
        return

    # Also get individual per-algo JFI if available
    fair_algos = []
    fair_jfis  = []
    fair_rows = df[(df['scenario'] == 'fairness') & (df['algorithm'] != 'cubic+bbr')]
    if not fair_rows.empty:
        jfi_val = fair_rows['jfi'].dropna()
        if not jfi_val.empty:
            fair_algos = ['CUBIC vs BBR']
            fair_jfis  = [float(jfi_val.iloc[0])]
    else:
        fair_algos = ['CUBIC vs BBR']
        fair_jfis  = [float(summary_jfi)]

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.set_facecolor('#f8f9fa')
    fig.patch.set_facecolor('white')

    colors = ['#7B2D8B', '#FF9800'][:len(fair_algos)]
    bars = ax.bar(fair_algos, fair_jfis, color=colors,
                  width=0.4, edgecolor='white', linewidth=1.5, zorder=3)
    for bar, val in zip(bars, fair_jfis):
        ax.text(bar.get_x() + bar.get_width() / 2,
                val + 0.01,
                f'{val:.4f}', ha='center', va='bottom',
                fontweight='bold', fontsize=12)

    # Reference lines
    ax.axhline(1.0, color='green', linestyle='--', alpha=0.6, label='Perfect (1.0)')
    ax.axhline(0.9, color='orange', linestyle=':', alpha=0.5, label='Good (0.9)')

    ax.set_title("Jain's Fairness Index — CUBIC vs BBR Fairness Test")
    ax.set_ylabel("Jain's Fairness Index (J)")
    ax.set_ylim(0, 1.15)
    ax.legend(loc='lower right')
    ax.grid(True, axis='y', linestyle='--', alpha=0.5, zorder=0)

    out = plots_dir / 'fairness_jfi.png'
    fig.tight_layout()
    fig.savefig(out, dpi=DPI_SAVE, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out}")


# ---------------------------------------------------------------------------
# Plot 7 — Throughput heat-map
# ---------------------------------------------------------------------------

def plot_heatmap(df: pd.DataFrame, plots_dir: Path):
    """Heat-map: rows = algorithms, columns = scenarios."""
    algos = [a for a in ['reno', 'cubic', 'bbr']
             if a in df['algorithm'].values]
    scenarios = [s for s in SCENARIO_ORDER
                 if s in df['scenario'].values]

    if not scenarios or not algos:
        return

    matrix = np.zeros((len(algos), len(scenarios)))
    for i, algo in enumerate(algos):
        for j, sc in enumerate(scenarios):
            row = df[(df['scenario'] == sc) & (df['algorithm'] == algo)]
            matrix[i, j] = row['avg_throughput_mbps'].iloc[0] if not row.empty else 0

    fig, ax = plt.subplots(figsize=(max(8, len(scenarios) * 1.5), 4))
    im = ax.imshow(matrix, cmap='YlOrRd', aspect='auto', vmin=0)

    ax.set_xticks(range(len(scenarios)))
    ax.set_xticklabels([SCENARIO_LABELS.get(s, s) for s in scenarios], fontsize=8)
    ax.set_yticks(range(len(algos)))
    ax.set_yticklabels([a.upper() for a in algos])
    ax.set_title('Throughput Heatmap (Mbps) — Algorithm × Scenario')

    # Annotate cells
    for i in range(len(algos)):
        for j in range(len(scenarios)):
            val = matrix[i, j]
            color = 'white' if val > matrix.max() * 0.7 else 'black'
            ax.text(j, i, f'{val:.1f}', ha='center', va='center',
                    fontsize=10, fontweight='bold', color=color)

    fig.colorbar(im, ax=ax, label='Avg Throughput (Mbps)', shrink=0.8)
    fig.tight_layout()

    out = plots_dir / 'throughput_heatmap.png'
    fig.savefig(out, dpi=DPI_SAVE, bbox_inches='tight')
    plt.close(fig)
    print(f"  Saved: {out}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Generate benchmark plots')
    parser.add_argument('--results-dir', type=Path, default=Path('results'),
                        help='Directory containing results (default: results/)')
    parser.add_argument('--plots-dir', type=Path, default=Path('plots'),
                        help='Output directory for plots (default: plots/)')
    args = parser.parse_args()

    results_dir = args.results_dir
    plots_dir   = args.plots_dir

    csv_path = results_dir / 'summary.csv'
    if not csv_path.exists():
        sys.exit(f"ERROR: {csv_path} not found. Run analyze.py first.")

    ensure_plots_dir(plots_dir)

    # Load summary CSV
    df = pd.read_csv(csv_path)
    print(f"\nLoaded summary: {len(df)} rows from {csv_path}")

    # Load interval data from raw JSON
    print("\nLoading interval data for time-series plots...")
    interval_data = load_interval_data(results_dir)

    print("\nGenerating plots...")
    print("─" * 50)

    # 1. Time-series per scenario
    print("[1/7] Throughput time-series (per scenario)...")
    plot_timeseries(interval_data, plots_dir)

    # 2. Fairness time-series
    print("[2/7] Fairness time-series...")
    plot_fairness_timeseries(results_dir, plots_dir)

    # 3. Bar chart per scenario
    print("[3/7] Average throughput bar (per scenario)...")
    plot_bar_per_scenario(df, plots_dir)

    # 4. Mega bar chart (all scenarios)
    print("[4/7] Average throughput bar (all scenarios)...")
    plot_bar_all_scenarios(df, plots_dir)

    # 5. Retransmissions
    print("[5/7] Retransmissions bar chart...")
    plot_retransmissions(df, plots_dir)

    # 6. JFI
    print("[6/7] Jain's Fairness Index bar chart...")
    plot_fairness_jfi(df, results_dir, plots_dir)

    # 7. Heatmap
    print("[7/7] Throughput heatmap...")
    plot_heatmap(df, plots_dir)

    # Summary
    plot_files = list(plots_dir.glob('*.png'))
    print(f"\n{'─'*50}")
    print(f"✓ Generated {len(plot_files)} plot(s) in {plots_dir.resolve()}/")
    for pf in sorted(plot_files):
        print(f"  • {pf.name}")
    print()


if __name__ == '__main__':
    main()
