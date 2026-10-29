import { useState } from 'react'
import type { ProjectList } from '../api/types'
import { Field, Loading, Modal, StatusPill, SysBadge, ErrorBox } from '../components/ui'
import { actions, useData, useStore } from '../state/store'

const FILTERS = ['All', 'Draft', 'In review', 'Approved', 'Sent', 'Changes requested']
const COLS = 'minmax(0,2.3fr) minmax(0,1.3fr) 190px 56px 150px 140px 130px 120px 34px'

export default function Dashboard() {
  const { data, error, reload } = useData<ProjectList>('list_projects')
  const [filter, setFilter] = useState('All')
  const [menu, setMenu] = useState<string | null>(null)
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return <Loading />
  const rows = data.rows.filter((p) => filter === 'All' || p.status === filter)
  return (
    <>
      <div className="row gap12">
        <h1 className="h1">Quotations</h1>
        <div className="ml-auto row gap8">
          <button className="btn" onClick={() => actions.go('library')}>Price Library</button>
          <button className="btn primary" onClick={() => actions.setNewProject(true)}>+ New quotation from drawings</button>
        </div>
      </div>
      <div className="card" style={{ display: 'grid', gridTemplateColumns: 'repeat(4,minmax(0,1fr))' }}>
        <Kpi label="Active quotations" value={String(data.kpis.active)} />
        <Kpi label="In review" value={String(data.kpis.review)} />
        <Kpi label="Changes requested" value={String(data.kpis.changes)} color={data.kpis.changes ? 'var(--err-2)' : undefined} />
        <Kpi label="Total quoted value (QAR)" value={data.kpis.pipelineF} last />
      </div>
      <div className="card">
        <div className="row gap6" style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)' }}>
          {FILTERS.map((f) => {
            const n = f === 'All' ? data.rows.length : data.rows.filter((p) => p.status === f).length
            return <div key={f} className={`chip${filter === f ? ' on' : ''}`} onClick={() => setFilter(f)}>{f}<span className="n">{n}</span></div>
          })}
          <div className="ml-auto muted" style={{ fontSize: 12 }}>{rows.length} of {data.rows.length} quotations</div>
        </div>
        <div className="th" style={{ gridTemplateColumns: COLS }}>
          <div>Project</div><div>Client</div><div>Reference</div><div>Rev</div><div>Systems</div>
          <div className="num">Combined total (QAR)</div><div>Status</div><div>Last edited</div><div />
        </div>
        {rows.map((p) => (
          <div key={p.id} className="tr click" style={{ gridTemplateColumns: COLS, background: p.id === data.openId ? 'var(--row-soft)' : undefined }}
            onClick={() => actions.openProject(p.id)}>
            <div style={{ minWidth: 0 }}><div style={{ fontWeight: 600, color: 'var(--navy-ink)' }}>{p.name}</div><div className="muted" style={{ fontSize: 11.5 }}>{p.scope}</div></div>
            <div style={{ fontSize: 12.5 }}>{p.client}</div>
            <div className="mono" style={{ fontSize: 11.5, color: 'var(--text-2)' }}>{p.ref}</div>
            <div style={{ fontSize: 12 }}>{p.rev}</div>
            <div className="row" style={{ gap: 3, flexWrap: 'wrap' }}>{p.systems.map((y) => <SysBadge key={y.key} ab={y.ab} color={y.color} title={y.name} />)}</div>
            <div className="num" style={{ fontWeight: 500 }}>{p.totalF}</div>
            <div><StatusPill status={p.status} /></div>
            <div className="muted" style={{ fontSize: 11.5, lineHeight: 1.35 }}>{p.edited}<br />{p.by}</div>
            <div style={{ position: 'relative' }} onClick={(e) => e.stopPropagation()}>
              <button className="btn xs plain" title="More" onClick={() => setMenu(menu === p.id ? null : p.id)}>⋯</button>
              {menu === p.id && (
                <div className="search-pop" style={{ right: 0, left: 'auto', width: 160, top: 30 }}>
                  <div className="it" onClick={() => { setMenu(null); actions.openProject(p.id) }}>Open</div>
                  <div className="it" onClick={async () => { setMenu(null); await actions.mutate('duplicate_project', { id: p.id }, 'Quotation duplicated'); reload() }}>Duplicate</div>
                </div>
              )}
            </div>
          </div>
        ))}
        {data.rows.length === 0 && (
          <div style={{ padding: 48, textAlign: 'center' }} className="muted">
            <div style={{ fontWeight: 600, color: 'var(--text)', fontSize: 14 }}>No quotations yet</div>
            <div style={{ marginTop: 6 }}>Start a new quotation from your AutoCAD floor plans (DWG, DXF or PDF), or open the sample project to explore.</div>
            <div className="row gap8" style={{ justifyContent: 'center', marginTop: 14 }}>
              <button className="btn primary" onClick={() => actions.setNewProject(true)}>+ New quotation from drawings</button>
              <button className="btn" onClick={() => actions.openSample()}>Open sample project</button>
            </div>
          </div>
        )}
        {data.rows.length > 0 && rows.length === 0 && (
          <div style={{ padding: 48, textAlign: 'center' }} className="muted">
            <div style={{ fontWeight: 600, color: 'var(--text)', fontSize: 14 }}>No quotations with this status</div>
            <div style={{ marginTop: 6 }}>Clear the filter or start a new quotation from drawings.</div>
          </div>
        )}
      </div>
    </>
  )
}

function Kpi({ label, value, color, last }: { label: string; value: string; color?: string; last?: boolean }) {
  return (
    <div style={{ padding: '12px 16px', borderRight: last ? 0 : '1px solid var(--border-2)' }}>
      <div className="lbl-sm">{label}</div>
      <div style={{ fontSize: 20, fontWeight: 600, marginTop: 4, color }}>{value}</div>
    </div>
  )
}

export function NewProjectModal() {
  const open = useStore((s) => s.newProject)
  const [f, setF] = useState<Record<string, string>>({ name: '', client: '', scope: '', location: '', pmc: '', consultant: '', ref: '', attention: '', validity_days: '30' })
  const [busy, setBusy] = useState(false)
  if (!open) return null
  const upd = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value })
  const submit = async () => {
    setBusy(true)
    try { await actions.createProject(f) } catch (e) { alert((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <Modal title="New quotation from drawings" onClose={() => actions.setNewProject(false)} width={620}
      footer={<>
        <button className="btn plain" onClick={() => actions.setNewProject(false)}>Cancel</button>
        <button className="btn primary" disabled={!f.name.trim() || busy} onClick={submit}>Create and upload drawings →</button>
      </>}>
      <div className="hint">Project details appear on the quotation cover and every page header. You can change them later in Project details.</div>
      <Field label="Project name *"><input className="input lg" autoFocus value={f.name} onChange={upd('name')} placeholder="e.g. Es'hailSat HQ Fit-Out" /></Field>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Field label="Client"><input className="input lg" value={f.client} onChange={upd('client')} /></Field>
        <Field label="Attention"><input className="input lg" value={f.attention} onChange={upd('attention')} /></Field>
        <Field label="PMC"><input className="input lg" value={f.pmc} onChange={upd('pmc')} /></Field>
        <Field label="Consultant"><input className="input lg" value={f.consultant} onChange={upd('consultant')} /></Field>
        <Field label="Scope / floors"><input className="input lg" value={f.scope} onChange={upd('scope')} placeholder="2nd & 3rd Floors" /></Field>
        <Field label="Location"><input className="input lg" value={f.location} onChange={upd('location')} placeholder="BC-B01 Gateway Offices, Lusail" /></Field>
        <Field label="Quotation reference"><input className="input lg mono" value={f.ref} onChange={upd('ref')} placeholder="auto if blank" /></Field>
        <Field label="Validity (days)"><input className="input lg" value={f.validity_days} onChange={upd('validity_days')} /></Field>
      </div>
    </Modal>
  )
}
