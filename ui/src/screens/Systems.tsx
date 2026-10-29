import { useState } from 'react'
import type { Option, ParamSpec, SystemsView } from '../api/types'
import { Card, ErrorBox, Loading, Toggle } from '../components/ui'
import { actions, useData } from '../state/store'

const COLS = '52px minmax(0,1.2fr) minmax(0,1.6fr) 130px 130px'
const STANDARDS: Record<string, string> = {
  cctv: 'MOI-SSD requirements, BS EN 62676-4 (pixel density), BS EN 62676 (CCTV).',
  access: 'MOI-SSD requirements, BS EN 60839-11 (access control), Qatar Civil Defence emergency release.',
  iptv: 'Display sizes by room area; IPTV over the converged network.',
  cabling: 'ISO/IEC 11801, TIA-568, 90 m permanent link limit.',
  intercom: 'SIP-based IP intercom.',
  intrusion: 'EN 50131 (grade per parameter).',
}

export default function Systems() {
  const { data, error, reload } = useData<SystemsView>('get_systems')
  const [sel, setSel] = useState('cctv')
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return <Loading />
  const cur = data.systems.find((s) => s.key === sel)!
  const toggleAll = () => {
    if (data.allOn) actions.mutate('set_systems', { combined: false })
    else actions.mutate('set_systems', { selected: data.systems.map((s) => s.key), combined: true })
  }
  const toggle = (key: string, on: boolean) => {
    const next = on ? [...data.selected, key] : data.selected.filter((k) => k !== key)
    actions.mutate('set_systems', { selected: next })
  }
  const comb = data.combined && data.selected.length > 1
  return (
    <>
      <div className="row gap12">
        <h2 className="h2">Step 2 · Systems &amp; design parameters</h2>
        <div className="ml-auto muted" style={{ fontSize: 12 }}>{data.summary}</div>
      </div>
      <div className="card row gap12" style={{ padding: '12px 16px', gap: 14 }}>
        <Toggle on={data.allOn} onChange={toggleAll} />
        <div>
          <div style={{ fontWeight: 600, color: 'var(--navy-ink)' }}>All six (combined award)</div>
          <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>Racks, UPS, network and cabling are shared when combined — shared infrastructure {data.sharedF !== '—' ? `QAR ${data.sharedF}` : ''} replaces per-system duplicates.</div>
        </div>
        <div className="row gap10 ml-auto">
          <label className="row gap6" style={{ fontSize: 12 }}>
            <Toggle small on={data.combined} onChange={(v) => actions.mutate('set_systems', { combined: v })} />Combined award
          </label>
          <div style={{ textAlign: 'right', marginLeft: 12 }}>
            <div className="lbl-sm">SAVING VS STANDALONE</div>
            <div style={{ fontSize: 16, fontWeight: 600, color: comb ? 'var(--ok)' : 'var(--muted-2)' }}>{comb ? `QAR ${data.savingF}` : 'Not applicable'}</div>
          </div>
        </div>
      </div>
      <div className="split" style={{ gridTemplateColumns: 'minmax(0,1fr) 380px' }}>
        <div className="card">
          <div className="th" style={{ gridTemplateColumns: COLS, gap: 10 }}>
            <div>Include</div><div>System</div><div>Quantities from layout</div><div className="num">Standalone (QAR)</div><div className="num">Combined (QAR)</div>
          </div>
          {data.systems.map((y) => (
            <div key={y.key} className="tr click" onClick={() => setSel(y.key)}
              style={{ gridTemplateColumns: COLS, gap: 10, minHeight: 48, background: sel === y.key ? 'var(--row-sel)' : undefined, opacity: y.on ? 1 : 0.5 }}>
              <div><Toggle small on={y.on} onChange={(v) => toggle(y.key, v)} /></div>
              <div className="row gap8"><span className="sq" style={{ background: y.color }} /><span style={{ fontWeight: 600 }}>{y.full}</span></div>
              <div style={{ fontSize: 12 }}><b style={{ fontWeight: 500 }}>{y.qty}</b><span className="muted"> · {y.detail}</span></div>
              <div className="num">{y.on ? y.standaloneF : '—'}</div>
              <div className="num" style={{ fontWeight: 500 }}>{y.on ? (comb ? y.combinedF : '—') : '—'}</div>
            </div>
          ))}
          <div className="tr" style={{ gridTemplateColumns: COLS, gap: 10, minHeight: 40, background: 'var(--sec-bg)', fontSize: 12.5 }}>
            <div /><div className="muted">Shared infrastructure</div><div className="muted" style={{ fontSize: 12 }}>Racks, UPS, backbone, containment</div>
            <div className="num muted2">—</div><div className="num" style={{ fontWeight: 500 }}>{data.sharedF}</div>
          </div>
          <div className="tr" style={{ gridTemplateColumns: COLS, gap: 10, minHeight: 42, borderTop: '2px solid var(--navy)', fontWeight: 600, borderBottom: 0 }}>
            <div /><div>Base total</div><div /><div className="num">{data.baseStandaloneF}</div><div className="num" style={{ color: 'var(--navy-ink)' }}>{comb ? data.baseCombinedF : '—'}</div>
          </div>
        </div>
        <Card title={<><span className="sq" style={{ background: cur.color }} />{cur.full} · design parameters</>}
          right={<button className="btn link" style={{ fontSize: 11.5 }} onClick={() => actions.mutate('set_params', { system: sel, reset: true }, 'Defaults restored')}>Reset</button>}>
          <div style={{ padding: '6px 14px 14px' }}>
            {data.params[sel].map((p) => <ParamRow key={p.key} sys={sel} p={p} />)}
            <div className="hint" style={{ marginTop: 12 }}>Standards: {STANDARDS[sel]} Changes re-run placement and pricing immediately; your edits on the plan are kept.</div>
          </div>
        </Card>
      </div>
    </>
  )
}

function opt(o: string | Option): Option { return typeof o === 'string' ? { value: o, label: o } : o }

function ParamRow({ sys, p }: { sys: string; p: ParamSpec }) {
  const [v, setV] = useState(String(p.value ?? ''))
  const [open, setOpen] = useState(false)
  const save = (value: unknown) => actions.mutate('set_params', { system: sys, values: { [p.key]: value } })
  let control: React.ReactNode
  if (p.type === 'select') {
    control = (
      <select className="input" value={String(p.value)} onChange={(e) => save(e.target.value)} style={{ maxWidth: 210 }}>
        {p.options.map(opt).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    )
  } else if (p.type === 'multi') {
    const vals: string[] = p.value || []
    const opts = p.options.map(opt)
    control = (
      <div style={{ position: 'relative' }}>
        <button className="input" style={{ maxWidth: 210, textAlign: 'right', cursor: 'pointer' }} onClick={() => setOpen(!open)} title={vals.map((x) => opts.find((o) => o.value === x)?.label).join(', ')}>
          {vals.length} room types ▾
        </button>
        {open && (
          <div className="search-pop" style={{ left: 'auto', right: 0, width: 240, top: 30, padding: 6 }} onMouseLeave={() => setOpen(false)}>
            {opts.map((o) => {
              const on = vals.includes(o.value)
              return (
                <label key={o.value} className="row gap8" style={{ padding: '4px 6px', cursor: 'pointer', fontSize: 12 }}
                  onClick={(e) => { e.preventDefault(); save(on ? vals.filter((x) => x !== o.value) : [...vals, o.value]) }}>
                  <span className={`cbx s14${on ? ' on' : ''}`}>{on ? '✓' : ''}</span>{o.label}
                </label>
              )
            })}
          </div>
        )}
      </div>
    )
  } else {
    control = (
      <span className="row gap6">
        <input className={`input${p.type === 'number' ? ' r' : ''}`} style={{ width: p.type === 'number' ? 80 : 170 }} value={v}
          onChange={(e) => setV(e.target.value)} onBlur={() => { if (v !== String(p.value)) save(v) }}
          onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }} />
        {p.unit && <span className="muted" style={{ fontSize: 11.5, minWidth: 24 }}>{p.unit}</span>}
      </span>
    )
  }
  return (
    <div className="row" style={{ justifyContent: 'space-between', gap: 12, padding: '8px 0', borderBottom: '1px solid var(--border-3)' }}>
      <span className="muted" style={{ fontSize: 12 }} title={p.help}>{p.label}</span>
      {control}
    </div>
  )
}
