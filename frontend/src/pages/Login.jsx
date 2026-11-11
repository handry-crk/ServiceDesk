import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useApp } from '../lib.jsx'
import { Btn, inputCls, ErrorBox } from '../ui.jsx'

export default function Login() {
  const { login } = useApp()
  const [name, setName] = useState(() => { try { return localStorage.getItem('sd_last_login') || '' } catch { return '' } })
  const [pin, setPin] = useState('')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null)
    try { await login(name.trim(), pin); try { localStorage.setItem('sd_last_login', name.trim()) } catch {} }
    catch (x) { setErr(x); setPin('') } finally { setBusy(false) }
  }
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        <form onSubmit={submit} className="bg-white rounded-3xl border border-line overflow-hidden">
          <div className="bg-brick text-white p-6">
            <img src="/icon.svg" className="w-12 h-12 rounded-xl ring-2 ring-white/40 mb-3" alt="" />
            <h1 className="text-2xl font-extrabold">CRK Service Desk</h1>
            <p className="text-sm opacity-90">Komplain & Service Excellence CRM/CS</p>
          </div>
          <div className="p-6 space-y-4">
            <label className="block"><span className="text-sm font-semibold">Email kantor</span>
              <input className={inputCls} type="text" inputMode="email" autoComplete="username" autoCapitalize="none" spellCheck={false}
                placeholder="nama@citarasakuliner.com" value={name} onChange={(e) => setName(e.target.value)} required />
              <span className="block text-xs text-mute mt-1">Admin lama tanpa email: isi nama pengguna.</span>
            </label>
            <label className="block"><span className="text-sm font-semibold">PIN (6 digit)</span>
              <input className={inputCls + ' tracking-[.5em] text-center text-xl'} inputMode="numeric" type="password" maxLength={6}
                value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))} required autoComplete="current-password" />
            </label>
            <ErrorBox error={err} />
            <Btn className="w-full" size="lg" disabled={busy || !name.trim() || pin.length !== 6}>{busy ? 'Memeriksa…' : 'Masuk'}</Btn>
          </div>
        </form>
        <p className="text-center text-sm mt-4">Belum punya akun? <Link to="/daftar" className="text-brick font-semibold underline">Daftar sebagai member baru</Link></p>
      </div>
    </div>
  )
}
