import { useEffect, useMemo, useRef, useState } from 'react'
import type { Device, LayoutView, Pt } from '../api/types'
import { useViewBox } from './viewbox'

export const SYS_COLOR: Record<string, string> = {
  cctv: '#E07A1F', access: '#2F9E6B', iptv: '#8A5CD6', cabling: '#2A86C9', intercom: '#B8901A', intrusion: '#D0457A',
}
const CORE = new Set(['corridor', 'lift_lobby', 'lift', 'stair', 'toilet', 'plant', 'electrical'])
const T = { bg: '#FFFFFF', room: '#F5F7FA', open: '#FBFCFD', stroke: '#B9C2D0', wall: '#2B3345', text: '#7A8396', grid: '#D6DDE8', gridT: '#5E6A7D', core: '#E8ECF2', comms: '#1F3B70', route: '#1F3B70', sel: '#0F172A', red: '#D32F2F' }

interface Props {
  view: LayoutView
  bg: string | null
  layers: Record<string, boolean>
  tool: 'select' | 'add' | 'delete'
  showFov: boolean
  routes: 'selected' | 'all'
  selected: string | null
  onSelect: (id: string | null) => void
  onMove: (id: string, x: number, y: number) => void
  onAdd: (x: number, y: number) => void
  onDelete: (id: string) => void
}

export default function FloorPlan({ view, bg, layers, tool, showFov, routes, selected, onSelect, onMove, onAdd, onDelete }: Props) {
  const [x0, y0, x1, y1] = view.extents
  const W = Math.max(x1 - x0, 1e-6), H = Math.max(y1 - y0, 1e-6)
  const { vb, svgRef, k, toUser, pan, zoom, reset } = useViewBox(W, H)
  const P = (x: number, y: number): Pt => [x - x0, y1 - y]
  const D = (u: number, v: number): Pt => [u + x0, y1 - v]
  const [drag, setDrag] = useState<{ id: string; dx: number; dy: number; x: number; y: number; moved: boolean } | null>(null)
  const panRef = useRef<{ cx: number; cy: number; moved: boolean } | null>(null)
  const unitsPerM = 1 / (view.unitM || 1)

  // comms rooms and corridor spines (for a live route preview while dragging)
  const comms = useMemo(() => view.rooms.filter((r) => r.comms), [view.rooms])
  const spines = useMemo(() => view.rooms.filter((r) => r.cat === 'corridor').map((r) => {
    const xs = r.poly.map((p) => p[0]), ys = r.poly.map((p) => p[1])
    const bx0 = Math.min(...xs), bx1 = Math.max(...xs), by0 = Math.min(...ys), by1 = Math.max(...ys)
    return bx1 - bx0 >= by1 - by0 ? { axis: 'h', c: (by0 + by1) / 2 } : { axis: 'v', c: (bx0 + bx1) / 2 }
  }), [view.rooms])
  const centroid = (poly: Pt[]): Pt => {
    let a = 0, cx = 0, cy = 0
    for (let i = 0; i < poly.length; i++) {
      const [xa, ya] = poly[i], [xb, yb] = poly[(i + 1) % poly.length]
      const c = xa * yb - xb * ya
      a += c; cx += (xa + xb) * c; cy += (ya + yb) * c
    }
    if (Math.abs(a) < 1e-9) return poly[0]
    return [cx / (3 * a), cy / (3 * a)]
  }
  const preview = (x: number, y: number) => {
    let best: { pts: Pt[]; len: number } | null = null
    for (const c of comms) {
      const d = centroid(c.poly)
      const cands: Pt[][] = spines.length ? spines.map((s) => s.axis === 'h' ? [[x, y], [x, s.c], [d[0], s.c], d] as Pt[] : [[x, y], [s.c, y], [s.c, d[1]], d] as Pt[]) : [[[x, y], [x, d[1]], d]]
      for (const pts of cands) {
        let L = 0
        for (let i = 1; i < pts.length; i++) L += Math.abs(pts[i][0] - pts[i - 1][0]) + Math.abs(pts[i][1] - pts[i - 1][1])
        const len = L * view.unitM * 1.1 + 7
        if (!best || len < best.len) best = { pts, len }
      }
    }
    return best
  }

  const devices = view.devices.filter((d) => layers[d.sys] !== false && d.on)
  const sel = devices.find((d) => d.id === selected) || null

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.key === 'Delete' || e.key === 'Backspace') && selected && !(e.target as HTMLElement).closest('input,textarea,select')) onDelete(selected)
      if (e.key === 'Escape') onSelect(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selected, onDelete, onSelect])

  const onDown = (e: React.PointerEvent) => {
    if (e.button === 1 || e.button === 2) { panRef.current = { cx: e.clientX, cy: e.clientY, moved: true }; (e.target as Element).setPointerCapture?.(e.pointerId); return }
    if (tool === 'add') {
      const p = toUser(e.clientX, e.clientY)
      const [x, y] = D(p.x, p.y)
      onAdd(x, y)
      return
    }
    panRef.current = { cx: e.clientX, cy: e.clientY, moved: false }
    svgRef.current?.setPointerCapture(e.pointerId)
  }
  const onMoveEv = (e: React.PointerEvent) => {
    if (drag) {
      const p = toUser(e.clientX, e.clientY)
      const [x, y] = D(p.x + drag.dx, p.y + drag.dy)
      setDrag({ ...drag, x, y, moved: true })
      return
    }
    const pr = panRef.current
    if (pr) {
      const dx = e.clientX - pr.cx, dy = e.clientY - pr.cy
      if (pr.moved || Math.abs(dx) + Math.abs(dy) > 3) {
        pan(dx, dy)
        panRef.current = { cx: e.clientX, cy: e.clientY, moved: true }
      }
    }
  }
  const onUp = () => {
    if (drag) {
      if (drag.moved) onMove(drag.id, drag.x, drag.y)
      setDrag(null)
      return
    }
    const pr = panRef.current
    panRef.current = null
    if (pr && !pr.moved && tool === 'select') onSelect(null)
  }
  const devDown = (d: Device) => (e: React.PointerEvent) => {
    e.stopPropagation()
    if (e.button !== 0) return
    if (tool === 'delete') { onDelete(d.id); return }
    if (tool === 'add') return
    onSelect(d.id)
    const p = toUser(e.clientX, e.clientY)
    const [u, v] = P(d.x, d.y)
    setDrag({ id: d.id, dx: u - p.x, dy: v - p.y, x: d.x, y: d.y, moved: false })
    svgRef.current?.setPointerCapture(e.pointerId)
  }

  const pos = (d: Device): Pt => (drag && drag.id === d.id ? P(drag.x, drag.y) : P(d.x, d.y))
  const fs = (px: number) => px * k

  // scale bar length: a round number of metres ~ 120 px on screen
  const target = 120 * k / unitsPerM
  const steps = [1, 2, 5, 10, 20, 50, 100, 200]
  const barM = steps.find((s) => s >= target * 0.6) || 200
  const barU = barM * unitsPerM

  const routeEls: React.ReactNode[] = []
  if (routes === 'all') {
    for (const d of devices) {
      if (!d.pts || d.id === selected) continue
      routeEls.push(<polyline key={'r' + d.id} points={d.pts.map((p) => P(p[0], p[1]).join(',')).join(' ')} fill="none"
        stroke={d.over ? T.red : T.route} strokeWidth={(d.over ? 1.6 : 0.8) * k} opacity={d.over ? 0.9 : 0.28} />)
    }
  }
  let selRoute: { pts: Pt[]; len: number; over: boolean; live: boolean } | null = null
  if (sel) {
    if (drag && drag.id === sel.id && drag.moved) {
      const pv = preview(drag.x, drag.y)
      if (pv) selRoute = { pts: pv.pts, len: pv.len, over: pv.len > 90 && sel.sys !== 'intrusion', live: true }
    } else if (sel.pts) selRoute = { pts: sel.pts, len: sel.len || 0, over: !!sel.over, live: false }
  }

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <svg ref={svgRef} viewBox={`${vb.x} ${vb.y} ${vb.w} ${vb.h}`} preserveAspectRatio="xMidYMid meet"
        style={{ width: '100%', height: '100%', display: 'block', touchAction: 'none', userSelect: 'none',
          cursor: tool === 'add' ? 'copy' : drag ? 'grabbing' : 'default', background: '#fff' }}
        onPointerDown={onDown} onPointerMove={onMoveEv} onPointerUp={onUp} onPointerLeave={onUp} onContextMenu={(e) => e.preventDefault()}>
        <rect x={vb.x - vb.w} y={vb.y - vb.h} width={vb.w * 3} height={vb.h * 3} fill={T.bg} />
        {bg && <image href={bg} x={0} y={0} width={W} height={H} preserveAspectRatio="none" opacity={0.55} style={{ pointerEvents: 'none' }} />}
        {view.grids.map((g, i) => {
          const a = P(g.a[0], g.a[1]), b = P(g.b[0], g.b[1])
          const top = g.axis === 'x' ? (a[1] < b[1] ? a : b) : (a[0] < b[0] ? a : b)
          return (
            <g key={'g' + i} style={{ pointerEvents: 'none' }}>
              <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke={T.grid} strokeWidth={k} strokeDasharray={`${6 * k} ${5 * k}`} />
              {g.label && <>
                <circle cx={top[0] - (g.axis === 'y' ? 14 * k : 0)} cy={top[1] - (g.axis === 'x' ? 14 * k : 0)} r={9 * k} fill={T.bg} stroke={T.gridT} strokeWidth={k} />
                <text x={top[0] - (g.axis === 'y' ? 14 * k : 0)} y={top[1] - (g.axis === 'x' ? 14 * k : 0) + 3.5 * k} fontSize={fs(10)} textAnchor="middle" fill={T.gridT}>{g.label}</text>
              </>}
            </g>
          )
        })}
        {view.rooms.map((r) => {
          const pts = r.poly.map((p) => P(p[0], p[1]).join(',')).join(' ')
          const fill = r.comms ? T.comms : r.cat === 'open_office' ? T.open : CORE.has(r.cat) ? T.core : T.room
          return <polygon key={r.id} points={pts} fill={fill} fillOpacity={r.comms ? 0.92 : bg ? 0.45 : 1} stroke={r.comms ? T.comms : T.stroke} strokeWidth={k} style={{ pointerEvents: 'none' }} />
        })}
        {view.rooms.map((r) => {
          const [u, v] = P(r.label[0], r.label[1])
          return <text key={'l' + r.id} x={u} y={v} fontSize={fs(r.comms ? 10 : r.cat === 'open_office' ? 11 : 8.5)} fontWeight={r.comms ? 700 : 400}
            textAnchor="middle" fill={r.comms ? '#fff' : T.text} style={{ pointerEvents: 'none' }}>{r.name}</text>
        })}
        <g style={{ pointerEvents: 'none' }}>{routeEls}</g>
        {showFov && layers.cctv !== false && devices.filter((d) => d.sys === 'cctv' && d.range_m).map((d) => {
          const [u, v] = pos(d)
          const r = (d.range_m || 10) * unitsPerM
          const a = -(d.a || 0) * Math.PI / 180, s = 0.62
          const xa = u + r * Math.cos(a - s), ya = v + r * Math.sin(a - s), xb = u + r * Math.cos(a + s), yb = v + r * Math.sin(a + s)
          const isSel = d.id === selected
          return <path key={'f' + d.id} d={`M${u},${v} L${xa},${ya} A${r},${r} 0 0 1 ${xb},${yb} Z`} fill="#E07A1F"
            fillOpacity={isSel ? 0.22 : 0.07} stroke="#E07A1F" strokeOpacity={isSel ? 0.8 : 0.22} strokeWidth={0.8 * k} style={{ pointerEvents: 'none' }} />
        })}
        {selRoute && (() => {
          const pts = selRoute.pts.map((p) => P(p[0], p[1]))
          const m1 = pts[1] || pts[0], m2 = pts[2] || pts[pts.length - 1]
          const mx = (m1[0] + m2[0]) / 2, my = (m1[1] + m2[1]) / 2
          const red = selRoute.over
          return (
            <g style={{ pointerEvents: 'none' }}>
              <polyline points={pts.map((p) => p.join(',')).join(' ')} fill="none" stroke={red ? T.red : T.route} strokeWidth={2.6 * k} strokeDasharray={red ? undefined : `${7 * k} ${4 * k}`} />
              <rect x={mx - 32 * k} y={my - 9 * k} width={64 * k} height={18 * k} rx={3 * k} fill={red ? T.red : T.route} />
              <text x={mx} y={my + 4 * k} fontSize={fs(10.5)} fontWeight={700} textAnchor="middle" fill="#fff">{selRoute.live ? '≈' : ''}{selRoute.len.toFixed(1)} m</text>
            </g>
          )
        })()}
        <g>
          {devices.map((d) => {
            const [u, v] = pos(d)
            const c = SYS_COLOR[d.sys]
            const isSel = d.id === selected
            let s: React.ReactNode
            if (d.sys === 'cctv') s = <circle r={5.5 * k} fill={c} stroke={T.bg} strokeWidth={1.5 * k} />
            else if (d.sys === 'access') s = <rect x={-4.5 * k} y={-4.5 * k} width={9 * k} height={9 * k} fill={c} stroke={T.bg} strokeWidth={1.2 * k} />
            else if (d.sys === 'iptv') s = <rect x={-7 * k} y={-3 * k} width={14 * k} height={6 * k} fill={c} stroke={T.bg} strokeWidth={k} />
            else if (d.sys === 'cabling') s = d.sub === 'ap'
              ? <g><circle r={6 * k} fill={T.bg} stroke={c} strokeWidth={2 * k} /><circle r={1.8 * k} fill={c} /></g>
              : <rect x={-2.4 * k} y={-2.4 * k} width={4.8 * k} height={4.8 * k} fill={c} />
            else if (d.sys === 'intercom') s = <polygon points={`0,${-6.5 * k} ${6.5 * k},0 0,${6.5 * k} ${-6.5 * k},0`} fill={c} stroke={T.bg} strokeWidth={1.2 * k} />
            else s = <polygon points={`0,${-5.5 * k} ${5.5 * k},${4.5 * k} ${-5.5 * k},${4.5 * k}`} fill={c} stroke={T.bg} strokeWidth={k} />
            return (
              <g key={d.id} transform={`translate(${u},${v})`} onPointerDown={devDown(d)}
                style={{ cursor: tool === 'delete' ? 'not-allowed' : tool === 'add' ? 'copy' : 'grab' }}>
                <title>{d.id} · {d.type}</title>
                <circle r={8 * k} fill="transparent" />
                {isSel && <circle r={11 * k} fill="none" stroke={T.sel} strokeWidth={1.8 * k} />}
                {d.over && !isSel && <circle r={8.5 * k} fill="none" stroke={T.red} strokeWidth={1.2 * k} />}
                {s}
              </g>
            )
          })}
        </g>
      </svg>
      <div style={{ position: 'absolute', right: 10, top: 10, display: 'flex', flexDirection: 'column', gap: 4 }}>
        <button className="btn xs plain" title="Zoom in" onClick={() => zoom(0.7)}>+</button>
        <button className="btn xs plain" title="Zoom out" onClick={() => zoom(1.4)}>−</button>
        <button className="btn xs plain" title="Fit to view" onClick={reset}>⤢</button>
      </div>
      <div style={{ position: 'absolute', right: 14, bottom: 12, background: 'rgba(255,255,255,.9)', padding: '4px 8px', borderRadius: 3, fontSize: 10.5, color: 'var(--muted)' }}>
        <div style={{ width: barU / k, height: 5, display: 'flex' }}><div style={{ flex: 1, background: T.wall }} /><div style={{ flex: 1, border: `1px solid ${T.wall}` }} /></div>
        <div className="row" style={{ justifyContent: 'space-between' }}><span>0</span><span>{barM} m</span></div>
      </div>
    </div>
  )
}
