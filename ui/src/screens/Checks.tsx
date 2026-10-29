import { useEffect, useState } from 'react'
import type { ChecksView } from '../api/types'
import { ErrorBox, Loading, Modal, Progress } from '../components/ui'
import { actions, useData, useStore } from '../state/store'

const COLS = '62px minmax(0,1.6fr) 130px 30px 140px'

export default function Checks() {
  const { data, error, reload } = useData<ChecksView>('get_checks')
  const jobs = useStore((s) => s.jobs)
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [showAll, setShowAll] = useState<Record<string, boolean>>({})
  const [log, setLog] = useState('')
  const [ovr, setOvr] = useState(false)
  const [reason, setReason] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  useEffect(() => { if (data) setLog(data.changeLog) }, [data?.changeLog]) // eslint-disable-line react-hooks/exhaustive-deps
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return <Loading />
  const job = jobId ? jobs[jobId] : undefined
  const allOk = data.passed === data.total
  const failing = data.total - data.passed
  const selCount = data.exports.filter((x) => x.on).length
  const isOpen = (g: ChecksView['groups'][number]) => open[g.id] ?? g.passed < g.n
  const generate = async () => {
    if (!data.canIssue) { setOvr(true); return }
    await actions.mutate('set_export_options', { change_log: log })
    const r = await actions.mutate<{ job: { id: string } }>('generate', { bump: data.bump, change_log: log })
    if (r?.job) setJobId(r.job.id)
  }
  const approved = data.approval.find((a) => a.step === 'approved')?.done
  return (
    <div className="split" style={{ gridTemplateColumns: 'minmax(0,1fr) 400px' }}>
      <div className="col gap12">
        <div className="card row gap16" style={{ padding: '12px 16px' }}>
          <div style={{ width: 40, height: 40, borderRadius: '50%', background: allOk ? 'var(--ok)' : data.blocking ? 'var(--err)' : 'var(--warn)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, fontWeight: 700 }}>{allOk ? '✓' : '!'}</div>
          <div>
            <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--navy-ink)' }}>{data.passed} / {data.total} checks passed</div>
            <div className="muted" style={{ fontSize: 12 }}>Last run {data.lastRun} · against layout, comms rooms and BOQ Rev {data.rev}{failing ? ` · ${data.blocking} blocking, ${failing - data.blocking} warning${failing - data.blocking === 1 ? '' : 's'}` : ''}</div>
          </div>
          <button className="btn sm outline ml-auto" onClick={() => { reload(); actions.refreshProject() }}>Re-run checks</button>
        </div>
        {data.override && data.blocking > 0 && (
          <div className="alert warn"><div className="ic">!</div>
            <div style={{ flex: 1, fontSize: 12 }}><b>Issue override recorded</b> by {data.override.by || 'user'} — “{data.override.reason}”</div>
            <button className="btn sm plain" onClick={() => actions.mutate('set_override', { reason: '' })}>Remove</button>
          </div>
        )}
        <div className="card">
          <div className="th" style={{ gridTemplateColumns: COLS, gap: 10, padding: '0 14px' }}><div>Result</div><div>Check</div><div className="num">Value</div><div style={{ textAlign: 'center' }}>Rule</div><div>Limit / expected</div></div>
          {data.groups.map((g) => {
            const o = isOpen(g)
            const ok = g.passed === g.n
            const rows = showAll[g.id] ? g.rows : [...g.rows.filter((r) => !r.pass), ...g.rows.filter((r) => r.pass)].slice(0, Math.max(5, g.rows.filter((r) => !r.pass).length))
            const more = g.rows.length - rows.length
            return (
              <div key={g.id}>
                <div onClick={() => setOpen({ ...open, [g.id]: !o })} className="row gap10" style={{ padding: '0 14px', height: 36, background: 'var(--sec-bg)', borderBottom: '1px solid var(--border-sec)', cursor: 'pointer' }}>
                  <span style={{ width: 12, fontSize: 10, color: 'var(--navy)' }}>{o ? '▼' : '▶'}</span><span style={{ fontWeight: 600, color: 'var(--navy-ink)' }}>{g.g}</span>
                  <span className="ml-auto" style={{ fontSize: 11.5, fontWeight: 600, padding: '2px 8px', borderRadius: 3, color: ok ? 'var(--ok-ink)' : 'var(--err-2)', background: ok ? 'var(--ok-bg)' : 'var(--err-bg)' }}>{g.passed} / {g.n} passed</span>
                </div>
                {o && rows.map((r, i) => (
                  <div key={i} style={{ display: 'grid', gridTemplateColumns: COLS, gap: 10, padding: '0 14px', minHeight: 32, alignItems: 'center', borderBottom: '1px solid var(--border-3)', fontSize: 12, background: r.pass ? '#fff' : r.sev === 'warn' ? 'var(--warn-row)' : '#FFF8F7' }}>
                    <div><span style={{ fontSize: 10.5, fontWeight: 700, padding: '2px 6px', borderRadius: 2, color: r.pass ? 'var(--ok-ink)' : r.sev === 'warn' ? 'var(--bud-ink)' : 'var(--err-2)', background: r.pass ? 'var(--ok-bg)' : r.sev === 'warn' ? 'var(--bud-bg)' : 'var(--err-bg)' }}>{r.pass ? 'PASS' : r.sev === 'warn' ? 'WARN' : 'FAIL'}</span></div>
                    <div>{r.name}</div><div className="num" style={{ fontWeight: 500 }}>{r.a}</div><div className="muted" style={{ textAlign: 'center' }}>{r.op}</div><div style={{ color: 'var(--text-2)' }}>{r.b}</div>
                  </div>
                ))}
                {o && more > 0 && <div className="muted" style={{ padding: '6px 14px 6px 86px', fontSize: 11.5, borderBottom: '1px solid var(--border-3)', cursor: 'pointer' }} onClick={() => setShowAll({ ...showAll, [g.id]: true })}>+ {more} more checks passed — show</div>}
              </div>
            )
          })}
        </div>
      </div>
      <div className="col gap12">
        <div className="card">
          <div className="card-h">Export outputs</div>
          {data.exports.map((x) => (
            <div key={x.id} className="row gap10" style={{ padding: '9px 14px', borderBottom: '1px solid var(--border-3)', cursor: 'pointer' }}
              onClick={() => actions.mutate('set_export_options', { selected: { [x.id]: !x.on } })}>
              <span className={`cbx${x.on ? ' on' : ''}`}>{x.on ? '✓' : ''}</span>
              <div style={{ flex: 1 }}><div style={{ fontWeight: 500, fontSize: 12.5 }}>{x.name}</div><div className="muted" style={{ fontSize: 11 }}>{x.fmt}</div></div>
            </div>
          ))}
          <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div className="row gap10" style={{ cursor: 'pointer' }} onClick={() => actions.mutate('set_export_options', { bump: !data.bump })}>
              <span className={`cbx${data.bump ? ' on' : ''}`}>{data.bump ? '✓' : ''}</span>
              <span style={{ fontSize: 12.5 }}>Bump revision on export</span>
              <span className="ml-auto mono" style={{ fontWeight: 600, fontSize: 12, color: 'var(--navy-ink)' }}>{data.bump ? `Rev ${data.rev} → Rev ${data.rev + 1}` : `Rev ${data.rev}`}</span>
            </div>
            <textarea className="input" rows={3} placeholder={`Rev ${data.rev + 1}: change log (what changed and why)`} value={log}
              onChange={(e) => setLog(e.target.value)} onBlur={() => { if (log !== data.changeLog) actions.mutate('set_export_options', { change_log: log }) }} />
          </div>
        </div>
        <div className="card">
          <div className="card-h">Approval</div>
          {data.approval.map((a, i) => (
            <div key={a.step} className="row gap12" style={{ padding: '10px 14px', borderBottom: '1px solid var(--border-3)', cursor: a.step !== 'approved' ? 'pointer' : 'default' }}
              title={a.step !== 'approved' ? (a.done ? 'Click to withdraw' : 'Click to sign') : ''}
              onClick={() => { if (a.step !== 'approved') actions.mutate('sign', { step: a.step }) }}>
              <div style={{ width: 22, height: 22, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700,
                background: a.done ? 'var(--ok)' : '#fff', color: a.done ? '#fff' : 'var(--muted)', border: `1.5px solid ${a.done ? 'var(--ok)' : 'var(--input-border)'}` }}>{a.done ? '✓' : i + 1}</div>
              <div style={{ flex: 1 }}><div style={{ fontSize: 12.5, fontWeight: 600 }}>{a.label}</div><div className="muted" style={{ fontSize: 11.5 }}>{a.who}{a.role ? `, ${a.role}` : ''}</div></div>
              <span style={{ fontSize: 11.5, color: a.done ? 'var(--muted)' : 'var(--amber-ink)' }}>{a.done ? a.when : 'Awaiting'}</span>
            </div>
          ))}
          <div style={{ padding: '12px 14px', display: 'flex', gap: 8 }}>
            <button className="btn outline" style={{ flex: 1, fontWeight: 600 }} onClick={() => actions.mutate('sign', { step: 'approved' })}>{approved ? 'Withdraw approval' : 'Approve as manager'}</button>
            <button className="btn primary" style={{ flex: 1.3 }} disabled={!!job && !job.done} onClick={generate}>{data.last ? 'Regenerate package' : `Generate ${selCount} outputs`}</button>
          </div>
          {job && !job.done && <div style={{ margin: '0 14px 14px' }}><div className="muted" style={{ fontSize: 11.5, marginBottom: 6 }}>{job.message}</div><Progress pct={job.pct} /></div>}
          {!data.canIssue && <div className="hint" style={{ margin: '0 14px 12px', color: 'var(--err-ink)' }}>{data.blocking} blocking check{data.blocking === 1 ? '' : 's'} failing — fix them or record an override reason to issue.</div>}
          {data.last && (!job || job.done) && (
            <div style={{ margin: '0 14px 14px', padding: '8px 10px', background: 'var(--ok-bg)', color: 'var(--ok-ink)', borderRadius: 3, fontSize: 12 }}>
              Package generated: {data.last.zip ? data.last.zip.split(/[\\/]/).pop() : `Rev ${data.last.rev}`} · {data.last.files.length} files
              <div><button className="btn link" style={{ fontSize: 12, color: 'var(--ok-ink)', textDecoration: 'underline' }} onClick={() => actions.mutate('open_folder', { path: data.last!.folder })}>Open outputs folder</button></div>
            </div>
          )}
        </div>
      </div>
      {ovr && (
        <Modal title="Issue with failing checks?" onClose={() => setOvr(false)} width={520}
          footer={<><button className="btn plain" onClick={() => setOvr(false)}>Cancel</button>
            <button className="btn primary" disabled={reason.trim().length < 10} onClick={async () => { await actions.mutate('set_override', { reason }); setOvr(false) }}>Record override</button></>}>
          <div style={{ fontSize: 12.5, lineHeight: 1.5 }}>{data.blocking} blocking check{data.blocking === 1 ? ' is' : 's are'} failing. Issue is blocked unless you record why it is acceptable. The reason is saved in the project and on the internal costing workbook.</div>
          <textarea className="input" rows={4} autoFocus placeholder="Reason (min. 10 characters), e.g. 'Two 3F links at 92 m accepted by consultant — consolidation point to be added at shop drawing stage'" value={reason} onChange={(e) => setReason(e.target.value)} />
        </Modal>
      )}
    </div>
  )
}
