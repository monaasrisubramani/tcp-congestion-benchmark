#!/usr/bin/env python3
"""
server.py — TCP Congestion Control Benchmark Server
===================================================
Launches FastAPI + Uvicorn server in WSL2/Linux. If FastAPI is not installed,
it provides an automated built-in fallback server using Python's standard library
so the React dashboard runs immediately without dependency friction.

Usage:
    # Run with root inside WSL2 (recommended for real Mininet execution):
    sudo python3 server.py

    # Or run in standard mode (simulation mode active):
    python3 server.py
"""

import sys
import os
import json
import urllib.parse
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

# Ensure workspace root is in python path
WORKSPACE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from backend.storage import (
    get_all_results,
    get_timeseries_for_scenario,
    get_fairness_data,
    SCENARIOS_META,
    LIVE_RESULTS_DIR,
    ensure_storage_dirs
)
from backend.runner import runner

PORT = 8000
HOST = "0.0.0.0"
FRONTEND_DIST = WORKSPACE_ROOT / "frontend" / "dist"


# ---------------------------------------------------------------------------
# Fallback Built-in HTTP Server (Zero Dependencies)
# ---------------------------------------------------------------------------

class BenchmarkRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIST), **kwargs)

    def end_headers(self):
        # Enable CORS and disable aggressive caching for dev
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def send_json(self, data, status=200):
        body = json.dumps(data, indent=2).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        # ── API Routes ──
        if path == '/api/health':
            env = runner.check_environment()
            status = runner.get_status()
            self.send_json({
                'status': 'healthy',
                'environment': env,
                'is_job_running': status['is_running'],
                'job_status': status['status']
            })
            return

        elif path == '/api/scenarios':
            self.send_json(SCENARIOS_META)
            return

        elif path == '/api/results':
            source = query.get('source', ['all'])[0]
            scenario = query.get('scenario', [None])[0]
            results = get_all_results()
            if source in ['historical', 'live']:
                results = [r for r in results if r['source'] == source]
            if scenario:
                results = [r for r in results if r['scenario'] == scenario]
            self.send_json({'count': len(results), 'results': results})
            return

        elif path.startswith('/api/timeseries/'):
            scenario = path.replace('/api/timeseries/', '').strip('/')
            source = query.get('source', ['all'])[0]
            data = get_timeseries_for_scenario(scenario, source=source)
            self.send_json(data)
            return

        elif path == '/api/fairness':
            self.send_json(get_fairness_data())
            return

        elif path == '/api/run/status':
            self.send_json(runner.get_status())
            return

        # ── Static Frontend ──
        if path.startswith('/assets/'):
            asset_file = FRONTEND_DIST / path.lstrip('/')
            if asset_file.exists() and asset_file.is_file():
                return super().do_GET()

        # SPA routing: fallback to index.html
        index_file = FRONTEND_DIST / 'index.html'
        if index_file.exists():
            self.path = '/index.html'
            return super().do_GET()

        self.send_json({'message': 'TCP Benchmark Suite API is running', 'path': path})

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        content_length = int(self.headers.get('Content-Length', 0))
        body_bytes = self.rfile.read(content_length)
        body = {}
        if body_bytes:
            try:
                body = json.loads(body_bytes.decode('utf-8'))
            except Exception:
                pass

        if path == '/api/run':
            res = runner.start_experiment(body)
            if 'error' in res:
                self.send_json({'detail': res['error']}, status=400)
            else:
                self.send_json(res)
            return

        elif path == '/api/run/cancel':
            runner.cancel()
            self.send_json({'status': 'cancellation_requested'})
            return

        self.send_json({'detail': 'Not found'}, status=404)

    def do_DELETE(self):
        parsed_url = urllib.parse.urlparse(self.path)
        if parsed_url.path == '/api/results/live':
            if LIVE_RESULTS_DIR.exists():
                for f in LIVE_RESULTS_DIR.glob('*.json'):
                    try:
                        f.unlink()
                    except Exception:
                        pass
            self.send_json({'status': 'cleared', 'message': 'Live results deleted'})
            return
        self.send_json({'detail': 'Not found'}, status=404)


def run_fallback_server():
    print(f"\n============================================================")
    print(f"  TCP Congestion Control Benchmark Server")
    print(f"  Running on: http://localhost:{PORT}")
    print(f"  Backend:    Zero-Dependency Built-in Server")
    print(f"  Root/sudo:  {'YES (Mininet Active)' if os.name == 'posix' and os.geteuid() == 0 else 'NO (Simulation Mode)'}")
    print(f"============================================================\n")
    ensure_storage_dirs()
    server = ThreadingHTTPServer((HOST, PORT), BenchmarkRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()


def main():
    # If fastapi and uvicorn are available, launch uvicorn
    try:
        import fastapi
        import uvicorn
        print(f"FastAPI & Uvicorn detected. Launching production ASGI server...")
        uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=True)
    except ImportError:
        run_fallback_server()


if __name__ == '__main__':
    main()

