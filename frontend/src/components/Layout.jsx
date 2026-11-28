import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { LayoutDashboard, Server, ShieldAlert, Activity, Lightbulb, RefreshCw, Zap } from 'lucide-react'
import SimulatePanel from './SimulatePanel.jsx'

const nav = [
  { to: '/', label: 'Overview', icon: LayoutDashboard },
  { to: '/resources', label: 'Resources', icon: Server },
  { to: '/security', label: 'Security', icon: ShieldAlert },
  { to: '/traffic', label: 'Traffic', icon: Activity },
  { to: '/recommendations', label: 'Recommendations', icon: Lightbulb },
]

const link = ({ isActive }) =>
  `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors ${
    isActive ? 'bg-raised text-text' : 'text-muted hover:bg-raised/60 hover:text-text'
  }`

export default function Layout() {
  const { pathname } = useLocation()
  const title = (nav.find((n) => n.to === pathname) || nav[0]).label
  const usingMock = (import.meta.env.VITE_USE_MOCK ?? 'true') !== 'false'

  const [refreshKey, setRefreshKey] = useState(0)
  const [simulateOpen, setSimulateOpen] = useState(false)

  return (
    <div className="min-h-screen md:flex">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-line bg-panel md:flex">
        <div className="px-5 py-5 text-lg font-semibold tracking-tight">AWSense</div>
        <nav className="flex flex-col gap-1 px-3" aria-label="Main">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === '/'} className={link}>
              <Icon size={18} aria-hidden /> {label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-panel/60 px-5 py-3 md:px-8">
          <div>
            <p className="text-base font-semibold">{title}</p>
            <p className="text-xs text-muted">Account 4821-0093-1175 · us-east-1 and eu-west-1</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-raised px-3 py-1 text-xs text-muted">
              {usingMock ? 'Sample data' : 'Live data'}
            </span>
            <button
              type="button"
              onClick={() => setRefreshKey((k) => k + 1)}
              className="flex items-center gap-2 rounded-md border border-line bg-ink px-3 py-1.5 text-xs font-medium text-text hover:bg-raised transition-colors"
            >
              <RefreshCw size={14} aria-hidden /> Refresh
            </button>
            <button
              type="button"
              onClick={() => setSimulateOpen(true)}
              className="flex items-center gap-2 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-ink hover:bg-accent/90 transition-colors"
            >
              <Zap size={14} aria-hidden /> Simulate Incident
            </button>
          </div>
        </header>

        <nav className="flex gap-1 overflow-x-auto border-b border-line px-3 py-2 md:hidden" aria-label="Main">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === '/'} className={link}>
              <Icon size={16} aria-hidden /> {label}
            </NavLink>
          ))}
        </nav>

        <main key={refreshKey} className="flex-1 px-5 py-6 md:px-8">
          <Outlet />
        </main>
      </div>

      <SimulatePanel
        open={simulateOpen}
        onClose={() => setSimulateOpen(false)}
        onSimulated={() => setRefreshKey((k) => k + 1)}
      />
    </div>
  )
}
