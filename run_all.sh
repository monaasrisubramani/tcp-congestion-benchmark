#!/usr/bin/env bash
# =============================================================================
#  run_all.sh — End-to-End TCP Congestion Control Benchmark Orchestrator
# =============================================================================
#
#  Usage:
#      sudo ./run_all.sh
#
#  What it does (in order):
#    1.  Verifies the script is run as root (Mininet requirement).
#    2.  Verifies required tools are installed (python3, iperf3, mn).
#    3.  Creates results/ and plots/ output directories.
#    4.  Runs 'sudo mn -c' to wipe any stale Mininet state.
#    5.  Loads the tcp_bbr kernel module (warn-only if unavailable).
#    6.  Runs run_tests.py   — executes all iperf3 experiments via Mininet.
#    7.  Runs analyze.py     — parses JSON, computes stats, writes summary.csv.
#    8.  Runs plot_results.py — generates all PNG visualizations.
#    9.  Prints a final summary of output locations.
#
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[0;33m'
BLU='\033[0;34m'; CYN='\033[0;36m'; BLD='\033[1m'; RST='\033[0m'

log_info()  { echo -e "${BLU}[INFO ]${RST}  $*"; }
log_ok()    { echo -e "${GRN}[  OK ]${RST}  $*"; }
log_warn()  { echo -e "${YLW}[WARN ]${RST}  $*"; }
log_error() { echo -e "${RED}[ERROR]${RST}  $*" >&2; }
log_step()  { echo -e "\n${BLD}${CYN}━━━  $*  ━━━${RST}"; }

# ---------------------------------------------------------------------------
# Timestamps / elapsed time
# ---------------------------------------------------------------------------
SCRIPT_START=$(date +%s)

elapsed() {
    local now; now=$(date +%s)
    local diff=$(( now - SCRIPT_START ))
    printf '%dm %02ds' $(( diff / 60 )) $(( diff % 60 ))
}

# ---------------------------------------------------------------------------
# Working directory: always relative to the script's own location
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "\n${BLD}============================================================${RST}"
echo -e "${BLD}   TCP Congestion Control Benchmark Suite${RST}"
echo -e "${BLD}   Comparing: Reno · CUBIC · BBR${RST}"
echo -e "${BLD}============================================================${RST}\n"

# ---------------------------------------------------------------------------
# Step 1 — Root check
# ---------------------------------------------------------------------------
log_step "Step 1: Privilege check"
if [[ "$EUID" -ne 0 ]]; then
    log_error "This script must be run as root. Use: sudo ./run_all.sh"
    exit 1
fi
log_ok "Running as root (UID=$EUID)"

# ---------------------------------------------------------------------------
# Step 2 — Dependency checks
# ---------------------------------------------------------------------------
log_step "Step 2: Dependency checks"

check_cmd() {
    local cmd="$1"
    local pkg="${2:-$1}"
    if command -v "$cmd" &>/dev/null; then
        log_ok "$cmd found: $(command -v "$cmd")"
    else
        log_error "$cmd not found. Install with: sudo apt install $pkg"
        exit 1
    fi
}

check_cmd python3  python3
check_cmd iperf3   iperf3
check_cmd mn       mininet
check_cmd ovs-vsctl openvswitch-switch

# Check Python packages
log_info "Checking Python packages..."
for pkg in mininet pandas matplotlib numpy; do
    if python3 -c "import $pkg" 2>/dev/null; then
        log_ok "  Python package '$pkg' available"
    else
        log_warn "  Python package '$pkg' not found — some features may fail"
        log_warn "  Install: sudo pip3 install $pkg  OR  sudo apt install python3-$pkg"
    fi
done

# ---------------------------------------------------------------------------
# Step 3 — Create output directories
# ---------------------------------------------------------------------------
log_step "Step 3: Creating output directories"
mkdir -p results plots
log_ok "results/ and plots/ directories ready"

# ---------------------------------------------------------------------------
# Step 4 — Clean previous Mininet state
# ---------------------------------------------------------------------------
log_step "Step 4: Cleaning stale Mininet state"
log_info "Running 'mn -c'..."
mn -c 2>&1 | head -20 || true
log_ok "Mininet cleanup complete"

# Kill any lingering iperf3 processes
log_info "Killing any lingering iperf3 processes..."
pkill -f iperf3 2>/dev/null || true
sleep 1
log_ok "iperf3 processes cleared"

# ---------------------------------------------------------------------------
# Step 5 — Load BBR kernel module
# ---------------------------------------------------------------------------
log_step "Step 5: Loading BBR kernel module"
if modprobe tcp_bbr 2>/dev/null; then
    log_ok "tcp_bbr module loaded"
else
    log_warn "Could not load tcp_bbr (may already be built-in or unavailable)"
    log_warn "BBR experiments will be skipped if not available"
fi

# Show available CC algorithms
AVAIL_CC=$(cat /proc/sys/net/ipv4/tcp_available_congestion_control 2>/dev/null || echo "unknown")
log_info "Available CC algorithms: $AVAIL_CC"

# ---------------------------------------------------------------------------
# Step 6 — Run experiments
# ---------------------------------------------------------------------------
log_step "Step 6: Running Mininet experiments (this will take a while…)"

ESTIMATED_MINS=$(python3 -c "
algos = [a for a in ['reno','cubic','bbr'] if a in '$AVAIL_CC']
scenarios = 5
duration = 60
total_s = len(algos) * scenarios * duration + (duration + 10)
print(f'{total_s//60}m {total_s%60}s (~{(total_s//60)+1} min)')
" 2>/dev/null || echo "~20+ min")
log_info "Estimated runtime: $ESTIMATED_MINS"
log_info "Starting: python3 run_tests.py"
echo ""

if python3 run_tests.py; then
    log_ok "run_tests.py completed successfully"
else
    log_error "run_tests.py exited with errors (partial results may exist)"
    log_warn  "Continuing to analysis with whatever results were produced..."
fi

# Final cleanup after test suite
log_info "Post-experiment Mininet cleanup..."
mn -c 2>/dev/null || true
pkill -f iperf3 2>/dev/null || true

# ---------------------------------------------------------------------------
# Step 7 — Analyze results
# ---------------------------------------------------------------------------
log_step "Step 7: Analyzing results"

JSON_COUNT=$(ls results/*.json 2>/dev/null | wc -l)
if [[ "$JSON_COUNT" -eq 0 ]]; then
    log_error "No JSON result files found in results/. Did run_tests.py produce any output?"
    exit 1
fi
log_info "Found $JSON_COUNT JSON result file(s)"

if python3 analyze.py; then
    log_ok "analyze.py completed successfully"
else
    log_error "analyze.py failed"
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 8 — Generate plots
# ---------------------------------------------------------------------------
log_step "Step 8: Generating plots"

if [[ ! -f "results/summary.csv" ]]; then
    log_error "results/summary.csv not found. Did analyze.py succeed?"
    exit 1
fi

if python3 plot_results.py; then
    log_ok "plot_results.py completed successfully"
else
    log_error "plot_results.py failed"
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 9 — Final summary
# ---------------------------------------------------------------------------
log_step "Step 9: Done!"

TOTAL_ELAPSED=$(elapsed)
PNG_COUNT=$(ls plots/*.png 2>/dev/null | wc -l)
CSV_COUNT=$(ls results/*.csv 2>/dev/null | wc -l)
JSON_FINAL=$(ls results/*.json 2>/dev/null | wc -l)

echo -e "\n${BLD}${GRN}╔══════════════════════════════════════════════════════════╗${RST}"
echo -e "${BLD}${GRN}║            BENCHMARK SUITE — COMPLETE ✓                  ║${RST}"
echo -e "${BLD}${GRN}╠══════════════════════════════════════════════════════════╣${RST}"
echo -e "${GRN}║${RST}  Total elapsed time : ${BLD}$TOTAL_ELAPSED${RST}"
echo -e "${GRN}║${RST}  JSON results       : ${BLD}$JSON_FINAL file(s)${RST} in ${CYN}$(realpath results/)${RST}"
echo -e "${GRN}║${RST}  CSV summaries      : ${BLD}$CSV_COUNT file(s)${RST} in ${CYN}$(realpath results/)${RST}"
echo -e "${GRN}║${RST}  Plots generated    : ${BLD}$PNG_COUNT PNG(s)${RST}  in ${CYN}$(realpath plots/)${RST}"
echo -e "${BLD}${GRN}╠══════════════════════════════════════════════════════════╣${RST}"
echo -e "${GRN}║${RST}  Key outputs:                                              "
echo -e "${GRN}║${RST}    • results/summary.csv        — machine-readable metrics "
echo -e "${GRN}║${RST}    • results/summary_table.md   — Markdown results table   "
echo -e "${GRN}║${RST}    • plots/throughput_bar_all.png  — combined bar chart    "
echo -e "${GRN}║${RST}    • plots/throughput_heatmap.png  — algorithm × scenario  "
echo -e "${GRN}║${RST}    • plots/fairness_jfi.png         — Jain's fairness      "
echo -e "${BLD}${GRN}╚══════════════════════════════════════════════════════════╝${RST}\n"
