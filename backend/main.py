"""
backend/main.py — FastAPI Application for TCP Congestion Control Benchmark
===========================================================================
Serves REST endpoints for system status, experiment execution, telemetry,
and static frontend distribution.
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from backend.storage import (
    get_all_results,
    get_timeseries_for_scenario,
    get_fairness_data,
    SCENARIOS_META,
    LIVE_RESULTS_DIR
)
from backend.runner import runner

app = FastAPI(
    title="TCP Congestion Control Benchmark API",
    description="Interactive benchmark dashboard backend for Reno, CUBIC, and BBR evaluation",
    version="1.0.0"
)

# Enable CORS for local Vite development server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class ExperimentConfig(BaseModel):
    algorithm: str = Field(default="bbr", description="reno | cubic | bbr | all | fairness")
    scenario: str = Field(default="baseline", description="baseline | loss_1 | loss_5 | high_rtt | small_buffer | fairness | custom")
    bw: float = Field(default=10.0, ge=1.0, le=1000.0, description="Bandwidth in Mbps")
    delay: str = Field(default="20ms", description="One-way propagation delay string (e.g. 20ms)")
    loss: float = Field(default=0.0, ge=0.0, le=50.0, description="Packet loss percentage")
    queue: int = Field(default=100, ge=1, le=5000, description="Buffer queue size in packets")
    duration: int = Field(default=15, ge=5, le=120, description="Duration in seconds")
    simulate: bool = Field(default=False, description="Explicitly use high-fidelity simulation")


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def get_health():
    """Returns system diagnostic information and Mininet/WSL2 execution readiness."""
    env = runner.check_environment()
    status = runner.get_status()
    return {
        "status": "healthy",
        "environment": env,
        "is_job_running": status["is_running"],
        "job_status": status["status"]
    }


@app.get("/api/scenarios")
def get_scenarios():
    """Returns predefined scenario configurations."""
    return SCENARIOS_META


@app.get("/api/results")
def list_results(
    source: Optional[str] = Query("all", description="all | historical | live"),
    scenario: Optional[str] = Query(None, description="Filter by scenario")
):
    """
    Returns benchmark results list with full distinction between
    Historical Baseline data and Live Experiment runs.
    """
    results = get_all_results()
    if source in ["historical", "live"]:
        results = [r for r in results if r["source"] == source]
    if scenario:
        results = [r for r in results if r["scenario"] == scenario]

    return {
        "count": len(results),
        "results": results
    }


@app.get("/api/results/{result_id}")
def get_single_result(result_id: str):
    """Returns details and time-series for a specific experiment run."""
    results = get_all_results()
    item = next((r for r in results if r["id"] == result_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Experiment result not found.")
    return item


@app.get("/api/timeseries/{scenario}")
def get_scenario_timeseries(
    scenario: str,
    source: str = Query("all", description="all | historical | live")
):
    """Returns overlaid interval time-series data for algorithms in a scenario."""
    return get_timeseries_for_scenario(scenario, source=source)


@app.get("/api/fairness")
def get_fairness():
    """Returns CUBIC vs BBR fairness competition telemetry and Jain's Index."""
    return get_fairness_data()


@app.post("/api/run")
def trigger_run(config: ExperimentConfig):
    """Triggers a live benchmark experiment inside Mininet or simulation mode."""
    res = runner.start_experiment(config.dict())
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@app.get("/api/run/status")
def poll_run_status():
    """Polls the status, live progress percentage, stage description, and logs."""
    return runner.get_status()


@app.post("/api/run/cancel")
def cancel_current_run():
    """Aborts a currently running experiment."""
    runner.cancel()
    return {"status": "cancellation_requested"}


@app.delete("/api/results/live")
def clear_live_results():
    """Clears all live experiment runs, preserving historical baseline data."""
    if LIVE_RESULTS_DIR.exists():
        for f in LIVE_RESULTS_DIR.glob("*.json"):
            try:
                f.unlink()
            except Exception:
                pass
    return {"status": "cleared", "message": "All live run results cleared."}


# ---------------------------------------------------------------------------
# Static frontend mounting (production or standalone mode)
# ---------------------------------------------------------------------------

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        file_path = FRONTEND_DIST / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    def root_fallback():
        return {
            "message": "TCP Congestion Control Benchmark API is running.",
            "docs": "/docs",
            "frontend_note": "Frontend dist not built yet. Start frontend with 'npm run dev' inside frontend/ directory."
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

