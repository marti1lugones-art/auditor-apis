import React from 'react'

const CARDS = [
  {
    key:   'total_endpoints',
    label: 'Total',
    icon:  '◉',
    alert: () => false,
    cls:   () => '',
    color: () => 'var(--text)',
  },
  {
    key:   'endpoints_up',
    label: 'Up',
    icon:  '✓',
    alert: v => v > 0,
    cls:   v => v > 0 ? 'alert-ok' : '',
    color: v => v > 0 ? 'var(--ok)' : 'var(--muted)',
  },
  {
    key:   'endpoints_down',
    label: 'Down',
    icon:  '✗',
    alert: v => v > 0,
    cls:   v => v > 0 ? 'alert-down' : '',
    color: v => v > 0 ? 'var(--down)' : 'var(--muted)',
  },
  {
    key:   'violaciones_activas',
    label: 'Violaciones',
    icon:  '⚠',
    alert: v => v > 0,
    cls:   v => v > 0 ? 'alert-warn' : '',
    color: v => v > 0 ? 'var(--warn)' : 'var(--muted)',
  },
  {
    key:   'breaking_changes_activos',
    label: 'Breaking',
    icon:  '💥',
    alert: v => v > 0,
    cls:   v => v > 0 ? 'alert-breaking' : '',
    color: v => v > 0 ? 'var(--breaking)' : 'var(--muted)',
  },
]

export default function SummaryCards({ summary }) {
  return (
    <div className="summary-row">
      {CARDS.map(({ key, label, icon, cls, color }) => {
        const val = summary[key] ?? 0
        return (
          <div key={key} className={`summary-card ${cls(val)}`}>
            <div className="summary-num" style={{ color: color(val) }}>{val}</div>
            <div className="summary-label">
              <span>{icon}</span>
              <span>{label}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
