import React, { useState, useEffect, useCallback } from 'react'
import { fetchSummary, fetchEndpoints, fetchIncidents, fetchHistory } from './api'
import SummaryCards from './components/SummaryCards'
import EndpointList from './components/EndpointList'
import HistoryChart from './components/HistoryChart'
import IncidentsPanel from './components/IncidentsPanel'

const REFRESH_MS = 30_000

export default function App() {
  const [summary,   setSummary]   = useState(null)
  const [endpoints, setEndpoints] = useState([])
  const [incidents, setIncidents] = useState([])
  const [selected,  setSelected]  = useState(null)   // endpoint seleccionado
  const [history,   setHistory]   = useState(null)   // datos del histórico
  const [lastUpdate, setLastUpdate] = useState(null)
  const [error,     setError]     = useState(null)
  const [loadingHistory, setLoadingHistory] = useState(false)

  // ── Fetch general (summary + endpoints + incidents) ─────────────────────
  const fetchAll = useCallback(async () => {
    try {
      const [s, e, i] = await Promise.all([
        fetchSummary(),
        fetchEndpoints(),
        fetchIncidents(50),
      ])
      setSummary(s)
      setEndpoints(e)
      setIncidents(i)
      setLastUpdate(new Date())
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }, [])

  // ── Cargar histórico cuando se selecciona un endpoint ───────────────────
  const handleSelect = useCallback(async ep => {
    if (selected?.nombre === ep.nombre) {
      setSelected(null)
      setHistory(null)
      return
    }
    setSelected(ep)
    setHistory(null)
    setLoadingHistory(true)
    try {
      const data = await fetchHistory(ep.nombre, 100)
      setHistory(data)
    } catch {
      setHistory({ checks: [], total: 0, nombre: ep.nombre })
    } finally {
      setLoadingHistory(false)
    }
  }, [selected])

  // ── Auto-refresh ─────────────────────────────────────────────────────────
  useEffect(() => {
    fetchAll()
    const id = setInterval(fetchAll, REFRESH_MS)
    return () => clearInterval(id)
  }, [fetchAll])

  // ── Refrescar histórico junto con el ciclo general ───────────────────────
  useEffect(() => {
    if (!selected) return
    const refreshHistory = async () => {
      try {
        const data = await fetchHistory(selected.nombre, 100)
        setHistory(data)
      } catch {}
    }
    const id = setInterval(refreshHistory, REFRESH_MS)
    return () => clearInterval(id)
  }, [selected])

  const timeStr = lastUpdate
    ? lastUpdate.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : '—'

  return (
    <div className="app">
      {/* ── Header ─────────────────────────────────────────────────── */}
      <header className="header">
        <div className="header-brand">
          <div className="header-dot" />
          <span className="header-title">API Monitor</span>
        </div>
        <div className="header-meta">
          {error && <span className="header-error">⚠ {error}</span>}
          <span className="header-update">Actualizado: {timeStr}</span>
          <button className="refresh-btn" onClick={fetchAll}>↺ Refrescar</button>
        </div>
      </header>

      {/* ── Main ──────────────────────────────────────────────────────── */}
      <main className="main">

        {/* Summary cards */}
        {summary && <SummaryCards summary={summary} />}

        {/* Endpoints | Incidents/History */}
        <div className="content-grid">
          <div className="panel">
            <div className="panel-header">
              <span className="panel-title">Endpoints</span>
              <span className="panel-title">{endpoints.length} monitoreados</span>
            </div>
            <div className="panel-body">
              <EndpointList
                endpoints={endpoints}
                selected={selected}
                onSelect={handleSelect}
              />
            </div>
          </div>

          {selected ? (
            <div className="panel">
              <div className="panel-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className="panel-title">Historial</span>
                  <span style={{ color: 'var(--text)', fontSize: 12, fontWeight: 500 }}>
                    {selected.nombre}
                  </span>
                </div>
                <button className="close-btn" onClick={() => { setSelected(null); setHistory(null) }}>✕</button>
              </div>
              <div className="panel-body" style={{ overflow: 'visible', maxHeight: 'none', padding: '12px 8px' }}>
                {loadingHistory
                  ? <div className="loading">Cargando historial…</div>
                  : <HistoryChart history={history} />
                }
              </div>
            </div>
          ) : (
            <IncidentsPanel incidents={incidents} />
          )}
        </div>

      </main>
    </div>
  )
}
