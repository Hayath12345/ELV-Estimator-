import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { call, onEvent, type JobEvent } from '../api/bridge'
import type { AppInfo, ProjectState } from '../api/types'

export type Screen =
  | 'dashboard' | 'library' | 'history' | 'settings'
  | 'drawings' | 'systems' | 'layout' | 'comms' | 'boq' | 'checks' | 'details' | 'texts'

export const PROJECT_SCREENS: Screen[] = ['drawings', 'systems', 'layout', 'comms', 'boq', 'checks', 'details', 'texts', 'history']

export interface Toast { id: number; kind: 'info' | 'ok' | 'err'; text: string }
export interface State {
  info: AppInfo | null
  screen: Screen
  project: ProjectState | null
  busy: number
  toasts: Toast[]
  jobs: Record<string, JobEvent>
  rev: number
  newProject: boolean
  layoutFloor: string | null
  focusDevice: string | null
}

let state: State = {
  info: null, screen: 'dashboard', project: null, busy: 0, toasts: [], jobs: {}, rev: 0, newProject: false,
  layoutFloor: null, focusDevice: null,
}
const subs = new Set<() => void>()
function set(patch: Partial<State> | ((s: State) => Partial<State>)) {
  const p = typeof patch === 'function' ? patch(state) : patch
  state = { ...state, ...p }
  subs.forEach((f) => f())
}
export function getState() { return state }
export function useStore<T>(sel: (s: State) => T): T {
  return useSyncExternalStore((cb) => { subs.add(cb); return () => subs.delete(cb) }, () => sel(state))
}

let toastId = 1
export function toast(text: string, kind: Toast['kind'] = 'info', ms = 4500) {
  const id = toastId++
  set((s) => ({ toasts: [...s.toasts, { id, kind, text }] }))
  setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), ms)
}

async function tracked<T>(p: Promise<T>): Promise<T> {
  set((s) => ({ busy: s.busy + 1 }))
  try { return await p } finally { set((s) => ({ busy: s.busy - 1 })) }
}

export const actions = {
  async init() {
    const info = await tracked(call<AppInfo>('app_info'))
    set({ info })
  },
  go(screen: Screen) {
    if (PROJECT_SCREENS.includes(screen) && !state.project && screen !== 'history') return
    set({ screen })
    window.scrollTo(0, 0)
  },
  async refreshInfo() { set({ info: await call<AppInfo>('app_info') }) },
  async refreshProject() {
    if (!state.project) return
    try {
      const project = await call<ProjectState>('project_state')
      set((s) => ({ project, rev: s.rev + 1 }))
    } catch (e) { toast(String((e as Error).message), 'err') }
  },
  bump() { set((s) => ({ rev: s.rev + 1 })) },
  async openProject(id: string, screen?: Screen) {
    const project = await tracked(call<ProjectState>('open_project', { id }))
    const first: Screen = screen || (project.steps[0].done ? 'layout' : 'drawings')
    set((s) => ({ project, screen: first, rev: s.rev + 1, layoutFloor: null, focusDevice: null }))
  },
  async createProject(info: Record<string, unknown>) {
    const project = await tracked(call<ProjectState>('create_project', info))
    set((s) => ({ project, screen: 'drawings', rev: s.rev + 1, newProject: false, layoutFloor: null }))
  },
  async openSample() {
    const r = await tracked(call<ProjectState & { job: JobEvent }>('open_sample_project'))
    set((s) => ({ project: r, screen: 'drawings', rev: s.rev + 1, layoutFloor: null }))
  },
  async closeProject() {
    await call('close_project')
    set((s) => ({ project: null, screen: 'dashboard', rev: s.rev + 1 }))
  },
  /** Run a mutation, then refresh header/steps and every visible screen. */
  async mutate<T = unknown>(method: string, args?: Record<string, unknown>, okText?: string): Promise<T | undefined> {
    try {
      const data = await tracked(call<T>(method, args))
      if (state.project) await actions.refreshProject()
      else set((s) => ({ rev: s.rev + 1 }))
      if (okText) toast(okText, 'ok')
      return data
    } catch (e) {
      toast(String((e as Error).message), 'err', 7000)
      return undefined
    }
  },
  setNewProject(v: boolean) { set({ newProject: v }) },
  setLayoutFloor(f: string | null, device: string | null = null) { set({ layoutFloor: f, focusDevice: device }) },
}

onEvent((e) => {
  if (e.type === 'job') {
    set((s) => ({ jobs: { ...s.jobs, [e.id]: e } }))
    if (e.done) {
      if (e.error) toast(e.error, 'err', 9000)
      else if (e.kind === 'export') toast('Outputs generated — the folder has been opened.', 'ok', 6000)
      else if (e.kind === 'extract') {
        const r = e.result || {}
        toast(r.failed ? `${r.extracted} extracted, ${r.failed} failed` : 'Extraction complete', r.failed ? 'err' : 'ok')
      }
      actions.refreshProject()
      actions.refreshInfo().catch(() => undefined)
    }
  } else if (e.type === 'drop') {
    ;(window as unknown as { __elvDropAt: number }).__elvDropAt = Date.now()
    if (!state.project) { toast('Open or create a quotation, then drop the drawings.', 'info'); return }
    actions.mutate('import_drawings', { paths: e.paths }).then(() => actions.go('drawings'))
  }
})

/** Fetch screen data; refetches when the store revision or deps change. */
export function useData<T>(method: string | null, args?: Record<string, unknown>, deps: unknown[] = []) {
  const rev = useStore((s) => s.rev)
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const seq = useRef(0)
  const key = JSON.stringify(args ?? {})
  const load = () => {
    if (!method) return
    const n = ++seq.current
    setLoading(true)
    call<T>(method, args)
      .then((d) => { if (n === seq.current) { setData(d); setError(null) } })
      .catch((e) => { if (n === seq.current) setError(String(e.message || e)) })
      .finally(() => { if (n === seq.current) setLoading(false) })
  }
  useEffect(load, [method, key, rev, ...deps]) // eslint-disable-line react-hooks/exhaustive-deps
  return { data, error, loading, reload: load, setData }
}
