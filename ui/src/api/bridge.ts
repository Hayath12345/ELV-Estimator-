// Bridge to the Python backend.
// Desktop: pywebview js_api  -> window.pywebview.api.call(method, args)
// Dev/browser: same API over HTTP (app/server.py --dev) with a per-session token.

/* eslint-disable @typescript-eslint/no-explicit-any */
declare global {
  interface Window {
    pywebview?: any
    __elvEvent?: (e: ElvEvent) => void
    __ELV_DEV?: boolean
    __ELV_TOKEN?: string
  }
}

export interface JobEvent { type: 'job'; id: string; kind: string; pct: number; message: string; done: boolean; error: string | null; result: any }
export interface DropEvent { type: 'drop'; paths: string[] }
export type ElvEvent = JobEvent | DropEvent

type Mode = 'pywebview' | 'http'
const listeners = new Set<(e: ElvEvent) => void>()
let modePromise: Promise<Mode> | null = null

export function onEvent(fn: (e: ElvEvent) => void): () => void {
  listeners.add(fn)
  return () => { listeners.delete(fn) }
}
function emit(e: ElvEvent) { listeners.forEach((l) => { try { l(e) } catch (err) { console.error(err) } }) }
window.__elvEvent = emit

function detect(): Promise<Mode> {
  if (window.__ELV_DEV) return Promise.resolve('http')
  if (window.pywebview?.api?.call) return Promise.resolve('pywebview')
  return new Promise((resolve) => {
    const done = () => resolve(window.pywebview?.api?.call ? 'pywebview' : 'http')
    window.addEventListener('pywebviewready', done, { once: true })
    setTimeout(done, 5000)
  })
}

export function mode(): Promise<Mode> {
  if (!modePromise) {
    modePromise = detect().then((m) => { if (m === 'http') pollEvents(); return m })
  }
  return modePromise
}

export class ApiError extends Error {}

export async function call<T = any>(method: string, args?: Record<string, any>): Promise<T> {
  const m = await mode()
  let r: any
  if (m === 'pywebview') {
    r = await window.pywebview.api.call(method, args ?? {})
  } else {
    const resp = await fetch('api/call', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-ELV-Token': window.__ELV_TOKEN || '' },
      body: JSON.stringify({ method, args: args ?? {} }),
    })
    r = await resp.json()
  }
  if (!r || !r.ok) throw new ApiError(r?.error || 'Request failed')
  return r.data as T
}

let polling = false
async function pollEvents() {
  if (polling) return
  polling = true
  let after = 0
  for (;;) {
    try {
      const resp = await fetch(`api/events?after=${after}`, { headers: { 'X-ELV-Token': window.__ELV_TOKEN || '' } })
      if (!resp.ok) { await sleep(2000); continue }
      const j = await resp.json()
      after = j.next
      for (const e of j.events) emit(e)
    } catch {
      await sleep(2000)
    }
  }
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

/** Native open dialog on desktop; null in the browser (caller falls back to <input type=file>). */
export async function pickFiles(kind: 'drawings' | 'csv'): Promise<string[] | null> {
  const m = await mode()
  if (m !== 'pywebview') return null
  const r = await window.pywebview.api.pick_files(kind)
  if (!r?.ok) throw new ApiError(r?.error || 'Could not open the file dialog')
  return r.data as string[]
}

export async function pickFolder(): Promise<string | null | undefined> {
  const m = await mode()
  if (m !== 'pywebview') return undefined
  const r = await window.pywebview.api.pick_folder()
  return r?.data ?? null
}

/** Send a File (from drag-and-drop or <input>) to the backend; returns a local path. */
export async function uploadFile(file: File): Promise<string> {
  const m = await mode()
  if (m === 'http') {
    const resp = await fetch(`api/upload?name=${encodeURIComponent(file.name)}`, {
      method: 'POST', headers: { 'X-ELV-Token': window.__ELV_TOKEN || '' }, body: file,
    })
    const j = await resp.json()
    if (!j.ok) throw new ApiError(j.error || 'Upload failed')
    return j.data
  }
  const id = Math.random().toString(36).slice(2)
  const CHUNK = 2 * 1024 * 1024
  let path = ''
  for (let off = 0; off < file.size || off === 0; off += CHUNK) {
    const blob = file.slice(off, off + CHUNK)
    const b64 = await blobToBase64(blob)
    const last = off + CHUNK >= file.size
    const r = await window.pywebview.api.upload_chunk(id, file.name, b64, last)
    if (!r?.ok) throw new ApiError(r?.error || 'Upload failed')
    if (last) { path = r.data; break }
  }
  return path
}

function blobToBase64(b: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const fr = new FileReader()
    fr.onload = () => resolve(String(fr.result).split(',')[1] || '')
    fr.onerror = () => reject(fr.error)
    fr.readAsDataURL(b)
  })
}
