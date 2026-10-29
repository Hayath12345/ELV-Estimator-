import { useEffect, useMemo, useRef, useState } from 'react'
import { call, mode, pickFiles, uploadFile } from '../api/bridge'
import type { DrawingsView, Pt } from '../api/types'
import { Card, EditCell, ErrorBox, Loading, Progress, ToneBadge } from '../components/ui'
import { useViewBox } from '../components/viewbox'
import { actions, toast, useData, useStore } from '../state/store'

const TONE_ROW: Record<string, string> = { bud: 'var(--warn-row)' }

export default function Drawings() {
  const { data, error, reload } = useData<DrawingsView>('get_drawings')
  const jobs = useStore((s) => s.jobs)
  const [calib, setCalib] = useState<string | null>(null)
  const [over, setOver] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const roomsOpen = useState(false)

  const running = Object.values(jobs).filter((j) => j.kind === 'extract' && !j.done)
  useEffect(() => {
    if (!running.length) return
    const t = setInterval(reload, 1500)
    return () => clearInterval(t)
  }, [running.length]) // eslint-disable-line react-hooks/exhaustive-deps

  const importPaths = async (paths: string[]) => {
    if (!paths.length) return
    await actions.mutate('import_drawings', { paths })
  }
  const browse = async () => {
    try {
      const p = await pickFiles('drawings')
      if (p === null) input.current?.click()
      else await importPaths(p)
    } catch (e) { toast((e as Error).message, 'err') }
  }
  const onFiles = async (files: FileList | File[]) => {
    const list = Array.from(files).filter((f) => /\.(dwg|dxf|pdf)$/i.test(f.name))
    if (!list.length) { toast('Only DWG, DXF and PDF files can be imported.', 'err'); return }
    const big = list.find((f) => f.size > 200 * 1024 * 1024)
    if (big) { toast(`${big.name} is larger than 200 MB.`, 'err'); return }
    const paths: string[] = []
    for (const f of list) paths.push(await uploadFile(f))
    await importPaths(paths)
  }
  const onDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    setOver(false)
    const files = Array.from(e.dataTransfer.files)
    if ((await mode()) === 'pywebview') {
      // the desktop shell resolves full paths and imports; fall back to uploading if it could not
      const before = Date.now()
      ;(window as any).__elvDropAt = 0 // eslint-disable-line @typescript-eslint/no-explicit-any
      setTimeout(() => { if (((window as any).__elvDropAt || 0) < before) onFiles(files) }, 1500) // eslint-disable-line @typescript-eslint/no-explicit-any
      return
    }
    onFiles(files)
  }

  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return <Loading />
  const pct = running.length ? running.reduce((a, j) => a + j.pct, 0) / running.length : 0
  const msg = running[0]?.message || 'Extracting rooms and doors…'
  const floors = data.floors
  const cols = `minmax(0,1.2fr) ${floors.map(() => '78px').join(' ')} 120px minmax(0,1.6fr)`
  return (
    <>
      <div className="row gap10">
        <h2 className="h2">Step 1 · Drawings &amp; extraction</h2>
        {!data.libredwg && <span className="badge t-bud" style={{ marginLeft: 8 }} title="vendor/libredwg not found">DWG reader not installed — DXF/PDF only</span>}
      </div>
      <div className="split" style={{ gridTemplateColumns: '400px minmax(0,1fr)' }}>
        <Card title="Upload floor plans">
          <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div className={`dropzone${over ? ' over' : ''}`} onDragOver={(e) => { e.preventDefault(); setOver(true) }}
              onDragLeave={() => setOver(false)} onDrop={onDrop}>
              <div style={{ fontWeight: 600, color: 'var(--navy-ink)' }}>Drop DWG or PDF files here</div>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>AutoCAD 2000–2024 DWG, DXF, vector PDF · max 200 MB per file</div>
              <button className="btn sm outline" style={{ marginTop: 12 }} onClick={browse}>Browse files</button>
              <input ref={input} type="file" multiple accept=".dwg,.dxf,.pdf" style={{ display: 'none' }}
                onChange={(e) => { if (e.target.files) onFiles(e.target.files); e.target.value = '' }} />
            </div>
            {data.files.length > 0 && (
              <div style={{ border: '1px solid var(--border-2)', borderRadius: 4 }}>
                {data.files.map((f, i) => (
                  <div key={f.id} className="row gap10" style={{ padding: '8px 10px', borderBottom: i < data.files.length - 1 ? '1px solid var(--border-2)' : 0 }}>
                    <span className="tag" style={{ background: f.kind === 'pdf' ? 'var(--oth-bg)' : 'var(--navy)', color: f.kind === 'pdf' ? 'var(--text-2)' : '#fff' }}>{f.ext}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div className="mono ellipsis" style={{ fontSize: 12 }} title={f.name}>{f.name}</div>
                      <div className="row gap6 muted" style={{ fontSize: 11 }}>
                        <span>Floor</span>
                        <EditCell value={f.floor} numeric={false} align="left" width={52} title="Floor name (e.g. 2F, GF, B1)"
                          onCommit={(v) => actions.mutate('update_drawing', { id: f.id, floor: v })} />
                        <span className="ellipsis">{f.meta.split(' · ').slice(1).join(' · ')}</span>
                      </div>
                    </div>
                    <span style={{ fontSize: 11, fontWeight: 600, color: f.stFg, whiteSpace: 'nowrap' }}>{f.status}</span>
                    <div className="row" style={{ gap: 2 }}>
                      <button className="btn xs plain" title="Move up" disabled={i === 0} onClick={() => actions.mutate('update_drawing', { id: f.id, move: -1 })}>↑</button>
                      <button className="btn xs plain" title="Move down" disabled={i === data.files.length - 1} onClick={() => actions.mutate('update_drawing', { id: f.id, move: 1 })}>↓</button>
                      <button className="btn xs danger" title="Remove drawing" onClick={() => { if (confirm(`Remove ${f.name} from this quotation?`)) actions.mutate('remove_drawing', { id: f.id }) }}>✕</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="hint">Upload one plan per floor. Floors are ordered top to bottom as listed (used for riser routing). Each page of a multi-page PDF becomes a floor.</div>
          </div>
        </Card>

        <Card title="Extraction results" right={data.caption} style={{ minHeight: 360, display: 'flex', flexDirection: 'column' }}>
          {data.state === 'empty' && (
            <div className="empty">
              <div className="box" />
              <div className="t">No drawings uploaded</div>
              <div style={{ marginTop: 6, maxWidth: 380, lineHeight: 1.5 }}>Upload the architectural floor plans to extract rooms, door tags, work positions and comms rooms. Each floor can be a separate DWG layout or PDF page.</div>
            </div>
          )}
          {data.state === 'loading' && (
            <div style={{ padding: '20px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div className="row" style={{ justifyContent: 'space-between', fontSize: 12.5 }}>
                <span style={{ fontWeight: 600 }}>Extracting rooms and doors…</span><span className="muted">{msg} · {Math.round(pct * 100)}%</span>
              </div>
              <Progress pct={pct} />
              <div className="col gap8" style={{ marginTop: 6 }}>
                <div className="skel" /><div className="skel" style={{ width: '86%' }} /><div className="skel" style={{ width: '92%' }} /><div className="skel" style={{ width: '70%' }} />
              </div>
            </div>
          )}
          {data.errors.map((er) => (
            <div key={er.id} className="alert err" style={{ margin: '16px 16px 0' }}>
              <div className="ic">!</div>
              <div style={{ flex: 1 }}><div style={{ fontWeight: 600 }}>{er.name} could not be read</div><div style={{ fontSize: 12, marginTop: 3, lineHeight: 1.5 }}>{er.message}</div></div>
              <button className="btn sm danger" onClick={() => actions.mutate('retry_drawing', { id: er.id })}>Retry</button>
            </div>
          ))}
          {data.state === 'warn' && (
            <div className="alert warn" style={{ margin: '16px 16px 0' }}>
              <div className="ic">!</div>
              <div style={{ flex: 1 }}><div style={{ fontWeight: 600 }}>Scale not found – calibrate manually</div>
                <div style={{ fontSize: 12, marginTop: 2 }}>{data.files.filter((f) => !f.scale.unit_m || f.scale.conf === 'Not found').map((f) => f.name).join(', ') || 'One or more drawings'} — lengths and cable routes are approximate until calibrated.</div></div>
              <button className="btn sm primary" onClick={() => setCalib(data.files.find((f) => !f.scale.unit_m || f.scale.conf === 'Not found')?.id || data.files[0].id)}>Calibrate scale</button>
            </div>
          )}
          {(data.state === 'results' || data.state === 'warn' || (data.state === 'error' && data.rows.length > 0)) && data.rows.length > 0 && (
            <div style={{ padding: 16 }}>
              <div className="th" style={{ gridTemplateColumns: cols, gap: 10, padding: '0 10px', minHeight: 30 }}>
                <div>Extracted item</div>{floors.map((f) => <div key={f} className="num">{f}</div>)}<div>Confidence</div><div>Source</div>
              </div>
              {data.rows.map((r) => (
                <div key={r.item} className="tr sm" style={{ gridTemplateColumns: cols, gap: 10, padding: '0 10px', background: TONE_ROW[r.tone] }}>
                  <div style={{ fontWeight: 500 }}>{r.item}</div>
                  {r.vals.map((v, i) => <div key={i} className="num">{v}</div>)}
                  <div><ToneBadge tone={r.tone}>{r.conf}</ToneBadge></div>
                  <div className="muted ellipsis" style={{ fontSize: 12 }} title={r.note}>{r.note}</div>
                </div>
              ))}
              {data.files.flatMap((f) => f.warnings.map((w) => <div key={f.id + w} className="hint" style={{ marginTop: 6 }}>⚠ {f.floor}: {w}</div>))}
              <div className="row gap8" style={{ marginTop: 14 }}>
                <button className="btn sm outline" onClick={() => setCalib(data.files.find((f) => f.status !== 'Failed')?.id || null)}>Calibrate scale</button>
                <button className="btn sm plain" onClick={() => actions.go('layout')}>Review on plan</button>
                <button className="btn sm plain" onClick={() => roomsOpen[1](!roomsOpen[0])}>{roomsOpen[0] ? 'Hide rooms' : `Review rooms (${data.rooms.length})`}</button>
                <button className="btn sm primary ml-auto" onClick={() => actions.go('systems')}>Continue to Systems →</button>
              </div>
            </div>
          )}
          {calib && <Calibration id={calib} files={data.files} onClose={() => setCalib(null)} onSwitch={setCalib} />}
        </Card>
      </div>
      {roomsOpen[0] && <RoomsReview data={data} />}
    </>
  )
}

function Calibration({ id, files, onClose, onSwitch }: { id: string; files: DrawingsView['files']; onClose: () => void; onSwitch: (id: string) => void }) {
  const [view, setView] = useState<{ extents: number[]; grids: { a: Pt; b: Pt; axis: string; label: string }[]; unit_m: number | null; note: string } | null>(null)
  const [bg, setBg] = useState<string | null>(null)
  const [pts, setPts] = useState<{ x: number; y: number; grid?: string }[]>([])
  const [dist, setDist] = useState('')
  useEffect(() => {
    setPts([]); setDist(''); setView(null); setBg(null)
    call('get_calibration_view', { id }).then(setView).catch((e) => toast(e.message, 'err'))
    call<{ url: string | null }>('get_background', { id }).then((r) => setBg(r.url)).catch(() => undefined)
  }, [id])
  const ext = view?.extents || [0, 0, 1, 1]
  const W = ext[2] - ext[0], H = ext[3] - ext[1]
  const { vb, svgRef, k, toUser } = useViewBox(W || 1, H || 1)
  const toPlan = (x: number, y: number): Pt => [x - ext[0], ext[3] - y]
  const grids = view?.grids || []
  const pick = (e: React.MouseEvent) => {
    const p = toUser(e.clientX, e.clientY)
    let x = p.x + ext[0], y = ext[3] - p.y, grid: string | undefined
    for (const g of grids) {
      const [gx, gy] = g.a
      if (g.axis === 'x' && Math.abs(x - gx) < 10 * k) { x = gx; grid = g.label || 'grid' }
      if (g.axis === 'y' && Math.abs(y - gy) < 10 * k) { y = gy; grid = g.label || 'grid' }
    }
    setPts((ps) => (ps.length >= 2 ? [{ x, y, grid }] : [...ps, { x, y, grid }]))
  }
  const du = pts.length === 2 ? Math.hypot(pts[1].x - pts[0].x, pts[1].y - pts[0].y) : 0
  const dm = parseFloat(dist)
  const unitM = du > 0 && dm > 0 ? dm / du : null
  const sameAxisGrid = pts.length === 2 && pts[0].grid && pts[1].grid
  const ref = sameAxisGrid ? `Grid ${pts[0].grid} → ${pts[1].grid}` : pts.length === 2 ? 'Two points' : '—'
  const apply = async (all: boolean) => {
    if (!unitM) return
    await actions.mutate('calibrate', { id, p1: [pts[0].x, pts[0].y], p2: [pts[1].x, pts[1].y], distance_m: dist, apply_all: all, label: ref, measured_units: du }, 'Scale applied')
    onClose()
  }
  return (
    <div style={{ margin: '0 16px 16px', border: '1px solid var(--navy)', borderRadius: 4, display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 260px' }}>
      <div style={{ height: 300, background: 'repeating-linear-gradient(135deg,#F3F5F9 0 8px,#EBEFF5 8px 16px)', borderRight: '1px solid var(--border)', position: 'relative' }}>
        <svg ref={svgRef} viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`} style={{ width: '100%', height: '100%', display: 'block', cursor: 'crosshair' }} onClick={pick}>
          <rect x={0} y={0} width={W} height={H} fill="#fff" />
          {bg && <image href={bg} x={0} y={0} width={W} height={H} preserveAspectRatio="none" opacity={0.9} />}
          {grids.map((g, i) => {
            const a = toPlan(g.a[0], g.a[1]), b = toPlan(g.b[0], g.b[1])
            return <g key={i}><line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="#E07A1F" strokeOpacity={0.55} strokeWidth={1.2 * k} strokeDasharray={`${6 * k} ${5 * k}`} />
              {g.label && <text x={a[0]} y={a[1] - 6 * k} fontSize={11 * k} fill="#E07A1F" textAnchor="middle">{g.label}</text>}</g>
          })}
          {pts.map((p, i) => { const q = toPlan(p.x, p.y); return <circle key={i} cx={q[0]} cy={q[1]} r={5 * k} fill="#E07A1F" stroke="#fff" strokeWidth={1.5 * k} /> })}
          {pts.length === 2 && (() => { const a = toPlan(pts[0].x, pts[0].y), b = toPlan(pts[1].x, pts[1].y); return <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke="#E07A1F" strokeWidth={2 * k} /> })()}
        </svg>
        <div style={{ position: 'absolute', left: 8, top: 8, font: "11.5px var(--mono)", color: 'var(--muted)', background: 'rgba(255,255,255,.9)', padding: '3px 6px', borderRadius: 3 }}>
          Click two points (snaps to grid lines) · scroll to zoom
        </div>
      </div>
      <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8, fontSize: 12 }}>
        <div className="row"><b style={{ color: 'var(--navy-ink)' }}>Two-point calibration</b><button className="x" onClick={onClose}>×</button></div>
        <select className="input" value={id} onChange={(e) => onSwitch(e.target.value)}>
          {files.filter((f) => f.status !== 'Failed').map((f) => <option key={f.id} value={f.id}>{f.floor} · {f.name}</option>)}
        </select>
        <div className="row" style={{ justifyContent: 'space-between' }}><span className="muted">Reference</span><span>{ref}</span></div>
        <div className="row" style={{ justifyContent: 'space-between' }}><span className="muted">Known distance</span>
          <span className="row gap6"><input className="input r" style={{ width: 80 }} value={dist} onChange={(e) => setDist(e.target.value)} placeholder="12.60" />m</span></div>
        <div className="row" style={{ justifyContent: 'space-between' }}><span className="muted">Measured</span><span>{du ? `${du.toLocaleString('en-US', { maximumFractionDigits: 2 })} drawing units` : '—'}</span></div>
        <div className="row" style={{ justifyContent: 'space-between' }}><span className="muted">Current</span><span>{view?.unit_m ? `${(1 / view.unit_m).toLocaleString('en-US', { maximumFractionDigits: 3 })} units/m` : 'not set'}</span></div>
        <div className="row" style={{ justifyContent: 'space-between' }}><span className="muted">Resulting</span><span style={{ fontWeight: 600 }}>{unitM ? `${(1 / unitM).toLocaleString('en-US', { maximumFractionDigits: 3 })} units/m` : '—'}</span></div>
        <button className="btn sm primary" disabled={!unitM} onClick={() => apply(false)}>Apply to this drawing</button>
        <button className="btn sm outline" disabled={!unitM} onClick={() => apply(true)}>Apply to all floors</button>
        {view?.note && <div className="hint">{view.note}</div>}
      </div>
    </div>
  )
}

function RoomsReview({ data }: { data: DrawingsView }) {
  const cats = useStore((s) => s.info?.roomCategories || [])
  const [q, setQ] = useState('')
  const rows = useMemo(() => data.rooms.filter((r) => !q || (r.name + r.floor + r.categoryLabel).toLowerCase().includes(q.toLowerCase())), [data.rooms, q])
  const COLS = '60px minmax(0,1.6fr) 190px 90px 110px 100px 60px'
  return (
    <Card title={`Rooms · ${data.rooms.length}`} right={<input className="input" placeholder="Filter rooms…" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 200 }} />}>
      <div className="th" style={{ gridTemplateColumns: COLS, gap: 10 }}><div>Floor</div><div>Room</div><div>Category (drives placement)</div><div className="num">Area m²</div><div>Comms role</div><div>Boundary</div><div className="num">WPs</div></div>
      <div style={{ maxHeight: 460, overflowY: 'auto' }}>
        {rows.map((r) => (
          <div key={r.drawing + r.id} className="tr sm" style={{ gridTemplateColumns: COLS, gap: 10 }}>
            <div>{r.floor}</div>
            <div className="ellipsis" title={r.name}>{r.name}</div>
            <select className="cell" value={r.category} onChange={(e) => actions.mutate('update_room', { drawing: r.drawing, id: r.id, category: e.target.value })}>
              {cats.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
            <div className="num">{r.area}</div>
            <select className="cell" value={r.comms} onChange={(e) => actions.mutate('update_room', { drawing: r.drawing, id: r.id, comms: e.target.value || 'none' })}>
              <option value="">—</option><option value="IDF">IDF</option><option value="MDF">MDF</option>
            </select>
            <div><span className={`badge ${r.boundary === 'estimated' ? 't-bud' : 't-oth'}`}>{r.boundary}</span></div>
            <div className="num">{r.wps || ''}</div>
          </div>
        ))}
      </div>
    </Card>
  )
}
