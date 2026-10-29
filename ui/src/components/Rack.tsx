import { useState } from 'react'
import type { RackV } from '../api/types'

const K: Record<string, string> = {
  patch: '#C9D2E1', mgr: '#E6EAF1', fibre: '#9ED3D0', switch: '#7EA6DA', server: '#1F3B70', storage: '#5A4E9C',
  av: '#8A5CD6', panel: '#D0457A', mgmt: '#AEB7C6', power: '#E0A526', battery: '#C98A12',
}
const LIGHT: Record<string, boolean> = { server: true, storage: true, av: true, panel: true, switch: true, battery: true }

/** 42U rack elevation (port of the design's Rack component). Click equipment for details, empty U to reserve. */
export default function Rack({ rack, uh = 12, onReserve }: { rack: RackV; uh?: number; onReserve?: (u: number) => void }) {
  const [sel, setSel] = useState<number | null>(null)
  const occ: Record<number, number> = {}
  rack.items.forEach((it, i) => { for (let k = 0; k < it.size; k++) occ[it.u + k] = i })
  const res = new Set(rack.reserved || [])
  const used = rack.used + res.size
  const pct = Math.round(used / 42 * 100)
  const hot = pct > 80
  const s = sel != null ? rack.items[sel] : null
  const rows: React.ReactNode[] = []
  for (let u = 42; u >= 1; u--) {
    const y = (42 - u) * uh
    rows.push(<div key={'n' + u} style={{ position: 'absolute', left: 0, top: y, width: 22, height: uh, fontSize: 8.5, lineHeight: uh + 'px', textAlign: 'right', color: '#6B7486' }}>{u}</div>)
    if (occ[u] === undefined) {
      rows.push(
        <div key={'e' + u} onClick={() => onReserve?.(u)} title={`Click to ${res.has(u) ? 'release' : 'reserve'} U${u}`}
          style={{ position: 'absolute', left: 30, right: 8, top: y, height: uh, background: res.has(u) ? '#FFE9C7' : '#F3F5F9', borderBottom: '1px solid #E1E6EE', cursor: 'pointer', fontSize: 8.5, lineHeight: uh + 'px', paddingLeft: 6, color: '#6B7486' }}>
          {res.has(u) ? 'Reserved — future expansion' : ''}
        </div>,
      )
    }
  }
  rack.items.forEach((it, i) => {
    const y = (42 - (it.u + it.size - 1)) * uh
    const isS = sel === i
    rows.push(
      <div key={'i' + i} onClick={() => setSel(isS ? null : i)} title={`${it.label} · U${it.u}${it.size > 1 ? '–U' + (it.u + it.size - 1) : ''}`}
        style={{ position: 'absolute', left: 30, right: 8, top: y + 1, height: it.size * uh - 2, background: K[it.kind] || K.mgmt, borderRadius: 2,
          boxShadow: isS ? '0 0 0 2px #E07A1F' : 'inset 0 0 0 1px rgba(0,0,0,.12)', cursor: 'pointer', color: LIGHT[it.kind] ? '#fff' : '#1B2333',
          fontSize: Math.min(10.5, uh * 0.75), fontWeight: 500, display: 'flex', alignItems: 'center', padding: '0 7px', overflow: 'hidden', whiteSpace: 'nowrap', justifyContent: 'space-between', gap: 6 }}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>{it.label}</span><span style={{ opacity: .75, fontSize: 9 }}>{it.size}U</span>
      </div>,
    )
  })
  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
        <div style={{ fontWeight: 600, fontSize: 13 }}>{rack.name} · 42U</div>
        <div style={{ fontSize: 12, color: hot ? '#D32F2F' : '#6B7486' }}>{used} U used · {42 - used} free · {pct}%</div>
      </div>
      <div style={{ height: 4, background: '#F3F5F9', borderRadius: 2, marginBottom: 10, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: hot ? '#D32F2F' : '#1F3B70' }} />
      </div>
      <div style={{ position: 'relative', height: 42 * uh, border: '6px solid #2B3345', borderTopWidth: 10, borderBottomWidth: 10, background: '#fff', borderRadius: 3, boxSizing: 'content-box' }}>{rows}</div>
      <div style={{ marginTop: 8, fontSize: 11.5, color: '#6B7486', minHeight: 16 }}>
        {s ? <span><b style={{ color: '#1B2333', fontWeight: 600 }}>{s.label}</b> · U{s.u}{s.size > 1 ? `–U${s.u + s.size - 1}` : ''} · {s.size}U</span> : 'Click equipment for details · click an empty U to reserve it'}
      </div>
    </div>
  )
}
