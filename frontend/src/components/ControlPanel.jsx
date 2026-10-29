import React from 'react';

const SCENARIOS = [
  { id: 'baseline', label: 'Baseline', bw: 10, delay: '20ms', loss: 0, queue: 100 },
  { id: 'loss_1', label: '1% Loss', bw: 10, delay: '20ms', loss: 1, queue: 100 },
  { id: 'loss_5', label: '5% Loss', bw: 10, delay: '20ms', loss: 5, queue: 100 },
  { id: 'high_rtt', label: 'High RTT', bw: 10, delay: '100ms', loss: 0, queue: 100 },
  { id: 'small_buffer', label: 'Small Buffer', bw: 10, delay: '20ms', loss: 0, queue: 10 },
  { id: 'fairness', label: 'Fairness', bw: 10, delay: '20ms', loss: 0, queue: 100 },
  { id: 'custom', label: 'Custom', bw: 10, delay: '20ms', loss: 0, queue: 100 },
];

export default function ControlPanel({
  selectedAlgo,
  setSelectedAlgo,
  selectedScenario,
  setSelectedScenario,
  params,
  setParams,
  onRun,
  isRunning,
  canRunRealMininet
}) {
  const handleScenarioChange = (scId) => {
    setSelectedScenario(scId);
    const preset = SCENARIOS.find(s => s.id === scId);
    if (preset && scId !== 'custom') {
      setParams(prev => ({
        ...prev,
        bw: preset.bw,
        delay: preset.delay,
        loss: preset.loss,
        queue: preset.queue
      }));
    }
  };

  return (
    <div className="card">
      <div className="card-title">
        <span>Experiment Configuration</span>
        <span style={{ fontSize: '12px', fontWeight: '500', color: '#9ca3af' }}>Mininet + iperf3</span>
      </div>

      {/* 1. Algorithm Selection */}
      <div style={{ marginBottom: '16px' }}>
        <div className="param-header">
          <span>Congestion Control Algorithm</span>
        </div>
        <div className="algo-picker">
          <button
            type="button"
            className={`algo-btn ${selectedAlgo === 'reno' ? 'active-reno' : ''}`}
            onClick={() => setSelectedAlgo('reno')}
          >
            <span>Reno</span>
            <span className="algo-sub">AIMD Classic</span>
          </button>
          <button
            type="button"
            className={`algo-btn ${selectedAlgo === 'cubic' ? 'active-cubic' : ''}`}
            onClick={() => setSelectedAlgo('cubic')}
          >
            <span>CUBIC</span>
            <span className="algo-sub">Linux Default</span>
          </button>
          <button
            type="button"
            className={`algo-btn ${selectedAlgo === 'bbr' ? 'active-bbr' : ''}`}
            onClick={() => setSelectedAlgo('bbr')}
          >
            <span>BBR</span>
            <span className="algo-sub">Google Model</span>
          </button>
          <button
            type="button"
            className={`algo-btn ${selectedAlgo === 'all' ? 'active-all' : ''}`}
            onClick={() => setSelectedAlgo('all')}
          >
            <span>Compare All</span>
            <span className="algo-sub">Reno/CUBIC/BBR</span>
          </button>
        </div>
      </div>

      {/* 2. Scenario Presets */}
      <div style={{ marginBottom: '20px' }}>
        <div className="param-header">
          <span>Network Scenario Preset</span>
        </div>
        <div className="scenario-list">
          {SCENARIOS.map(sc => (
            <button
              key={sc.id}
              type="button"
              className={`scenario-pill ${selectedScenario === sc.id ? 'active' : ''}`}
              onClick={() => handleScenarioChange(sc.id)}
            >
              {sc.label}
            </button>
          ))}
        </div>
      </div>

      {/* 3. Configurable Parameters */}
      <div className="param-group">
        <div className="param-header">
          <span>Bottleneck Bandwidth</span>
          <span className="param-value">{params.bw} Mbps</span>
        </div>
        <input
          type="range"
          min="1"
          max="100"
          step="1"
          value={params.bw}
          disabled={isRunning}
          onChange={(e) => {
            setSelectedScenario('custom');
            setParams(p => ({ ...p, bw: Number(e.target.value) }));
          }}
          className="param-slider"
        />
      </div>

      <div className="param-group">
        <div className="param-header">
          <span>One-Way Propagation Delay</span>
          <span className="param-value">{params.delay}</span>
        </div>
        <input
          type="range"
          min="1"
          max="200"
          step="5"
          value={parseInt(params.delay, 10) || 20}
          disabled={isRunning}
          onChange={(e) => {
            setSelectedScenario('custom');
            setParams(p => ({ ...p, delay: `${e.target.value}ms` }));
          }}
          className="param-slider"
        />
      </div>

      <div className="param-group">
        <div className="param-header">
          <span>Packet Loss Rate</span>
          <span className="param-value">{params.loss}%</span>
        </div>
        <input
          type="range"
          min="0"
          max="10"
          step="0.5"
          value={params.loss}
          disabled={isRunning}
          onChange={(e) => {
            setSelectedScenario('custom');
            setParams(p => ({ ...p, loss: Number(e.target.value) }));
          }}
          className="param-slider"
        />
      </div>

      <div className="param-group">
        <div className="param-header">
          <span>Switch Queue Buffer</span>
          <span className="param-value">{params.queue} pkts</span>
        </div>
        <input
          type="range"
          min="5"
          max="300"
          step="5"
          value={params.queue}
          disabled={isRunning}
          onChange={(e) => {
            setSelectedScenario('custom');
            setParams(p => ({ ...p, queue: Number(e.target.value) }));
          }}
          className="param-slider"
        />
      </div>

      <div className="param-group" style={{ marginBottom: '24px' }}>
        <div className="param-header">
          <span>Experiment Duration</span>
          <span className="param-value">{params.duration} seconds</span>
        </div>
        <input
          type="range"
          min="5"
          max="60"
          step="5"
          value={params.duration}
          disabled={isRunning}
          onChange={(e) => setParams(p => ({ ...p, duration: Number(e.target.value) }))}
          className="param-slider"
        />
      </div>

      {/* Simulation Mode Toggle (Useful for Windows/non-root development) */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '10px 14px',
        background: '#0d1322',
        borderRadius: '8px',
        marginBottom: '20px',
        border: '1px solid #1e293b'
      }}>
        <div>
          <div style={{ fontSize: '13px', fontWeight: '600' }}>Simulation Mode</div>
          <div style={{ fontSize: '11px', color: '#9ca3af' }}>
            {canRunRealMininet
              ? 'Execute via mathematical model instead of kernel Mininet'
              : 'Auto-enabled (root / Mininet requires sudo in WSL2)'}
          </div>
        </div>
        <input
          type="checkbox"
          checked={params.simulate}
          disabled={isRunning}
          onChange={(e) => setParams(p => ({ ...p, simulate: e.target.checked }))}
          style={{ width: '18px', height: '18px', cursor: 'pointer', accentColor: '#3b82f6' }}
        />
      </div>

      {/* Primary Action Button */}
      <button
        type="button"
        className="btn-primary"
        disabled={isRunning}
        onClick={onRun}
      >
        {isRunning ? (
          <>
            <span style={{ display: 'inline-block', animation: 'spin 1s linear infinite' }}>⏳</span>
            <span>Running Benchmark...</span>
          </>
        ) : (
          <>
            <span>🚀</span>
            <span>Run Experiment</span>
          </>
        )}
      </button>
    </div>
  );
}

