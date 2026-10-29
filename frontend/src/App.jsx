import React, { useState, useEffect, useRef } from 'react';
import Navbar from './components/Navbar';
import MetricCards from './components/MetricCards';
import ControlPanel from './components/ControlPanel';
import ThroughputChart from './components/ThroughputChart';
import RetransmissionsChart from './components/RetransmissionsChart';
import FairnessGauge from './components/FairnessGauge';
import ResultsTable from './components/ResultsTable';
import ExecutionModal from './components/ExecutionModal';

import {
  fetchHealth,
  fetchResults,
  fetchTimeseries,
  fetchFairness,
  startExperiment,
  pollStatus,
  cancelExperiment,
  clearLiveResults
} from './api/client';

export default function App() {
  const [health, setHealth] = useState(null);
  const [results, setResults] = useState([]);
  const [fairnessData, setFairnessData] = useState(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Configuration state
  const [selectedAlgo, setSelectedAlgo] = useState('bbr');
  const [selectedScenario, setSelectedScenario] = useState('baseline');
  const [selectedSource, setSelectedSource] = useState('all'); // all | historical | live
  const [params, setParams] = useState({
    bw: 10,
    delay: '20ms',
    loss: 0,
    queue: 100,
    duration: 15,
    simulate: false
  });

  // Telemetry for charts
  const [timeseriesData, setTimeseriesData] = useState(null);

  // Execution state
  const [jobStatus, setJobStatus] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const pollIntervalRef = useRef(null);

  // Initial load
  useEffect(() => {
    loadAllData();
    checkSystemHealth();
  }, []);

  // Update timeseries when scenario or source changes
  useEffect(() => {
    loadTimeseries(selectedScenario, selectedSource);
  }, [selectedScenario, selectedSource]);

  const checkSystemHealth = async () => {
    try {
      const h = await fetchHealth();
      setHealth(h);
      if (!h.environment?.can_run_real_mininet) {
        setParams(p => ({ ...p, simulate: true }));
      }
    } catch {
      setHealth(null);
      setParams(p => ({ ...p, simulate: true }));
    }
  };

  const loadAllData = async () => {
    setIsRefreshing(true);
    try {
      const [resData, fairData] = await Promise.all([
        fetchResults('all'),
        fetchFairness()
      ]);
      setResults(resData.results || []);
      setFairnessData(fairData);
      await loadTimeseries(selectedScenario, selectedSource);
    } catch (e) {
      console.warn('Could not load data from API:', e);
    } finally {
      setIsRefreshing(false);
    }
  };

  const loadTimeseries = async (scenario, source = null) => {
    try {
      const src = source || selectedSource || 'all';
      const ts = await fetchTimeseries(scenario, src);
      setTimeseriesData(ts);
    } catch (e) {
      console.warn('Could not load timeseries:', e);
    }
  };

  // Run live experiment
  const handleRun = async () => {
    try {
      setShowModal(true);
      const res = await startExperiment({
        algorithm: selectedAlgo,
        scenario: selectedScenario,
        bw: params.bw,
        delay: params.delay,
        loss: params.loss,
        queue: params.queue,
        duration: params.duration,
        simulate: params.simulate
      });

      // Start polling
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = setInterval(async () => {
        try {
          const status = await pollStatus();
          setJobStatus(status);
          if (!status.is_running && status.status !== 'starting') {
            clearInterval(pollIntervalRef.current);
            setSelectedSource('live');
            await loadAllData();
            await loadTimeseries(selectedScenario, 'live');
          }
        } catch {
          clearInterval(pollIntervalRef.current);
        }
      }, 500);

    } catch (err) {
      setJobStatus({
        status: 'error',
        is_running: false,
        error_message: err.message,
        step_description: 'Failed to initiate benchmark job.',
        logs: [`[ERROR] ${err.message}`]
      });
    }
  };

  const handleCancel = async () => {
    try {
      await cancelExperiment();
    } catch (e) {
      console.error(e);
    }
  };

  const handleDismissModal = () => {
    setShowModal(false);
    if (!jobStatus?.is_running) {
      setJobStatus(null);
    }
  };

  const handleClearLive = async () => {
    if (window.confirm('Clear all live experiment runs and keep only baseline results?')) {
      await clearLiveResults();
      loadAllData();
    }
  };

  const canRunRealMininet = health?.environment?.can_run_real_mininet ?? false;

  const scenarioResults = results.filter(r => r.scenario === selectedScenario);
  const liveResults = scenarioResults.filter(r => r.source === 'live');
  const histResults = scenarioResults.filter(r => r.source === 'historical');

  let effectiveSource = selectedSource;
  if (effectiveSource === 'all') {
    effectiveSource = (selectedScenario === 'custom' || liveResults.length > 0) ? 'live' : 'historical';
  }
  if (selectedScenario === 'custom') {
    effectiveSource = 'live';
  }

  const handleInspectRow = (row) => {
    setSelectedScenario(row.scenario);
    if (row.algorithm && row.algorithm !== 'all' && row.algorithm !== 'unknown') {
      setSelectedAlgo(row.algorithm);
    }
    if (row.source) {
      setSelectedSource(row.source);
    }
    loadTimeseries(row.scenario, row.source);
  };

  return (
    <div className="app-container">
      <Navbar
        health={health}
        onRefresh={loadAllData}
        isRefreshing={isRefreshing}
      />

      <main className="main-content">
        {/* Top KPIs */}
        <MetricCards
          scenario={selectedScenario}
          algorithm={selectedAlgo}
          source={effectiveSource}
          results={results}
          fairnessData={fairnessData}
          customParams={params}
        />

        {/* Controls + Primary Charts Layout */}
        <div className="controls-layout">
          <ControlPanel
            selectedAlgo={selectedAlgo}
            setSelectedAlgo={setSelectedAlgo}
            selectedScenario={selectedScenario}
            setSelectedScenario={setSelectedScenario}
            params={params}
            setParams={setParams}
            onRun={handleRun}
            isRunning={jobStatus?.is_running}
            canRunRealMininet={canRunRealMininet}
          />

          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Data Source Selector */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#0d1322', padding: '10px 14px', borderRadius: '8px', border: '1px solid #1e293b' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '12px', fontWeight: '600', color: '#94a3b8' }}>Data Source:</span>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setSelectedSource('live')}
                  style={{
                    fontSize: '11px',
                    padding: '3px 10px',
                    background: effectiveSource === 'live' ? '#10b981' : '#111827',
                    color: '#fff',
                    borderColor: effectiveSource === 'live' ? '#34d399' : '#243248'
                  }}
                >
                  Live Runs ({liveResults.length})
                </button>
                {selectedScenario !== 'custom' && (
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => setSelectedSource('historical')}
                    style={{
                      fontSize: '11px',
                      padding: '3px 10px',
                      background: effectiveSource === 'historical' ? '#2563eb' : '#111827',
                      color: '#fff',
                      borderColor: effectiveSource === 'historical' ? '#60a5fa' : '#243248'
                    }}
                  >
                    Saved Baseline ({histResults.length})
                  </button>
                )}
              </div>
              <div style={{ fontSize: '11px', color: '#64748b' }}>
                Viewing: <span style={{ color: '#e2e8f0', fontWeight: '600' }}>{effectiveSource === 'live' ? 'LIVE EXPERIMENT RESULTS' : 'SAVED BASELINE DATA'}</span>
              </div>
            </div>

            <ThroughputChart
              timeseriesData={timeseriesData}
              scenario={selectedScenario}
              source={effectiveSource}
              bottleneckBw={params.bw}
            />

            {selectedScenario === 'fairness' ? (
              <FairnessGauge fairnessData={fairnessData} source={effectiveSource} />
            ) : (
              <RetransmissionsChart
                scenario={selectedScenario}
                source={effectiveSource}
                results={results}
              />
            )}
          </div>
        </div>

        {/* Comprehensive Comparison Table */}
        <ResultsTable
          results={results}
          onSelectScenario={handleInspectRow}
          onClearLive={handleClearLive}
          activeScenario={selectedScenario}
        />
      </main>

      {/* Live Experiment Progress & Diagnostic Modal */}
      {showModal && (
        <ExecutionModal
          jobStatus={jobStatus}
          onCancel={handleCancel}
          onDismiss={handleDismissModal}
        />
      )}
    </div>
  );
}

