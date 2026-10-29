import React from 'react';

export default function Navbar({ health, onRefresh, isRefreshing }) {
  const isConnected = !!health;
  const isRoot = health?.environment?.is_root;
  const isLinux = health?.environment?.is_linux;
  const bbrLoaded = health?.environment?.bbr_loaded;

  return (
    <header className="navbar">
      <div className="nav-brand">
        <div className="brand-icon">TCP</div>
        <div>
          <div className="brand-title">TCP Congestion Control Benchmark</div>
          <div className="brand-subtitle">Reno · CUBIC · BBR Performance Evaluation</div>
        </div>
      </div>

      <div className="nav-status">
        {isConnected ? (
          <span className="badge badge-connected" title="FastAPI backend connected">
            <span className="badge-dot" />
            Backend Connected
          </span>
        ) : (
          <span className="badge badge-offline" title="FastAPI backend not detected at /api">
            <span className="badge-dot" />
            Backend Disconnected
          </span>
        )}

        {isLinux && (
          <span
            className="badge"
            style={{
              background: isRoot ? 'rgba(16, 185, 129, 0.12)' : 'rgba(245, 158, 11, 0.12)',
              color: isRoot ? '#34d399' : '#fbbf24',
              borderColor: isRoot ? 'rgba(16, 185, 129, 0.3)' : 'rgba(245, 158, 11, 0.3)'
            }}
            title={isRoot ? 'Running as root (Mininet ready)' : 'Not root (Simulation mode will be used)'}
          >
            {isRoot ? 'WSL2 (Root / Mininet)' : 'WSL2 (Non-root / Sim)'}
          </span>
        )}

        {bbrLoaded && (
          <span className="badge" style={{ background: '#1e293b', color: '#10b981', borderColor: '#10b981' }}>
            tcp_bbr Active
          </span>
        )}

        <button
          className="btn-secondary"
          onClick={onRefresh}
          disabled={isRefreshing}
          title="Reload latest benchmark results"
        >
          {isRefreshing ? 'Refreshing...' : '🔄 Refresh Data'}
        </button>
      </div>
    </header>
  );
}

