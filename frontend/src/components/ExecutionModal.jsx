import React, { useEffect, useRef } from 'react';

export default function ExecutionModal({
  jobStatus,
  onCancel,
  onDismiss
}) {
  const terminalRef = useRef(null);

  // Auto-scroll logs to bottom
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [jobStatus?.logs]);

  if (!jobStatus || jobStatus.status === 'idle') return null;

  const isCompleted = jobStatus.status === 'completed';
  const isError = jobStatus.status === 'error';
  const isCancelled = jobStatus.status === 'cancelled';
  const isRunning = jobStatus.is_running;

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="modal-header">
          <div className="modal-title">
            {isRunning && '⚡ Live Mininet Experiment in Progress'}
            {isCompleted && '✅ Experiment Completed Successfully'}
            {isError && '❌ Benchmark Execution Error'}
            {isCancelled && '⚠️ Experiment Cancelled'}
          </div>
          {(isCompleted || isError || isCancelled) && (
            <button
              className="btn-secondary"
              onClick={onDismiss}
              style={{ padding: '4px 10px', fontSize: '12px' }}
            >
              Close
            </button>
          )}
        </div>

        {/* Current Step Description */}
        <div style={{ fontSize: '13px', color: '#cbd5e1' }}>
          {jobStatus.step_description || 'Executing network benchmark...'}
        </div>

        {/* Animated Progress Bar */}
        <div className="progress-bar-bg">
          <div
            className="progress-bar-fill"
            style={{
              width: `${jobStatus.progress || 0}%`,
              background: isError ? '#ef4444' : isCompleted ? '#10b981' : 'linear-gradient(90deg, #3b82f6, #10b981)'
            }}
          />
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#64748b' }}>
          <span>Progress: {jobStatus.progress || 0}%</span>
          <span>Elapsed: {jobStatus.elapsed_seconds || 0}s / ~{jobStatus.estimated_total_seconds || 15}s</span>
        </div>

        {/* Error diagnosis banner */}
        {isError && (
          <div className="alert-error">
            <div style={{ fontWeight: '700', marginBottom: '4px' }}>Execution Failed</div>
            <div>{jobStatus.error_message}</div>
            <div style={{ marginTop: '8px', fontSize: '11px', color: '#fca5a5', opacity: 0.9 }}>
              Tip: Mininet network emulation requires root privileges. In your WSL2 terminal, start the server using:
              <br />
              <code style={{ background: '#200c0c', padding: '2px 6px', borderRadius: '4px', display: 'inline-block', marginTop: '4px' }}>
                sudo ./start_backend.sh
              </code>
              <br />
              Or enable "Simulation Mode" in the control panel to test without root.
            </div>
          </div>
        )}

        {/* Live Output Log Terminal */}
        <div className="terminal-box" ref={terminalRef}>
          {(jobStatus.logs || []).length === 0 ? (
            <span style={{ color: '#475569' }}>Awaiting process logs...</span>
          ) : (
            jobStatus.logs.map((line, idx) => (
              <div key={idx}>{line}</div>
            ))
          )}
        </div>

        {/* Modal Actions */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          {isRunning && (
            <button
              type="button"
              className="btn-secondary"
              onClick={onCancel}
              style={{ color: '#f87171', borderColor: 'rgba(239, 68, 68, 0.3)' }}
            >
              Cancel Experiment
            </button>
          )}

          {(isCompleted || isError || isCancelled) && (
            <button
              type="button"
              className="btn-primary"
              onClick={onDismiss}
              style={{ width: 'auto', padding: '8px 20px' }}
            >
              Done
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

