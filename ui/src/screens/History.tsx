import { useState } from 'react'
import type { HistoryView } from '../api/types'
import { Empty, ErrorBox, Loading, StatusPill } from '../components/ui'
import { useData, useStore } from '../state/store'

export default function History() {
  const project = useStore((s) => s.project)
  const [rev, setRev] = useState<number | null>(null)
  const { data, error, reload } = useData<HistoryView>(project ? 'get_history' : null, rev != null ? { rev } : {})
  if (!project) return <div className="card" style={{ minHeight: 300, display: 'flex' }}><Empty title="No quotation open">Open a quotation to see its revision history.</Empty></div>
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return <Loading />
  return (
    <>
      <div className="row gap12"><h1 className="h1">Revision history</h1><span className="muted" style={{ fontSize: 12 }}>{project.info.name} · {project.info.ref}</span></div>
      {data.revisions.length === 0 ? (
        <div className="card" style={{ minHeight: 260, display: 'flex' }}><Empty title={`Rev ${data.current.rev} · not issued yet`}>Revisions are recorded when you generate outputs with “Bump revision on export” ticked (Checks &amp; Export). Each revision keeps its totals, quantities, prices and change log. Current total QAR {data.current.totalF}.</Empty></div>
      ) : (
        <div className="split" style={{ gridTemplateColumns: '300px minmax(0,1fr)' }}>
          <div className="card">
            {data.revisions.map((r) => {
              const a = r.rev === data.selected
              return (
                <div key={r.rev} onClick={() => setRev(r.rev)} style={{ padding: '12px 14px', borderBottom: '1px solid var(--border-3)', cursor: 'pointer', boxShadow: a ? 'inset 3px 0 0 var(--navy)' : undefined, background: a ? 'var(--row-hover)' : undefined }}>
                  <div className="row" style={{ justifyContent: 'space-between' }}><b className="mono">{r.label}</b><StatusPill status={r.status} /></div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>{r.at} · {r.by}</div>
                  {r.note && <div style={{ fontSize: 12, marginTop: 4, color: 'var(--text-2)' }}>{r.note}</div>}
                  <div style={{ fontWeight: 600, marginTop: 4 }}>{r.totalF}</div>
                </div>
              )
            })}
          </div>
          <div className="card">
            <div className="card-h">{data.compare?.from ? `Changes ${data.compare.from} → ${data.compare.to}` : `${data.compare?.to} · first issue`}</div>
            <div style={{ display: 'grid', gridTemplateColumns: '160px minmax(0,1fr) 140px', gap: 10, padding: '0 14px', height: 30, alignItems: 'center', fontSize: 11.5, fontWeight: 600, borderBottom: '1px solid var(--border-2)' }} className="muted"><div>Area</div><div>Change</div><div className="num">Delta (QAR)</div></div>
            {data.changes.map((c, i) => (
              <div key={i} style={{ display: 'grid', gridTemplateColumns: '160px minmax(0,1fr) 140px', gap: 10, padding: '0 14px', minHeight: 40, alignItems: 'center', borderBottom: '1px solid var(--border-3)', fontSize: 12.5 }}>
                <div style={{ fontWeight: 500 }}>{c.area}</div><div>{c.what}</div><div className="num" style={{ fontWeight: 600, color: c.pos ? 'var(--err-2)' : 'var(--ok)' }}>{c.deltaF}</div>
              </div>
            ))}
            {data.changes.length === 0 && <div className="muted" style={{ padding: 16 }}>{data.compare?.from ? 'No differences in totals.' : 'This is the first issued revision.'}</div>}
            {data.compare && (
              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 160px 160px 160px', gap: 10, padding: '12px 14px', background: 'var(--sec-bg)', borderTop: '2px solid var(--navy)', fontSize: 12.5 }}>
                <div style={{ fontWeight: 600 }}>Base total</div>
                <div className="num">{data.compare.from && <><div className="muted" style={{ fontSize: 11 }}>{data.compare.from}</div>{data.compare.fromF}</>}</div>
                <div className="num"><div className="muted" style={{ fontSize: 11 }}>{data.compare.to}</div><b>{data.compare.toF}</b></div>
                <div className="num">{data.compare.deltaF && <><div className="muted" style={{ fontSize: 11 }}>Delta</div><b style={{ color: data.compare.up ? 'var(--err-2)' : 'var(--ok)' }}>{data.compare.deltaF}</b></>}</div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}
