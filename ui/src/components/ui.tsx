import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useStore } from '../state/store'

export const STATUS: Record<string, [string, string]> = {
  'In review': ['var(--review-bg)', 'var(--bud-ink)'],
  Approved: ['var(--ok-bg)', 'var(--ok-ink)'],
  Draft: ['var(--oth-bg)', 'var(--oth-ink)'],
  Sent: ['var(--med-bg)', 'var(--med-ink)'],
  'Changes requested': ['var(--err-bg)', 'var(--err-2)'],
}

export function StatusPill({ status }: { status: string }) {
  const [bg, fg] = STATUS[status] || STATUS.Draft
  return <span className="pill" style={{ background: bg, color: fg }}>{status}</span>
}

const CONF_TONE: Record<string, string> = { H: 'high', M: 'med', L: 'lab', B: 'bud', O: 'oth' }
export const CONF_LABEL: Record<string, string> = { H: 'High', M: 'Medium', L: 'Labour rate', B: 'Budgetary', O: 'Other' }

export function ConfBadge({ conf, label }: { conf: string | null; label?: string }) {
  if (!conf) return <span className="badge t-none">{label || 'No price'}</span>
  return <span className={`badge t-${CONF_TONE[conf] || 'oth'}`}>{label || CONF_LABEL[conf] || conf}</span>
}

export function ToneBadge({ tone, children }: { tone: string; children: ReactNode }) {
  return <span className={`badge t-${tone}`} style={{ fontSize: 11, padding: '2px 7px' }}>{children}</span>
}

export function Toggle({ on, onChange, small }: { on: boolean; onChange?: (v: boolean) => void; small?: boolean }) {
  return (
    <button type="button" className={`toggle${on ? ' on' : ''}${small ? ' sm' : ''}`} aria-pressed={on}
      onClick={(e) => { e.stopPropagation(); onChange?.(!on) }}>
      <span className="k" />
    </button>
  )
}

export function Check({ on, onChange, label, size14 }: { on: boolean; onChange?: (v: boolean) => void; label?: ReactNode; size14?: boolean }) {
  return (
    <label className="row gap6" style={{ cursor: 'pointer', userSelect: 'none' }} onClick={(e) => { e.preventDefault(); onChange?.(!on) }}>
      <span className={`cbx${on ? ' on' : ''}${size14 ? ' s14' : ''}`}>{on ? '✓' : ''}</span>
      {label}
    </label>
  )
}

export function Seg<T extends string>({ value, options, onChange, light }: { value: T; options: { value: T; label: ReactNode }[]; onChange: (v: T) => void; light?: boolean }) {
  return (
    <div className={`seg${light ? ' light' : ''}`}>
      {options.map((o) => <div key={o.value} className={o.value === value ? 'on' : ''} onClick={() => onChange(o.value)}>{o.label}</div>)}
    </div>
  )
}

export function SysBadge({ ab, color, title }: { ab: string; color: string; title?: string }) {
  return <span className="sysb" title={title} style={{ background: color }}>{ab}</span>
}

export function Card({ title, right, children, style, bodyStyle, small }: { title?: ReactNode; right?: ReactNode; children: ReactNode; style?: React.CSSProperties; bodyStyle?: React.CSSProperties; small?: boolean }) {
  return (
    <div className="card" style={style}>
      {title !== undefined && <div className={`card-h${small ? ' sm' : ''}`}>{title}{right !== undefined && <span className="r">{right}</span>}</div>}
      <div style={bodyStyle}>{children}</div>
    </div>
  )
}

export function Modal({ title, onClose, children, footer, width }: { title: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; width?: number }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
  return (
    <div className="backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="modal" style={width ? { width } : undefined}>
        <div className="modal-h">{title}<button className="x" onClick={onClose} aria-label="Close">×</button></div>
        <div className="modal-b">{children}</div>
        {footer && <div className="modal-f">{footer}</div>}
      </div>
    </div>
  )
}

/** Inline editable cell: looks like text, becomes an input on hover/focus, commits on Enter/blur. */
export function EditCell({ value, onCommit, align = 'right', placeholder, className = '', width, title, numeric = true, disabled }:
  { value: string; onCommit: (v: string) => void; align?: 'left' | 'right'; placeholder?: string; className?: string; width?: number | string; title?: string; numeric?: boolean; disabled?: boolean }) {
  const [v, setV] = useState(value)
  const ref = useRef<HTMLInputElement>(null)
  useEffect(() => { if (document.activeElement !== ref.current) setV(value) }, [value])
  const commit = () => {
    const t = v.trim()
    if (t !== value.trim()) {
      if (numeric && t !== '' && isNaN(Number(t.replace(/,/g, '')))) { setV(value); return }
      onCommit(numeric ? t.replace(/,/g, '') : t)
    }
  }
  return (
    <input ref={ref} className={`cell${align === 'right' ? ' r' : ''} ${className}`} value={v} placeholder={placeholder} title={title}
      style={width !== undefined ? { width } : undefined} disabled={disabled} inputMode={numeric ? 'decimal' : undefined}
      onChange={(e) => setV(e.target.value)} onBlur={commit}
      onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); if (e.key === 'Escape') { setV(value); setTimeout(() => ref.current?.blur()) } }} />
  )
}

export function CurrencySelect({ value, onChange, className = 'cell', title }: { value: string; onChange: (v: string) => void; className?: string; title?: string }) {
  const currencies = useStore((s) => s.info?.currencies || [])
  return (
    <select className={className} value={value} title={title || currencies.find((c) => c.code === value)?.name}
      onChange={(e) => onChange(e.target.value)}>
      {currencies.map((c) => <option key={c.code} value={c.code} title={c.name}>{c.code}</option>)}
    </select>
  )
}

export function Progress({ pct }: { pct: number }) {
  return <div className="progress"><div style={{ width: `${Math.round(pct * 100)}%` }} /></div>
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <div className="box" />
      <div className="t">{title}</div>
      {children && <div style={{ marginTop: 6, maxWidth: 420, lineHeight: 1.5 }}>{children}</div>}
    </div>
  )
}

export function Loading({ text = 'Loading…' }: { text?: string }) {
  return <div className="row gap8 muted" style={{ padding: 24 }}><span className="spin" />{text}</div>
}

export function ErrorBox({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="alert err">
      <div className="ic">!</div>
      <div style={{ flex: 1 }}>{error}</div>
      {onRetry && <button className="btn sm danger" onClick={onRetry}>Retry</button>}
    </div>
  )
}

export function Field({ label, children, style }: { label: string; children: ReactNode; style?: React.CSSProperties }) {
  return <div className="field" style={style}><label>{label}</label>{children}</div>
}
