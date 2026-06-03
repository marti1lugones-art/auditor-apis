import React from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts'

// ── Helpers ──────────────────────────────────────────────────

const fmtTime = iso => {
  const d = new Date(iso)
  return d.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' })
}

const fmtFull = iso =>
  new Date(iso).toLocaleString('es-AR', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })

// ── Custom tooltip ────────────────────────────────────────────

const ChartTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-time">{fmtFull(d.iso)}</div>
      <div
        className="chart-tooltip-val"
        style={{ color: d.is_up ? 'var(--ok)' : 'var(--down)' }}
      >
        {d.is_up
          ? `${d.latencia != null ? d.latencia + 'ms' : '—'}`
          : '✗ sin respuesta'}
      </div>
      {d.status && (
        <div style={{ color: 'var(--muted)', fontFamily: 'var(--mono)', fontSize: 11 }}>
          HTTP {d.status}
        </div>
      )}
    </div>
  )
}

// ── Custom dot: rojo para puntos down ─────────────────────────

const CustomDot = ({ cx, cy, payload }) => {
  if (!payload?.is_up) {
    return <circle key={`down-${cx}`} cx={cx} cy={cy} r={4} fill="var(--down)" stroke="none" />
  }
  return null
}

// ── Componente principal ──────────────────────────────────────

export default function HistoryChart({ history }) {
  if (!history) return <div className="empty">Sin datos de historial</div>
  if (!history.checks?.length)
    return <div className="empty">Aún no hay chequeos registrados para este endpoint</div>

  // Los checks vienen DESC (más reciente primero) — invertir para el gráfico
  const chartData = [...history.checks]
    .reverse()
    .map(c => ({
      time:    fmtTime(c.timestamp),
      iso:     c.timestamp,
      latencia: c.is_up && c.latencia_ms != null ? Math.round(c.latencia_ms) : null,
      is_up:   c.is_up,
      status:  c.status_code,
    }))

  // Calcular líneas de referencia para puntos "down"
  const downPoints = chartData
    .filter(d => !d.is_up)
    .map(d => d.time)

  const maxLat = Math.max(...chartData.map(d => d.latencia ?? 0), 10)

  return (
    <div style={{ width: '100%' }}>
      {/* Leyenda rápida */}
      <div style={{ display: 'flex', gap: 16, padding: '0 8px 10px', fontSize: 11, color: 'var(--muted)' }}>
        <span><span style={{ color: 'var(--accent)' }}>─</span> Latencia (ms)</span>
        <span><span style={{ color: 'var(--down)' }}>●</span> Sin respuesta (down)</span>
        <span style={{ marginLeft: 'auto', fontFamily: 'var(--mono)' }}>
          {history.total} chequeos
        </span>
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
          <XAxis
            dataKey="time"
            stroke="var(--border)"
            tick={{ fill: 'var(--muted)', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            stroke="var(--border)"
            tick={{ fill: 'var(--muted)', fontSize: 10, fontFamily: 'JetBrains Mono, monospace' }}
            tickLine={false}
            axisLine={false}
            tickFormatter={v => `${v}`}
            domain={[0, Math.ceil(maxLat * 1.15)]}
            unit="ms"
            width={48}
          />
          <Tooltip content={<ChartTooltip />} />

          {/* Líneas verticales de referencia para momentos down */}
          {downPoints.map(t => (
            <ReferenceLine key={t} x={t} stroke="var(--down)" strokeOpacity={0.35} strokeDasharray="4 3" />
          ))}

          <Line
            type="monotone"
            dataKey="latencia"
            stroke="var(--accent)"
            strokeWidth={1.5}
            dot={<CustomDot />}
            activeDot={{ r: 5, fill: 'var(--accent)', stroke: 'var(--surface)', strokeWidth: 2 }}
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
