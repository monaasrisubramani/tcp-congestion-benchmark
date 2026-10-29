import React, { useState, useRef } from 'react';

export function getSeriesStyle(seriesKey, currentSource = 'all') {
  const lower = (seriesKey || '').toLowerCase();
  
  // Base algorithm
  let algo = 'unknown';
  if (lower.includes('reno')) algo = 'reno';
  else if (lower.includes('cubic')) algo = 'cubic';
  else if (lower.includes('bbr')) algo = 'bbr';

  // Source determination: live vs historical
  let isHistorical = false;
  if (lower.includes('(historical)') || lower.includes('baseline')) {
    isHistorical = true;
  } else if (lower.includes('(live)')) {
    isHistorical = false;
  } else {
    isHistorical = (currentSource === 'historical');
  }

  const config = {
    reno: {
      live: { color: '#ef4444', dash: '', width: 2.5, label: 'Reno (Live)' },
      historical: { color: '#f87171', dash: '6 4', width: 2, label: 'Reno (Historical)' }
    },
    cubic: {
      live: { color: '#3b82f6', dash: '', width: 2.5, label: 'CUBIC (Live)' },
      historical: { color: '#60a5fa', dash: '6 4', width: 2, label: 'CUBIC (Historical)' }
    },
    bbr: {
      live: { color: '#10b981', dash: '', width: 2.5, label: 'BBR (Live)' },
      historical: { color: '#34d399', dash: '6 4', width: 2, label: 'BBR (Historical)' }
    },
    unknown: {
      live: { color: '#94a3b8', dash: '', width: 2, label: seriesKey },
      historical: { color: '#64748b', dash: '6 4', width: 1.8, label: `${seriesKey} (Hist)` }
    }
  };

  const algoConfig = config[algo] || config.unknown;
  const style = isHistorical ? algoConfig.historical : algoConfig.live;

  let displayLabel = style.label.toUpperCase();
  if (seriesKey && seriesKey.includes('(')) {
    displayLabel = seriesKey.toUpperCase();
  }

  return {
    algo,
    isHistorical,
    color: style.color,
    dash: style.dash,
    width: style.width,
    label: displayLabel
  };
}

export default function ThroughputChart({ timeseriesData, scenario, source = 'all', bottleneckBw = 10 }) {
  const [hoverIndex, setHoverIndex] = useState(null);
  const [hiddenAlgos, setHiddenAlgos] = useState(new Set());
  const svgRef = useRef(null);

  const chartData = timeseriesData?.chart_data || [];
  const algorithms = (timeseriesData?.algorithms_present || ['reno', 'cubic', 'bbr']).filter(
    a => a !== 'all' && a !== 'unknown' && !hiddenAlgos.has(a)
  );

  // SVG dimensions
  const width = 800;
  const height = 340;
  const padding = { top: 30, right: 30, bottom: 40, left: 55 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;

  // Max values
  const maxSeconds = Math.max(15, chartData.length);
  let maxMbps = bottleneckBw * 1.25;
  chartData.forEach(row => {
    algorithms.forEach(algo => {
      const val = row[algo];
      if (typeof val === 'number' && val > maxMbps) {
        maxMbps = val * 1.1;
      }
    });
  });
  maxMbps = Math.ceil(maxMbps);

  // Scales
  const getX = (sec) => padding.left + ((sec - 1) / (maxSeconds - 1 || 1)) * plotWidth;
  const getY = (mbps) => padding.top + plotHeight - (mbps / maxMbps) * plotHeight;

  // Generate SVG path for an algorithm
  const generatePath = (algo) => {
    const points = chartData
      .map(row => {
        const val = row[algo];
        if (typeof val !== 'number') return null;
        return `${getX(row.second).toFixed(1)},${getY(val).toFixed(1)}`;
      })
      .filter(Boolean);

    if (points.length === 0) return '';
    return `M ${points.join(' L ')}`;
  };

  const handleMouseMove = (e) => {
    if (!svgRef.current || chartData.length === 0) return;
    const rect = svgRef.current.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const ratio = Math.max(0, Math.min(1, (mouseX - padding.left) / plotWidth));
    const idx = Math.min(chartData.length - 1, Math.round(ratio * (chartData.length - 1)));
    setHoverIndex(idx);
  };

  const toggleAlgo = (algo) => {
    setHiddenAlgos(prev => {
      const next = new Set(prev);
      if (next.has(algo)) next.delete(algo);
      else next.add(algo);
      return next;
    });
  };

  const hoveredPoint = hoverIndex !== null && chartData[hoverIndex] ? chartData[hoverIndex] : null;

  return (
    <div className="card">
      <div className="card-title">
        <span>Throughput over Time (1-Second Telemetry)</span>
        <span style={{ fontSize: '12px', fontWeight: '500', color: '#9ca3af' }}>
          Scenario: {scenario?.toUpperCase()} · Source: {source?.toUpperCase()} · Bottleneck: {bottleneckBw} Mbps
        </span>
      </div>

      <div className="chart-container">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${width} ${height}`}
          className="svg-chart"
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoverIndex(null)}
        >
          {chartData.length === 0 ? (
            <g>
              <rect
                x={padding.left}
                y={padding.top}
                width={plotWidth}
                height={plotHeight}
                fill="#0d1322"
                rx="6"
                stroke="#1e293b"
              />
              <text
                x={width / 2}
                y={height / 2 - 8}
                fill="#94a3b8"
                fontSize="14"
                textAnchor="middle"
                fontWeight="600"
              >
                No telemetry data recorded for {scenario?.toUpperCase()} ({source?.toUpperCase()})
              </text>
              <text
                x={width / 2}
                y={height / 2 + 16}
                fill="#64748b"
                fontSize="12"
                textAnchor="middle"
              >
                Click "Run Experiment" to execute benchmarks and stream dynamic 1-second interval telemetry.
              </text>
            </g>
          ) : (
            <>
              <defs>
                <linearGradient id="grid-fade" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#1e293b" stopOpacity="0.4" />
                  <stop offset="100%" stopColor="#1e293b" stopOpacity="0.1" />
                </linearGradient>
              </defs>

          {/* Background Grid Lines */}
          {[0, 0.25, 0.5, 0.75, 1.0].map((pct, i) => {
            const yVal = maxMbps * pct;
            const y = getY(yVal);
            return (
              <g key={i}>
                <line
                  x1={padding.left}
                  y1={y}
                  x2={width - padding.right}
                  y2={y}
                  stroke="#1f293d"
                  strokeDasharray="4 4"
                />
                <text
                  x={padding.left - 10}
                  y={y + 4}
                  fill="#64748b"
                  fontSize="10"
                  textAnchor="end"
                  fontFamily="ui-monospace"
                >
                  {yVal.toFixed(0)}M
                </text>
              </g>
            );
          })}

          {/* Time axis ticks */}
          {[0, 10, 20, 30, 40, 50, 60].filter(t => t <= maxSeconds).map(sec => {
            const x = getX(sec === 0 ? 1 : sec);
            return (
              <g key={sec}>
                <line x1={x} y1={padding.top + plotHeight} x2={x} y2={padding.top + plotHeight + 6} stroke="#334155" />
                <text
                  x={x}
                  y={padding.top + plotHeight + 18}
                  fill="#64748b"
                  fontSize="10"
                  textAnchor="middle"
                  fontFamily="ui-monospace"
                >
                  {sec}s
                </text>
              </g>
            );
          })}

          {/* Bottleneck Capacity Reference Line */}
          <line
            x1={padding.left}
            y1={getY(bottleneckBw)}
            x2={width - padding.right}
            y2={getY(bottleneckBw)}
            stroke="#e2e8f0"
            strokeDasharray="6 6"
            strokeWidth="1.2"
            opacity="0.6"
          />
          <text
            x={width - padding.right - 6}
            y={getY(bottleneckBw) - 6}
            fill="#cbd5e1"
            fontSize="10"
            textAnchor="end"
            fontFamily="ui-monospace"
          >
            Line Rate ({bottleneckBw} Mbps)
          </text>

          {/* Algorithm Curves */}
          {algorithms.map(algo => {
            const pathD = generatePath(algo);
            const style = getSeriesStyle(algo, source);
            if (!pathD) return null;
            return (
              <g key={algo}>
                <path
                  d={pathD}
                  fill="none"
                  stroke={style.color}
                  strokeWidth={style.width}
                  strokeDasharray={style.dash || undefined}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </g>
            );
          })}

          {/* Interactive Hover Crosshair */}
          {hoveredPoint && (
            <g>
              <line
                x1={getX(hoveredPoint.second)}
                y1={padding.top}
                x2={getX(hoveredPoint.second)}
                y2={padding.top + plotHeight}
                stroke="#94a3b8"
                strokeWidth="1"
                strokeDasharray="3 3"
              />
              {algorithms.map(algo => {
                const val = hoveredPoint[algo];
                if (typeof val !== 'number') return null;
                const style = getSeriesStyle(algo, source);
                return (
                  <circle
                    key={algo}
                    cx={getX(hoveredPoint.second)}
                    cy={getY(val)}
                    r="4.5"
                    fill={style.color}
                    stroke="#0b0f19"
                    strokeWidth="2"
                  />
                );
              })}
            </g>
          )}
            </>
          )}
        </svg>

        {/* Hover Tooltip Overlay */}
        {hoveredPoint && (
          <div
            style={{
              position: 'absolute',
              top: '16px',
              left: `${Math.min(75, Math.max(15, (getX(hoveredPoint.second) / width) * 100))}%`,
              transform: 'translateX(-50%)',
              background: 'rgba(15, 23, 42, 0.95)',
              border: '1px solid #334155',
              borderRadius: '8px',
              padding: '10px 14px',
              fontSize: '12px',
              pointerEvents: 'none',
              boxShadow: '0 4px 14px rgba(0,0,0,0.5)',
              zIndex: 10
            }}
          >
            <div style={{ fontWeight: '700', color: '#e2e8f0', marginBottom: '4px' }}>
              Second {hoveredPoint.second} of {maxSeconds}s
            </div>
            {algorithms.map(algo => {
              const val = hoveredPoint[algo];
              if (typeof val !== 'number') return null;
              const style = getSeriesStyle(algo, source);
              return (
                <div key={algo} style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', color: '#cbd5e1' }}>
                  <span style={{ color: style.color, fontWeight: '600' }}>{style.label}:</span>
                  <span style={{ fontFamily: 'ui-monospace', fontWeight: '700' }}>{val.toFixed(2)} Mbps</span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Interactive Legend with click-to-hide */}
      <div className="chart-legend">
        {(timeseriesData?.algorithms_present || ['reno', 'cubic', 'bbr']).map(algo => {
          const isHidden = hiddenAlgos.has(algo);
          const style = getSeriesStyle(algo, source);
          return (
            <div
              key={algo}
              className="legend-item"
              onClick={() => toggleAlgo(algo)}
              style={{ opacity: isHidden ? 0.35 : 1 }}
              title="Click to toggle visibility"
            >
              <svg width="22" height="10" style={{ verticalAlign: 'middle', marginRight: '6px' }}>
                <line
                  x1="0"
                  y1="5"
                  x2="22"
                  y2="5"
                  stroke={style.color}
                  strokeWidth={style.width}
                  strokeDasharray={style.dash || undefined}
                  strokeLinecap="round"
                />
              </svg>
              <span>{style.label}</span>
            </div>
          );
        })}
        <div className="legend-item" style={{ cursor: 'default' }}>
          <svg width="22" height="10" style={{ verticalAlign: 'middle', marginRight: '6px' }}>
            <line x1="0" y1="5" x2="22" y2="5" stroke="#e2e8f0" strokeWidth="1.5" strokeDasharray="6 6" />
          </svg>
          <span>Line Rate ({bottleneckBw} Mbps)</span>
        </div>
      </div>
    </div>
  );
}

