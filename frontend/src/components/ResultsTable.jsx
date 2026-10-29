import React, { useState } from 'react';

const ALGO_COLORS = {
  reno: '#ef4444',
  cubic: '#3b82f6',
  bbr: '#10b981'
};

export default function ResultsTable({
  results,
  onSelectScenario,
  onClearLive,
  activeScenario
}) {
  const [sourceFilter, setSourceFilter] = useState('all'); // all | historical | live
  const [scenarioFilter, setScenarioFilter] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');

  // Counts
  const totalCount = results.length;
  const liveCount = results.filter(r => r.source === 'live').length;
  const historicalCount = results.filter(r => r.source === 'historical').length;

  // Filtered rows
  const filtered = results.filter(r => {
    if (r.algorithm === 'all') return false; // Sanitize invalid runs
    if (sourceFilter !== 'all' && r.source !== sourceFilter) return false;
    if (scenarioFilter !== 'all' && r.scenario !== scenarioFilter) return false;
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      const matchAlgo = r.algorithm?.toLowerCase().includes(term);
      const matchScenario = r.scenario?.toLowerCase().includes(term);
      if (!matchAlgo && !matchScenario) return false;
    }
    return true;
  });

  // Unique scenarios for filter dropdown
  const uniqueScenarios = Array.from(new Set(results.map(r => r.scenario)));

  return (
    <div className="card">
      <div className="card-title">
        <span>Benchmark Results & Historical Comparisons</span>
        <div style={{ display: 'flex', gap: '8px' }}>
          {liveCount > 0 && (
            <button
              className="btn-secondary"
              onClick={onClearLive}
              style={{ fontSize: '11px', padding: '4px 10px', color: '#f87171', borderColor: 'rgba(239, 68, 68, 0.3)' }}
              title="Remove newly executed live runs"
            >
              Clear Live Runs ({liveCount})
            </button>
          )}
        </div>
      </div>

      {/* Filter Toolbar */}
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '12px',
        marginBottom: '16px',
        padding: '12px',
        background: '#0d1322',
        borderRadius: '8px',
        border: '1px solid #1e293b'
      }}>
        {/* Source Pills */}
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            type="button"
            className={`btn-secondary ${sourceFilter === 'all' ? 'active' : ''}`}
            onClick={() => setSourceFilter('all')}
            style={{
              background: sourceFilter === 'all' ? '#2563eb' : '#111827',
              borderColor: sourceFilter === 'all' ? '#3b82f6' : '#243248',
              color: '#fff'
            }}
          >
            All Results ({totalCount})
          </button>
          <button
            type="button"
            className={`btn-secondary ${sourceFilter === 'historical' ? 'active' : ''}`}
            onClick={() => setSourceFilter('historical')}
            style={{
              background: sourceFilter === 'historical' ? '#2563eb' : '#111827',
              borderColor: sourceFilter === 'historical' ? '#60a5fa' : '#243248',
              color: '#fff'
            }}
          >
            Saved Baseline ({historicalCount})
          </button>
          <button
            type="button"
            className={`btn-secondary ${sourceFilter === 'live' ? 'active' : ''}`}
            onClick={() => setSourceFilter('live')}
            style={{
              background: sourceFilter === 'live' ? '#10b981' : '#111827',
              borderColor: sourceFilter === 'live' ? '#34d399' : '#243248',
              color: '#fff'
            }}
          >
            Live Runs ({liveCount})
          </button>
        </div>

        {/* Search & Scenario Dropdown */}
        <div style={{ display: 'flex', gap: '10px' }}>
          <select
            value={scenarioFilter}
            onChange={(e) => setScenarioFilter(e.target.value)}
            style={{
              background: '#111827',
              border: '1px solid #243248',
              color: '#e2e8f0',
              padding: '6px 12px',
              borderRadius: '6px',
              fontSize: '13px',
              outline: 'none'
            }}
          >
            <option value="all">All Scenarios</option>
            {uniqueScenarios.map(sc => (
              <option key={sc} value={sc}>{sc.toUpperCase()}</option>
            ))}
          </select>

          <input
            type="text"
            placeholder="Search algo or scenario..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              background: '#111827',
              border: '1px solid #243248',
              color: '#e2e8f0',
              padding: '6px 12px',
              borderRadius: '6px',
              fontSize: '13px',
              outline: 'none',
              width: '180px'
            }}
          />
        </div>
      </div>

      {/* Table */}
      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>Source</th>
              <th>Scenario</th>
              <th>Algorithm</th>
              <th>Avg Throughput</th>
              <th>End Throughput</th>
              <th>Total Data</th>
              <th>Retransmissions</th>
              <th>Jain's FI</th>
              <th>Timestamp</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan="10" style={{ textAlign: 'center', padding: '24px', color: '#64748b' }}>
                  No benchmark results matching criteria.
                </td>
              </tr>
            ) : (
              filtered.map((row) => {
                const isSelected = activeScenario === row.scenario;
                const algoColor = ALGO_COLORS[row.algorithm?.toLowerCase()] || '#cbd5e1';

                return (
                  <tr
                    key={row.id}
                    style={{
                      background: isSelected ? 'rgba(37, 99, 235, 0.08)' : 'transparent'
                    }}
                  >
                    <td>
                      {row.source === 'live' ? (
                        <span className="badge badge-live">
                          LIVE RUN
                        </span>
                      ) : (
                        <span className="badge badge-historical">
                          Historical Baseline
                        </span>
                      )}
                    </td>
                    <td style={{ fontWeight: '600', textTransform: 'uppercase' }}>
                      {row.scenario}
                    </td>
                    <td>
                      <span
                        style={{
                          fontWeight: '700',
                          textTransform: 'uppercase',
                          color: algoColor,
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '6px'
                        }}
                      >
                        <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: algoColor }} />
                        {row.algorithm}
                      </span>
                    </td>
                    <td style={{ fontFamily: 'ui-monospace', fontWeight: '700' }}>
                      {row.avg_throughput_mbps?.toFixed(2)} Mbps
                    </td>
                    <td style={{ fontFamily: 'ui-monospace' }}>
                      {row.end_throughput_mbps ? `${row.end_throughput_mbps.toFixed(2)} Mbps` : '—'}
                    </td>
                    <td style={{ fontFamily: 'ui-monospace' }}>
                      {row.total_bytes_mb ? `${row.total_bytes_mb.toFixed(1)} MB` : '—'}
                    </td>
                    <td style={{ fontFamily: 'ui-monospace' }}>
                      {row.retransmissions.toLocaleString()}
                    </td>
                    <td style={{ fontFamily: 'ui-monospace' }}>
                      {row.jfi ? (
                        <span style={{ color: row.jfi > 0.9 ? '#10b981' : '#f59e0b', fontWeight: '700' }}>
                          {row.jfi.toFixed(4)}
                        </span>
                      ) : '—'}
                    </td>
                    <td style={{ fontSize: '11px', color: '#64748b' }}>
                      {row.timestamp ? new Date(row.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn-secondary"
                        style={{ fontSize: '11px', padding: '3px 8px' }}
                        onClick={() => onSelectScenario(row)}
                        title="Display this scenario and algorithm in the interactive chart"
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

