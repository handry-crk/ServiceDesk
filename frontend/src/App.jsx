import { lazy, Suspense, useEffect, useState } from 'react'
import { Routes, Route, NavLink, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useApp, api, fmtDT } from './lib.jsx'
import { Skeleton } from './ui.jsx'
import Login from './pages/Login.jsx'
import Inbox from './pages/Inbox.jsx'
import Catat from './pages/Catat.jsx'
import Cases from './pages/Cases.jsx'
import CaseDetail from './pages/CaseDetail.jsx'
import { SurveiOutlet, SurveiCase } from './pages/Public.jsx'

const Dashboard = lazy(() => import('./pages/Dashboard.jsx'))
const Meetings = lazy(() => import('./pages/Meetings.jsx'))
const MeetingView = lazy(() => import('./pages/MeetingView.jsx'))
const Lainnya = lazy(() => import('./pages/Lainnya.jsx'))
const Csat = lazy(() => import('./pages/Csat.jsx'))
const Reviews = lazy(() => import('./pages/Reviews.jsx'))
const Vouchers = lazy(() => import('./pages/Vouchers.jsx'))
const Settings = lazy(() => import('./pages/Settings.jsx'))

const NAV = [
  { to: '/', label: 'Inbox', icon: 'M4 4h16v12H5.2L4 17.2V4zm2 7h4l1 2h2l1-2h4', end: true },
  { to: '/case', label: 'Case', icon: 'M4 6h16M4 12h16M4 18h10' },
  { to: '/catat', label: 'Catat', icon: 'M12 5v14M5 12h14', primary: true },
  { to: '/dashboard', label: 'Dashboard', icon: 'M4 20V10M10 20V4M16 20v-7M22 20H2' },
  { to: '/meeting', label: 'Meeting', icon: 'M3 5h18v11H3zM8 21h8M12 16v5' },
  { to: '/lainnya', label: 'Lainnya', icon: 'M5 12h.01M12 12h.01M19 12h.01' },
]

const Icon = ({ d, className = 'w-6 h-6' }) => (
  <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
)

function Bell() {
  const [open, setOpen] = useState(false)
  const [rows, setRows] = useState([])
  const { user } = useApp()
  useEffect(() => {
    const load = () => api('/notifications').then(setRows).catch(() => {})
    load(); const t = setInterval(load, 60000); return () => clearInterval(t)
  }, [])
  const unread = rows.filter((n) => !(n.readBy || []).includes(user?.id)).length
  return (
    <div className="relative">
      <button className="relative w-10 h-10 rounded-full hover:bg-white/15 flex items-center justify-center" aria-label="Notifikasi"
        onClick={() => { setOpen(!open); if (!open && unread) api('/notifications/read', { method: 'POST' }).then(() => setRows((r) => r.map((n) => ({ ...n, readBy: [...(n.readBy || []), user.id] })))) }}>
        <Icon d="M6 8a6 6 0 1112 0c0 7 3 9 3 9H3s3-2 3-9M10 21h4" className="w-5 h-5" />
        {unread > 0 && <span className="absolute top-1 right-1 min-w-[18px] h-[18px] rounded-full bg-white text-brick text-[11px] font-bold flex items-center justify-center">{unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-80 max-h-96 overflow-y-auto bg-white text-ink rounded-2xl shadow-xl border border-line z-50 p-2">
          {rows.length === 0 && <div className="p-4 text-sm text-mute">Belum ada notifikasi.</div>}
          {rows.map((n, i) => (
            <a key={i} href={n.caseId ? `/case/${n.caseId}` : undefined} className="block p-3 rounded-xl hover:bg-cream">
              <div className={`text-sm ${n.kind === 'critical' ? 'text-brick font-semibold' : ''}`}>{n.text}</div>
              <div className="text-xs text-mute mt-1">{fmtDT(n.at)}</div>
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

function Shell({ children }) {
  const { user, logout, toast, setToast } = useApp()
  const nav = useNavigate()
  const loc = useLocation()
  const fullscreen = /^\/meeting\/[^/]+/.test(loc.pathname)
  return (
    <div className="min-h-screen md:flex">
      <aside className={`${fullscreen ? 'hidden' : 'hidden md:flex'} no-print flex-col w-60 shrink-0 bg-white border-r border-line sticky top-0 h-screen p-4`}>
        <div className="flex items-center gap-3 mb-8 px-2">
          <img src="/icon.svg" className="w-10 h-10" alt="" />
          <div><div className="font-extrabold leading-tight">Service Desk</div><div className="text-xs text-mute">CRK Group · CRM/CS</div></div>
        </div>
        <nav className="space-y-1 flex-1">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => `flex items-center gap-3 px-3 py-2.5 rounded-xl font-semibold ${isActive ? 'bg-brick text-white' : n.primary ? 'text-brick hover:bg-brick-soft' : 'hover:bg-cream'}`}>
              <Icon d={n.icon} className="w-5 h-5" />{n.label === 'Catat' ? 'Catat Komplain' : n.label}
            </NavLink>
          ))}
        </nav>
        <div className="text-sm border-t border-line pt-3 px-2">
          <div className="font-semibold">{user?.name}</div><div className="text-xs text-mute">{user?.role}</div>
          <button className="text-xs text-brick mt-2" onClick={async () => { await logout(); nav('/login') }}>Keluar</button>
        </div>
      </aside>
      <div className="flex-1 min-w-0 pb-24 md:pb-6">
        {!fullscreen && (
          <header className="no-print sticky top-0 z-30 bg-brick text-white">
            <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
              <div className="flex items-center gap-2 md:hidden"><img src="/icon.svg" className="w-8 h-8 rounded-lg ring-1 ring-white/40" alt="" /><span className="font-bold">Service Desk</span></div>
              <div className="hidden md:block text-sm opacity-90">Klasifikasi & kompensasi mengikuti CRM.STD.001 Rev. 00</div>
              <div className="flex items-center gap-1"><Bell />
                <button className="md:hidden text-xs px-2 py-1 rounded-lg hover:bg-white/15" onClick={async () => { await logout(); nav('/login') }}>{user?.name} · Keluar</button>
              </div>
            </div>
          </header>
        )}
        <main className={fullscreen ? '' : 'max-w-6xl mx-auto px-4 py-4'}>{children}</main>
      </div>
      <nav className={`${fullscreen ? 'hidden' : 'md:hidden'} no-print fixed bottom-0 inset-x-0 z-40 bg-white border-t border-line grid grid-cols-6 pb-[env(safe-area-inset-bottom)]`}>
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} className={({ isActive }) => `flex flex-col items-center justify-center py-2 text-[11px] font-semibold ${isActive ? 'text-brick' : 'text-mute'}`}>
            {n.primary ? <span className="w-11 h-11 -mt-5 rounded-full bg-brick text-white flex items-center justify-center shadow-lg"><Icon d={n.icon} /></span> : <Icon d={n.icon} />}
            <span>{n.label}</span>
          </NavLink>
        ))}
      </nav>
      {toast && (
        <div className="fixed z-[60] left-1/2 -translate-x-1/2 bottom-24 md:bottom-6 w-[92%] max-w-md">
          <div className={`rounded-2xl shadow-xl px-4 py-3 text-white flex items-center gap-3 ${toast.kind === 'err' ? 'bg-brick' : 'bg-ink'}`}>
            <div className="flex-1 text-sm">{toast.msg}</div>
            {toast.action && <button className="text-sm font-bold underline" onClick={() => { toast.action.fn(); setToast(null) }}>{toast.action.label}</button>}
            <button onClick={() => setToast(null)} className="opacity-70">×</button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function App() {
  const { user, ready } = useApp()
  const loc = useLocation()
  if (loc.pathname.startsWith('/survei')) {
    return (
      <Routes>
        <Route path="/survei-outlet" element={<SurveiOutlet />} />
        <Route path="/survei-outlet/:outletId" element={<SurveiOutlet />} />
        <Route path="/survei/:token" element={<SurveiCase />} />
      </Routes>
    )
  }
  if (!ready) return <div className="p-6"><Skeleton /></div>
  if (!user) return <Routes><Route path="*" element={<Login />} /></Routes>
  return (
    <Shell>
      <Suspense fallback={<Skeleton h="h-64" />}>
        <Routes>
          <Route path="/" element={<Inbox />} />
          <Route path="/catat" element={<Catat />} />
          <Route path="/case" element={<Cases />} />
          <Route path="/case/:id" element={<CaseDetail />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/meeting" element={<Meetings />} />
          <Route path="/meeting/:id" element={<MeetingView />} />
          <Route path="/lainnya" element={<Lainnya />} />
          <Route path="/csat" element={<Csat />} />
          <Route path="/review" element={<Reviews />} />
          <Route path="/voucher" element={<Vouchers />} />
          <Route path="/pengaturan" element={<Settings />} />
          <Route path="/login" element={<Navigate to="/" />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </Suspense>
    </Shell>
  )
}
