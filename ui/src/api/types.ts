/* View models returned by app/backend.py. Money arrives pre-formatted ("4,010,502.21"). */

export interface SystemDef { key: string; name: string; full: string; abbr: string; color: string }
export interface Option { value: string; label: string }

export interface AppInfo {
  version: string
  libredwg: boolean
  user: { name: string; role: string; initials: string }
  company: Record<string, string>
  ticker: string
  currencies: { code: string; name: string; symbol: string }[]
  systems: SystemDef[]
  roomCategories: Option[]
  categories: string[]
  projectsDir: string
  libraryCount: number
  status: string[]
  addTypes: Record<string, Option[]>
}

export interface ProjectRow {
  id: string; name: string; scope: string; client: string; ref: string; rev: string
  systems: { key: string; name: string; color: string; ab: string }[]
  total: string; totalF: string; status: string; edited: string; by: string
}
export interface ProjectList { rows: ProjectRow[]; kpis: { active: number; review: number; changes: number; pipelineF: string }; openId: string | null }

export interface Step { key: string; label: string; sub: string; done: boolean }
export interface ProjectState {
  id: string
  info: Record<string, any>
  folder: string
  revLabel: string
  rev: number
  status: string
  header: { baseLabel: string; baseF: string; networkF: string; savingF: string; combined: boolean }
  steps: Step[]
  floors: { key: string; name: string }[]
  company: Record<string, string>
  signoff: Record<string, { name?: string; role?: string; at?: string | null }>
  drawingRefs: string
  commercial: Record<string, string>
}

export interface DrawingFile {
  id: string; name: string; file: string; ext: string; kind: string; floor: string; order: number; meta: string
  status: string; stFg: string; error: string | null; role: string
  scale: { unit_m: number | null; conf: string; note: string; plot: number | null }
  warnings: string[]; counts: Record<string, number>
}
export interface ExtractRow { item: string; vals: string[]; conf: string; tone: string; note: string }
export interface RoomRow { id: string; drawing: string; floor: string; name: string; category: string; categoryLabel: string; area: string; comms: string; conf: string; boundary: string; wps: number }
export interface DrawingsView {
  files: DrawingFile[]; rows: ExtractRow[]; floors: string[]
  state: 'empty' | 'loading' | 'results' | 'warn' | 'error'
  caption: string; errors: { id: string; name: string; message: string }[]; rooms: RoomRow[]
  jobs: { id: string; pct: number; message: string }[]; libredwg: boolean
}

export interface ParamSpec { key: string; label: string; type: 'number' | 'select' | 'text' | 'multi' | 'bool'; default: any; unit: string; options: (string | Option)[]; help: string; value: any }
export interface SystemsView {
  systems: { key: string; full: string; name: string; color: string; on: boolean; qty: string; detail: string; standaloneF: string; combinedF: string }[]
  allOn: boolean; combined: boolean; selected: string[]; sharedF: string; baseStandaloneF: string; baseCombinedF: string; savingF: string; summary: string
  params: Record<string, ParamSpec[]>
}

export type Pt = [number, number]
export interface Device {
  id: string; sys: string; item: string; sub?: string; x: number; y: number; a: number; type: string; location: string
  edited: boolean; auto: boolean; on: boolean
  target?: string; range_m?: number; leaves?: number; readers?: number; lock?: string; tag?: string; ports?: number
  idf?: string; len?: number; over?: boolean; pts?: Pt[]; riser?: boolean
}
export interface LayoutView {
  floors: { key: string; name: string }[]; floor: string | null; floorName: string
  extents: [number, number, number, number]; unitM: number; calibrated: boolean
  rooms: { id: string; rid: string; name: string; cat: string; poly: Pt[]; comms: string | null; label: Pt; area: number }[]
  grids: { a: Pt; b: Pt; axis: string; label: string }[]
  devices: Device[]
  counts: { floor: Record<string, number>; total: Record<string, number>; devices: number; max: string; long: number }
  scale: string; hasBg: boolean
}

export interface RackItemV { label: string; size: number; kind: string; u: number }
export interface RackV { name: string; used: number; reserved: number[]; items: RackItemV[] }
export interface CommsRoom {
  id: string; name: string; floor: string; role: string; served: number; mix: { name: string; color: string; n: number }[]
  poe: number; budget: number; poeF: string; budgetF: string; pct: number; over: boolean; switches: number; elvSwitches: number; userSwitches: number
  elvPorts: number; dataPorts: number; loadW: number; ups: string; runtime: number; runtimeOk: boolean; rackList: string; racks: RackV[]; uUsed: number; uTotal: number
}
export interface CommsView { rooms: CommsRoom[]; scenario: string; candidates: { id: string; drawing: string; name: string; floor: string; comms: string }[] }

export interface BoqLine {
  key: string; tab: string; section: string; item: string | null; desc: string; mfr: string; part: string; unit: string; category: string
  qty: string; qtyF: string; qtyAuto: string; note: string; list: string | null; listF: string; cur: string; disc: string; discF: string
  conf: string | null; confLabel: string; unitQ: string | null; unitF: string; total: string; totalF: string
  shared: boolean; budget: boolean; unpriced: boolean; custom: boolean; overridden: string[]; source: string; date: string
}
export interface BoqSection { id: string; name: string; count: number; isShared: boolean; sub: string; subF: string; lines: BoqLine[]; excluded: boolean }
export interface BoqTab { key: string; name: string; color: string | null; isSystem: boolean; combined: string; standalone: string; combinedF: string; standaloneF: string; sections: BoqSection[] }
export interface FxRow { code: string; name: string; rate: string; libRate: string; asOf: string; source: string; project: boolean }
export interface BoqView {
  tabs: BoqTab[]; combined: boolean
  sysRows: { key: string; name: string; color: string; sa: string; co: string }[]
  m: { shared: string; standalone: string; combinedBase: string; base: string; saving: string; network: string; optional: string }
  confMix: { k: string; v: number; amount: string; tone: string }[]
  unpriced: number; rfq: number
  commercial: Record<string, string>
  fx: FxRow[]
  labour: { key: string; role: string; rate: string; currency: string }[]
}

export interface PriceRow {
  key: string; system: string; systemName: string; category: string; desc: string; mfr: string; part: string; unit: string
  list: string; cur: string; disc: string; source: string; date: string; dateF: string; conf: string; stale: boolean; custom: boolean; used: string
}
export interface PricesView { rows: PriceRow[]; total: number; shown: number; priced: number; usedCount: number; unpricedUsed: number }

export interface CheckRow { name: string; a: string; op: string; b: string; pass: boolean; sev: 'block' | 'warn' }
export interface CheckGroup { id: string; g: string; n: number; passed: number; rows: CheckRow[] }
export interface ChecksView {
  groups: CheckGroup[]; total: number; passed: number; blocking: number; lastRun: string; rev: number
  exports: { id: string; name: string; fmt: string; on: boolean }[]
  bump: boolean; changeLog: string
  approval: { step: string; label: string; who: string; role: string; done: boolean; when: string }[]
  override: { reason: string; by: string; at: string; failing: number } | null
  canIssue: boolean
  last: { at: string; rev: number; folder: string; files: string[]; zip?: string } | null
  status: string
}

export interface HistoryView {
  revisions: { rev: number; label: string; at: string; by: string; note: string; status: string; totalF: string }[]
  selected: number | null
  changes: { area: string; what: string; delta: string; deltaF: string; pos: boolean }[]
  compare: { from: string | null; to: string; fromF?: string; toF: string; deltaF?: string; up?: boolean } | null
  current: { rev: number; totalF: string }
}
