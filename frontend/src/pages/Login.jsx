import { useEffect, useState } from 'react'
import { api, useApp } from '../lib.jsx'
import { Btn, inputCls, ErrorBox } from '../ui.jsx'

export default function Login() {
  const { login } = useApp()
  const [names, setNames] = useState([])
  const [name, setName] = useState(() => { try { return localStorage.getItem('sd_last_name') || '' } catch { return '' } })
  const [pin, setPin] = useState('')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => { api('/auth/users').then(setNames).catch(() => {}) }, [])
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null)
    try { await login(name, pin); try { localStorage.setItem('sd_last_name', name) } catch {} }
    catch (x) { setErr(x); setPin('') } finally { setBusy(false) }
  }
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm bg-white rounded-3xl border border-line overflow-hidden">
        <div className="bg-brick text-white p-6">
          <img src="/icon.svg" className="w-12 h-12 rounded-xl ring-2 ring-white/40 mb-3" alt="" />
          <h1 className="text-2xl font-extrabold">CRK Service Desk</h1>
          <p className="text-sm opacity-90">Komplain & Service Excellence CRM/CS</p>
        </div>
        <div className="p-6 space-y-4">
          <label className="block"><span className="text-sm font-semibold">Nama</span>
            <select className={inputCls} value={name} onChange={(e) => setName(e.target.value)} required>
              <option value="">Pilih nama…</option>
              {names.map((n) => <option key={n}>{n}</option>)}
            </select>
          </label>
          <label className="block"><span className="text-sm font-semibold">PIN (6 digit)</span>
            <input className={inputCls + ' tracking-[.5em] text-center text-xl'} inputMode="numeric" type="password" maxLength={6}
              value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))} required autoComplete="current-password" />
          </label>
          <ErrorBox error={err} />
          <Btn className="w-full" size="lg" disabled={busy || !name || pin.length !== 6}>{busy ? 'Memeriksa…' : 'Masuk'}</Btn>
        </div>
      </form>
    </div>
  )
}
