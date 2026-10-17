# TCP Congestion Control Benchmark Suite

> A fully-automated Mininet benchmarking suite that rigorously compares **TCP Reno**, **CUBIC**, and **BBR** congestion control algorithms across five network scenarios and a fairness test.

---

## Table of Contents

1. [Overview](#overview)
2. [Project Structure](#project-structure)
3. [Dependencies](#dependencies)
4. [Installation (Ubuntu 22.04 / WSL2)](#installation-ubuntu-2204--wsl2)
5. [Running the Suite](#running-the-suite)
6. [Scenarios](#scenarios)
7. [Output Files](#output-files)
8. [Architecture & Script Reference](#architecture--script-reference)
9. [Understanding the Results](#understanding-the-results)
10. [Troubleshooting](#troubleshooting)

---

## Overview

This suite programmatically orchestrates Mininet network emulations to stress-test three major TCP congestion control algorithms:

| Algorithm | Description |
|-----------|-------------|
| **Reno** | Classic additive-increase / multiplicative-decrease (AIMD). Sensitive to packet loss. |
| **CUBIC** | Linux default. Uses a cubic function for window growth; more aggressive in high-BDP paths. |
| **BBR** | Google's model-based algorithm. Estimates bottleneck bandwidth and RTT; loss-independent. |

Each algorithm is evaluated in 5 distinct network conditions plus a **fairness test** where CUBIC and BBR compete simultaneously. Results are parsed, summarized in CSV, and visualized in 7 different chart types.

---

## Project Structure

```
tcp_benchmark/
├── topo.py           # Mininet topology (SingleBottleneckTopo)
├── run_tests.py      # Automated test driver (Mininet + iperf3)
├── analyze.py        # JSON parser, metric extractor, CSV writer
├── plot_results.py   # Matplotlib visualization generator
├── run_all.sh        # Single-command end-to-end orchestrator
├── README.md         # This file
├── results/          # Auto-created: iperf3 JSON + summary CSV
└── plots/            # Auto-created: PNG visualizations
```

---

## Dependencies

| Tool | Purpose | Package |
|------|---------|---------|
| **Mininet** | Network emulation | `mininet` |
| **iperf3** | TCP bandwidth measurement | `iperf3` |
| **Open vSwitch** | SDN switch for Mininet | `openvswitch-switch` |
| **Python 3.8+** | Script runtime | `python3` |
| **pandas** | Data manipulation | `python3-pandas` |
| **matplotlib** | Visualization | `python3-matplotlib` |
| **numpy** | Numerical operations | `python3-numpy` |
| **tc / iproute2** | Traffic shaping (TCLink) | `iproute2` |

---

## Installation (Ubuntu 22.04 / WSL2)

### 1. Update package lists

```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Install system packages

```bash
sudo apt install -y \
    mininet \
    iperf3 \
    openvswitch-switch \
    iproute2 \
    python3-pip \
    python3-pandas \
    python3-matplotlib \
    python3-numpy
```

### 3. Install Python Mininet binding (if not already included)

```bash
pip3 install mininet
# OR install from source for the latest version:
git clone https://github.com/mininet/mininet.git
cd mininet && sudo python3 setup.py install
```

### 4. Enable BBR in the kernel

```bash
# Load the BBR module (temporary — survives until reboot)
sudo modprobe tcp_bbr

# Verify it loaded
lsmod | grep bbr

# Make it persistent across reboots
echo 'tcp_bbr' | sudo tee -a /etc/modules-load.d/modules.conf

# Optionally set BBR as system default
echo 'net.ipv4.tcp_congestion_control=bbr' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### 5. Start Open vSwitch (required by Mininet)

```bash
sudo service openvswitch-switch start
# On WSL2:
sudo /etc/init.d/openvswitch-switch start
```

### 6. Clone / navigate to the project

```bash
# If you downloaded the files as a zip:
cd /path/to/tcp_benchmark

# Make run_all.sh executable
chmod +x run_all.sh
```

---

## Running the Suite

```bash
# From the tcp_benchmark/ directory:
sudo ./run_all.sh
```

The orchestrator will:
1. Check for root, verify all dependencies
2. Clean stale Mininet state (`mn -c`)
3. Load `tcp_bbr` module
4. Run all Mininet experiments (~20–30 min depending on hardware)
5. Parse and summarize results → `results/summary.csv`
6. Generate all plots → `plots/*.png`
7. Print a completion banner with file locations

### Running individual steps

```bash
# Test topology only (quick sanity check, ~30s):
sudo python3 topo.py --bw 10 --delay 20ms --loss 0 --queue 100

# Run experiments only:
sudo python3 run_tests.py

# Analyze existing results:
python3 analyze.py

# Generate plots from existing results:
python3 plot_results.py
```

---

## Scenarios

| Scenario | Bandwidth | Delay | Loss | Queue | Purpose |
|----------|-----------|-------|------|-------|---------|
| `baseline` | 10 Mbps | 20 ms | 0% | 100 pkts | Reference point |
| `loss_1` | 10 Mbps | 20 ms | 1% | 100 pkts | Light loss (realistic WiFi) |
| `loss_5` | 10 Mbps | 20 ms | 5% | 100 pkts | Heavy loss (congested wireless) |
| `high_rtt` | 10 Mbps | 100 ms | 0% | 100 pkts | High BDP (satellite/WAN) |
| `small_buffer` | 10 Mbps | 20 ms | 0% | 10 pkts | Shallow buffer (bufferbloat mitigation) |
| `fairness` | 10 Mbps | 20 ms | 0% | 100 pkts | CUBIC vs BBR competing simultaneously |

---

## Output Files

### `results/`

| File | Description |
|------|-------------|
| `<algo>_<scenario>.json` | Raw iperf3 JSON (60s experiment) |
| `cubic_fairness.json` | CUBIC stream in fairness test |
| `bbr_fairness.json` | BBR stream in fairness test |
| `fairness_summary.json` | Aggregated fairness metrics + Jain's FI |
| `summary.csv` | Parsed metrics table (all experiments) |
| `summary_table.md` | Markdown-formatted results table |

### `plots/`

| File | Description |
|------|-------------|
| `throughput_timeseries_<scenario>.png` | Per-second throughput lines (overlaid) |
| `throughput_timeseries_fairness.png` | Fairness test time-series |
| `throughput_bar_<scenario>.png` | Grouped bar: avg throughput per scenario |
| `throughput_bar_all.png` | Mega bar: all scenarios × all algorithms |
| `retransmissions_bar.png` | Retransmit counts grouped bar |
| `fairness_jfi.png` | Jain's Fairness Index bar chart |
| `throughput_heatmap.png` | Heatmap: algorithm × scenario |

---

## Architecture & Script Reference

### `topo.py` — Mininet Topology

Defines `SingleBottleneckTopo` (inherits `mininet.topo.Topo`):

```
h1 ──[1 Gbps, 0ms]──► s1 ──[bw/delay/loss/queue]──► h2
```

- h1 = sender, h2 = receiver, s1 = OVS switch
- All shaping applied on the `s1 → h2` link using `TCLink` (Linux `tc netem + tbf`)
- Can be imported or run standalone for topology validation

### `run_tests.py` — Test Driver

```
For each scenario × algorithm:
  1. Build Mininet with SingleBottleneckTopo (topo_kwargs)
  2. sysctl -w net.ipv4.tcp_congestion_control=<algo>
  3. iperf3 -s on h2 (daemon)
  4. iperf3 -c <h2_ip> -t 60 -i 1 -J on h1
  5. Parse JSON, save to results/<algo>_<scenario>.json
  6. Stop Mininet, clean state, sleep 2s
Fairness:
  1. Start two iperf3 servers (ports 5201, 5202)
  2. Run CUBIC client (-C cubic) and BBR client (-C bbr) concurrently
  3. Save individual JSONs + combined fairness_summary.json
```

### `analyze.py` — Parser & Analyzer

- Reads all `results/*.json` via `json.load()`
- Extracts: `avg_throughput_mbps`, `end_throughput_mbps`, `total_bytes_mb`, `retransmissions`
- Computes Jain's Fairness Index: **J = (Σxᵢ)² / (n · Σxᵢ²)**
- Outputs `results/summary.csv` and a Markdown + ASCII table

### `plot_results.py` — Visualization

- Reads `results/summary.csv` (parsed metrics) + raw JSON (interval data)
- Generates 7 plot types using `matplotlib` with `Agg` backend (no display needed)
- All plots saved at **300 DPI** for publication quality

### `run_all.sh` — Orchestrator

```bash
Root check → Dependency check → mkdir results/ plots/ → mn -c →
modprobe tcp_bbr → python3 run_tests.py → python3 analyze.py →
python3 plot_results.py → Print summary banner
```

---

## Understanding the Results

### Throughput

- **BBR** typically achieves near-line-rate throughput even under loss because it doesn't treat loss as a congestion signal
- **CUBIC** degrades gracefully under loss but can be aggressive in high-BDP paths
- **Reno** is most sensitive to packet loss (backs off on every loss event)

### Retransmissions

- High retransmits + high throughput (BBR) = BBR ignores loss-based backoff
- High retransmits + low throughput (Reno/CUBIC under 5% loss) = algorithms struggling

### Jain's Fairness Index

- **J = 1.0**: Perfectly fair (CUBIC and BBR share bandwidth equally)
- **J > 0.9**: Good fairness
- **J < 0.7**: Poor fairness (one algorithm dominates)
- BBR is known to sometimes under-perform vs CUBIC in fairness tests when competing

---

## Troubleshooting

### `RTNETLINK answers: Operation not permitted`
> Mininet requires root. Always use `sudo`.

### `ovs-vsctl: unix:/var/run/openvswitch/db.sock: …`
```bash
sudo /etc/init.d/openvswitch-switch start
# or
sudo service openvswitch-switch start
```

### `BBR not in available_congestion_control`
```bash
sudo modprobe tcp_bbr
# If unavailable, kernel may not support it:
uname -r     # Must be >= 4.9
```

### `iperf3: error - the server is busy`
```bash
sudo pkill -f iperf3
```

### `mn: command not found` in WSL2
```bash
sudo apt install mininet
# Or build from source:
git clone https://github.com/mininet/mininet && sudo mininet/util/install.sh -a
```

### Empty plots / no CSV
Run steps individually to isolate the failure:
```bash
sudo python3 run_tests.py   # Check for JSON output in results/
python3 analyze.py           # Check for summary.csv
python3 plot_results.py      # Check for PNG files in plots/
```

---

*Generated by TCP Congestion Control Benchmark Suite*
