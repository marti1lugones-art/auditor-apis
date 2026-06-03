const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const get = async url => {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`HTTP ${r.status} — ${url}`)
  return r.json()
}

export const fetchSummary   = ()              => get(`${BASE}/api/summary`)
export const fetchEndpoints = ()              => get(`${BASE}/api/endpoints`)
export const fetchIncidents = (limit = 50)    => get(`${BASE}/api/incidents?limit=${limit}`)
export const fetchHistory   = (nombre, limit = 100) =>
  get(`${BASE}/api/endpoints/${encodeURIComponent(nombre)}/history?limit=${limit}`)
