import React from 'react';

const ALGO_COLORS = {
  reno: '#ef4444',
  cubic: '#3b82f6',
  bbr: '#10b981',
  all: '#38bdf8'
};

export default function MetricCards({ scenario, algorithm, source = 'all', results, fairnessData, customParams }) {
  // Filter relevant scenario results
  const scenarioResults = results.filter(r => r.scenario === scenario);
  const liveResults = scenarioResults.filter(r => r.source === 'live');

  // Determine effective data source
  let effectiveSource = source;
  if (effectiveSource === 'all') {
    effectiveSource = (scenario === 'custom' || liveResults.length > 0) ? 'live' : 'historical';
  }
  if (scenario === 'custom') {
    effectiveSource = 'live';
  }

  const filteredBySource = scenarioResults.filter(r => r.source === effectiveSource);

  let avgThroughput = null;
  let avgThroughputHint = '';
  let retransmits = null;
  let retransmitsHint = '';
  let totalMb = null;
  let totalMbHint = 'Data payload volume';
  let jfi = null;
  let jfiHint = '';
  let jfiColor = '#9ca3af';

  if (algorithm === 'all') {
    const renoRes = filteredBySource.find(r => r.algorithm === 'reno');
    const cubicRes = filteredBySource.find(r => r.algorithm === 'cubic');
    const bbrRes = filteredBySource.find(r => r.algorithm === 'bbr');
    const present = [renoRes, cubicRes, bbrRes].filter(Boolean);

    if (present.length > 0) {
      const sumTp = present.reduce((acc, r) => acc + (r.avg_throughput_mbps || 0), 0);
      avgThroughput = sumTp / present.length;
      avgThroughputHint = `Mean of ${present.length} algos (R: ${renoRes ? renoRes.avg_throughput_mbps.toFixed(1) : '—'}, C: ${cubicRes ? cubicRes.avg_throughput_mbps.toFixed(1) : '—'}, B: ${bbrRes ? bbrRes.avg_throughput_mbps.toFixed(1) : '—'} Mbps)`;
      retransmits = present.reduce((acc, r) => acc + (r.retransmissions || 0), 0);
      retransmitsHint = `Total across algos (R: ${renoRes ? renoRes.retransmissions : '—'}, C: ${cubicRes ? cubicRes.retransmissions : '—'}, B: ${bbrRes ? bbrRes.retransmissions : '—'})`;
      totalMb = present.reduce((acc, r) => acc + (r.total_bytes_mb || 0), 0);
      totalMbHint = `Sum of ${present.length} runs (${effectiveSource.toUpperCase()})`;
    } else {
      avgThroughputHint = `No ${effectiveSource.toUpperCase()} data for Compare All`;
      retransmitsHint = 'Run Compare All to measure';
      totalMbHint = 'No data available';
    }
  } else {
    const selectedResult = filteredBySource.find(r => r.algorithm === algorithm);
    if (selectedResult) {
      avgThroughput = selectedResult.avg_throughput_mbps;
      const bottleneckBw = selectedResult.topo_params?.bw || customParams?.bw || 10;
      const rxTp = selectedResult.receiver_throughput_mbps || selectedResult.goodput_mbps;
      if (rxTp && Math.abs(rxTp - avgThroughput) > 0.4) {
        avgThroughputHint = `${avgThroughput.toFixed(2)} Mbps sent (${selectedResult.retransmissions} drops) · ${rxTp.toFixed(2)} Mbps goodput (${Math.round((rxTp / bottleneckBw) * 100)}% of ${bottleneckBw}M link)`;
      } else {
        const sat = Math.round((avgThroughput / bottleneckBw) * 100);
        avgThroughputHint = `${sat}% of ${bottleneckBw} Mbps link (${selectedResult.source.toUpperCase()})`;
      }
      retransmits = selectedResult.retransmissions;
      retransmitsHint = retransmits === 0 ? 'Clean channel (0 drops)' : `${retransmits.toLocaleString()} TCP retransmits observed`;
      totalMb = selectedResult.total_bytes_mb;
      totalMbHint = `Measured payload (${selectedResult.source.toUpperCase()})`;
    } else {
      avgThroughputHint = `No ${effectiveSource.toUpperCase()} data for ${algorithm.toUpperCase()}`;
      retransmitsHint = 'Run experiment to measure';
      totalMbHint = 'No data available';
    }
  }

  // Jain's Fairness Index: ONLY applicable to fairness scenario
  if (scenario === 'fairness') {
    const fairObj = effectiveSource === 'live' ? fairnessData?.live : fairnessData?.historical;
    jfi = fairObj?.jfi ?? fairnessData?.jains_fairness_index;
    if (typeof jfi === 'number') {
      jfiColor = jfi > 0.9 ? '#10b981' : jfi > 0.7 ? '#f59e0b' : '#ef4444';
      jfiHint = jfi > 0.95 ? 'Near-ideal fair resource sharing' : jfi > 0.9 ? 'Good resource sharing' : 'Asymmetric allocation';
    } else {
      jfiHint = 'No fairness competition data recorded';
    }
  } else {
    jfi = null;
    jfiHint = 'Applicable only to simultaneous fairness test';
  }

  return (
    <div className="grid-4">
      <div className="metric-card">
        <div className="metric-label">Avg Throughput</div>
        <div className="metric-value" style={{ color: ALGO_COLORS[algorithm] || '#fff' }}>
          {avgThroughput !== null ? (
            <>
              {avgThroughput.toFixed(2)} <span style={{ fontSize: '14px', color: '#9ca3af' }}>Mbps</span>
            </>
          ) : (
            <span style={{ color: '#64748b' }}>—</span>
          )}
        </div>
        <div className="metric-hint">{avgThroughputHint}</div>
      </div>

      <div className="metric-card">
        <div className="metric-label">Retransmissions</div>
        <div className="metric-value" style={{ color: retransmits === null ? '#64748b' : retransmits > 500 ? '#ef4444' : retransmits > 50 ? '#f59e0b' : '#10b981' }}>
          {retransmits !== null ? retransmits.toLocaleString() : <span style={{ color: '#64748b' }}>—</span>}
        </div>
        <div className="metric-hint">{retransmitsHint}</div>
      </div>

      <div className="metric-card">
        <div className="metric-label">Total Transferred</div>
        <div className="metric-value">
          {totalMb !== null ? (
            <>
              {totalMb.toFixed(1)} <span style={{ fontSize: '14px', color: '#9ca3af' }}>MB</span>
            </>
          ) : (
            <span style={{ color: '#64748b' }}>—</span>
          )}
        </div>
        <div className="metric-hint">{totalMbHint}</div>
      </div>

      <div className="metric-card">
        <div className="metric-label">Jain's Fairness Index</div>
        <div className="metric-value" style={{ color: jfi !== null ? jfiColor : '#64748b' }}>
          {jfi !== null ? jfi.toFixed(4) : <span style={{ fontSize: '16px', color: '#64748b' }}>N/A</span>}
        </div>
        <div className="metric-hint">{jfiHint}</div>
      </div>
    </div>
  );
}

