"""
backend/storage.py — Results Management & Telemetry Extraction
==============================================================
Manages both historical baseline benchmark results and live experiment runs.
Extracts per-second interval time-series and calculates summary statistics.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

RESULTS_DIR = Path('results')
LIVE_RESULTS_DIR = RESULTS_DIR / 'live_runs'

SCENARIOS_META = {
    'baseline': {
        'name': 'Baseline Reference',
        'bw': 10,
        'delay': '20ms',
        'loss': 0.0,
        'max_queue_size': 100,
        'description': 'Clean 10 Mbps bottleneck with 20ms delay and 100 pkt queue.'
    },
    'loss_1': {
        'name': '1% Packet Loss',
        'bw': 10,
        'delay': '20ms',
        'loss': 1.0,
        'max_queue_size': 100,
        'description': 'Simulates typical home Wi-Fi or light wireless interference.'
    },
    'loss_5': {
        'name': '5% Packet Loss',
        'bw': 10,
        'delay': '20ms',
        'loss': 5.0,
        'max_queue_size': 100,
        'description': 'Heavy wireless interference or congested cellular link.'
    },
    'high_rtt': {
        'name': 'High RTT (100ms)',
        'bw': 10,
        'delay': '100ms',
        'loss': 0.0,
        'max_queue_size': 100,
        'description': 'High Bandwidth-Delay Product (BDP) intercontinental or satellite path.'
    },
    'small_buffer': {
        'name': 'Small Buffer (10 pkts)',
        'bw': 10,
        'delay': '20ms',
        'loss': 0.0,
        'max_queue_size': 10,
        'description': 'Shallow buffer to evaluate bufferbloat resistance and tail-drops.'
    },
    'fairness': {
        'name': 'Fairness (CUBIC vs BBR)',
        'bw': 10,
        'delay': '20ms',
        'loss': 0.0,
        'max_queue_size': 100,
        'description': 'Simultaneous competition between CUBIC and BBR on shared bottleneck.'
    }
}


def ensure_storage_dirs():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    LIVE_RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def jains_fairness_index(throughputs: List[float]) -> float:
    """Calculate Jain's Fairness Index: J = (sum(x))^2 / (n * sum(x^2))"""
    valid = [x for x in throughputs if x > 0]
    n = len(valid)
    if n == 0:
        return 0.0
    sum_x = sum(valid)
    sum_x2 = sum(x ** 2 for x in valid)
    if sum_x2 == 0:
        return 0.0
    return round((sum_x ** 2) / (n * sum_x2), 6)


def parse_json_result(filepath: Path, source_type: str = 'historical') -> Optional[Dict[str, Any]]:
    """Parse raw iperf3 json file and return structured metadata and metrics."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return None

    if data.get('_error') or ('error' in data and len(data) <= 3):
        return None

    meta = data.get('_meta', {})
    stem = filepath.stem

    # Determine scenario and algo
    scenario = meta.get('scenario')
    if not scenario:
        for s in SCENARIOS_META.keys():
            if s in stem:
                scenario = s
                break
        if not scenario:
            scenario = 'custom'

    algo = meta.get('algorithm')
    if algo == 'all':
        return None  # Ignore legacy invalid runs where 'all' was recorded as an algorithm
    if not algo:
        for a in ['reno', 'cubic', 'bbr']:
            if a in stem:
                algo = a
                break
        if not algo:
            algo = 'unknown'

    # Telemetry
    end = data.get('end', {})
    sum_sent = end.get('sum_sent', {})
    sum_received = end.get('sum_received', {})
    end_bps = sum_sent.get('bits_per_second', 0.0)
    end_bytes = sum_sent.get('bytes', 0)
    retransmits = sum_sent.get('retransmits', 0)

    # Receiver goodput across bottleneck
    rx_bps = sum_received.get('bits_per_second', 0.0)
    rx_bytes = sum_received.get('bytes', 0)

    # Intervals
    intervals = data.get('intervals', [])
    interval_bps = []
    timeseries = []
    for idx, iv in enumerate(intervals):
        streams = iv.get('streams', [])
        if streams:
            bps = sum(s.get('bits_per_second', 0) for s in streams)
        else:
            bps = iv.get('sum', {}).get('bits_per_second', 0)
        mbps = round(bps / 1e6, 3)
        interval_bps.append(bps)
        timeseries.append({'second': idx + 1, 'mbps': mbps})

    avg_bps = (sum(interval_bps) / len(interval_bps)) if interval_bps else end_bps
    avg_mbps = round(avg_bps / 1e6, 3)
    end_mbps = round(end_bps / 1e6, 3)
    rx_mbps = round(rx_bps / 1e6, 3) if rx_bps > 0 else avg_mbps
    total_mb = round(end_bytes / 1e6, 3)
    rx_total_mb = round(rx_bytes / 1e6, 3) if rx_bytes > 0 else total_mb

    # Creation time
    mtime = os.path.getmtime(filepath)
    timestamp = meta.get('timestamp') or datetime.fromtimestamp(mtime).isoformat()

    return {
        'id': f"{source_type}_{filepath.stem}",
        'filename': filepath.name,
        'source': source_type,  # 'historical' or 'live'
        'scenario': scenario,
        'algorithm': algo,
        'avg_throughput_mbps': avg_mbps,
        'end_throughput_mbps': end_mbps,
        'sender_throughput_mbps': avg_mbps,
        'receiver_throughput_mbps': rx_mbps,
        'goodput_mbps': rx_mbps,
        'total_bytes_mb': total_mb,
        'rx_total_bytes_mb': rx_total_mb,
        'retransmissions': int(retransmits),
        'jfi': None,
        'timestamp': timestamp,
        'num_intervals': len(timeseries),
        'topo_params': meta.get('topo_kwargs', SCENARIOS_META.get(scenario, {})),
        'timeseries': timeseries
    }


def get_all_results() -> List[Dict[str, Any]]:
    """Scan both historical results and live runs, computing JFI where applicable."""
    ensure_storage_dirs()
    results = []

    # 1. Historical results
    for jf in sorted(RESULTS_DIR.glob('*.json')):
        if jf.name in ['fairness_summary.json'] or 'ERROR' in jf.name:
            continue
        item = parse_json_result(jf, source_type='historical')
        if item:
            results.append(item)

    # 2. Live run results
    for jf in sorted(LIVE_RESULTS_DIR.glob('*.json')):
        if 'ERROR' in jf.name or 'fairness_summary' in jf.name:
            continue
        item = parse_json_result(jf, source_type='live')
        if item:
            results.append(item)

    # 3. Handle Fairness JFI annotation
    # Check historical fairness summary
    fs_path = RESULTS_DIR / 'fairness_summary.json'
    historical_jfi = None
    if fs_path.exists():
        try:
            with open(fs_path, 'r', encoding='utf-8') as f:
                fs_data = json.load(f)
                historical_jfi = fs_data.get('jains_fairness_index')
        except Exception:
            pass

    for r in results:
        if r['scenario'] == 'fairness':
            if r['source'] == 'historical' and historical_jfi is not None:
                r['jfi'] = round(historical_jfi, 4)
            elif r['jfi'] is None:
                # Find counterpart flow in same run
                counterparts = [
                    x for x in results
                    if x['scenario'] == 'fairness' and x['source'] == r['source'] and x['id'] != r['id']
                ]
                if counterparts:
                    jfi = jains_fairness_index([r['avg_throughput_mbps'], counterparts[0]['avg_throughput_mbps']])
                    r['jfi'] = jfi
                    counterparts[0]['jfi'] = jfi

    return results


def get_timeseries_for_scenario(scenario: str, source: str = 'all') -> Dict[str, Any]:
    """
    Get aggregated timeseries data for all algorithms in a scenario.
    Returns:
      {
        scenario: str,
        algorithms: { 'reno': [...], 'cubic': [...], 'bbr': [...] },
        meta: {...}
      }
    """
    all_res = get_all_results()
    matching = [r for r in all_res if r['scenario'] == scenario and r['algorithm'] in ['reno', 'cubic', 'bbr']]
    if source != 'all':
        matching = [r for r in matching if r['source'] == source]

    # Sort matching by timestamp ascending so latest runs overwrite older runs for the same algorithm
    matching = sorted(matching, key=lambda x: str(x.get('timestamp', '')))

    algos_data = {}
    for item in matching:
        algo = item['algorithm']
        # When viewing 'all' or when multiple sources exist, distinguish historical vs live
        key = f"{algo} ({item['source']})" if (source == 'all' or any(
            x['algorithm'] == algo and x['source'] != item['source'] for x in matching
        )) else algo
        algos_data[key] = item['timeseries']

    # Max length across streams
    max_len = 0
    for ts in algos_data.values():
        if len(ts) > max_len:
            max_len = len(ts)

    # Format into unified table for charting
    unified = []
    for s in range(1, max_len + 1):
        point = {'second': s}
        for k, ts in algos_data.items():
            val = next((p['mbps'] for p in ts if p['second'] == s), None)
            point[k] = val
        unified.append(point)

    return {
        'scenario': scenario,
        'scenario_info': SCENARIOS_META.get(scenario, {'name': scenario.capitalize()}),
        'chart_data': unified,
        'algorithms_present': list(algos_data.keys()),
        'runs': matching
    }


def get_fairness_data() -> Dict[str, Any]:
    """Return historical and live fairness comparison data."""
    results = get_all_results()
    fair_results = [r for r in results if r['scenario'] == 'fairness']

    historical_cubic = next((r for r in fair_results if r['source'] == 'historical' and r['algorithm'] == 'cubic'), None)
    historical_bbr = next((r for r in fair_results if r['source'] == 'historical' and r['algorithm'] == 'bbr'), None)
    live_cubic = next((r for r in fair_results if r['source'] == 'live' and r['algorithm'] == 'cubic'), None)
    live_bbr = next((r for r in fair_results if r['source'] == 'live' and r['algorithm'] == 'bbr'), None)

    hist_jfi = None
    if historical_cubic and historical_bbr:
        hist_jfi = jains_fairness_index([historical_cubic['avg_throughput_mbps'], historical_bbr['avg_throughput_mbps']])

    live_jfi = None
    if live_cubic and live_bbr:
        live_jfi = jains_fairness_index([live_cubic['avg_throughput_mbps'], live_bbr['avg_throughput_mbps']])

    # Active preferred JFI: prefer live run if available, else historical
    active_jfi = live_jfi if live_jfi is not None else hist_jfi

    return {
        'scenario': 'fairness',
        'jains_fairness_index': active_jfi,
        'has_fairness_data': (active_jfi is not None),
        'live': {
            'cubic': live_cubic,
            'bbr': live_bbr,
            'jfi': live_jfi
        },
        'historical': {
            'cubic': historical_cubic,
            'bbr': historical_bbr,
            'jfi': hist_jfi
        },
        'all_fairness_runs': fair_results
    }

