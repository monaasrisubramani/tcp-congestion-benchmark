# TCP Congestion Control Benchmark — React Dashboard

An interactive, modern dashboard for benchmarking, visualizing, and analyzing **TCP Reno**, **TCP CUBIC**, and **TCP BBR** congestion control algorithms.

---

## Architecture Overview

```
tcp-congestion-benchmark/
├── backend/
│   ├── main.py              # FastAPI application & REST endpoints
│   ├── runner.py            # Mininet & iperf3 execution manager (background thread, cancellation, progress)
│   ├── storage.py           # Historical vs live runs parser & telemetry extractor
│   └── requirements.txt     # FastAPI, Uvicorn, Pydantic dependencies
├── frontend/
│   ├── index.html           # Vite HTML entry point
│   ├── package.json         # React 18 & Vite configuration
│   ├── vite.config.js       # Vite configuration with /api reverse proxy
│   ├── src/
│   │   ├── main.jsx         # React application entry
│   │   ├── App.jsx          # Master dashboard layout & state orchestrator
│   │   ├── index.css        # Dashboard styling & color variables
│   │   ├── api/client.js    # API communication layer
│   │   └── components/
│   │       ├── Navbar.jsx               # Header with backend health & WSL2 status
│   │       ├── MetricCards.jsx          # Key performance indicators
│   │       ├── ControlPanel.jsx         # Algorithm, scenario & custom parameter sliders
│   │       ├── ThroughputChart.jsx      # Interactive SVG timeseries chart
│   │       ├── RetransmissionsChart.jsx # Grouped retransmissions bar chart
│   │       ├── FairnessGauge.jsx        # Jain's Fairness Index & flow share widget
│   │       ├── ResultsTable.jsx         # Historical vs Live results comparison table
│   │       └── ExecutionModal.jsx       # Live experiment progress, logs & error diagnosis
│   └── dist/                # Zero-setup pre-built bundle served directly by the backend
├── server.py                # Standalone universal server (FastAPI or built-in fallback)
├── start_backend.sh         # One-click startup script for Ubuntu / WSL2
└── README_UI.md             # This guide
```

---

## Running the Application

You can run the dashboard in two ways:
- **Option A (Zero-Setup)**: Run the backend inside WSL2; the web dashboard is served directly at `http://localhost:8000`.
- **Option B (VS Code Developer Workflow)**: Run the backend inside WSL2 and the Vite React development server in VS Code with hot-reloading at `http://localhost:5173`.

---

### Option A: Direct Backend Serving (Zero Build Step)

1. **Open WSL2 (Ubuntu) in your terminal**:
   ```bash
   cd ~/tcp-congestion-benchmark   # or the path where this repository is located
   ```

2. **Start Open vSwitch and grant execution permissions**:
   ```bash
   sudo /etc/init.d/openvswitch-switch start
   sudo modprobe tcp_bbr
   chmod +x start_backend.sh
   ```

3. **Launch the Benchmark Server with root privileges** (required for Mininet `tc` network shaping):
   ```bash
   sudo ./start_backend.sh
   # (Or: sudo bash start_backend.sh  /  sudo python3 server.py)
   ```

4. **Open your browser**:
   Navigate to **`http://localhost:8000`** (or `http://127.0.0.1:8000`).
   The React dashboard will load immediately with all baseline benchmark data.

---

### Option B: VS Code + Vite Development Mode (Live Hot Reloading)

If you are developing or modifying the React components:

1. **Terminal 1 (WSL2 Backend)**:
   ```bash
   sudo ./start_backend.sh
   ```
   *The API will be available at `http://localhost:8000/api`.*

2. **Terminal 2 (VS Code / Host)**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   *Vite starts at `http://localhost:5173` and automatically proxies `/api` calls to `http://localhost:8000`.*

---

## Features & UI Walkthrough

### 1. Algorithm Selection
- **Reno**: Additive-increase / multiplicative-decrease (AIMD). Highly sensitive to packet drops.
- **CUBIC**: Linux default. Cubic window growth function optimized for high-BDP paths.
- **BBR**: Google's model-based pacing algorithm. Estimates bottleneck bandwidth and RTT independently of packet loss.
- **Compare All**: Overlays all three algorithms simultaneously on the same scenario.

### 2. Scenario Presets & Custom Configuration
- **Baseline**: 10 Mbps, 20 ms delay, 0% loss, 100 packet queue buffer.
- **1% Loss**: Simulates typical home Wi-Fi and light packet loss.
- **5% Loss**: Simulates congested or degraded wireless connections.
- **High RTT**: 100 ms delay, evaluating high-BDP long-distance links.
- **Small Buffer**: 10 packet queue, evaluating bufferbloat mitigation and shallow buffer tail-drops.
- **Fairness**: CUBIC and BBR competing concurrently on a shared 10 Mbps bottleneck.
- **Custom Controls**: Real-time sliders for Bandwidth (1–100 Mbps), One-Way Delay (1–200 ms), Packet Loss (0–10%), Queue Size (5–300 pkts), and Test Duration (5–60s).

### 3. Interactive Visualizations
- **Throughput Time-Series Chart**:
  - Overlaid 60-second telemetry curves for Reno (red), CUBIC (blue), and BBR (green).
  - Theoretical line rate limit indicator.
  - Interactive hover crosshair and tooltips showing exact timestamp and throughput.
  - Clickable legend pills to show/hide specific algorithms.
- **Retransmissions Comparison Bar Chart**:
  - Highlights the contrast between BBR's rate pacing (higher retransmissions under loss without throughput penalty) vs Reno/CUBIC window backoff.
- **Fairness & Jain's Fairness Index Gauge**:
  - Displays Jain's Fairness Index ($JFI \approx 0.917$) with qualitative ratings and bandwidth split bars.

### 4. Results Table & Live Run Tracking
- **Historical Baseline vs Live Runs**:
  - Saved benchmarks have a distinct `[Historical Baseline]` badge.
  - Newly executed live tests are badged as `[LIVE RUN]` with exact timestamps and live telemetry.
- **Filter Toolbar**:
  - Toggle between `All Results`, `Saved Baseline`, and `Live Runs`.
  - Filter by scenario or search by algorithm.
  - "Inspect" button to load any row's scenario directly into the active charts.
  - "Clear Live Runs" button to reset newly created runs while preserving historical baselines.

### 5. Live Execution & Error Diagnosis
- Clicking **Run Experiment**:
  - Displays a live progress overlay with animated percentage bar, elapsed/estimated time, and stage descriptions (Initializing topology $\rightarrow$ Setting CC $\rightarrow$ Measuring with iperf3 $\rightarrow$ Computing telemetry).
  - Streams real-time terminal output logs.
  - Includes a **Cancel Experiment** button to abort execution safely.
  - If started without root privileges, provides actionable troubleshooting advice and allows toggling **Simulation Mode** to preview UI workflows without sudo.

---

## Preserved Files & Clean Architecture
All existing scripts (`topo.py`, `run_tests.py`, `analyze.py`, `plot_results.py`, `run_all.sh`) and existing results in `results/` and `plots/` have been strictly preserved. Newly executed live runs are stored in `results/live_runs/` to maintain clean separation.

