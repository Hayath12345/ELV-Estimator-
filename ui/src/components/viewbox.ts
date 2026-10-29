import { useCallback, useEffect, useRef, useState } from 'react'

export interface VB { x: number; y: number; w: number; h: number }

/** Zoom (wheel, around the cursor) and pan for an SVG whose user space is plan units (y down). */
export function useViewBox(width: number, height: number, margin = 0.04) {
  const fit = useCallback((): VB => {
    const m = Math.max(width, height) * margin
    return { x: -m, y: -m, w: width + 2 * m, h: height + 2 * m }
  }, [width, height, margin])
  const [vb, setVb] = useState<VB>(fit)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const [px, setPx] = useState({ w: 800, h: 500 })

  useEffect(() => { setVb(fit()) }, [fit])
  useEffect(() => {
    const el = svgRef.current
    if (!el) return
    const ro = new ResizeObserver(() => { const r = el.getBoundingClientRect(); setPx({ w: r.width || 800, h: r.height || 500 }) })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  /** user units per screen pixel (meet: the larger ratio wins) */
  const k = Math.max(vb.w / px.w, vb.h / px.h)

  const toUser = useCallback((clientX: number, clientY: number) => {
    const el = svgRef.current
    if (!el) return { x: 0, y: 0 }
    const pt = el.createSVGPoint()
    pt.x = clientX
    pt.y = clientY
    const m = el.getScreenCTM()
    if (!m) return { x: 0, y: 0 }
    const q = pt.matrixTransform(m.inverse())
    return { x: q.x, y: q.y }
  }, [])

  useEffect(() => {
    const el = svgRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const p = toUser(e.clientX, e.clientY)
      const f = Math.exp((e.deltaY > 0 ? 1 : -1) * Math.min(Math.abs(e.deltaY), 120) / 600)
      setVb((v) => {
        const w = Math.min(Math.max(v.w * f, width * 0.01 + 1e-6), (width + height) * 4)
        const h = v.h * (w / v.w)
        return { x: p.x - (p.x - v.x) * (w / v.w), y: p.y - (p.y - v.y) * (h / v.h), w, h }
      })
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [toUser, width, height])

  const pan = useCallback((dxPx: number, dyPx: number) => {
    setVb((v) => ({ ...v, x: v.x - dxPx * k, y: v.y - dyPx * k }))
  }, [k])

  const zoom = useCallback((f: number) => {
    setVb((v) => {
      const cx = v.x + v.w / 2, cy = v.y + v.h / 2
      const w = v.w * f, h = v.h * f
      return { x: cx - w / 2, y: cy - h / 2, w, h }
    })
  }, [])

  return { vb, setVb, svgRef, k, toUser, pan, zoom, reset: () => setVb(fit()) }
}
