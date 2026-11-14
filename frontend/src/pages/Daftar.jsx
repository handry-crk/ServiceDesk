import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../lib.jsx'
import { Btn, Field, inputCls, ErrorBox } from '../ui.jsx'

const DESC = {
  'CS Lead': 'Memantau case, membereskan data, memimpin meeting Service Excellence, mengelola pengaturan.',
  'Marketing TL': 'Melihat dashboard & case, menyusun insight dan action di meeting.',
  'CS Agent': 'Mencatat dan menangani komplain customer setiap hari.',
}
const STATUS = {
  verify: ['Cek email Anda', 'Masukkan kode 6 digit yang dikirim ke email kantor.'],
  pending: ['Menunggu persetujuan Admin', 'Pendaftaran sudah diterima. Anda bisa login setelah Admin menyetujui.'],
  approved: ['Akun sudah aktif', 'Silakan login dengan email kantor dan PIN yang Anda buat.'],
  rejected: ['Pendaftaran ditolak', 'Hubungi Admin atau CRM Supervisor bila ada pertanyaan.'],
  replaced: ['Pendaftaran diganti', 'Ada pendaftaran yang lebih baru dengan email yang sama.'],
}

const Wrap = ({ children }) => (
  <div className="min-h-screen bg-cream flex justify-center p-4">
    <div className="w-full max-w-md">
      <div className="bg-brick text-white rounded-3xl p-5 mb-4 flex items-center gap-3">
        <img src="/icon.svg" className="w-11 h-11 rounded-xl ring-2 ring-white/40" alt="" />
        <div><div className="text-xl font-extrabold">Daftar member baru</div><div className="text-sm opacity-90">CRK Service Desk</div></div>
      </div>
      {children}
      <p className="text-center text-sm mt-4"><Link to="/login" className="text-brick underline">Kembali ke halaman login</Link></p>
    </div>
  </div>
)

export default function Daftar() {
  const { rid } = useParams()
  const nav = useNavigate()
  const [info, setInfo] = useState(null)
  const [f, setF] = useState({ name: '', email: '', role: '', pin: '', pin2: '', phone: '', desk: '' })
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)
  const [st, setSt] = useState(null)
  const [code, setCode] = useState('')

  useEffect(() => { api('/public/register/info').then(setInfo).catch(setErr) }, [])
  useEffect(() => { if (rid) api('/public/register/' + rid).then(setSt).catch(setErr) }, [rid])

  const domain = info?.domain || 'citarasakuliner.com'
  const emailOk = f.email.trim().toLowerCase().endsWith('@' + domain)
  const ok = f.name.trim().length >= 3 && emailOk && f.role && f.pin.length === 6 && f.pin === f.pin2 && (f.role !== 'CS Agent' || f.desk)

  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr(null)
    try {
      const r = await api('/public/register', { method: 'POST', body: { name: f.name, email: f.email, role: f.role, pin: f.pin, phone: f.phone, desk: f.role === 'CS Agent' ? f.desk : null } })
      nav('/daftar/' + r.id, { replace: true })
    } catch (x) { setErr(x) } finally { setBusy(false) }
  }
  const verify = async () => {
    setBusy(true); setErr(null)
    try { await api(`/public/register/${rid}/verify`, { method: 'POST', body: { code } }); setSt(await api('/public/register/' + rid)) }
    catch (x) { setErr(x) } finally { setBusy(false) }
  }

  if (rid) {
    const [t, d] = STATUS[st?.status] || ['Memuat…', '']
    return (
      <Wrap>
        <div className="bg-white rounded-3xl p-6 space-y-4">
          <div className="text-xl font-bold">{t}</div>
          <p className="text-mute">{d}</p>
          {st && <div className="text-sm bg-cream rounded-xl p-3">{st.email} · {st.role}{st.reason ? ` · Alasan: ${st.reason}` : ''}</div>}
          {st?.status === 'verify' && <>
            <input className={inputCls + ' tracking-[.5em] text-center text-xl'} inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} placeholder="••••••" />
            <Btn className="w-full" disabled={code.length !== 6 || busy} onClick={verify}>Verifikasi</Btn>
          </>}
          {st?.status === 'pending' && <p className="text-sm text-mute">Simpan halaman ini untuk mengecek status: <span className="break-all">{location.href}</span></p>}
          {st?.status === 'approved' && <Link to="/login"><Btn className="w-full">Ke halaman login</Btn></Link>}
          <ErrorBox error={err} />
        </div>
      </Wrap>
    )
  }

  return (
    <Wrap>
      <form onSubmit={submit} className="bg-white rounded-3xl p-5 space-y-4">
        <p className="text-sm text-mute">Khusus karyawan dengan email <b>@{domain}</b>. Akun aktif setelah disetujui Admin.</p>
        <Field label="Nama lengkap" required><input className={inputCls} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} autoComplete="name" /></Field>
        <Field label="Email kantor" required hint={f.email && !emailOk ? `Harus berakhiran @${domain}` : null}>
          <input className={inputCls} type="email" autoCapitalize="none" autoComplete="email" placeholder={`nama@${domain}`} value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        </Field>
        <Field label="Peran" required>
          <div className="space-y-2">
            {(info?.roles || []).map((r) => {
              const full = r.available <= 0
              return (
                <button type="button" key={r.role} disabled={full} onClick={() => setF({ ...f, role: r.role })}
                  className={`w-full text-left rounded-xl border px-3 py-2.5 ${f.role === r.role ? 'border-brick bg-brick-soft' : 'border-line'} ${full ? 'opacity-50 cursor-not-allowed' : ''}`}>
                  <div className="flex justify-between items-center"><span className="font-semibold">{r.label}</span>
                    <span className={`text-xs font-bold px-2 py-0.5 rounded ${full ? 'bg-[#E9E5DF] text-mute' : 'bg-[#DCEBDD] text-ok'}`}>{full ? 'Kuota penuh' : `Sisa ${r.available} dari ${r.slots}`}</span></div>
                  <div className="text-xs text-mute mt-0.5">{DESC[r.role]}</div>
                </button>
              )
            })}
          </div>
        </Field>
        {f.role === 'CS Agent' && <Field label="Desk CS" required>
          <div className="grid grid-cols-2 gap-2">{[['Online', 'CS Online / Marketplace', 'Marketplace frozen, GoFood/GrabFood/ShopeeFood'], ['Offline', 'CS Offline', 'Komplain outlet & gerobak']].map(([k, l, d]) => (
            <button type="button" key={k} onClick={() => setF({ ...f, desk: k })} className={`text-left rounded-xl border px-3 py-2.5 ${f.desk === k ? 'border-brick bg-brick-soft' : 'border-line'}`}>
              <div className="font-semibold text-sm">{l}</div><div className="text-xs text-mute">{d}</div></button>))}</div>
        </Field>}
        <Field label="No. HP (opsional)"><input className={inputCls} inputMode="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Buat PIN (6 digit)" required><input className={inputCls + ' tracking-[.3em] text-center'} type="password" inputMode="numeric" maxLength={6} autoComplete="new-password" value={f.pin} onChange={(e) => setF({ ...f, pin: e.target.value.replace(/\D/g, '') })} /></Field>
          <Field label="Ulangi PIN" required hint={f.pin2 && f.pin !== f.pin2 ? 'PIN tidak sama' : null}><input className={inputCls + ' tracking-[.3em] text-center'} type="password" inputMode="numeric" maxLength={6} autoComplete="new-password" value={f.pin2} onChange={(e) => setF({ ...f, pin2: e.target.value.replace(/\D/g, '') })} /></Field>
        </div>
        <p className="text-xs text-mute">Hindari PIN mudah ditebak seperti 123456 atau 111111. PIN dipakai untuk login bersama email kantor.</p>
        <ErrorBox error={err} />
        <Btn className="w-full" size="lg" disabled={!ok || busy}>{busy ? 'Mengirim…' : 'Daftar'}</Btn>
      </form>
    </Wrap>
  )
}
