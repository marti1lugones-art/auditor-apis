import React from 'react'

// ── Helpers ──────────────────────────────────────────────────

const relTime = iso => {
  const diff = Date.now() - new Date(iso).getTime()
  const min  = Math.floor(diff / 60_000)
  if (min < 1)   return 'ahora'
  if (min < 60)  return `hace ${min}m`
  const h = Math.floor(min / 60)
  if (h < 24)    return `hace ${h}h`
  return `hace ${Math.floor(h / 24)}d`
}

// ── Componente ────────────────────────────────────────────────

export default function IncidentsPanel({ incidents }) {
  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Incidentes</span>
        <span className="panel-title">{incidents.length} recientes</span>
      </div>
      <div className="panel-body">
        {incidents.length === 0 ? (
          <div className="empty">Sin incidentes recientes ✓</div>
        ) : (
          incidents.map((inc, i) => {
            const isViol    = inc.tipo === 'violacion_regla'
            const badge     = isViol ? 'badge-violacion' : 'badge-breaking2'
            const badgeText = isViol ? '⚠ regla' : '💥 breaking'
            const icon      = isViol ? '⚠' : '💥'

            return (
              <div key={i} className="incident-row">
                <span
                  className="incident-icon"
                  style={{ color: isViol ? 'var(--warn)' : 'var(--breaking)' }}
                >
                  {icon}
                </span>
                <div className="incident-body">
                  <div
                    className="incident-name"
                    title={inc.endpoint_name}
                    style={{ color: isViol ? 'var(--warn)' : 'var(--breaking)' }}
                  >
                    {inc.endpoint_name}
                  </div>
                  <div className="incident-desc">{inc.descripcion}</div>
                  <div className="incident-meta">
                    <span className={`incident-badge ${badge}`}>{badgeText}</span>
                    <span className="incident-time">{relTime(inc.detected_at)}</span>
                  </div>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
