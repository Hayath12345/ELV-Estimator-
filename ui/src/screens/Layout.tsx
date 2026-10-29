import { useCallback, useEffect, useState } from 'react'
import { call } from '../api/bridge'
import type { Device, LayoutView } from '../api/types'
import FloorPlan, { SYS_COLOR } from '../components/FloorPlan'
import { Check, Empty, ErrorBox, Loading, Seg } from '../components/ui'
import { actions, toast, useData, useStore } from '../state/store'

const SHAPE: Record<string, [number, number, string, string, number]> = {
  cctv: [10, 10, '50%', 'none', 0], access: [9, 9, '1px', 'none', 0], iptv: [14, 6, '1px', 'none', 0],
  cabling: [7, 7, '1px', 'none', 0], intercom: [8, 8, '1px', 'none', 45], intrusion: [11, 10, '0', 'polygon(50% 0,100% 100%,0 100%)', 0],
}
const bgCache = new Map<string, string | null>()

export default function Layout() {
  const systems = useStore((s) => s.info?.systems || [])
  const addTypes = useStore((s) => s.info?.addTypes || {})
  const storeFloor = useStore((s) => s.layoutFloor)
  const focus = useStore((s) => s.focusDevice)
  const [floor, setFloor] = useState<string | null>(storeFloor)
  const { data, error, reload, setData } = useData<LayoutView>('get_layout', floor ? { floor } : {})
  const [tool, setTool] = useState<'select' | 'add' | 'delete'>('select')
  const [addSys, setAddSys] = useState('cctv')
  const [addItem, setAddItem] = useState<string>('')
  const [fov, setFov] = useState(true)
  const [allRoutes, setAllRoutes] = useState(false)
  const [layers, setLayers] = useState<Record<string, boolean>>({})
  const [selected, setSelected] = useState<string | null>(focus)
  const [bg, setBg] = useState<string | null>(null)

  useEffect(() => { if (focus) setSelected(focus) }, [focus])
  useEffect(() => {
    if (!data?.floor) return
    if (floor !== data.floor) setFloor(data.floor)
    const key = data.floor
    if (!data.hasBg) { setBg(null); return }
    if (bgCache.has(key)) { setBg(bgCache.get(key) || null); return }
    call<{ url: string | null }>('get_background', { id: key }).then((r) => { bgCache.set(key, r.url); setBg(r.url) }).catch(() => setBg(null))
  }, [data?.floor, data?.hasBg]) // eslint-disable-line react-hooks/exhaustive-deps

  const onMove = useCallback(async (id: string, x: number, y: number) => {
    setData((d) => d ? { ...d, devices: d.devices.map((v) => v.id === id ? { ...v, x, y } : v) } : d)
    await actions.mutate('move_device', { id, x, y })
  }, [setData])
  const onAdd = useCallback(async (x: number, y: number) => {
    if (!data?.floor) return
    const r = await actions.mutate<{ id: string }>('add_device', { sys: addSys, item: addItem || undefined, floor: data.floor, x, y })
    if (r?.id) setSelected(r.id)
  }, [data?.floor, addSys, addItem])
  const onDelete = useCallback(async (id: string) => {
    if (selected === id) setSelected(null)
    await actions.mutate('delete_device', { id })
  }, [selected])

  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return <Loading />
  if (!data.floor) return <div className="card" style={{ minHeight: 360, display: 'flex' }}><Empty title="No floors yet">Upload and extract drawings in Step 1 to generate the device layout.</Empty></div>

  const c = data.counts
  const sel = data.devices.find((d) => d.id === selected) || null
  const selSys = sel ? systems.find((y) => y.key === sel.sys) : null
  return (
    <>
      <div className="card row" style={{ gap: 14, padding: '8px 12px', flexWrap: 'wrap' }}>
        <Seg value={data.floor} options={data.floors.map((f) => ({ value: f.key, label: f.name }))} onChange={(v) => { setFloor(v); setSelected(null); actions.setLayoutFloor(v) }} />
        <div style={{ width: 1, height: 22, background: 'var(--border)' }} />
        <div className="row" style={{ gap: 4 }}>
          {([['select', 'Select / move'], ['add', 'Add device'], ['delete', 'Delete']] as const).map(([k, label]) => (
            <div key={k} onClick={() => setTool(k)} className={`chip${tool === k ? ' on' : ''}`} style={{ height: 30, padding: '0 12px', borderRadius: 4, borderColor: tool === k ? 'var(--navy)' : 'var(--input-border)' }}>{label}</div>
          ))}
        </div>
        {tool === 'add' && (
          <div className="row gap6 muted" style={{ fontSize: 12 }}>Add
            {systems.map((y) => (
              <div key={y.key} onClick={() => { setAddSys(y.key); setAddItem('') }} className="chip"
                style={{ height: 24, padding: '0 8px', fontSize: 11.5, background: addSys === y.key ? y.color : '#fff', color: addSys === y.key ? '#fff' : 'var(--text)', borderColor: addSys === y.key ? y.color : 'var(--border)' }}>{y.name}</div>
            ))}
            {(addTypes[addSys] || []).length > 1 && (
              <select className="input" value={addItem} onChange={(e) => setAddItem(e.target.value)} style={{ maxWidth: 200 }}>
                {(addTypes[addSys] || []).map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            )}
          </div>
        )}
        <div className="row ml-auto" style={{ gap: 14, fontSize: 12, color: 'var(--text-2)' }}>
          <Check size14 on={fov} onChange={setFov} label="Fields of view" />
          <Check size14 on={allRoutes} onChange={setAllRoutes} label="All cable routes" />
          <span className="muted">{data.scale || (data.calibrated ? '' : 'Scale not calibrated')}</span>
          <button className="btn xs plain" title="Discard your edits on this floor and restore the rule-based layout"
            onClick={() => { if (confirm('Reset all device edits on this floor to the automatic layout?')) actions.mutate('reset_layout', { floor: data.floor }, 'Floor layout reset') }}>Reset floor</button>
        </div>
      </div>
      <div className="split" style={{ gridTemplateColumns: '214px minmax(0,1fr) 260px', gap: 12 }}>
        <div className="card">
          <div className="th" style={{ gridTemplateColumns: 'minmax(0,1fr) 32px 38px', gap: 6, padding: '0 10px', fontSize: 11, minHeight: 30 }}>
            <div>Layer</div><div className="num">{data.floorName}</div><div className="num">Total</div>
          </div>
          {systems.map((y) => {
            const on = layers[y.key] !== false
            const sh = SHAPE[y.key]
            return (
              <div key={y.key} onClick={() => setLayers({ ...layers, [y.key]: !on })} title={y.name}
                style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 32px 38px', gap: 6, padding: '0 10px', height: 36, alignItems: 'center', borderBottom: '1px solid var(--border-3)', cursor: 'pointer', opacity: on ? 1 : 0.45 }}>
                <div className="row gap8" style={{ minWidth: 0 }}>
                  <span className={`cbx s14${on ? ' on' : ''}`} />
                  <span style={{ width: sh[0], height: sh[1], borderRadius: sh[2], background: y.color, clipPath: sh[3], transform: `rotate(${sh[4]}deg)`, flex: 'none' }} />
                  <span className="ellipsis" style={{ fontSize: 12 }}>{y.name}</span>
                </div>
                <div className="num" style={{ fontSize: 12 }}>{c.floor[y.key] ?? ''}</div>
                <div className="num" style={{ fontSize: 12, fontWeight: 600 }}>{c.total[y.key] ?? ''}</div>
              </div>
            )
          })}
          <div style={{ padding: 10, fontSize: 11.5, lineHeight: 1.6 }} className="muted">
            <div className="row" style={{ justifyContent: 'space-between' }}><span>Devices on {data.floorName}</span><b style={{ color: 'var(--text)', fontWeight: 600 }}>{c.devices}</b></div>
            <div className="row" style={{ justifyContent: 'space-between' }}><span>Wi-Fi APs on {data.floorName}</span><b style={{ color: 'var(--text)', fontWeight: 600 }}>{c.floor.ap}</b></div>
            <div className="row" style={{ justifyContent: 'space-between' }}><span>Longest link on {data.floorName}</span><b style={{ color: 'var(--text)', fontWeight: 600 }}>{c.max} m</b></div>
            <div className="row" style={{ justifyContent: 'space-between' }}><span>Links over 90 m</span><b style={{ fontWeight: 600, color: c.long > 0 ? 'var(--err)' : 'var(--ok)' }}>{c.long}</b></div>
          </div>
        </div>
        <div className="card" style={{ padding: 6, height: 'max(460px, calc(100vh - 330px))', position: 'relative' }}>
          <FloorPlan view={data} bg={bg} layers={layers} tool={tool} showFov={fov} routes={allRoutes ? 'all' : 'selected'}
            selected={selected} onSelect={setSelected} onMove={onMove} onAdd={onAdd} onDelete={onDelete} />
          <div style={{ position: 'absolute', left: 14, bottom: 12, display: 'flex', gap: 12, fontSize: 11, color: 'var(--muted)', background: 'rgba(255,255,255,.9)', padding: '4px 8px', borderRadius: 3, pointerEvents: 'none' }}>
            <span className="row gap6"><span style={{ width: 16, borderTop: '2px dashed var(--navy)' }} />Route ≤ 90 m</span>
            <span className="row gap6"><span style={{ width: 16, borderTop: '2px solid var(--err-line)' }} />Over 90 m</span>
            <span>Drag to move · drag empty plan to pan · scroll to zoom</span>
          </div>
        </div>
        <div className="card">
          <div className="card-h">Device detail</div>
          {sel ? <DeviceDetail d={sel} sysName={selSys?.name || ''} addTypes={addTypes[sel.sys] || []}
            onDelete={() => onDelete(sel.id)} onDuplicate={async () => { const r = await actions.mutate<{ id: string }>('duplicate_device', { id: sel.id }); if (r?.id) setSelected(r.id) }} />
            : <div className="muted" style={{ padding: '24px 14px', fontSize: 12, lineHeight: 1.5 }}>Select a device on the plan to see its details, target and cable route. Use <b>Add</b> to place new devices or <b>Delete</b> to remove them. Edits are saved in the project and kept when design parameters change.</div>}
        </div>
      </div>
    </>
  )
}

function DeviceDetail({ d, sysName, addTypes, onDelete, onDuplicate }: { d: Device; sysName: string; addTypes: { value: string; label: string }[]; onDelete: () => void; onDuplicate: () => void }) {
  const upd = (props: Record<string, unknown>) => actions.mutate('update_device', { id: d.id, props })
  const row = (k: string, v: React.ReactNode, strong = false, color?: string) => (
    <div className="kv"><span>{k}</span><span style={{ textAlign: 'right', fontWeight: strong ? 600 : 400, color }}>{v}</span></div>
  )
  return (
    <div style={{ padding: '12px 14px' }}>
      <div className="row gap8" style={{ marginBottom: 8 }}>
        <span className="sq" style={{ width: 10, height: 10, background: SYS_COLOR[d.sys] }} />
        <span className="mono" style={{ fontWeight: 600, fontSize: 16, color: 'var(--navy-ink)' }}>{d.id}</span>
        <span className="ml-auto muted" style={{ fontSize: 11.5 }}>{sysName}{d.edited ? ' · edited' : !d.auto ? ' · added' : ''}</span>
      </div>
      {addTypes.length > 1
        ? row('Type', <select className="cell" style={{ maxWidth: 160 }} value={d.item} onChange={(e) => upd({ item: e.target.value })}>
            {addTypes.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}</select>)
        : row('Type', d.type)}
      {row('Location', d.location)}
      {d.sys === 'cctv' && (
        <div style={{ padding: '8px 0', borderBottom: '1px solid var(--border-3)', fontSize: 12 }}>
          <div className="muted" style={{ marginBottom: 6 }}>Target (EN 62676-4) · range {d.range_m} m</div>
          <div className="seg light" style={{ display: 'flex' }}>
            {['Identify', 'Recognise', 'Observe'].map((t) => <div key={t} style={{ flex: 1, textAlign: 'center' }} className={d.target === t ? 'on' : ''} onClick={() => upd({ target: t })}>{t}</div>)}
          </div>
          <AngleSlider key={d.id} value={Math.round(d.a || 0)} onCommit={(a) => upd({ a })} />
        </div>
      )}
      {d.sys === 'access' && <>
        {row('Door leaves', <Seg light value={String(d.leaves || 1)} options={[{ value: '1', label: '1' }, { value: '2', label: '2' }]} onChange={(v) => upd({ leaves: Number(v) })} />)}
        {row('Readers', <Seg light value={String(d.readers || 1)} options={[{ value: '1', label: 'In + REX' }, { value: '2', label: 'In / out' }]} onChange={(v) => upd({ readers: Number(v) })} />)}
        {row('Lock', <Seg light value={d.lock || 'strike'} options={[{ value: 'strike', label: 'Strike' }, { value: 'maglock', label: 'Maglock' }]} onChange={(v) => upd({ lock: v })} />)}
        {d.tag && row('Door tag', <span className="mono">{d.tag}</span>)}
      </>}
      {d.sys === 'cabling' && d.sub !== 'ap' && row('Outlets', <Seg light value={String(d.ports || 2)} options={[{ value: '1', label: '1' }, { value: '2', label: '2' }, { value: '4', label: '4' }]} onChange={(v) => upd({ ports: Number(v) })} />)}
      {row('Assigned comms room', d.idf || '—', true)}
      {row('Cable length', d.len != null ? `${d.len.toFixed(1)} m${d.riser ? ' (via riser)' : ''}` : '—', true, d.over ? 'var(--err)' : undefined)}
      {d.over && <div style={{ marginTop: 8, padding: '8px 10px', background: 'var(--err-bg)', color: 'var(--err-ink)', fontSize: 11.5, borderRadius: 3, lineHeight: 1.45 }}>Exceeds the 90 m permanent-link limit. Move the device, re-home to another IDF or add a consolidation point.</div>}
      <div className="row gap6" style={{ marginTop: 12 }}>
        <button className="btn sm plain" style={{ flex: 1 }} onClick={onDuplicate}>Duplicate</button>
        <button className="btn sm danger" style={{ flex: 1 }} onClick={onDelete}>Delete</button>
      </div>
    </div>
  )
}

function AngleSlider({ value, onCommit }: { value: number; onCommit: (v: number) => void }) {
  const [v, setV] = useState(value)
  useEffect(() => setV(value), [value])
  const commit = () => { if (v !== value) onCommit(v) }
  return (
    <div className="row gap6" style={{ marginTop: 8 }}>
      <span className="muted">Direction</span>
      <input type="range" min={-180} max={180} step={15} value={v} style={{ flex: 1, accentColor: 'var(--navy)' }}
        onChange={(e) => setV(Number(e.target.value))} onMouseUp={commit} onTouchEnd={commit} onKeyUp={commit} />
      <span style={{ width: 34, textAlign: 'right' }}>{v}°</span>
    </div>
  )
}

export { toast }
