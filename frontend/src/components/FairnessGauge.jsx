import React from 'react';

export default function FairnessGauge({ fairnessData, source = 'all' }) {
  const fairObj = source === 'live' ? fairnessData?.live : fairnessData?.historical;
  const jfi = fairObj?.jfi ?? fairnessData?.jains_fairness_index;
  const cubicTp = fairObj?.cubic?.avg_throughput_mbps ?? fairnessData?.historical?.cubic?.avg_throughput_mbps;
  const bbrTp = fairObj?.bbr?.avg_throughput_mbps ?? fairnessData?.historical?.bbr?.avg_throughput_mbps;

  if (jfi === null || jfi === undefined) {
    return (
      <div className="card">
        <div className="card-title">
          <span>CUBIC vs BBR Fairness Competition</span>
          <span className="badge" style={{ background: 'rgba(59, 130, 246, 0.15)', color: '#93c5fd' }}>
            Simultaneous Bottleneck Test
          </span>
        </div>
        <div style={{ textAlign: 'center', padding: '36px', color: '#64748b' }}>
          No simultaneous fairness experiment data recorded for {source.toUpperCase()} view.<br />
          Select the "Fairness" preset and run the benchmark to measure flow competition.
        </div>
      </div>
    );
  }

  const total = (cubicTp || 0) + (bbrTp || 0);
  const cubicPct = total > 0 ? Math.round(((cubicTp || 0) / total) * 100) : 50;
  const bbrPct = total > 0 ? 100 - cubicPct : 50;

  const getStatus = (val) => {
    if (val >= 0.95) return { label: 'Near Perfect Sharing', color: '#10b981' };
    if (val >= 0.90) return { label: 'Good Fairness', color: '#34d399' };
    if (val >= 0.75) return { label: 'Moderate Asymmetry', color: '#f59e0b' };
    return { label: 'Unbalanced Monopoly', color: '#ef4444' };
  };

  const status = getStatus(jfi);

  return (
    <div className="card">
      <div className="card-title">
        <span>CUBIC vs BBR Fairness Competition</span>
        <span className="badge" style={{ background: 'rgba(59, 130, 246, 0.15)', color: '#93c5fd' }}>
          Simultaneous Bottleneck Test
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '24px', margin: '14px 0' }}>
        <div style={{
          width: '100px',
          height: '100px',
          borderRadius: '50%',
          border: `6px solid ${status.color}`,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: `0 0 16px ${status.color}33`,
          flexShrink: 0
        }}>
          <div style={{ fontSize: '20px', fontWeight: '800', fontFamily: 'ui-monospace' }}>
            {jfi.toFixed(3)}
          </div>
          <div style={{ fontSize: '10px', color: '#9ca3af', textTransform: 'uppercase' }}>
            Jain's FI
          </div>
        </div>

        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '14px', fontWeight: '700', color: status.color, marginBottom: '4px' }}>
            {status.label}
          </div>
          <div style={{ fontSize: '12px', color: '#94a3b8', lineHeight: 1.5 }}>
            Jain's Fairness Index evaluates equal bandwidth distribution: J=1.0 is ideal equality, J &gt; 0.9 represents good fairness.
          </div>
        </div>
      </div>

      {/* Bandwidth Sharing Split Bar */}
      <div style={{ margin: '18px 0 10px 0' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', fontWeight: '600', marginBottom: '6px' }}>
          <span style={{ color: '#3b82f6' }}>CUBIC: {cubicTp ? cubicTp.toFixed(2) : '—'} Mbps ({cubicPct}%)</span>
          <span style={{ color: '#10b981' }}>BBR: {bbrTp ? bbrTp.toFixed(2) : '—'} Mbps ({bbrPct}%)</span>
        </div>

        <div style={{ display: 'flex', height: '16px', borderRadius: '6px', overflow: 'hidden' }}>
          <div style={{ width: `${cubicPct}%`, background: '#3b82f6', transition: 'width 0.4s' }} />
          <div style={{ width: `${bbrPct}%`, background: '#10b981', transition: 'width 0.4s' }} />
        </div>
      </div>

      <div style={{ fontSize: '11px', color: '#64748b', marginTop: '12px', borderTop: '1px solid #1e293b', paddingTop: '8px' }}>
        <strong>Theory:</strong> When CUBIC and BBR compete, CUBIC aggressively inflates the switch queue, while BBR periodically drains the queue during its ProbeRTT phase, allowing CUBIC to claim a larger share of deep buffers.
      </div>
    </div>
  );
}

