import { useEffect, useRef, useState } from 'react'
import { call } from '../api/bridge'
import type { PriceRow, ProjectRow } from '../api/types'
import { actions, useStore, type Screen } from '../state/store'
import { StatusPill } from './ui'

const STEP_SCREENS: Screen[] = ['drawings', 'systems', 'layout', 'comms', 'boq', 'checks']

export function Sidebar() {
  const screen = useStore((s) => s.screen)
  const project = useStore((s) => s.project)
  const info = useStore((s) => s.info)
  const count = useStore((s) => s.info?.libraryCount)
  const [nProjects, setN] = useState<number | null>(null)
  const rev = useStore((s) => s.rev)
  useEffect(() => { call<{ rows: unknown[] }>('list_projects').then((r) => setN(r.rows.length)).catch(() => undefined) }, [rev])
  const nav: [Screen, string, string][] = [
    ['dashboard', 'Quotations', nProjects == null ? '' : String(nProjects)],
    ['library', 'Price Library', count ? count.toLocaleString('en-US') : ''],
    ['history', 'Revision history', ''],
    ['settings', 'Settings', ''],
  ]
  return (
    <aside className="side">
      <div className="side-brand">
        <div className="side-logo">EE</div>
        <div className="col"><span className="side-title">ELV Estimator</span><span className="side-sub">Estimating &amp; Quotations</span></div>
      </div>
      <div className="side-label">WORKSPACE</div>
      {nav.map(([k, label, badge]) => (
        <div key={k} className={`side-item${screen === k ? ' active' : ''}`} onClick={() => actions.go(k)}
          style={k === 'history' && !project ? { opacity: .5, cursor: 'default' } : undefined}>
          {label}<span className="side-badge">{badge}</span>
        </div>
      ))}
      {project && <>
        <div className="side-label mt">OPEN QUOTATION</div>
        <div className="side-card" onClick={() => actions.go('details')} title="Project details">
          <div className="t">{project.info.name}</div>
          <div className="r">{project.info.ref || '—'}</div>
        </div>
        {project.steps.map((st, i) => (
          <div key={st.key} className={`side-step${screen === st.key ? ' active' : ''}`} onClick={() => actions.go(st.key as Screen)}>
            <span className="n">{i + 1}</span>{st.label}
          </div>
        ))}
        <div className="side-sep" />
        <div className={`side-step${screen === 'details' ? ' active' : ''}`} onClick={() => actions.go('details')}><span className="n">·</span>Project details</div>
        <div className={`side-step${screen === 'texts' ? ' active' : ''}`} onClick={() => actions.go('texts')}><span className="n">·</span>Assumptions &amp; exclusions</div>
      </>}
      <div className="side-foot">
        <div className="avatar">{info?.user.initials || 'EE'}</div>
        <div className="col" style={{ minWidth: 0 }}>
          <span style={{ fontSize: 12.5 }} className="ellipsis">{info?.user.name || 'Estimator'}</span>
          <span style={{ fontSize: 11, color: 'var(--side-muted-2)' }}>{info?.user.role || 'ELV Estimator'}</span>
        </div>
      </div>
    </aside>
  )
}

const CRUMBS: Partial<Record<Screen, string>> = {
  dashboard: 'Quotations', library: 'Price Library', settings: 'Settings', history: 'Revision history',
  drawings: 'Drawings', systems: 'Systems', layout: 'Device Layout', comms: 'Comms Rooms', boq: 'BOQ & Pricing',
  checks: 'Checks & Export', details: 'Project details', texts: 'Assumptions & exclusions',
}

export function TopBar() {
  const screen = useStore((s) => s.screen)
  const project = useStore((s) => s.project)
  const ticker = useStore((s) => s.info?.ticker)
  const inProject = project && !['dashboard', 'library', 'settings'].includes(screen)
  return (
    <div className="topbar">
      <div className="crumb">
        {inProject ? <>
          <span onClick={() => actions.go('dashboard')}>Quotations</span> / <span onClick={() => actions.go('details')}>{project!.info.name}</span> / {CRUMBS[screen]}
        </> : CRUMBS[screen]}
      </div>
      <Search />
      <div className="ticker" title="Exchange rates to QAR (Settings)">{ticker}</div>
    </div>
  )
}

function Search() {
  const [q, setQ] = useState('')
  const [res, setRes] = useState<{ projects: ProjectRow[]; items: PriceRow[] } | null>(null)
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (q.trim().length < 2) { setRes(null); return }
    const t = setTimeout(() => { call<{ projects: ProjectRow[]; items: PriceRow[] }>('search', { q }).then(setRes).catch(() => undefined) }, 180)
    return () => clearTimeout(t)
  }, [q])
  useEffect(() => {
    const h = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  return (
    <div className="search" ref={box}>
      <input placeholder="Search projects, items, part numbers…" value={q} onFocus={() => setOpen(true)}
        onChange={(e) => { setQ(e.target.value); setOpen(true) }} onKeyDown={(e) => { if (e.key === 'Escape') { setOpen(false); (e.target as HTMLInputElement).blur() } }} />
      {open && res && (res.projects.length > 0 || res.items.length > 0) && (
        <div className="search-pop">
          {res.projects.length > 0 && <div className="grp">QUOTATIONS</div>}
          {res.projects.map((p) => (
            <div key={p.id} className="it" onClick={() => { setOpen(false); setQ(''); actions.openProject(p.id) }}>
              <div style={{ fontWeight: 600, color: 'var(--navy-ink)' }}>{p.name}</div>
              <div className="mono muted" style={{ fontSize: 11 }}>{p.ref} · {p.client}</div>
            </div>
          ))}
          {res.items.length > 0 && <div className="grp">PRICE LIBRARY</div>}
          {res.items.map((r) => (
            <div key={r.key} className="it" onClick={() => { setOpen(false); sessionStorage.setItem('elv-lib-q', r.part || r.desc); actions.go('library'); actions.bump() }}>
              <div>{r.desc}</div>
              <div className="muted" style={{ fontSize: 11 }}><span className="mono">{r.part}</span> · {r.mfr} · {r.list ? `${r.cur} ${r.list}` : 'no price'}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function ProjectHeader() {
  const p = useStore((s) => s.project)!
  const screen = useStore((s) => s.screen)
  const h = p.header
  const meta = [p.info.scope, p.info.location].filter(Boolean).join(', ')
  return (
    <div className="phead">
      <div className="phead-top">
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="row gap10">
            <h1>{p.info.name}</h1>
            <span className="rev-chip">{p.revLabel}</span>
            <StatusPill status={p.status} />
          </div>
          <div className="phead-meta">
            {meta && <span>{meta}</span>}
            {p.info.client && <span>Client <b>{p.info.client}</b></span>}
            {p.info.pmc && <span>PMC <b>{p.info.pmc}</b></span>}
            {p.info.ref && <span className="mono">{p.info.ref}</span>}
            {p.drawingRefs && <span className="mono">{p.drawingRefs}</span>}
          </div>
        </div>
        <div className="kpibox">
          <div><div className="kpi-l">{h.baseLabel}</div><div className="kpi-big">{h.baseF}</div></div>
          <div><div className="kpi-l">NETWORK ACTIVE</div><div className="kpi-v">{h.networkF}</div></div>
          <div><div className="kpi-l">SAVING VS STANDALONE</div><div className="kpi-v" style={{ color: 'var(--ok)' }}>{h.savingF}</div></div>
        </div>
      </div>
      <div className="stepper">
        {p.steps.map((st, i) => {
          const a = screen === st.key
          const done = st.done && !a
          return (
            <div key={st.key} className={`step${a ? ' active' : ''}`} onClick={() => actions.go(STEP_SCREENS[i])}>
              <div className="step-dot" style={{
                background: a ? 'var(--navy)' : '#fff', color: a ? '#fff' : done ? 'var(--ok)' : 'var(--muted)',
                borderColor: a ? 'var(--navy)' : done ? 'var(--ok-border)' : 'var(--input-border)',
              }}>{a || !done ? i + 1 : '✓'}</div>
              <div className="col" style={{ minWidth: 0 }}>
                <span className="step-label" style={{ fontWeight: a ? 600 : 500, color: a ? 'var(--navy-ink)' : 'var(--text-2)' }}>{st.label}</span>
                <span className="step-sub">{st.sub}</span>
              </div>
              <div className="step-line" />
            </div>
          )
        })}
      </div>
    </div>
  )
}
