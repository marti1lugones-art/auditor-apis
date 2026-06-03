import React from 'react'

const ESTADO_MAP = {
  ok:       { dot: 'dot-ok',       badge: 'badge-ok',       label: 'ok'       },
  down:     { dot: 'dot-down',     badge: 'badge-down',     label: 'down'     },
  breaking: { dot: 'dot-breaking', badge: 'badge-breaking', label: 'breaking' },
  violacion:{ dot: 'dot-warn',     badge: 'badge-warn',     label: 'violación'},
  sin_datos:{ dot: 'dot-nodata',   badge: 'badge-nodata',   label: 'sin datos'},
}

export default function EndpointList({ endpoints, selected, onSelect }) {
  if (!endpoints.length)
    return <div className="empty">Sin endpoints configurados</div>

  return (
    <>
      {endpoints.map(ep => {
        const st = ESTADO_MAP[ep.estado] || ESTADO_MAP.sin_datos
        const uc = ep.ultimo_chequeo
        const isSelected = selected?.nombre === ep.nombre

        return (
          <div
            key={ep.nombre}
            className={`ep-row ${isSelected ? 'selected' : ''}`}
            onClick={() => onSelect(ep)}
            title={ep.url}
          >
            {/* Status dot */}
            <span className={`ep-dot ${st.dot}`} />

            {/* Name */}
            <span className="ep-name">{ep.nombre}</span>

            {/* Estado badge */}
            <span className={`ep-badge ${st.badge}`}>{st.label}</span>

            {/* Status code */}
            <span className="ep-code">
              {uc?.status_code ?? '—'}
            </span>

            {/* Latency */}
            <span className="ep-lat">
              {uc?.latencia_ms != null ? `${Math.round(uc.latencia_ms)}ms` : '—'}
            </span>
          </div>
        )
      })}
    </>
  )
}
