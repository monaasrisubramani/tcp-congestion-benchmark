/**
 * frontend/src/api/client.js
 * API communication layer for the TCP Congestion Control Benchmark Suite.
 */

const API_BASE = '/api';

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
  return await res.json();
}

export async function fetchScenarios() {
  const res = await fetch(`${API_BASE}/scenarios`);
  if (!res.ok) throw new Error(`Failed to load scenarios: ${res.statusText}`);
  return await res.json();
}

export async function fetchResults(source = 'all', scenario = null) {
  let url = `${API_BASE}/results?source=${encodeURIComponent(source)}`;
  if (scenario) {
    url += `&scenario=${encodeURIComponent(scenario)}`;
  }
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to fetch results: ${res.statusText}`);
  return await res.json();
}

export async function fetchTimeseries(scenario, source = 'all') {
  const res = await fetch(`${API_BASE}/timeseries/${encodeURIComponent(scenario)}?source=${encodeURIComponent(source)}`);
  if (!res.ok) throw new Error(`Failed to fetch timeseries: ${res.statusText}`);
  return await res.json();
}

export async function fetchFairness() {
  const res = await fetch(`${API_BASE}/fairness`);
  if (!res.ok) throw new Error(`Failed to fetch fairness data: ${res.statusText}`);
  return await res.json();
}

export async function startExperiment(config) {
  const res = await fetch(`${API_BASE}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config)
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Failed to start experiment');
  }
  return await res.json();
}

export async function pollStatus() {
  const res = await fetch(`${API_BASE}/run/status`);
  if (!res.ok) throw new Error(`Failed to poll status: ${res.statusText}`);
  return await res.json();
}

export async function cancelExperiment() {
  const res = await fetch(`${API_BASE}/run/cancel`, { method: 'POST' });
  if (!res.ok) throw new Error(`Failed to cancel: ${res.statusText}`);
  return await res.json();
}

export async function clearLiveResults() {
  const res = await fetch(`${API_BASE}/results/live`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`Failed to clear live runs: ${res.statusText}`);
  return await res.json();
}

