import { useEffect, useState } from 'react'
import { ProjectHeader, Sidebar, TopBar } from './components/Shell'
import { ErrorBox } from './components/ui'
import Boq from './screens/Boq'
import Checks from './screens/Checks'
import Comms from './screens/Comms'
import Dashboard, { NewProjectModal } from './screens/Dashboard'
import Drawings from './screens/Drawings'
import { ProjectDetails, Settings, Texts } from './screens/Forms'
import History from './screens/History'
import Layout from './screens/Layout'
import PriceLibrary from './screens/PriceLibrary'
import Systems from './screens/Systems'
import { actions, useStore } from './state/store'

const STEP = new Set(['drawings', 'systems', 'layout', 'comms', 'boq', 'checks'])

export default function App() {
  const screen = useStore((s) => s.screen)
  const project = useStore((s) => s.project)
  const busy = useStore((s) => s.busy)
  const toasts = useStore((s) => s.toasts)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { actions.init().catch((e) => setErr(String(e.message || e))) }, [])
  const inProject = !!project && (STEP.has(screen) || screen === 'details' || screen === 'texts')
  let body: React.ReactNode
  switch (screen) {
    case 'dashboard': body = <Dashboard />; break
    case 'library': body = <PriceLibrary />; break
    case 'history': body = <History />; break
    case 'settings': body = <Settings />; break
    case 'drawings': body = <Drawings />; break
    case 'systems': body = <Systems />; break
    case 'layout': body = <Layout />; break
    case 'comms': body = <Comms />; break
    case 'boq': body = <Boq />; break
    case 'checks': body = <Checks />; break
    case 'details': body = <ProjectDetails />; break
    case 'texts': body = <Texts />; break
  }
  return (
    <div className="app">
      {busy > 0 && <div className="loading-bar"><div /></div>}
      <Sidebar />
      <main className="main">
        <TopBar />
        {inProject && STEP.has(screen) && <ProjectHeader />}
        <div className="content">
          {err ? <ErrorBox error={`Could not start: ${err}`} onRetry={() => location.reload()} /> : body}
        </div>
      </main>
      <NewProjectModal />
      <div className="toasts">{toasts.map((t) => <div key={t.id} className={`toast ${t.kind}`}>{t.text}</div>)}</div>
    </div>
  )
}
