#!/usr/bin/env python3
"""
run_tests.py — Automated TCP Congestion Control Benchmark Runner
================================================================
Drives Mininet programmatically to execute iperf3 experiments comparing
Reno, CUBIC, and BBR across five network scenarios plus a fairness test.

Each experiment:
  1. Instantiates a fresh SingleBottleneckTopo with scenario-specific params.
  2. Sets the TCP congestion control algorithm system-wide via sysctl.
  3. Starts an iperf3 server on h2, runs the client on h1 for 60 seconds.
  4. Saves the iperf3 JSON output to results/<algo>_<scenario>.json.
  5. Tears down Mininet cleanly.

Run with:
    sudo python3 run_tests.py

Requires:
    - Mininet installed  (apt install mininet)
    - iperf3 installed   (apt install iperf3)
    - Root/sudo access
"""

import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

from mininet.net import Mininet
from mininet.link import TCLink
from mininet.log import setLogLevel, info, error, warn
from mininet.node import OVSBridge
from mininet.clean import cleanup

from topo import SingleBottleneckTopo

# ---------------------------------------------------------------------------
# Global configuration
# ---------------------------------------------------------------------------

RESULTS_DIR = Path('results')
IPERF_DURATION = 60          # seconds for each iperf3 run
IPERF_INTERVAL = 1           # reporting interval (seconds)
ALGORITHMS = ['reno', 'cubic', 'bbr']

# Scenario definitions:  name → topology kwargs
SCENARIOS: dict[str, dict] = {
    'baseline':     {'bw': 10,  'delay': '20ms',  'loss': 0,  'max_queue_size': 100},
    'loss_1':       {'bw': 10,  'delay': '20ms',  'loss': 1,  'max_queue_size': 100},
    'loss_5':       {'bw': 10,  'delay': '20ms',  'loss': 5,  'max_queue_size': 100},
    'high_rtt':     {'bw': 10,  'delay': '100ms', 'loss': 0,  'max_queue_size': 100},
    'small_buffer': {'bw': 10,  'delay': '20ms',  'loss': 0,  'max_queue_size': 10 },
}

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def ensure_dirs():
    """Create results/ and plots/ if they do not exist."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    Path('plots').mkdir(parents=True, exist_ok=True)


def is_root() -> bool:
    return os.geteuid() == 0


def check_iperf3() -> bool:
    """Return True if iperf3 is available on PATH."""
    try:
        subprocess.run(['iperf3', '--version'], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def available_congestion_algos() -> list[str]:
    """Return the list of TCP CC algorithms currently available in the kernel."""
    try:
        with open('/proc/sys/net/ipv4/tcp_available_congestion_control') as f:
            return f.read().strip().split()
    except OSError:
        return []


def load_bbr_module():
    """
    Attempt to load tcp_bbr kernel module.
    Returns True on success or if already loaded, False otherwise.
    """
    try:
        result = subprocess.run(
            ['modprobe', 'tcp_bbr'],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            info("*** BBR module loaded successfully\n")
            return True
        else:
            warn(f"*** modprobe tcp_bbr failed: {result.stderr.strip()}\n")
            return False
    except Exception as e:
        warn(f"*** Could not load tcp_bbr: {e}\n")
        return False


def set_congestion_control(net, algo: str):
    """
    Set TCP congestion control on both hosts and the host OS.

    Uses sysctl on each host so that iperf3 processes inherit the setting,
    and also sets it globally in case host namespaces share the kernel CC.
    """
    for host in net.hosts:
        result = host.cmd(f'sysctl -w net.ipv4.tcp_congestion_control={algo}')
        info(f"    [{host.name}] sysctl → {result.strip()}\n")

    # Also apply globally (Mininet hosts share kernel in most setups)
    subprocess.run(
        ['sysctl', '-w', f'net.ipv4.tcp_congestion_control={algo}'],
        capture_output=True
    )


def save_json(data: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    info(f"    Saved: {path}\n")


def mininet_cleanup():
    """Best-effort Mininet cleanup (equivalent to 'sudo mn -c')."""
    try:
        cleanup()
    except Exception:
        pass
    try:
        subprocess.run(['mn', '-c'], capture_output=True, timeout=30)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Core experiment runner
# ---------------------------------------------------------------------------

def run_single_experiment(
    scenario_name: str,
    algo: str,
    topo_kwargs: dict,
    net=None,
    h1=None,
    h2=None,
    parallel_streams: int = 1,
    extra_tag: str = ''
) -> dict | None:
    """
    Run a single iperf3 experiment inside the provided (or newly created) Mininet.

    Parameters
    ----------
    scenario_name : str   Scenario label for file naming.
    algo : str            CC algorithm ('reno', 'cubic', 'bbr').
    topo_kwargs : dict    Passed to SingleBottleneckTopo.build().
    net, h1, h2          If provided, reuse an existing Mininet instance.
    parallel_streams      Number of parallel iperf3 streams from h1.
    extra_tag            Additional tag appended to output filename.

    Returns
    -------
    Parsed iperf3 result dict, or None on failure.
    """
    own_net = net is None
    try:
        if own_net:
            info(f"\n*** Building topology for scenario='{scenario_name}' algo='{algo}'\n")
            topo = SingleBottleneckTopo(**topo_kwargs)
            net = Mininet(topo=topo, link=TCLink, switch=OVSBridge, controller=None,
                          autoSetMacs=True)
            net.start()
            h1 = net.get('h1')
            h2 = net.get('h2')
            # Give OVS a moment to install flows
            time.sleep(2)

        # Set CC algorithm
        set_congestion_control(net, algo)

        # Verify ping reachability before spending 60s on iperf
        ping_result = h1.cmd(f'ping -c 3 -W 2 {h2.IP()}')
        if '0 received' in ping_result and '3 received' not in ping_result:
            warn(f"    WARNING: ping h1→h2 may have issues:\n{ping_result}\n")

        # Start iperf3 server on h2 (daemon mode, JSON log to /dev/null)
        h2.cmd('pkill -f iperf3 2>/dev/null; sleep 0.5')
        h2.cmd('iperf3 -s -D --logfile /dev/null')
        time.sleep(1)

        # Build iperf3 client command
        parallel_flag = f'-P {parallel_streams}' if parallel_streams > 1 else ''
        client_cmd = (
            f'iperf3 -c {h2.IP()} '
            f'-t {IPERF_DURATION} '
            f'-i {IPERF_INTERVAL} '
            f'-J '            # JSON output
            f'{parallel_flag}'
        )
        info(f"    Running: {client_cmd}\n")

        # Execute with generous timeout
        timeout = IPERF_DURATION + 30
        raw_output = h1.cmd(client_cmd, timeout=timeout)

        # Kill server
        h2.cmd('pkill -f iperf3 2>/dev/null')

        # Parse JSON
        if not raw_output or not raw_output.strip():
            error(f"    ERROR: empty iperf3 output for {algo}/{scenario_name}\n")
            return _error_result(scenario_name, algo, 'empty iperf3 output')

        # Strip any non-JSON prefix (Mininet sometimes prepends shell echo)
        json_start = raw_output.find('{')
        if json_start == -1:
            error(f"    ERROR: no JSON in iperf3 output:\n{raw_output[:300]}\n")
            return _error_result(scenario_name, algo, 'no JSON in output')

        raw_json = raw_output[json_start:]
        try:
            result = json.loads(raw_json)
        except json.JSONDecodeError as e:
            error(f"    ERROR: JSON parse error: {e}\n{raw_json[:300]}\n")
            return _error_result(scenario_name, algo, f'JSON parse error: {e}')

        # Annotate with metadata
        result['_meta'] = {
            'scenario': scenario_name,
            'algorithm': algo,
            'topo_kwargs': topo_kwargs,
            'parallel_streams': parallel_streams,
        }

        # Save to disk
        tag = f'_{extra_tag}' if extra_tag else ''
        out_path = RESULTS_DIR / f'{algo}_{scenario_name}{tag}.json'
        save_json(result, out_path)

        # Summary log
        try:
            end_bps = result['end']['sum_sent']['bits_per_second']
            retrans = result['end']['sum_sent'].get('retransmits', 0)
            info(f"    ✓ {algo}/{scenario_name}: "
                 f"{end_bps/1e6:.2f} Mbps, {retrans} retransmits\n")
        except (KeyError, TypeError):
            info(f"    ✓ {algo}/{scenario_name}: result saved (could not parse summary)\n")

        return result

    except Exception as e:
        error(f"    EXCEPTION in {algo}/{scenario_name}: {e}\n")
        traceback.print_exc()
        return _error_result(scenario_name, algo, str(e))

    finally:
        if own_net and net is not None:
            try:
                net.stop()
            except Exception:
                pass
            mininet_cleanup()
            time.sleep(2)   # Let kernel clean up netns/OVS state


def _error_result(scenario: str, algo: str, reason: str) -> dict:
    """Return a stub result dict indicating failure."""
    stub = {
        '_meta': {'scenario': scenario, 'algorithm': algo, 'error': reason},
        '_error': True,
        'error': reason,
    }
    out_path = RESULTS_DIR / f'{algo}_{scenario}_ERROR.json'
    save_json(stub, out_path)
    return stub


# ---------------------------------------------------------------------------
# Fairness scenario
# ---------------------------------------------------------------------------

def run_fairness_scenario(topo_kwargs: dict):
    """
    Fairness test: CUBIC and BBR compete simultaneously on the same bottleneck.

    Two separate iperf3 clients start concurrently. Each saves its own JSON.
    A combined fairness result is also saved.
    """
    scenario = 'fairness'
    info(f"\n*** [FAIRNESS] CUBIC vs BBR competing on same bottleneck\n")

    try:
        topo = SingleBottleneckTopo(**topo_kwargs)
        net = Mininet(topo=topo, link=TCLink, switch=OVSBridge, controller=None,
                      autoSetMacs=True)
        net.start()
        h1 = net.get('h1')
        h2 = net.get('h2')
        time.sleep(2)

        # We need two senders.  In a single-switch topology the simplest approach
        # is to add virtual interfaces to h1 and run two concurrent iperf3 clients,
        # one with CC=cubic, one with CC=bbr.  Since Linux iperf3 inherits the
        # *per-socket* CC from /proc, we temporarily set both and use -C flag.
        h2.cmd('pkill -f iperf3 2>/dev/null; sleep 0.5')
        # Start two iperf3 servers on different ports
        h2.cmd('iperf3 -s -p 5201 -D --logfile /dev/null')
        h2.cmd('iperf3 -s -p 5202 -D --logfile /dev/null')
        time.sleep(1)

        cubic_outfile = '/tmp/fairness_cubic.json'
        bbr_outfile   = '/tmp/fairness_bbr.json'

        # iperf3 supports -C (--congestion) to select CC per socket on Linux
        cmd_cubic = (
            f'iperf3 -c {h2.IP()} -p 5201 '
            f'-t {IPERF_DURATION} -i {IPERF_INTERVAL} -J -C cubic '
            f'> {cubic_outfile} 2>&1 &'
        )
        cmd_bbr = (
            f'iperf3 -c {h2.IP()} -p 5202 '
            f'-t {IPERF_DURATION} -i {IPERF_INTERVAL} -J -C bbr '
            f'> {bbr_outfile} 2>&1 &'
        )

        info(f"    Starting CUBIC client (port 5201)...\n")
        h1.cmd(cmd_cubic)
        info(f"    Starting BBR client (port 5202)...\n")
        h1.cmd(cmd_bbr)

        # Wait for both to finish (+10 s grace)
        info(f"    Waiting {IPERF_DURATION + 10}s for fairness streams to complete...\n")
        time.sleep(IPERF_DURATION + 10)

        # Kill servers
        h2.cmd('pkill -f iperf3 2>/dev/null')

        # Read outputs from temp files via host
        raw_cubic = h1.cmd(f'cat {cubic_outfile}')
        raw_bbr   = h1.cmd(f'cat {bbr_outfile}')

        def _parse_iperf_output(raw: str, algo: str) -> dict | None:
            idx = raw.find('{')
            if idx == -1:
                warn(f"    WARNING: no JSON in {algo} fairness output\n")
                return None
            try:
                return json.loads(raw[idx:])
            except json.JSONDecodeError as e:
                warn(f"    WARNING: JSON parse error for {algo}: {e}\n")
                return None

        result_cubic = _parse_iperf_output(raw_cubic, 'cubic')
        result_bbr   = _parse_iperf_output(raw_bbr,   'bbr')

        # Extract throughputs
        def _bps(r: dict | None) -> float:
            try:
                return r['end']['sum_sent']['bits_per_second']
            except (TypeError, KeyError):
                return 0.0

        tp_cubic = _bps(result_cubic)
        tp_bbr   = _bps(result_bbr)

        # Jain's Fairness Index
        flows = [tp_cubic, tp_bbr]
        n = len(flows)
        jfi = (sum(flows) ** 2) / (n * sum(x ** 2 for x in flows)) if any(flows) else 0.0

        info(f"    CUBIC throughput : {tp_cubic/1e6:.2f} Mbps\n")
        info(f"    BBR   throughput : {tp_bbr/1e6:.2f} Mbps\n")
        info(f"    Jain's FI        : {jfi:.4f}\n")

        # Save individual JSON results
        if result_cubic:
            result_cubic['_meta'] = {'scenario': scenario, 'algorithm': 'cubic'}
            save_json(result_cubic, RESULTS_DIR / 'cubic_fairness.json')
        else:
            save_json(_error_result(scenario, 'cubic', 'parse error'),
                      RESULTS_DIR / 'cubic_fairness.json')

        if result_bbr:
            result_bbr['_meta'] = {'scenario': scenario, 'algorithm': 'bbr'}
            save_json(result_bbr, RESULTS_DIR / 'bbr_fairness.json')
        else:
            save_json(_error_result(scenario, 'bbr', 'parse error'),
                      RESULTS_DIR / 'bbr_fairness.json')

        # Save combined fairness summary
        fairness_summary = {
            '_meta': {'scenario': scenario, 'topo_kwargs': topo_kwargs},
            'cubic_throughput_bps': tp_cubic,
            'bbr_throughput_bps':   tp_bbr,
            'jains_fairness_index': jfi,
            'flows': {'cubic': tp_cubic, 'bbr': tp_bbr},
        }
        save_json(fairness_summary, RESULTS_DIR / 'fairness_summary.json')

    except Exception as e:
        error(f"    EXCEPTION in fairness scenario: {e}\n")
        traceback.print_exc()
    finally:
        try:
            net.stop()
        except Exception:
            pass
        mininet_cleanup()
        time.sleep(2)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def main():
    setLogLevel('info')

    # ── Pre-flight checks ──────────────────────────────────────────────────
    if not is_root():
        sys.exit("ERROR: This script must be run as root (use sudo).")

    if not check_iperf3():
        sys.exit("ERROR: iperf3 not found. Install with: sudo apt install iperf3")

    ensure_dirs()

    # BBR availability
    available = available_congestion_algos()
    info(f"*** Available CC algorithms: {available}\n")
    if 'bbr' not in available:
        info("*** Attempting to load tcp_bbr module...\n")
        if not load_bbr_module():
            warn("*** BBR not available — BBR experiments will be skipped.\n")
            ALGORITHMS.remove('bbr') if 'bbr' in ALGORITHMS else None

    # Re-read after potential module load
    available = available_congestion_algos()
    algos_to_run = [a for a in ALGORITHMS if a in available]
    if not algos_to_run:
        sys.exit("ERROR: No valid CC algorithms available.")

    info(f"*** Will test algorithms: {algos_to_run}\n")
    info(f"*** Scenarios: {list(SCENARIOS.keys())} + fairness\n")
    info(f"*** iperf3 duration per run: {IPERF_DURATION}s\n\n")

    total = len(SCENARIOS) * len(algos_to_run) + 1   # +1 for fairness
    done = 0
    failures = []

    # ── Standard scenarios ─────────────────────────────────────────────────
    for scenario_name, topo_kwargs in SCENARIOS.items():
        for algo in algos_to_run:
            info(f"\n{'='*60}\n")
            info(f"  [{done+1}/{total}] Scenario: {scenario_name} | Algo: {algo}\n")
            info(f"{'='*60}\n")
            result = run_single_experiment(
                scenario_name=scenario_name,
                algo=algo,
                topo_kwargs=topo_kwargs
            )
            if result is None or result.get('_error'):
                failures.append(f"{algo}/{scenario_name}")
            done += 1

    # ── Fairness scenario ──────────────────────────────────────────────────
    info(f"\n{'='*60}\n")
    info(f"  [{done+1}/{total}] Scenario: fairness (CUBIC vs BBR)\n")
    info(f"{'='*60}\n")
    run_fairness_scenario(topo_kwargs=SCENARIOS['baseline'])
    done += 1

    # ── Final summary ──────────────────────────────────────────────────────
    info(f"\n{'='*60}\n")
    info(f"*** All experiments complete! ({done}/{total} ran)\n")
    if failures:
        warn(f"*** The following experiments reported errors:\n")
        for f in failures:
            warn(f"      - {f}\n")
    info(f"*** Results saved in: {RESULTS_DIR.resolve()}\n")
    info(f"{'='*60}\n")


if __name__ == '__main__':
    main()
