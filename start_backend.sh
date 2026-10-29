#!/usr/bin/env bash
# =============================================================================
#  start_backend.sh — Start FastAPI Backend for TCP Benchmark UI in WSL2/Linux
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo " Starting TCP Congestion Control Benchmark API Server"
echo "============================================================"

# Ensure root privileges for Mininet/tc
if [[ "$EUID" -ne 0 ]]; then
    echo "[WARN] Not running as root (UID=$EUID)."
    echo "[WARN] Mininet network emulation requires root (sudo)."
    echo "[WARN] Live runs will fall back to simulation mode unless run with 'sudo ./start_backend.sh'."
    echo ""
fi

# Load BBR module if available
if modprobe tcp_bbr 2>/dev/null; then
    echo "[OK] BBR kernel module loaded."
else
    echo "[INFO] tcp_bbr module already loaded or built-in."
fi

# Ensure output directories exist
mkdir -p results/live_runs plots

# Install backend dependencies if missing
if ! python3 -c "import fastapi, uvicorn" 2>/dev/null; then
    echo "[INFO] Installing FastAPI and Uvicorn..."
    pip3 install -r backend/requirements.txt 2>/dev/null || apt-get install -y python3-fastapi python3-uvicorn 2>/dev/null || true
fi

echo ""
echo "API Server starting on http://0.0.0.0:8000"
echo "Press Ctrl+C to stop."
echo "============================================================"

python3 server.py
