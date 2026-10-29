import { useEffect, useState } from 'react'
import { pickFolder } from '../api/bridge'
import type { FxRow } from '../api/types'
import { Card, EditCell, ErrorBox, Field, Loading } from '../components/ui'
import { actions, toast, useData, useStore } from '../state/store'

/* ------------------------------------------------------------------ Project details */
export function ProjectDetails() {
  const p = useStore((s) => s.project)!
  const statuses = useStore((s) => s.info?.status || [])
  const [info, setInfo] = useState<Record<string, string>>({})
  const [company, setCompany] = useState<Record<string, string>>({})
  const [signoff, setSignoff] = useState<Record<string, { name?: string; role?: string }>>({})
  useEffect(() => {
    setInfo(Object.fromEntries(Object.entries(p.info).map(([k, v]) => [k, String(v ?? '')])))
    setCompany({ ...p.company })
    setSignoff(JSON.parse(JSON.stringify(p.signoff || {})))
  }, [p.id]) // eslint-disable-line react-hooks/exhaustive-deps
  const save = () => actions.mutate('update_project_info', { info, company, signoff }, 'Project details saved')
  const fld = (k: string, label: string, mono = false) => (
    <Field label={label}><input className={`input lg${mono ? ' mono' : ''}`} value={info[k] || ''} onChange={(e) => setInfo({ ...info, [k]: e.target.value })} /></Field>
  )
  return (
    <>
      <div className="row gap12"><h2 className="h2">Project details</h2>
        <div className="ml-auto row gap8">
          <button className="btn" onClick={() => actions.mutate('duplicate_project', { id: p.id }, 'Duplicated — find the copy in Quotations')}>Duplicate quotation</button>
          <button className="btn primary" onClick={save}>Save details</button>
        </div>
      </div>
      <div className="split" style={{ gridTemplateColumns: 'minmax(0,1.4fr) minmax(0,1fr)' }}>
        <Card title="Quotation">
          <div style={{ padding: 14, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div style={{ gridColumn: '1 / span 2' }}>{fld('name', 'Project name')}</div>
            {fld('client', 'Client')}{fld('attention', 'Attention')}
            {fld('pmc', 'PMC')}{fld('consultant', 'Consultant')}
            {fld('scope', 'Scope / floors')}{fld('location', 'Location')}
            {fld('ref', 'Quotation reference', true)}{fld('drawing_refs', 'Drawing references', true)}
            {fld('date', 'Quotation date (YYYY-MM-DD)')}{fld('validity_days', 'Validity (days)')}
            <div style={{ gridColumn: '1 / span 2' }}>{fld('subject', 'Subject line (cover letter)')}</div>
            <Field label="Status">
              <select className="input lg" value={p.status} onChange={(e) => actions.mutate('set_status', { status: e.target.value })}>
                {statuses.map((s) => <option key={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Project folder"><div className="row gap8"><input className="input lg mono" readOnly value={p.folder} style={{ flex: 1, fontSize: 11 }} />
              <button className="btn sm" onClick={() => actions.mutate('open_folder', { path: p.folder })}>Open</button></div></Field>
          </div>
        </Card>
        <div className="col gap16">
          <Card title="Prepared / Checked / Approved">
            <div style={{ padding: 14, display: 'grid', gridTemplateColumns: '90px 1fr 1fr', gap: 8, alignItems: 'center' }}>
              {(['prepared', 'checked', 'approved'] as const).map((k) => (
                <div key={k} style={{ display: 'contents' }}>
                  <span className="muted" style={{ textTransform: 'capitalize' }}>{k}</span>
                  <input className="input lg" placeholder="Name" value={signoff[k]?.name || ''} onChange={(e) => setSignoff({ ...signoff, [k]: { ...signoff[k], name: e.target.value } })} />
                  <input className="input lg" placeholder="Role" value={signoff[k]?.role || ''} onChange={(e) => setSignoff({ ...signoff, [k]: { ...signoff[k], role: e.target.value } })} />
                </div>
              ))}
            </div>
          </Card>
          <Card title="Quoting company (overrides Settings for this quotation)">
            <div style={{ padding: 14, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              {[['name', 'Company name'], ['phone', 'Phone'], ['email', 'Email'], ['cr', 'CR / licence no.'], ['website', 'Website']].map(([k, l]) => (
                <Field key={k} label={l}><input className="input lg" value={company[k] || ''} placeholder="(Settings)" onChange={(e) => setCompany({ ...company, [k]: e.target.value })} /></Field>
              ))}
              <Field label="Address" style={{ gridColumn: '1 / span 2' }}><textarea className="input" rows={2} value={company.address || ''} placeholder="(Settings)" onChange={(e) => setCompany({ ...company, address: e.target.value })} /></Field>
            </div>
          </Card>
          <CommercialTerms />
        </div>
      </div>
    </>
  )
}

function CommercialTerms() {
  const p = useStore((s) => s.project)!
  const c = p.commercial || {}
  const keys: [string, string][] = [['payment_terms', 'Payment terms'], ['delivery', 'Delivery'], ['warranty', 'Warranty']]
  return (
    <Card title="Commercial terms (quotation terms & conditions)">
      <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div className="hint">Markup {c.markup}% · duty {c.duty}% · freight {c.freight}% — change these in BOQ &amp; Pricing.</div>
        {keys.map(([k, l]) => (
          <Field key={k} label={l}>
            <input key={p.id + k + (c[k] || '')} className="input lg" defaultValue={c[k] || ''}
              onBlur={(e) => { if (e.target.value !== (c[k] || '')) actions.mutate('set_commercial', { [k]: e.target.value }, 'Saved') }} />
          </Field>
        ))}
      </div>
    </Card>
  )
}

/* ------------------------------------------------------------------ Assumptions, exclusions, RFIs */
const LISTS: [string, string, string][] = [
  ['assumptions', 'Assumptions', 'Basis of the quotation.'],
  ['exclusions', 'Exclusions', 'Not included in the price.'],
  ['rfis', 'Requests for information (RFIs)', 'Questions to the client/consultant.'],
  ['terms', 'Terms & conditions', 'Placeholders {validity}, {payment}, {delivery}, {warranty} are filled from the commercial terms.'],
]

export function Texts() {
  const { data, error, reload } = useData<{ texts: Record<string, string[]> }>('get_texts')
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return <Loading />
  return (
    <>
      <div className="row"><h2 className="h2">Assumptions, exclusions &amp; RFIs</h2><span className="ml-auto hint">Printed in the quotation PDF and Excel. Edit per project.</span></div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {LISTS.map(([k, title, hint]) => <ListEditor key={k} kind={k} title={title} hint={hint} items={data.texts[k] || []} />)}
      </div>
    </>
  )
}

function ListEditor({ kind, title, hint, items }: { kind: string; title: string; hint: string; items: string[] }) {
  const [list, setList] = useState(items)
  useEffect(() => setList(items), [items])
  const save = (next: string[]) => { setList(next); actions.mutate('update_texts', { kind, items: next }) }
  return (
    <Card title={`${title} · ${list.length}`} right={<button className="btn link" style={{ fontSize: 11.5 }} onClick={() => { if (confirm(`Restore default ${title.toLowerCase()}?`)) actions.mutate('reset_texts', { kind }) }}>Restore defaults</button>}>
      <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div className="hint">{hint}</div>
        {list.map((t, i) => (
          <div key={i} className="row gap6" style={{ alignItems: 'flex-start' }}>
            <span className="muted mono" style={{ width: 20, paddingTop: 6, fontSize: 11 }}>{i + 1}.</span>
            <textarea className="input" rows={Math.max(1, Math.ceil(t.length / 70))} style={{ flex: 1 }} defaultValue={t}
              onBlur={(e) => { if (e.target.value !== t) { const n = [...list]; n[i] = e.target.value; save(n.filter((x) => x.trim())) } }} />
            <div className="col" style={{ gap: 2 }}>
              <button className="btn xs plain" disabled={i === 0} onClick={() => { const n = [...list];[n[i - 1], n[i]] = [n[i], n[i - 1]]; save(n) }}>↑</button>
              <button className="btn xs danger" onClick={() => save(list.filter((_, j) => j !== i))}>✕</button>
            </div>
          </div>
        ))}
        <button className="btn sm plain" style={{ alignSelf: 'flex-start' }} onClick={() => setList([...list, ''])}>+ Add line</button>
      </div>
    </Card>
  )
}

/* ------------------------------------------------------------------ Settings */
interface SettingsView { settings: { user: Record<string, string>; company: Record<string, string>; signoff: Record<string, Record<string, string>>; commercial: Record<string, string>; projects_dir: string; ref_prefix: string }; fx: FxRow[]; dataDir: string }

export function Settings() {
  const { data, error, reload } = useData<SettingsView>('get_settings')
  const info = useStore((s) => s.info)
  const [s, setS] = useState<SettingsView['settings'] | null>(null)
  const [fxq, setFxq] = useState('')
  useEffect(() => { if (data) setS(JSON.parse(JSON.stringify(data.settings))) }, [data])
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data || !s) return <Loading />
  const save = async () => { await actions.mutate('update_settings', s, 'Settings saved'); actions.refreshInfo() }
  const inp = (sec: 'user' | 'company' | 'commercial', k: string, label: string) => (
    <Field label={label}><input className="input lg" value={(s[sec] as Record<string, string>)[k] || ''} onChange={(e) => setS({ ...s, [sec]: { ...s[sec], [k]: e.target.value } })} /></Field>
  )
  const browse = async () => {
    const f = await pickFolder()
    if (f === undefined) { toast('Type the folder path (folder picker is available in the desktop app).'); return }
    if (f) setS({ ...s, projects_dir: f })
  }
  return (
    <>
      <div className="row"><h1 className="h1">Settings</h1><button className="btn primary ml-auto" onClick={save}>Save settings</button></div>
      <div className="split" style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)' }}>
        <div className="col gap16">
          <Card title="You">
            <div style={{ padding: 14, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>{inp('user', 'name', 'Your name')}{inp('user', 'role', 'Role')}</div>
          </Card>
          <Card title="Quoting company (cover letter and page headers)">
            <div style={{ padding: 14, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              {inp('company', 'name', 'Company name')}{inp('company', 'phone', 'Phone')}{inp('company', 'email', 'Email')}{inp('company', 'cr', 'CR / licence no.')}{inp('company', 'website', 'Website')}
              <Field label="Address" style={{ gridColumn: '1 / span 2' }}><textarea className="input" rows={2} value={s.company.address || ''} onChange={(e) => setS({ ...s, company: { ...s.company, address: e.target.value } })} /></Field>
            </div>
          </Card>
          <Card title="Default sign-off names (new quotations)">
            <div style={{ padding: 14, display: 'grid', gridTemplateColumns: '90px 1fr 1fr', gap: 8, alignItems: 'center' }}>
              {(['prepared', 'checked', 'approved'] as const).map((k) => (
                <div key={k} style={{ display: 'contents' }}>
                  <span className="muted" style={{ textTransform: 'capitalize' }}>{k}</span>
                  <input className="input lg" placeholder="Name" value={s.signoff[k]?.name || ''} onChange={(e) => setS({ ...s, signoff: { ...s.signoff, [k]: { ...s.signoff[k], name: e.target.value } } })} />
                  <input className="input lg" placeholder="Role" value={s.signoff[k]?.role || ''} onChange={(e) => setS({ ...s, signoff: { ...s.signoff, [k]: { ...s.signoff[k], role: e.target.value } } })} />
                </div>
              ))}
            </div>
          </Card>
          <Card title="Defaults for new quotations">
            <div style={{ padding: 14, display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
              {inp('commercial', 'markup', 'Markup %')}{inp('commercial', 'duty', 'Duty %')}{inp('commercial', 'freight', 'Freight %')}
              {inp('commercial', 'validity_days', 'Validity (days)')}{inp('commercial', 'pm_pct', 'PM hours (% of labour)')}
              <Field label="Reference prefix"><input className="input lg mono" value={s.ref_prefix || ''} onChange={(e) => setS({ ...s, ref_prefix: e.target.value })} /></Field>
              <div style={{ gridColumn: '1 / span 3' }}>{inp('commercial', 'payment_terms', 'Payment terms')}</div>
              <div style={{ gridColumn: '1 / span 3' }}>{inp('commercial', 'delivery', 'Delivery')}</div>
              <div style={{ gridColumn: '1 / span 3' }}>{inp('commercial', 'warranty', 'Warranty')}</div>
            </div>
          </Card>
          <Card title="Storage">
            <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <Field label="Projects folder"><div className="row gap8"><input className="input lg mono" style={{ flex: 1, fontSize: 11.5 }} value={s.projects_dir} onChange={(e) => setS({ ...s, projects_dir: e.target.value })} /><button className="btn sm" onClick={browse}>Browse…</button></div></Field>
              <div className="hint">Price library and settings: <span className="mono">{data.dataDir}</span> · LibreDWG DWG reader: {info?.libredwg ? 'installed' : 'not found (DXF/PDF only)'} · version {info?.version}</div>
            </div>
          </Card>
        </div>
        <Card title="Exchange rates to QAR (price library default)" right={<input className="input" placeholder="Filter…" style={{ width: 120 }} value={fxq} onChange={(e) => setFxq(e.target.value)} />}>
          <div className="hint" style={{ padding: '8px 14px' }}>Used to convert list prices to QAR. Indicative defaults — verify against your bank rate before issue. A quotation can override a rate in BOQ &amp; Pricing.</div>
          <div className="th" style={{ gridTemplateColumns: '64px minmax(0,1fr) 110px 100px', gap: 10, padding: '0 14px' }}><div>Code</div><div>Currency</div><div className="num">QAR per unit</div><div>As of</div></div>
          <div style={{ maxHeight: 640, overflowY: 'auto' }}>
            {data.fx.filter((f) => !fxq || (f.code + f.name).toLowerCase().includes(fxq.toLowerCase())).map((f) => (
              <div key={f.code} className="tr sm" style={{ gridTemplateColumns: '64px minmax(0,1fr) 110px 100px', gap: 10, padding: '0 14px' }}>
                <div className="mono" style={{ fontWeight: 600 }}>{f.code}</div><div>{f.name}</div>
                {f.code === 'QAR' ? <div className="num">1</div> : <EditCell value={f.rate} onCommit={async (v) => { await actions.mutate('set_fx', { code: f.code, rate: v }); reload(); actions.refreshInfo() }} />}
                <div className="muted" style={{ fontSize: 11.5 }}>{f.asOf || (f.code === 'QAR' ? '' : 'indicative')}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </>
  )
}
