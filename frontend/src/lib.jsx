import { createContext, useContext, useEffect, useState, useCallback } from 'react'

// ---------------- API ----------------
const TOKEN_KEY = 'sd_token'
export const getToken = () => { try { return localStorage.getItem(TOKEN_KEY) } catch { return null } }
export const setToken = (t) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch {} }

export class ApiError extends Error {
  constructor(status, detail) {
    super(typeof detail === 'string' ? detail : detail?.message || 'Terjadi kesalahan')
    this.status = status; this.detail = detail
  }
}

export async function api(path, { method = 'GET', body, form, params } = {}) {
  let url = '/api' + path
  if (params) {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''))
    if ([...q].length) url += '?' + q
  }
  const headers = {}
  const t = getToken()
  if (t) headers.Authorization = 'Bearer ' + t
  let payload
  if (form) payload = form
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body) }
  const r = await fetch(url, { method, headers, body: payload })
  if (r.status === 401 && path !== '/auth/login') {
    setToken(null)
    if (!location.pathname.startsWith('/login')) location.href = '/login'
  }
  const ct = r.headers.get('content-type') || ''
  const data = ct.includes('json') ? await r.json().catch(() => ({})) : r
  if (!r.ok) {
    const fallback = r.status >= 500 ? `Server sedang bermasalah atau sedang restart (kode ${r.status}). Coba lagi 1 menit lagi.` : `Terjadi kesalahan (kode ${r.status}).`
    throw new ApiError(r.status, data?.detail ?? fallback)
  }
  return data
}

export async function download(path, params, filename) {
  const r = await api(path, { params })
  const blob = await r.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob); a.download = filename; a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}

// ---------------- auth + masters context ----------------
const Ctx = createContext(null)
export const useApp = () => useContext(Ctx)

export function AppProvider({ children }) {
  const [user, setUser] = useState(null)
  const [masters, setMasters] = useState(null)
  const [ready, setReady] = useState(false)
  const [toast, setToast] = useState(null)

  const loadMasters = useCallback(async () => { setMasters(await api('/masters')) }, [])
  useEffect(() => {
    (async () => {
      if (getToken()) {
        try { setUser(await api('/auth/me')); await loadMasters() } catch { setToken(null) }
      }
      setReady(true)
    })()
  }, [loadMasters])

  const notify = useCallback((msg, kind = 'ok', action) => {
    setToast({ msg, kind, action, id: Date.now() })
    setTimeout(() => setToast((t) => (t && Date.now() - t.id > 3500 ? null : t)), action ? 6000 : 3800)
  }, [])

  const login = async (name, pin) => {
    const r = await api('/auth/login', { method: 'POST', body: { name, pin } })
    setToken(r.token); setUser(r.user); await loadMasters()
  }
  const logout = async () => { try { await api('/auth/logout', { method: 'POST' }) } catch {} setToken(null); setUser(null) }
  const can = (...roles) => user && roles.includes(user.role)

  return <Ctx.Provider value={{ user, masters, loadMasters, ready, login, logout, can, notify, toast, setToast }}>{children}</Ctx.Provider>
}

export const WRITERS = ['Admin', 'CS Lead', 'CS Agent']
export const LEAD = ['Admin', 'CS Lead']

// ---------------- format ----------------
const WIB = 'Asia/Jakarta'
export const fmtDT = (s) => s ? new Date(s).toLocaleString('id-ID', { timeZone: WIB, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }).replace(/\./g, ':') : '–'
export const fmtD = (s) => s ? new Date(s.length === 10 ? s + 'T00:00:00+07:00' : s).toLocaleDateString('id-ID', { timeZone: WIB, day: '2-digit', month: 'short', year: 'numeric' }) : '–'
export const fmtNum = (n) => (n === null || n === undefined) ? '–' : Number(n).toLocaleString('id-ID', { maximumFractionDigits: 1 })
export const fmtRp = (n) => (n === null || n === undefined) ? '–' : 'Rp' + Number(n).toLocaleString('id-ID')
export const fmtPct = (n) => (n === null || n === undefined) ? '–' : Math.round(n * 100) + '%'
export const fmtMin = (m) => {
  if (m === null || m === undefined) return '–'
  if (m < 60) return `${Math.round(m)} mnt`
  if (m < 1440) return `${Math.floor(m / 60)} jam ${Math.round(m % 60)} mnt`
  return `${Math.floor(m / 1440)} hari ${Math.floor((m % 1440) / 60)} jam`
}
export const todayWIB = () => new Date(Date.now() + 7 * 3600e3).toISOString().slice(0, 10)
export const addDays = (iso, n) => { const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10) }
export const toLocalInput = (iso) => { const d = new Date(new Date(iso || Date.now()).getTime() + 7 * 3600e3); return d.toISOString().slice(0, 16) }
export const fromLocalInput = (v) => v ? v + ':00+07:00' : null

export function presets() {
  const t = todayWIB()
  const d = new Date(t + 'T00:00:00Z'); const dow = (d.getUTCDay() + 6) % 7
  const mon = addDays(t, -dow)
  const first = t.slice(0, 8) + '01'
  const lastMonthEnd = addDays(first, -1)
  return [
    { key: 'week', label: 'Minggu ini', from: mon, to: t },
    { key: 'lastweek', label: 'Minggu lalu', from: addDays(mon, -7), to: addDays(mon, -1) },
    { key: 'month', label: 'Bulan ini', from: first, to: t },
    { key: 'lastmonth', label: 'Bulan lalu', from: lastMonthEnd.slice(0, 8) + '01', to: lastMonthEnd },
    { key: '30', label: '30 hari', from: addDays(t, -29), to: t },
  ]
}

export function useAsync(fn, deps = []) {
  const [state, set] = useState({ loading: true, data: null, error: null })
  const run = useCallback(async () => {
    set((s) => ({ ...s, loading: true }))
    try { set({ loading: false, data: await fn(), error: null }) } catch (e) { set({ loading: false, data: null, error: e }) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { run() }, [run])
  return { ...state, reload: run, setData: (d) => set((s) => ({ ...s, data: typeof d === 'function' ? d(s.data) : d })) }
}

export async function compressImage(file, maxW = 1280, quality = 0.7) {
  const img = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = URL.createObjectURL(file) })
  const scale = Math.min(1, maxW / img.width)
  const c = document.createElement('canvas'); c.width = img.width * scale; c.height = img.height * scale
  c.getContext('2d').drawImage(img, 0, 0, c.width, c.height)
  let q = quality; let blob
  do { blob = await new Promise((r) => c.toBlob(r, 'image/jpeg', q)); q -= 0.1 } while (blob.size > 300_000 && q > 0.3)
  return blob
}
