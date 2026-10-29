import { useEffect, useState } from 'react'
import type { CommsView } from '../api/types'
import Rack from '../components/Rack'
import { Empty, ErrorBox, Loading } from '../components/ui'
import { actions, useData } from '../state/store'

const COLS = '150px 50px 80px minmax(0,1.6fr) minmax(0,1.2fr) 130px minmax(0,1fr)'

export default function Comms() {
  const { data, error, reload } = useData<CommsView>('get_comms')
  const [roomId, setRoomId] = useState<string | null>(null)
  const [rackName, setRackName] = useState<string | null>(null)
  const [adding, setAdding] = useState('')
  useEffect(() => {
    if (data && data.rooms.length && !data.rooms.find((r) => r.id === roomId)) { setRoomId(data.rooms[0].id); setRackName(data.rooms[0].racks[0]?.name || null) }
  }, [data]) // eslint-disable-line react-hooks/exhaustive-deps
  if (error) return <ErrorBox error={error} onRetry={reload} />
  if (!data) return <Loading />
  const addRoom = (val: string) => {
    if (!val) return
    const [drawing, id] = val.split('|')
    actions.mutate('update_room', { drawing, id, comms: 'IDF' }, 'Comms room added')
    setAdding('')
  }
  const header = (
    <div className="row gap12">
      <h2 className="h2">Step 4 · Comms rooms</h2>
      <span className="muted" style={{ fontSize: 12 }}>Sized for the award: {data.scenario}</span>
      <div className="ml-auto row gap8">
        <select className="input" value={adding} onChange={(e) => addRoom(e.target.value)} style={{ maxWidth: 260 }}>
          <option value="">+ Mark a room as IDF…</option>
          {data.candidates.filter((c) => !c.comms).map((c) => <option key={c.drawing + c.id} value={`${c.drawing}|${c.id}`}>{c.floor} · {c.name}</option>)}
        </select>
      </div>
    </div>
  )
  if (!data.rooms.length) {
    return <>{header}<div className="card" style={{ minHeight: 320, display: 'flex' }}><Empty title="No comms rooms identified">Rooms named MDF, IDF, Server, Telecom or ELV are detected automatically. Mark a room as IDF above (or in Step 1 › Review rooms) so devices can be routed and racks sized.</Empty></div></>
  }
  const room = data.rooms.find((r) => r.id === roomId) || data.rooms[0]
  const rack = room.racks.find((k) => k.name === rackName) || room.racks[0]
  const rtPct = Math.min(100, Math.round(room.runtime / 180 * 100))
  return (
    <>
      {header}
      <div className="card">
        <div className="th" style={{ gridTemplateColumns: COLS, padding: '0 14px' }}>
          <div>Room</div><div>Floor</div><div className="num">Devices</div><div>PoE load vs budget</div><div>UPS</div><div>Runtime (min 60)</div><div>Racks · U used</div>
        </div>
        {data.rooms.map((r) => (
          <div key={r.id} className="tr click" onClick={() => { setRoomId(r.id); setRackName(r.racks[0]?.name || null) }}
            style={{ gridTemplateColumns: COLS, padding: '0 14px', background: r.id === room.id ? 'var(--row-sel)' : undefined, boxShadow: `inset 3px 0 0 ${r.id === room.id ? 'var(--navy)' : 'transparent'}` }}>
            <div className="row gap6" style={{ minWidth: 0 }}>
              <span className="mono ellipsis" style={{ fontWeight: 600, fontSize: 12.5, color: 'var(--navy-ink)' }} title={r.name}>{r.name}</span>
              <span className="badge t-oth">{r.role}</span>
            </div>
            <div>{r.floor}</div>
            <div className="num">{r.served}</div>
            <div className="row gap10">
              <div style={{ flex: 1, height: 8, background: 'var(--border-2)', borderRadius: 2, position: 'relative', overflow: 'hidden' }}>
                <div style={{ width: `${Math.min(100, r.pct)}%`, height: '100%', background: r.over ? 'var(--err)' : 'var(--navy)' }} />
                <div style={{ position: 'absolute', left: '80%', top: 0, bottom: 0, width: 1, background: 'var(--muted)' }} />
              </div>
              <span style={{ fontSize: 12, width: 168, whiteSpace: 'nowrap', textAlign: 'right', color: r.over ? 'var(--err)' : 'var(--text)' }}>{r.poeF} / {r.budgetF} · {r.pct}%</span>
            </div>
            <div style={{ fontSize: 12 }} className="ellipsis" title={r.ups}>{r.ups}</div>
            <div>{r.runtime ? <span className="badge" style={{ fontSize: 11.5, padding: '3px 8px', background: r.runtimeOk ? 'var(--ok-bg)' : 'var(--err-bg)', color: r.runtimeOk ? 'var(--ok-ink)' : 'var(--err-2)' }}>{r.runtime} min {r.runtimeOk ? '✓' : '✗'}</span> : '—'}</div>
            <div style={{ fontSize: 12, color: 'var(--text-2)' }} className="ellipsis">{r.rackList}</div>
          </div>
        ))}
      </div>
      <div className="split" style={{ gridTemplateColumns: 'minmax(0,1fr) 360px' }}>
        <div className="col gap16">
          <div className="card">
            <div className="card-h">{room.name} · devices served by system</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,minmax(0,1fr))' }}>
              {room.mix.map((m) => (
                <div key={m.name} style={{ padding: '12px 14px', borderRight: '1px solid var(--border-3)' }}>
                  <div className="row gap6 muted" style={{ fontSize: 11.5 }}><span className="sq" style={{ background: m.color }} /><span className="ellipsis">{m.name}</span></div>
                  <div style={{ fontSize: 18, fontWeight: 600, marginTop: 4 }}>{m.n}</div>
                </div>
              ))}
            </div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div className="card" style={{ padding: 14 }}>
              <div style={{ fontWeight: 600, fontSize: 12.5, color: 'var(--navy-ink)' }}>PoE budget</div>
              <div className="row gap8" style={{ alignItems: 'baseline', marginTop: 8 }}>
                <span style={{ fontSize: 24, fontWeight: 600, color: room.over ? 'var(--err)' : 'var(--text)' }}>{room.pct}%</span>
                <span className="muted" style={{ fontSize: 12 }}>{room.poeF} of {room.budgetF} · {room.switches} PoE switches</span>
              </div>
              <div style={{ height: 10, background: 'var(--border-2)', borderRadius: 2, marginTop: 10, position: 'relative', overflow: 'hidden' }}>
                <div style={{ width: `${Math.min(100, room.pct)}%`, height: '100%', background: room.over ? 'var(--err)' : 'var(--navy)' }} />
                <div style={{ position: 'absolute', left: '80%', top: 0, bottom: 0, width: 2, background: 'var(--text)' }} />
              </div>
              <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>
                {room.over ? 'Above 80% design headroom — add a PoE switch or re-home devices to another IDF.' : 'Within 80% design headroom. Marker = 80%.'} ELV ports {room.elvPorts} · data ports {room.dataPorts}.
              </div>
            </div>
            <div className="card" style={{ padding: 14 }}>
              <div style={{ fontWeight: 600, fontSize: 12.5, color: 'var(--navy-ink)' }}>UPS runtime</div>
              <div className="row gap8" style={{ alignItems: 'baseline', marginTop: 8 }}>
                <span style={{ fontSize: 24, fontWeight: 600, color: room.runtimeOk ? 'var(--ok)' : 'var(--err)' }}>{room.runtime} min</span>
                <span className="muted" style={{ fontSize: 12 }}>{room.ups}</span>
              </div>
              <div style={{ height: 10, background: 'var(--border-2)', borderRadius: 2, marginTop: 10, position: 'relative', overflow: 'hidden' }}>
                <div style={{ width: `${rtPct}%`, height: '100%', background: room.runtimeOk ? 'var(--ok)' : 'var(--err)' }} />
                <div style={{ position: 'absolute', left: '33.3%', top: 0, bottom: 0, width: 2, background: 'var(--text)' }} />
              </div>
              <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>Marker = 60 min MOI-SSD minimum · scale to 180 min · load {room.loadW.toLocaleString('en-US', { maximumFractionDigits: 0 })} W</div>
            </div>
          </div>
        </div>
        <div className="card" style={{ padding: '12px 14px' }}>
          <div className="row" style={{ gap: 4, marginBottom: 12, flexWrap: 'wrap' }}>
            {room.racks.map((k) => (
              <div key={k.name} onClick={() => setRackName(k.name)} className={`chip${rack && k.name === rack.name ? ' on' : ''}`} style={{ height: 'auto', padding: '5px 10px' }}>{k.name} · {k.used}U</div>
            ))}
          </div>
          {rack ? <Rack rack={rack} uh={12} onReserve={(u) => actions.mutate('reserve_u', { rack: rack.name, u })} /> : <div className="muted">No rack equipment in this room.</div>}
        </div>
      </div>
    </>
  )
}
