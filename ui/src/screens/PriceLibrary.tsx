import { useEffect, useRef, useState } from 'react'
import { call, pickFiles } from '../api/bridge'
import type { PriceRow, PricesView } from '../api/types'
import { CurrencySelect, EditCell, ErrorBox, Loading, Modal, Field } from '../components/ui'
import { actions, toast, useData, useStore } from '../state/store'

const COLS = 'minmax(0,1.8fr) 130px 150px minmax(0,1.3fr) 104px 112px 68px 110px'
const SYSTEMS: [string, string][] = [['', 'All systems'], ['cctv', 'CCTV'], ['access', 'Access Control'], ['iptv', 'Smart TV / IPTV'], ['cabling', 'Structured Cabling'],
  ['intercom', 'Intercom'], ['intrusion', 'Intrusion'], ['shared', 'Shared infrastructure'], ['network', 'Network Active'], ['optional', 'Optional'], ['labour', 'Labour']]
const CONF = [['', '—'], ['H', 'High'], ['M', 'Medium'], ['B', 'Budgetary'], ['O', 'Other']]
const CONF_STYLE: Record<string, [string, string]> = { H: ['var(--ok-bg)', 'var(--ok-ink)'], M: ['var(--med-bg)', 'var(--med-ink)'], B: ['var(--bud-bg)', 'var(--bud-ink)'], O: ['var(--oth-bg)', 'var(--oth-ink)'], L: ['var(--lab-bg)', 'var(--lab-ink)'], '': ['var(--err-bg)', 'var(--err-2)'] }

interface ImportPreview { rows: number; updates: number; new: number; warnings: number; preview: { part: string; desc: string; old: string | null; new: string | null; status: string; warn: string }[]; mapped: string[]; columns: number; name: string }

export default function PriceLibrary() {
  const project = useStore((s) => s.project)
  const categories = useStore((s) => s.info?.categories || [])
  const init = (() => { try { return JSON.parse(sessionStorage.getItem('elv-lib-filter') || '{}') } catch { return {} } })()
  const [q, setQ] = useState<string>(sessionStorage.getItem('elv-lib-q') || '')
  const [system, setSystem] = useState('')
  const [category, setCategory] = useState('')
  const [used, setUsed] = useState<boolean>(!!init.used && !!project)
  const [unpriced, setUnpriced] = useState<boolean>(!!init.unpriced)
  const [dq, setDq] = useState(q)
  useEffect(() => { sessionStorage.removeItem('elv-lib-filter'); sessionStorage.removeItem('elv-lib-q') }, [])
  useEffect(() => { const t = setTimeout(() => setDq(q), 200); return () => clearTimeout(t) }, [q])
  const { data, error, reload, setData } = useData<PricesView>('get_prices', { q: dq, system, category, used, unpriced })
  const [imp, setImp] = useState<{ preview: ImportPreview; args: Record<string, unknown> } | null>(null)
  const [adding, setAdding] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const update = async (r: PriceRow, patch: Record<string, unknown>) => {
    try {
      await call('update_price', { key: r.key, patch })
      reload()
      actions.refreshProject()
    } catch (e) { toast((e as Error).message, 'err', 6000) }
  }
  const startImport = async () => {
    try {
      const p = await pickFiles('csv')
      if (p === null) { fileInput.current?.click(); return }
      if (!p.length) return
      const args = { path: p[0] }
      setImp({ preview: await call<ImportPreview>('import_prices', args), args })
    } catch (e) { toast((e as Error).message, 'err') }
  }
  const onCsv = async (f: File) => {
    const text = await f.text()
    const args = { text, name: f.name }
    try { setImp({ preview: await call<ImportPreview>('import_prices', args), args }) } catch (e) { toast((e as Error).message, 'err') }
  }
  const commit = async () => {
    if (!imp) return
    try {
      const r = await call<ImportPreview>('import_prices', { ...imp.args, commit: true })
      toast(`${r.updates} prices updated, ${r.new} new items`, 'ok')
      setImp(null); reload(); actions.refreshProject(); actions.refreshInfo()
    } catch (e) { toast((e as Error).message, 'err') }
  }
  const exportCsv = async () => {
    try { const r = await call<{ path: string }>('export_prices'); toast(`Exported to ${r.path}`, 'ok', 8000) } catch (e) { toast((e as Error).message, 'err') }
  }

  if (error) return <ErrorBox error={error} onRetry={reload} />
  return (
    <>
      <div className="row gap12">
        <h1 className="h1">Price Library</h1>
        <span className="muted" style={{ fontSize: 12 }}>{data ? `${data.total.toLocaleString('en-US')} items · ${data.priced} priced · ${data.shown} shown` : ''}</span>
        <div className="ml-auto row gap8">
          <button className="btn plain" onClick={exportCsv}>Export CSV</button>
          <button className="btn plain" onClick={() => setAdding(true)}>+ Add item</button>
          <button className="btn primary" onClick={startImport}>Bulk import from CSV</button>
          <input ref={fileInput} type="file" accept=".csv,.txt" style={{ display: 'none' }} onChange={(e) => { const f = e.target.files?.[0]; if (f) onCsv(f); e.target.value = '' }} />
        </div>
      </div>
      {imp && (
        <div className="card" style={{ borderColor: 'var(--navy)', display: 'grid', gridTemplateColumns: '300px minmax(0,1fr)' }}>
          <div style={{ padding: 14, borderRight: '1px solid var(--border)' }}>
            <div className="dropzone" style={{ padding: 18 }}>
              <div style={{ fontWeight: 600, color: 'var(--navy-ink)' }}>{imp.preview.name || 'CSV file'}</div>
              <div className="muted" style={{ fontSize: 11.5, marginTop: 4 }}>{imp.preview.rows} rows · {imp.preview.columns} columns</div>
            </div>
            <div className="hint" style={{ marginTop: 10 }}>Columns mapped automatically: {imp.preview.mapped.join(', ')}. Rows are matched by key, part number, then description; unmatched rows become new items.</div>
          </div>
          <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div className="row gap16" style={{ fontSize: 12 }}>
              <span><b style={{ color: 'var(--ok)' }}>{imp.preview.updates}</b> price updates</span>
              <span><b style={{ color: 'var(--navy)' }}>{imp.preview.new}</b> new items</span>
              <span><b style={{ color: 'var(--amber-ink)' }}>{imp.preview.warnings}</b> warnings</span>
            </div>
            <div className="th" style={{ gridTemplateColumns: '130px minmax(0,1fr) 80px 80px 110px', gap: 8, fontSize: 11, padding: '6px 10px', minHeight: 0 }}>
              <div>Part No.</div><div>Description</div><div className="num">Old</div><div className="num">New</div><div>Status</div>
            </div>
            <div style={{ maxHeight: 220, overflowY: 'auto' }}>
              {imp.preview.preview.slice(0, 200).map((r, i) => (
                <div key={i} style={{ display: 'grid', gridTemplateColumns: '130px minmax(0,1fr) 80px 80px 110px', gap: 8, fontSize: 12, padding: '3px 10px' }}>
                  <div className="mono ellipsis" style={{ fontSize: 11 }}>{r.part}</div><div className="ellipsis">{r.desc}</div>
                  <div className="num">{r.old ?? '—'}</div><div className="num">{r.new ?? '—'}</div>
                  <div style={{ color: r.status === 'Update' ? 'var(--ok)' : r.status === 'New' ? 'var(--navy)' : 'var(--amber-ink)' }} title={r.warn}>{r.status}</div>
                </div>
              ))}
            </div>
            <div className="row gap8" style={{ justifyContent: 'flex-end' }}>
              <button className="btn sm plain" onClick={() => setImp(null)}>Cancel</button>
              <button className="btn sm primary" onClick={commit}>Import {imp.preview.updates + imp.preview.new} rows</button>
            </div>
          </div>
        </div>
      )}
      <div className="card">
        <div className="row gap8" style={{ padding: '10px 12px', borderBottom: '1px solid var(--border)', flexWrap: 'wrap' }}>
          <input className="input lg" style={{ width: 280 }} placeholder="Search item, manufacturer, part no., source…" value={q} onChange={(e) => setQ(e.target.value)} />
          <select className="input lg" value={system} onChange={(e) => setSystem(e.target.value)}>{SYSTEMS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          <select className="input lg" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>{categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          {project && <div className={`chip${used ? ' on' : ''}`} onClick={() => setUsed(!used)}>Used in this quotation<span className="n">{data?.usedCount ?? ''}</span></div>}
          <div className={`chip${unpriced ? ' on' : ''}`} onClick={() => setUnpriced(!unpriced)}>Unpriced only</div>
          <span className="ml-auto hint">Prices are list prices in the selected currency; discount, FX, duty, freight and markup are applied in the BOQ.</span>
        </div>
        <div className="th" style={{ gridTemplateColumns: COLS, gap: 10, padding: '0 14px' }}>
          <div>Item</div><div>Manufacturer</div><div>Part No.</div><div>Source</div><div>Date checked</div><div>Confidence</div><div>Curr.</div><div className="num">List price</div>
        </div>
        {!data && <Loading />}
        {data && data.rows.map((x) => {
          const cs = CONF_STYLE[x.category === 'Labour' && x.list ? 'L' : x.list ? x.conf : ''] || CONF_STYLE.O
          return (
            <div key={x.key} style={{ display: 'grid', gridTemplateColumns: COLS, gap: 10, padding: '0 14px', minHeight: 42, alignItems: 'center', borderBottom: '1px solid var(--border-3)', fontSize: 12, background: x.conf === 'B' ? 'var(--bud-row)' : '#fff' }}>
              <div style={{ minWidth: 0 }}>
                <div className="ellipsis" style={{ fontWeight: 500 }} title={x.desc}>{x.desc}</div>
                <div className="muted" style={{ fontSize: 11 }}>{x.category} · {x.systemName}{x.used ? <> · <b style={{ color: 'var(--navy)', fontWeight: 600 }}>{x.used} {x.unit} in this quotation</b></> : ` · per ${x.unit}`}</div>
              </div>
              <EditCell value={x.mfr} numeric={false} align="left" onCommit={(v) => update(x, { manufacturer: v })} />
              <EditCell value={x.part} numeric={false} align="left" className="mono" onCommit={(v) => update(x, { part_no: v })} />
              <EditCell value={x.source} numeric={false} align="left" placeholder="quote / price list ref" onCommit={(v) => update(x, { source: v })} />
              <div style={{ color: x.stale ? 'var(--amber-ink)' : 'var(--text)' }} title={x.stale ? 'Checked more than 90 days ago' : ''}>{x.dateF || <span className="muted2">—</span>}</div>
              <div>
                {x.category === 'Labour' ? <span className="badge t-lab">Labour rate</span> : (
                  <select className="cell" value={x.conf} onChange={(e) => update(x, { confidence: e.target.value })}
                    style={{ background: cs[0], color: cs[1], fontWeight: 600, fontSize: 10.5, borderRadius: 3, width: 'auto', padding: '2px 4px' }}>
                    {CONF.map(([v, l]) => <option key={v} value={v}>{v === '' ? (x.list ? '—' : 'No price') : l}</option>)}
                  </select>
                )}
              </div>
              <CurrencySelect value={x.cur} onChange={(v) => update(x, { currency: v })} />
              <EditCell value={x.list} placeholder="enter price" className={x.list ? '' : 'need'}
                onCommit={(v) => { setData((d) => d ? { ...d, rows: d.rows.map((r) => r.key === x.key ? { ...r, list: v } : r) } : d); update(x, { list_price: v }) }} />
            </div>
          )
        })}
        {data && data.rows.length === 0 && <div className="muted" style={{ padding: 32, textAlign: 'center' }}>No items match these filters.</div>}
      </div>
      {adding && <AddItem onClose={() => setAdding(false)} onDone={() => { setAdding(false); reload(); actions.refreshInfo() }} />}
    </>
  )
}

function AddItem({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const categories = useStore((s) => s.info?.categories || [])
  const [f, setF] = useState({ description: '', manufacturer: '', part_no: '', unit: 'ea', category: 'Device', system: 'optional', list_price: '', currency: 'USD' })
  const save = async () => {
    try { await call('add_price_item', f); toast('Item added', 'ok'); onDone() } catch (e) { toast((e as Error).message, 'err') }
  }
  return (
    <Modal title="Add item to price library" onClose={onClose} width={560}
      footer={<><button className="btn plain" onClick={onClose}>Cancel</button><button className="btn primary" disabled={!f.description.trim()} onClick={save}>Add item</button></>}>
      <Field label="Description"><input className="input lg" autoFocus value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <Field label="Manufacturer"><input className="input lg" value={f.manufacturer} onChange={(e) => setF({ ...f, manufacturer: e.target.value })} /></Field>
        <Field label="Part No."><input className="input lg mono" value={f.part_no} onChange={(e) => setF({ ...f, part_no: e.target.value })} /></Field>
        <Field label="Category"><select className="input lg" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>{categories.map((c) => <option key={c}>{c}</option>)}</select></Field>
        <Field label="System"><select className="input lg" value={f.system} onChange={(e) => setF({ ...f, system: e.target.value })}>{SYSTEMS.slice(1).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
        <Field label="Unit"><input className="input lg" value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} /></Field>
        <Field label="List price"><div className="row gap6"><input className="input lg r" style={{ flex: 1 }} value={f.list_price} onChange={(e) => setF({ ...f, list_price: e.target.value })} /><CurrencySelect className="input lg" value={f.currency} onChange={(v) => setF({ ...f, currency: v })} /></div></Field>
      </div>
    </Modal>
  )
}
