import { useEffect, useMemo, useState } from 'react'
import { call } from '../api/bridge'
import type { BoqLine, BoqView, PricesView } from '../api/types'
import { ConfBadge, CurrencySelect, EditCell, ErrorBox, Loading, Modal, Seg } from '../components/ui'
import { actions, useData } from '../state/store'

const COLS = 'minmax(0,1fr) 118px 124px 38px 64px 86px 62px 54px 92px 104px 96px 26px'
const BAR: Record<string, string> = { high: 'var(--ok)', med: 'var(--med-bar)', lab: 'var(--lab-bar)', bud: 'var(--bud)', oth: 'var(--oth-bar)' }

export default function Boq() {
  const { data, error, reload } = useData<BoqView>('get_boq')
  const [tab, setTab] = useState('cctv')
  const [view, setView] = useState<'combined' | 'standalone'>('combined')
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [adding, setAdding] = useState<{ tab: string; section: string } | null>(null)
  useEffect(() => {
    if (data && !data.tabs.find((t) => t.key === tab)) setTab(data.tabs[0]?.key || 'cctv')
  }, [data]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (data && !data.combined) setView('standalone') }, [data?.combined]) // eslint-disable-line react-hooks/exhaustive-deps
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return <Loading />
  const T = data.tabs.find((t) => t.key === tab) || data.tabs[0]
  if (!T) return <div className="card" style={{ padding: 24 }}>Select at least one system in Step 2.</div>
  const comb = view === 'combined' && data.combined
  const isOpen = (id: string, i: number) => open[id] ?? i === 0
  const anyClosed = T.sections.some((s, i) => !isOpen(s.id, i))
  const tabTotal = T.isSystem && !comb ? T.standaloneF : T.combinedF
  const tabNote = T.isSystem
    ? (comb ? 'Shared-eligible items excluded — priced once in Shared infrastructure' : 'Includes system-specific racks, UPS, network and cabling')
    : ({ shared: 'Priced once for the combined award', network: 'Quoted separately from the ELV base total', optional: 'Not included in base total — client to confirm' } as Record<string, string>)[T.key]
  const editLine = (l: BoqLine, patch: Record<string, unknown>) => actions.mutate('update_boq_line', { key: l.key, item: l.item, patch })
  return (
    <>
      {data.unpriced > 0 && (
        <div className="alert warn">
          <div className="ic">!</div>
          <div style={{ flex: 1 }}><b>{data.unpriced} BOQ line{data.unpriced === 1 ? ' has' : 's have'} no price.</b> <span style={{ fontSize: 12 }}>Type list prices directly in the table, or fill the Price Library once and every quotation uses them.</span></div>
          <button className="btn sm primary" onClick={() => { sessionStorage.setItem('elv-lib-filter', JSON.stringify({ used: true, unpriced: true })); actions.go('library') }}>Enter prices in Price Library</button>
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.15fr) minmax(0,1fr) minmax(0,1.25fr)', gap: 12 }}>
        <div className="card">
          <div className="card-h sm">Standalone vs combined (QAR)</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 96px 96px', gap: 8, padding: '4px 12px', fontSize: 11.5 }}>
            <div className="muted" style={{ padding: '3px 0' }}>System</div><div className="muted num" style={{ padding: '3px 0' }}>Standalone</div><div className="muted num" style={{ padding: '3px 0' }}>Combined</div>
            {data.sysRows.map((y) => <Frag key={y.key}>
              <div className="row gap6" style={{ padding: '2px 0' }}><span className="sq" style={{ width: 7, height: 7, background: y.color }} />{y.name}</div>
              <div className="num muted" style={{ padding: '2px 0' }}>{y.sa}</div><div className="num" style={{ padding: '2px 0' }}>{y.co}</div>
            </Frag>)}
            <div style={{ padding: '2px 0' }}>Shared infrastructure</div><div className="num muted2">—</div><div className="num">{data.combined ? data.m.shared : '—'}</div>
            <div style={{ padding: '5px 0 3px', borderTop: '1px solid var(--navy)', fontWeight: 600 }}>Base total</div>
            <div className="num" style={{ padding: '5px 0 3px', borderTop: '1px solid var(--navy)', fontWeight: 600 }}>{data.m.standalone}</div>
            <div className="num" style={{ padding: '5px 0 3px', borderTop: '1px solid var(--navy)', fontWeight: 600, color: 'var(--navy-ink)' }}>{data.combined ? data.m.combinedBase : '—'}</div>
            <div style={{ color: 'var(--ok)', fontWeight: 600 }}>Saving</div><div /><div className="num" style={{ color: 'var(--ok)', fontWeight: 600 }}>{data.combined ? data.m.saving : '—'}</div>
          </div>
        </div>
        <div className="card">
          <div className="card-h sm">Price confidence (by value)</div>
          <div style={{ padding: 12 }}>
            <div style={{ display: 'flex', height: 12, borderRadius: 2, overflow: 'hidden', gap: 1, background: 'var(--border-2)' }}>
              {data.confMix.map((c) => <div key={c.k} style={{ width: `${c.v}%`, background: BAR[c.tone] }} />)}
            </div>
            <div className="col" style={{ gap: 5, marginTop: 10, fontSize: 12 }}>
              {data.confMix.map((c) => <div key={c.k} className="row gap8"><span className="sq" style={{ width: 9, height: 9, background: BAR[c.tone] }} />{c.k}<span className="ml-auto" style={{ fontWeight: 600 }}>{c.v}%</span></div>)}
            </div>
            <div style={{ marginTop: 10, paddingTop: 8, borderTop: '1px solid var(--border-3)', display: 'grid', gridTemplateColumns: '1fr auto', gap: 3, fontSize: 12 }}>
              <span className="muted">Network Active (separate)</span><b style={{ fontWeight: 600 }}>{data.m.network}</b>
              <span className="muted">Optional items</span><b style={{ fontWeight: 600 }}>{data.m.optional}</b>
              <span className="muted">Lines without price · RFQ</span><b style={{ fontWeight: 600, color: data.unpriced ? 'var(--err)' : undefined }}>{data.unpriced} · {data.rfq}</b>
            </div>
          </div>
        </div>
        <Commercial data={data} />
      </div>

      <div className="card">
        <div className="row" style={{ alignItems: 'flex-end', borderBottom: '1px solid var(--border)', padding: '0 8px', gap: 2, flexWrap: 'wrap' }}>
          {data.tabs.map((t) => {
            const a = t.key === tab
            return (
              <div key={t.key} onClick={() => setTab(t.key)} style={{ padding: '9px 11px 8px', cursor: 'pointer', borderBottom: `3px solid ${a ? 'var(--navy)' : 'transparent'}`, display: 'flex', flexDirection: 'column', gap: 1 }}>
                <span className="row gap6" style={{ fontSize: 12, fontWeight: a ? 600 : 500, color: a ? 'var(--navy-ink)' : 'var(--text-2)', whiteSpace: 'nowrap' }}>
                  <span className="sq" style={{ width: 7, height: 7, background: t.color || 'var(--muted-2)' }} />{t.name}
                </span>
                <span className="muted" style={{ fontSize: 11, paddingLeft: 13 }}>{t.isSystem && !comb ? t.standaloneF : t.combinedF}</span>
              </div>
            )
          })}
          <div className="row gap8 ml-auto" style={{ paddingBottom: 8 }}>
            <span className="muted" style={{ fontSize: 11.5 }}>View</span>
            <Seg light value={comb ? 'combined' : 'standalone'} onChange={(v) => setView(v as 'combined' | 'standalone')}
              options={data.combined ? [{ value: 'combined', label: 'Combined' }, { value: 'standalone', label: 'Standalone' }] : [{ value: 'standalone', label: 'Standalone' }]} />
            <button className="btn xs plain" onClick={() => { const o = { ...open }; T.sections.forEach((s) => { o[s.id] = anyClosed }); setOpen(o) }}>{anyClosed ? 'Expand all' : 'Collapse all'}</button>
          </div>
        </div>
        <div className="th" style={{ gridTemplateColumns: COLS, gap: 8, fontSize: 11 }}>
          <div>Description</div><div>Manufacturer</div><div>Part No.</div><div>Unit</div><div className="num">Qty</div><div className="num">List price</div><div>Curr.</div><div className="num">Disc. %</div><div className="num">Unit QAR</div><div className="num">Total QAR</div><div>Confidence</div><div />
        </div>
        {T.sections.map((s, i) => {
          const o = isOpen(s.id, i)
          const muted = s.isShared && comb
          return (
            <div key={s.id}>
              <div onClick={() => setOpen({ ...open, [s.id]: !o })} className="row gap10"
                style={{ padding: '0 12px', height: 34, background: s.isShared ? 'var(--sec-shared-bg)' : 'var(--sec-bg)', borderBottom: '1px solid var(--border-sec)', cursor: 'pointer', opacity: muted ? 0.75 : 1 }}>
                <span style={{ width: 12, fontSize: 10, color: 'var(--navy)' }}>{o ? '▼' : '▶'}</span>
                <span style={{ fontWeight: 600, color: 'var(--navy-ink)' }}>{s.name}</span>
                <span className="muted" style={{ fontSize: 11.5 }}>{s.count} lines</span>
                {s.isShared && <span className="row gap6" style={{ fontSize: 11, color: 'var(--navy)', border: '1px solid var(--dash)', borderRadius: 3, padding: '1px 6px', background: '#fff' }}>
                  <b>⇄</b>{comb ? 'Moved to Shared infrastructure in combined award' : 'Moves to Shared infrastructure if combined'}</span>}
                <span className="ml-auto" style={{ fontWeight: 600, textDecoration: muted ? 'line-through' : 'none' }}>{s.subF}</span>
              </div>
              {o && s.lines.map((l) => (
                <div key={l.key} style={{ display: 'grid', gridTemplateColumns: COLS, gap: 8, padding: '0 12px', minHeight: 34, alignItems: 'center', borderBottom: '1px solid var(--border-3)', fontSize: 12,
                  background: l.unpriced ? '#FFFBFA' : l.budget ? 'var(--bud-row)' : '#fff', opacity: muted ? 0.5 : Number(l.qty) === 0 ? 0.55 : 1 }}>
                  <div className="row gap6" style={{ minWidth: 0, paddingLeft: 22 }}>
                    {l.shared && <span title="Moves to Shared infrastructure in a combined award" style={{ flex: 'none', width: 16, height: 16, border: '1px solid var(--dash)', borderRadius: 3, fontSize: 10, fontWeight: 700, color: 'var(--navy)', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fff' }}>⇄</span>}
                    {l.custom ? <EditCell value={l.desc} numeric={false} align="left" onCommit={(v) => editLine(l, { description: v })} />
                      : <span className="ellipsis" title={`${l.desc}${l.note ? '\nQuantity: ' + l.note : ''}`}>{l.desc}</span>}
                    {l.budget && <span className="rfq">RFQ required</span>}
                  </div>
                  <div className="ellipsis" title={l.mfr}>{l.mfr}</div>
                  <div className="mono ellipsis" style={{ fontSize: 11, color: 'var(--text-2)' }} title={l.part}>{l.part}</div>
                  <div className="muted">{l.unit}</div>
                  <EditCell value={l.qtyF.replace(/,/g, '')} className={l.overridden.includes('qty') ? 'ovr' : ''} title={l.overridden.includes('qty') ? `Overridden (layout: ${l.qtyAuto}) — clear to restore` : l.note}
                    onCommit={(v) => editLine(l, { qty: v })} />
                  <EditCell value={l.list ?? ''} placeholder="price" className={`${l.overridden.includes('list_price') ? 'ovr' : ''} ${l.unpriced ? 'need' : ''}`}
                    title={l.source ? `${l.source}${l.date ? ' · ' + l.date : ''}` : 'Enter the list price'} onCommit={(v) => editLine(l, { list_price: v })} />
                  <CurrencySelect value={l.cur} onChange={(v) => editLine(l, { currency: v })} />
                  <EditCell value={l.disc === '0' ? '' : l.disc} placeholder="—" disabled={l.category === 'Labour'} onCommit={(v) => editLine(l, { discount: v })} />
                  <div className="num">{l.unitF}</div>
                  <div className="num" style={{ fontWeight: 500 }}>{l.totalF}</div>
                  <div><ConfBadge conf={l.conf} label={l.confLabel} /></div>
                  <div>
                    {l.custom ? <button className="btn xs plain" title="Remove line" onClick={() => actions.mutate('delete_boq_line', { key: l.key })}>✕</button>
                      : l.overridden.length > 0 ? <button className="btn xs plain" title="Restore calculated values" onClick={() => editLine(l, { reset: true })}>↺</button> : null}
                  </div>
                </div>
              ))}
              {o && (
                <div style={{ padding: '4px 12px 6px 46px', borderBottom: '1px solid var(--border-3)' }}>
                  <button className="btn link" style={{ fontSize: 11.5 }} onClick={() => setAdding({ tab: T.key, section: s.name })}>+ Add item to {s.name}</button>
                </div>
              )}
            </div>
          )
        })}
        {T.sections.length === 0 && <div className="muted" style={{ padding: 20 }}>No lines.</div>}
        <div className="row gap16" style={{ padding: '0 12px', height: 44, borderTop: '2px solid var(--navy)', background: 'var(--sec-bg)' }}>
          <span style={{ fontWeight: 600, color: 'var(--navy-ink)' }}>{T.name} — {T.isSystem ? (comb ? 'combined' : 'standalone') : 'tab'} total</span>
          <span className="muted" style={{ fontSize: 11.5 }}>{tabNote}</span>
          <span className="ml-auto" style={{ fontSize: 16, fontWeight: 700, color: 'var(--navy-ink)' }}>QAR {tabTotal}</span>
        </div>
      </div>
      {adding && <AddLine {...adding} onClose={() => setAdding(null)} />}
    </>
  )
}

function Frag({ children }: { children: React.ReactNode }) { return <>{children}</> }

function Commercial({ data }: { data: BoqView }) {
  const c = data.commercial
  const [markup, setMarkup] = useState(Number(c.markup || 0))
  useEffect(() => { setMarkup(Number(c.markup || 0)) }, [c.markup])
  const set = (k: string) => (v: string) => actions.mutate('set_commercial', { [k]: v })
  return (
    <div className="card">
      <div className="card-h sm">Commercial controls<span className="r">applies to all tabs</span></div>
      <div style={{ padding: '10px 12px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 16px', fontSize: 12 }}>
        <div className="row gap10" style={{ gridColumn: '1 / span 2' }}>
          <span className="muted" style={{ width: 52 }}>Markup</span>
          <input type="range" min={0} max={60} step={1} value={markup} style={{ flex: 1, accentColor: 'var(--navy)' }}
            onChange={(e) => setMarkup(Number(e.target.value))}
            onMouseUp={() => actions.mutate('set_commercial', { markup: String(markup) })}
            onKeyUp={() => actions.mutate('set_commercial', { markup: String(markup) })}
            onTouchEnd={() => actions.mutate('set_commercial', { markup: String(markup) })} />
          <b style={{ width: 38, textAlign: 'right' }}>{markup}%</b>
        </div>
        <Pct label="Duty" value={c.duty} onCommit={set('duty')} />
        <Pct label="Freight" value={c.freight} onCommit={set('freight')} />
        {data.fx.filter((f) => f.code !== 'QAR').map((f) => (
          <div key={f.code} className="row" style={{ justifyContent: 'space-between' }}>
            <span className="muted" title={f.name}>{f.code} → QAR{f.project ? ' *' : ''}</span>
            <EditCell value={f.rate} width={70} title={f.project ? 'Project rate (blank = library rate ' + f.libRate + ')' : `Library rate${f.asOf ? ' as of ' + f.asOf : ''}`}
              className={f.project ? 'ovr' : ''} onCommit={(v) => actions.mutate('set_fx', { code: f.code, rate: v, scope: 'project' })} />
          </div>
        ))}
        <div style={{ gridColumn: '1 / span 2', borderTop: '1px solid var(--border-3)', paddingTop: 6, fontSize: 11, fontWeight: 600 }} className="muted">LABOUR RATES (QAR / HR, COST)</div>
        <div style={{ gridColumn: '1 / span 2', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2px 16px' }}>
          {data.labour.map((lb) => (
            <div key={lb.key} className="row" style={{ justifyContent: 'space-between' }}>
              <span>{lb.role}</span>
              <EditCell value={lb.rate} width={64} placeholder="rate" className={lb.rate ? '' : 'need'} onCommit={(v) => actions.mutate('set_labour_rate', { key: lb.key, rate: v, currency: 'QAR' })} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function Pct({ label, value, onCommit }: { label: string; value: string; onCommit: (v: string) => void }) {
  return (
    <div className="row" style={{ justifyContent: 'space-between' }}>
      <span className="muted">{label}</span>
      <span className="row" style={{ gap: 2 }}><EditCell value={value} width={48} onCommit={onCommit} /><b>%</b></span>
    </div>
  )
}

function AddLine({ tab, section, onClose }: { tab: string; section: string; onClose: () => void }) {
  const [q, setQ] = useState('')
  const [res, setRes] = useState<PricesView | null>(null)
  const [custom, setCustom] = useState({ description: '', manufacturer: '', part_no: '', unit: 'ea', qty: '1', list_price: '', currency: 'USD' })
  useEffect(() => {
    const t = setTimeout(() => call<PricesView>('get_prices', { q }).then(setRes).catch(() => undefined), 150)
    return () => clearTimeout(t)
  }, [q])
  const rows = useMemo(() => (res?.rows || []).slice(0, 60), [res])
  const add = async (args: Record<string, unknown>) => { await actions.mutate('add_boq_line', { tab, section, ...args }, 'Line added'); onClose() }
  return (
    <Modal title={`Add item · ${section}`} onClose={onClose} width={760}>
      <div className="hint">Pick from the price library (its price is used), or add a one-off line below.</div>
      <input className="input lg" autoFocus placeholder="Search description, manufacturer or part number…" value={q} onChange={(e) => setQ(e.target.value)} />
      <div style={{ maxHeight: 280, overflowY: 'auto', border: '1px solid var(--border-2)', borderRadius: 4 }}>
        {rows.map((r) => (
          <div key={r.key} className="tr sm click" style={{ gridTemplateColumns: 'minmax(0,1fr) 120px 120px 90px', gap: 10 }} onClick={() => add({ item: r.key, qty: 1 })}>
            <div className="ellipsis">{r.desc}<span className="muted" style={{ fontSize: 11 }}> · {r.systemName}</span></div>
            <div className="ellipsis muted">{r.mfr}</div>
            <div className="mono ellipsis" style={{ fontSize: 11 }}>{r.part}</div>
            <div className="num">{r.list ? `${r.cur} ${r.list}` : <span className="badge t-none">no price</span>}</div>
          </div>
        ))}
      </div>
      <div className="lbl-sm" style={{ marginTop: 6 }}>ONE-OFF LINE</div>
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 60px 70px 90px 80px', gap: 8 }}>
        <input className="input" placeholder="Description" value={custom.description} onChange={(e) => setCustom({ ...custom, description: e.target.value })} />
        <input className="input" placeholder="Manufacturer" value={custom.manufacturer} onChange={(e) => setCustom({ ...custom, manufacturer: e.target.value })} />
        <input className="input" placeholder="Part No." value={custom.part_no} onChange={(e) => setCustom({ ...custom, part_no: e.target.value })} />
        <input className="input" placeholder="Unit" value={custom.unit} onChange={(e) => setCustom({ ...custom, unit: e.target.value })} />
        <input className="input r" placeholder="Qty" value={custom.qty} onChange={(e) => setCustom({ ...custom, qty: e.target.value })} />
        <input className="input r" placeholder="List price" value={custom.list_price} onChange={(e) => setCustom({ ...custom, list_price: e.target.value })} />
        <CurrencySelect className="input" value={custom.currency} onChange={(v) => setCustom({ ...custom, currency: v })} />
      </div>
      <div className="row"><button className="btn sm primary ml-auto" disabled={!custom.description.trim()} onClick={() => add(custom)}>Add one-off line</button></div>
    </Modal>
  )
}
