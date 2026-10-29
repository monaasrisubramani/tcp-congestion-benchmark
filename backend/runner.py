"""
backend/runner.py — Mininet & Live Experiment Execution Engine
==============================================================
Manages live benchmark execution in a background thread, tracking real-time
progress, system status, logs, cancellation, and simulation fallbacks.
"""

import json
import math
import os
import random
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from backend.storage import LIVE_RESULTS_DIR, ensure_storage_dirs, parse_json_result

# Try importing Mininet components (available when running in WSL2/Linux with Mininet)
try:
    from mininet.net import Mininet
    from mininet.link import TCLink
    from mininet.node import OVSBridge
    from mininet.clean import cleanup
    from topo import SingleBottleneckTopo
    MININET_AVAILABLE = True
except ImportError:
    MININET_AVAILABLE = False


class ExperimentRunner:
    def __init__(self):
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self.cancel_requested = False

        # State tracking
        self.state: Dict[str, Any] = {
            'is_running': False,
            'job_id': None,
            'status': 'idle',        # idle | starting | running | analyzing | completed | error | cancelled
            'progress': 0,           # 0 to 100
            'step_description': 'Ready',
            'elapsed_seconds': 0,
            'estimated_total_seconds': 0,
            'logs': [],
            'error_message': None,
            'result': None,
            'config': None
        }

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self.state)

    def log(self, message: str):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_line = f"[{timestamp}] {message}"
        with self.lock:
            self.state['logs'].append(log_line)
            # keep last 200 log entries
            if len(self.state['logs']) > 200:
                self.state['logs'] = self.state['logs'][-200:]

    def check_environment(self) -> Dict[str, Any]:
        """Check system environment, root status, and kernel capabilities."""
        is_linux = os.name == 'posix'
        is_root = False
        avail_cc = []
        bbr_loaded = False
        iperf3_ok = False

        if is_linux:
            is_root = os.geteuid() == 0
            try:
                with open('/proc/sys/net/ipv4/tcp_available_congestion_control', 'r') as f:
                    avail_cc = f.read().strip().split()
                    bbr_loaded = 'bbr' in avail_cc
            except Exception:
                pass

            try:
                res = subprocess.run(['iperf3', '--version'], capture_output=True)
                iperf3_ok = (res.returncode == 0)
            except Exception:
                iperf3_ok = False

        return {
            'is_linux': is_linux,
            'is_root': is_root,
            'mininet_available': MININET_AVAILABLE,
            'available_cc': avail_cc,
            'bbr_loaded': bbr_loaded,
            'iperf3_available': iperf3_ok,
            'can_run_real_mininet': is_linux and is_root and MININET_AVAILABLE and iperf3_ok
        }

    def cancel(self):
        with self.lock:
            if not self.state['is_running']:
                return
            self.cancel_requested = True
            self.log("Cancelling experiment on user request...")

        # Best-effort cleanup
        try:
            subprocess.run(['pkill', '-f', 'iperf3'], capture_output=True)
            if MININET_AVAILABLE:
                cleanup()
                subprocess.run(['mn', '-c'], capture_output=True)
        except Exception:
            pass

    def start_experiment(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        config dict:
          - algorithm: 'reno' | 'cubic' | 'bbr' | 'all'
          - scenario: 'baseline' | 'loss_1' | 'loss_5' | 'high_rtt' | 'small_buffer' | 'fairness' | 'custom'
          - bw: float (Mbps)
          - delay: str (e.g. '20ms')
          - loss: float (%)
          - queue: int (packets)
          - duration: int (seconds, default 15)
          - simulate: bool (optional explicit simulation mode)
        """
        with self.lock:
            if self.state['is_running']:
                return {'error': 'Another experiment is currently running.'}

            self.cancel_requested = False
            job_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            duration = config.get('duration', 15)
            algo = config.get('algorithm', 'bbr')
            estimated_total = (duration * 3 + 12) if algo == 'all' else (duration + 5)

            self.state = {
                'is_running': True,
                'job_id': job_id,
                'status': 'starting',
                'progress': 0,
                'step_description': 'Initializing experiment...',
                'elapsed_seconds': 0,
                'estimated_total_seconds': estimated_total,
                'logs': [],
                'error_message': None,
                'result': None,
                'config': config
            }

        self.thread = threading.Thread(target=self._worker, args=(config, job_id))
        self.thread.daemon = True
        self.thread.start()
        return {'status': 'started', 'job_id': job_id}

    def _worker(self, config: Dict[str, Any], job_id: str):
        env = self.check_environment()
        use_simulation = config.get('simulate', False) or (not env['can_run_real_mininet'])

        if not use_simulation and not env['is_root']:
            with self.lock:
                self.state['status'] = 'error'
                self.state['is_running'] = False
                self.state['error_message'] = (
                    "Root privileges required: Mininet and TCLink need sudo permissions "
                    "to configure network namespaces and tc traffic shaping. "
                    "Start backend with 'sudo python3 -m backend.main' inside WSL2, "
                    "or enable Simulation Mode to test UI without root."
                )
            self.log(f"ERROR: {self.state['error_message']}")
            return

        if use_simulation:
            self.log("Note: Executing in high-fidelity mathematical simulation mode.")
            self._run_simulation(config, job_id)
        else:
            self.log("Executing live experiment with Mininet + iperf3 in kernel...")
            self._run_real_mininet(config, job_id)

    # ---------------------------------------------------------------------------
    # Real Mininet + iperf3 Execution
    # ---------------------------------------------------------------------------
    def _run_real_mininet(self, config: Dict[str, Any], job_id: str):
        ensure_storage_dirs()
        algo = config.get('algorithm', 'bbr')
        scenario = config.get('scenario', 'baseline')
        bw = float(config.get('bw', 10.0))
        delay = str(config.get('delay', '20ms'))
        loss = float(config.get('loss', 0.0))
        queue = int(config.get('queue', 100))
        duration = int(config.get('duration', 15))

        topo_kwargs = {'bw': bw, 'delay': delay, 'loss': loss, 'max_queue_size': queue}
        start_time = time.time()

        try:
            self.log(f"Building Mininet SingleBottleneckTopo (BW: {bw}M, Delay: {delay}, Loss: {loss}%, Queue: {queue})")
            with self.lock:
                self.state['status'] = 'running'
                self.state['step_description'] = 'Setting up network topology & TCLink shaping...'
                self.state['progress'] = 10

            topo = SingleBottleneckTopo(**topo_kwargs)
            net = Mininet(topo=topo, link=TCLink, switch=OVSBridge, controller=None, autoSetMacs=True)
            net.start()
            h1 = net.get('h1')
            h2 = net.get('h2')
            time.sleep(1)

            if self.cancel_requested:
                net.stop()
                self._handle_cancelled()
                return

            if scenario == 'fairness' or algo == 'fairness':
                self._run_mininet_fairness(net, h1, h2, topo_kwargs, duration, job_id)
            elif algo == 'all':
                self._run_mininet_compare_all(net, h1, h2, scenario, topo_kwargs, duration, job_id)
            else:
                self._run_mininet_single(net, h1, h2, algo, scenario, topo_kwargs, duration, job_id)

        except Exception as e:
            with self.lock:
                self.state['status'] = 'error'
                self.state['is_running'] = False
                self.state['error_message'] = f"Mininet execution exception: {str(e)}"
            self.log(f"EXCEPTION: {e}")
        finally:
            try:
                if 'net' in locals() and net:
                    net.stop()
                cleanup()
                subprocess.run(['mn', '-c'], capture_output=True)
            except Exception:
                pass

    def _run_mininet_compare_all(self, net, h1, h2, scenario: str, topo_kwargs: dict, duration: int, job_id: str):
        target_algos = ['reno', 'cubic', 'bbr']
        completed_results = {}
        failed_algos = {}

        self.log(f"Starting Compare All: sequentially testing Reno, CUBIC, and BBR under identical topology...")

        env = self.check_environment()
        available_cc = set(env.get('available_cc', []))

        total_algos = len(target_algos)
        for idx, current_algo in enumerate(target_algos):
            if self.cancel_requested:
                self._handle_cancelled()
                return

            base_pct = 5 + int((idx / total_algos) * 90)
            self.log(f"--- Compare All [{idx + 1}/{total_algos}]: Setting up {current_algo.upper()} ---")

            # Check kernel CC availability and load BBR if needed
            if current_algo == 'bbr' and 'bbr' not in available_cc:
                subprocess.run(['modprobe', 'tcp_bbr'], capture_output=True)
                env_refresh = self.check_environment()
                available_cc = set(env_refresh.get('available_cc', []))

            if available_cc and current_algo not in available_cc:
                err_msg = f"Algorithm '{current_algo}' not available in kernel (available: {', '.join(sorted(available_cc))})"
                self.log(f"[ERROR] {err_msg}")
                failed_algos[current_algo] = err_msg
                continue

            try:
                # Apply sysctl for this algorithm on all hosts
                for host in net.hosts:
                    host.cmd(f'sysctl -w net.ipv4.tcp_congestion_control={current_algo}')
                subprocess.run(['sysctl', '-w', f'net.ipv4.tcp_congestion_control={current_algo}'], capture_output=True)

                h2.cmd('pkill -f iperf3 2>/dev/null; sleep 0.5')
                h2.cmd('iperf3 -s -D --logfile /dev/null')
                time.sleep(1)

                # Explicitly pass -C <algo> to iperf3
                client_cmd = f"iperf3 -c {h2.IP()} -p 5201 -t {duration} -i 1 -J -C {current_algo}"
                self.log(f"Running: {client_cmd}")

                # Monitor progress
                for s in range(duration):
                    if self.cancel_requested:
                        h2.cmd('pkill -f iperf3 2>/dev/null')
                        self._handle_cancelled()
                        return
                    time.sleep(1)
                    sub_pct = base_pct + int(((s + 1) / duration) * (90 / total_algos))
                    with self.lock:
                        self.state['progress'] = min(95, sub_pct)
                        self.state['elapsed_seconds'] += 1
                        self.state['step_description'] = (
                            f"Compare All ({idx + 1}/{total_algos}): Measuring {current_algo.upper()} "
                            f"({s + 1}/{duration}s)..."
                        )

                raw_output = h1.cmd(client_cmd)
                h2.cmd('pkill -f iperf3 2>/dev/null')

                idx_brace = raw_output.find('{')
                if idx_brace == -1:
                    raise RuntimeError(f"No JSON returned from iperf3 for {current_algo}: {raw_output[:200]}")

                result_json = json.loads(raw_output[idx_brace:])
                result_json['_meta'] = {
                    'scenario': scenario,
                    'algorithm': current_algo,
                    'topo_kwargs': topo_kwargs,
                    'timestamp': datetime.now().isoformat(),
                    'job_id': job_id,
                    'is_live': True
                }

                out_file = LIVE_RESULTS_DIR / f"live_{current_algo}_{scenario}_{job_id}.json"
                with open(out_file, 'w', encoding='utf-8') as f:
                    json.dump(result_json, f, indent=2)

                parsed = parse_json_result(out_file, source_type='live')
                if parsed:
                    completed_results[current_algo] = parsed
                    self.log(f"Finished {current_algo.upper()}: Avg = {parsed['avg_throughput_mbps']} Mbps, Retransmits = {parsed['retransmissions']}")
                else:
                    raise RuntimeError(f"Failed to parse iperf3 result for {current_algo}")

            except Exception as e:
                self.log(f"[ERROR] Exception running {current_algo}: {e}")
                failed_algos[current_algo] = str(e)

        with self.lock:
            self.state['is_running'] = False
            self.state['progress'] = 100
            if completed_results and not failed_algos:
                self.state['status'] = 'completed'
                summary_str = ", ".join([f"{a.upper()}: {r['avg_throughput_mbps']} Mbps" for a, r in completed_results.items()])
                self.state['step_description'] = f"Compare All completed! ({summary_str})"
                self.state['result'] = completed_results
            elif completed_results and failed_algos:
                self.state['status'] = 'completed'
                self.state['step_description'] = (
                    f"Compare All partial: {len(completed_results)}/3 completed. "
                    f"Failed: {', '.join(failed_algos.keys())}"
                )
                self.state['result'] = completed_results
            else:
                self.state['status'] = 'error'
                self.state['error_message'] = f"All algorithms failed in Compare All: {failed_algos}"
                self.state['step_description'] = "All algorithms failed."

        self.log(f"Compare All completed. Succeeded: {list(completed_results.keys())}, Failed: {list(failed_algos.keys())}")

    def _run_mininet_single(self, net, h1, h2, algo, scenario, topo_kwargs, duration, job_id):
        if algo == 'all':
            raise ValueError("Internal error: 'all' passed to _run_mininet_single")

        env = self.check_environment()
        available_cc = set(env.get('available_cc', []))
        if algo == 'bbr' and 'bbr' not in available_cc:
            subprocess.run(['modprobe', 'tcp_bbr'], capture_output=True)
            available_cc = set(self.check_environment().get('available_cc', []))

        if available_cc and algo not in available_cc:
            raise RuntimeError(f"Congestion control algorithm '{algo}' is not available in the kernel (available: {', '.join(sorted(available_cc))})")

        self.log(f"Applying TCP congestion control algorithm: {algo.upper()}")
        for host in net.hosts:
            host.cmd(f'sysctl -w net.ipv4.tcp_congestion_control={algo}')
        subprocess.run(['sysctl', '-w', f'net.ipv4.tcp_congestion_control={algo}'], capture_output=True)

        verify = h1.cmd('sysctl -n net.ipv4.tcp_congestion_control').strip()
        if verify != algo:
            self.log(f"[WARN] h1 reported '{verify}' when setting '{algo}'")

        h2.cmd('pkill -f iperf3 2>/dev/null; sleep 0.5')
        h2.cmd('iperf3 -s -D --logfile /dev/null')
        time.sleep(1)

        self.log(f"Starting iperf3 measurement for {duration} seconds with -C {algo}...")
        client_cmd = f"iperf3 -c {h2.IP()} -p 5201 -t {duration} -i 1 -J -C {algo}"

        # Polling progress
        for s in range(duration):
            if self.cancel_requested:
                h2.cmd('pkill -f iperf3 2>/dev/null')
                self._handle_cancelled()
                return
            time.sleep(1)
            pct = 15 + int(((s + 1) / duration) * 75)
            with self.lock:
                self.state['progress'] = min(95, pct)
                self.state['elapsed_seconds'] = s + 1
                self.state['step_description'] = f"Measuring TCP throughput: second {s + 1}/{duration}..."

        raw_output = h1.cmd(client_cmd)
        h2.cmd('pkill -f iperf3 2>/dev/null')

        # Parse output
        with self.lock:
            self.state['status'] = 'analyzing'
            self.state['step_description'] = 'Parsing iperf3 telemetry...'
            self.state['progress'] = 95

        idx = raw_output.find('{')
        if idx == -1:
            raise RuntimeError(f"No JSON returned from iperf3: {raw_output[:200]}")

        result = json.loads(raw_output[idx:])
        result['_meta'] = {
            'scenario': scenario,
            'algorithm': algo,
            'topo_kwargs': topo_kwargs,
            'timestamp': datetime.now().isoformat(),
            'job_id': job_id,
            'is_live': True
        }

        # Save to live runs
        out_file = LIVE_RESULTS_DIR / f"live_{algo}_{scenario}_{job_id}.json"
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)

        parsed = parse_json_result(out_file, source_type='live')
        with self.lock:
            self.state['status'] = 'completed'
            self.state['is_running'] = False
            self.state['progress'] = 100
            self.state['step_description'] = f"Completed successfully! Avg Throughput: {parsed['avg_throughput_mbps']} Mbps"
            self.state['result'] = parsed

        self.log(f"Experiment finished: Avg={parsed['avg_throughput_mbps']} Mbps, Retransmits={parsed['retransmissions']}")

    def _run_mininet_fairness(self, net, h1, h2, topo_kwargs, duration, job_id):
        self.log("Running simultaneous CUBIC vs BBR fairness competition...")
        h2.cmd('pkill -f iperf3 2>/dev/null; sleep 0.5')
        h2.cmd('iperf3 -s -p 5201 -D --logfile /dev/null')
        h2.cmd('iperf3 -s -p 5202 -D --logfile /dev/null')
        time.sleep(1)

        c_out = f"/tmp/fairness_c_{job_id}.json"
        b_out = f"/tmp/fairness_b_{job_id}.json"

        h1.cmd(f"iperf3 -c {h2.IP()} -p 5201 -t {duration} -i 1 -J -C cubic > {c_out} 2>&1 &")
        h1.cmd(f"iperf3 -c {h2.IP()} -p 5202 -t {duration} -i 1 -J -C bbr > {b_out} 2>&1 &")

        for s in range(duration + 2):
            if self.cancel_requested:
                h2.cmd('pkill -f iperf3 2>/dev/null')
                self._handle_cancelled()
                return
            time.sleep(1)
            pct = 15 + int((s / (duration + 2)) * 75)
            with self.lock:
                self.state['progress'] = pct
                self.state['elapsed_seconds'] = s + 1
                self.state['step_description'] = f"Fairness test running: {s + 1}/{duration}s..."

        h2.cmd('pkill -f iperf3 2>/dev/null')
        raw_c = h1.cmd(f'cat {c_out}')
        raw_b = h1.cmd(f'cat {b_out}')

        data_c = json.loads(raw_c[raw_c.find('{'):])
        data_b = json.loads(raw_b[raw_b.find('{'):])

        data_c['_meta'] = {'scenario': 'fairness', 'algorithm': 'cubic', 'timestamp': datetime.now().isoformat()}
        data_b['_meta'] = {'scenario': 'fairness', 'algorithm': 'bbr', 'timestamp': datetime.now().isoformat()}

        file_c = LIVE_RESULTS_DIR / f"live_cubic_fairness_{job_id}.json"
        file_b = LIVE_RESULTS_DIR / f"live_bbr_fairness_{job_id}.json"

        with open(file_c, 'w') as f:
            json.dump(data_c, f, indent=2)
        with open(file_b, 'w') as f:
            json.dump(data_b, f, indent=2)

        parsed_c = parse_json_result(file_c, source_type='live')
        parsed_b = parse_json_result(file_b, source_type='live')

        jfi = (
            (parsed_c['avg_throughput_mbps'] + parsed_b['avg_throughput_mbps']) ** 2
            / (2 * (parsed_c['avg_throughput_mbps'] ** 2 + parsed_b['avg_throughput_mbps'] ** 2))
        )
        parsed_c['jfi'] = round(jfi, 4)
        parsed_b['jfi'] = round(jfi, 4)

        with self.lock:
            self.state['status'] = 'completed'
            self.state['is_running'] = False
            self.state['progress'] = 100
            self.state['step_description'] = f"Fairness completed! JFI: {jfi:.4f} (CUBIC: {parsed_c['avg_throughput_mbps']}M, BBR: {parsed_b['avg_throughput_mbps']}M)"
            self.state['result'] = {'cubic': parsed_c, 'bbr': parsed_b, 'jfi': jfi}

    # ---------------------------------------------------------------------------
    # High-Fidelity Simulation Mode (for testing outside root / Windows dev)
    # ---------------------------------------------------------------------------
    def _simulate_single_algo(self, single_algo: str, scenario: str, bw: float, loss: float, queue: int, duration: int, job_id: str, base_pct: int = 5, pct_share: int = 90):
        timeseries = []
        cumulative_bytes = 0
        retransmits = 0

        # Step delay per simulated second (snappy for UI animation)
        step_sleep = 0.15 if pct_share < 50 else 0.35

        for s in range(1, duration + 1):
            if self.cancel_requested:
                return None

            time.sleep(step_sleep)
            sub_pct = base_pct + int((s / duration) * pct_share)

            # Mathematical TCP throughput models
            if single_algo == 'bbr':
                # BBR: model-based pacing, estimates bottleneck bandwidth, largely loss-insensitive
                jitter = random.uniform(-0.15, 0.15)
                mbps = max(0.5, bw * 0.96 + jitter)
                if loss > 0:
                    # BBR pushes full rate but causes retransmits
                    retransmits += int(mbps * 125 * (loss / 100.0) * random.uniform(0.8, 1.2))
                if queue < 20:
                    mbps *= 0.98

            elif single_algo == 'cubic':
                # CUBIC: window growth cubic with time since loss. Highly degraded by random loss
                if loss == 0:
                    ramp = min(1.0, 0.4 + 0.6 * (s / 5.0))
                    jitter = random.uniform(-0.1, 0.1)
                    mbps = bw * 0.97 * ramp + jitter
                    if queue < 20:
                        mbps = bw * 0.6 + random.uniform(-0.3, 0.3)
                        retransmits += random.randint(1, 4)
                elif loss <= 1.5:
                    mbps = bw * 0.46 + random.uniform(-0.3, 0.3)
                    retransmits += random.randint(2, 6)
                else:
                    mbps = max(0.4, bw * 0.18 + random.uniform(-0.2, 0.2))
                    retransmits += random.randint(5, 12)

            elif single_algo == 'reno':
                # Reno: AIMD classic. Drops 50% on loss
                if loss == 0:
                    ramp = min(1.0, 0.3 + 0.7 * (s / 6.0))
                    jitter = random.uniform(-0.15, 0.15)
                    mbps = bw * 0.96 * ramp + jitter
                    if queue < 20:
                        mbps = bw * 0.58 + random.uniform(-0.3, 0.3)
                        retransmits += random.randint(2, 5)
                elif loss <= 1.5:
                    mbps = bw * 0.50 + random.uniform(-0.3, 0.3)
                    retransmits += random.randint(2, 7)
                else:
                    mbps = max(0.4, bw * 0.20 + random.uniform(-0.2, 0.2))
                    retransmits += random.randint(6, 14)
            else:
                mbps = bw * 0.9

            mbps = round(mbps, 3)
            bytes_this_sec = int(mbps * 125000)
            cumulative_bytes += bytes_this_sec
            timeseries.append({'second': s, 'mbps': mbps})

            with self.lock:
                self.state['progress'] = min(98, sub_pct)
                self.state['elapsed_seconds'] += 1
                self.state['step_description'] = f"Simulating {single_algo.upper()}: second {s}/{duration} ({mbps} Mbps)"

        avg_mbps = round(sum(p['mbps'] for p in timeseries) / len(timeseries), 3)
        end_mbps = timeseries[-1]['mbps']
        total_mb = round(cumulative_bytes / 1e6, 3)

        mock_result = {
            '_meta': {
                'scenario': scenario,
                'algorithm': single_algo,
                'topo_kwargs': {'bw': bw, 'loss': loss, 'max_queue_size': queue},
                'timestamp': datetime.now().isoformat(),
                'job_id': job_id,
                'is_live': True,
                'is_simulated': True
            },
            'intervals': [
                {'streams': [{'bits_per_second': p['mbps'] * 1e6}]} for p in timeseries
            ],
            'end': {
                'sum_sent': {
                    'bits_per_second': end_mbps * 1e6,
                    'bytes': cumulative_bytes,
                    'retransmits': retransmits
                }
            }
        }

        out_file = LIVE_RESULTS_DIR / f"live_{single_algo}_{scenario}_{job_id}.json"
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(mock_result, f, indent=2)

        return parse_json_result(out_file, source_type='live')

    def _run_simulation(self, config: Dict[str, Any], job_id: str):
        ensure_storage_dirs()
        algo = config.get('algorithm', 'bbr')
        scenario = config.get('scenario', 'baseline')
        bw = float(config.get('bw', 10.0))
        loss = float(config.get('loss', 0.0))
        queue = int(config.get('queue', 100))
        duration = int(config.get('duration', 15))

        if algo == 'all':
            target_algos = ['reno', 'cubic', 'bbr']
            completed_results = {}
            total = len(target_algos)

            self.log(f"Simulation started for Compare All (Reno, CUBIC, BBR) under '{scenario}' ({bw} Mbps, loss={loss}%, Q={queue})")
            for idx, target_algo in enumerate(target_algos):
                if self.cancel_requested:
                    self._handle_cancelled()
                    return

                base_pct = 5 + int((idx / total) * 90)
                pct_share = int(90 / total)
                self.log(f"Simulating {target_algo.upper()} ({idx + 1}/{total})...")
                res = self._simulate_single_algo(target_algo, scenario, bw, loss, queue, duration, job_id, base_pct, pct_share)
                if res:
                    completed_results[target_algo] = res

            with self.lock:
                self.state['status'] = 'completed'
                self.state['is_running'] = False
                self.state['progress'] = 100
                summary_str = ", ".join([f"{a.upper()}: {r['avg_throughput_mbps']} Mbps" for a, r in completed_results.items()])
                self.state['step_description'] = f"Simulation Compare All completed! ({summary_str})"
                self.state['result'] = completed_results

            self.log(f"Simulation Compare All finished for {list(completed_results.keys())}")

        else:
            self.log(f"Simulation started for {algo.upper()} under scenario '{scenario}' ({bw} Mbps, loss={loss}%, Q={queue})")
            with self.lock:
                self.state['status'] = 'running'
                self.state['step_description'] = f'Simulating {algo.upper()} dynamic congestion window...'

            parsed = self._simulate_single_algo(algo, scenario, bw, loss, queue, duration, job_id, base_pct=5, pct_share=90)
            if self.cancel_requested or parsed is None:
                self._handle_cancelled()
                return

            with self.lock:
                self.state['status'] = 'completed'
                self.state['is_running'] = False
                self.state['progress'] = 100
                self.state['step_description'] = f"Simulation completed! Avg: {parsed['avg_throughput_mbps']} Mbps, Retransmits: {parsed['retransmissions']}"
                self.state['result'] = parsed

            self.log(f"Simulation completed: Avg Throughput = {parsed['avg_throughput_mbps']} Mbps, Retransmits = {parsed['retransmissions']}")

    def _handle_cancelled(self):
        with self.lock:
            self.state['status'] = 'cancelled'
            self.state['is_running'] = False
            self.state['step_description'] = 'Experiment cancelled by user.'
        self.log("Experiment successfully cancelled.")


# Global singleton instance
runner = ExperimentRunner()

