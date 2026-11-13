import { useEffect, useState } from 'react'
import { fmtPct, presets } from './lib.jsx'

export const Card = ({ className = '', children, ...p }) => (
  <div className={`bg-white rounded-2xl border border-line ${className}`} {...p}>{children}</div>
)

export const Btn = ({ kind = 'primary', className = '', size = 'md', ...p }) => {
  const k = {
    primary: 'bg-brick text-white hover:bg-brick-dark disabled:opacity-50',
    ghost: 'bg-white border border-line text-ink hover:bg-cream disabled:opacity-50',
    ok: 'bg-ok text-white hover:opacity-90 disabled:opacity-50',
    soft: 'bg-brick-soft text-brick hover:bg-[#efc9c3] disabled:opacity-50',
    link: 'text-brick underline-offset-2 hover:underline px-1',
  }[kind]
  const s = size === 'sm' ? 'min-h-[36px] px-3 text-sm' : size === 'lg' ? 'min-h-[52px] px-5 text-base' : 'min-h-[44px] px-4'
  return <button className={`${k} ${kind !== 'link' ? s : ''} rounded-xl font-semibold transition active:scale-[.98] ${className}`} {...p} />
}

const LV = { Minor: 'bg-[#E9E5DF] text-[#5E574F]', Major: 'bg-[#F6E6C6] text-[#7A5410]', Critical: 'bg-brick text-white' }
export const LevelBadge = ({ level }) => (
  <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-bold ${LV[level] || 'bg-[#EDE7F6] text-[#4A3B7A]'}`}>{level || 'Belum Diatur'}</span>
)

const ST = { Open: 'bg-brick-soft text-brick', Responded: 'bg-[#F6E6C6] text-[#7A5410]', Resolved: 'bg-[#DCEBDD] text-ok', Closed: 'bg-[#E9E5DF] text-[#5E574F]' }
export const StatusBadge = ({ status }) => <span className={`px-2 py-0.5 rounded-md text-xs font-semibold ${ST[status] || ''}`}>{status}</span>

export const Chip = ({ active, className = '', ...p }) => (
  <button type="button" className={`min-h-[40px] px-3 rounded-full border text-sm font-medium transition ${active ? 'bg-brick text-white border-brick' : 'bg-white border-line hover:border-brick'} ${className}`} {...p} />
)

export const Field = ({ label, hint, children, required }) => (
  <label className="block">
    <span className="block text-sm font-semibold mb-1">{label}{required && <span className="text-brick"> *</span>}</span>
    {children}
    {hint && <span className="block text-xs text-mute mt-1">{hint}</span>}
  </label>
)

export const inputCls = 'w-full min-h-[44px] rounded-xl border border-line bg-white px-3 text-base focus:outline-none focus:ring-2 focus:ring-brick/40'

export function Sheet({ open, onClose, title, children, wide }) {
  useEffect(() => {
    if (!open) return
    const h = (e) => e.key === 'Escape' && onClose?.()
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/40" onClick={onClose}>
      <div className={`bg-white w-full ${wide ? 'sm:max-w-3xl' : 'sm:max-w-lg'} rounded-t-3xl sm:rounded-3xl max-h-[92vh] overflow-y-auto p-5 pb-8`} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold">{title}</h3>
          <button onClick={onClose} className="w-10 h-10 rounded-full hover:bg-cream text-xl" aria-label="Tutup">×</button>
        </div>
        {children}
      </div>
    </div>
  )
}

export const Info = ({ text }) => (
  <span className="relative group inline-flex align-middle ml-1">
    <span className="w-4 h-4 rounded-full border border-mute text-mute text-[10px] flex items-center justify-center cursor-help">i</span>
    <span className="pointer-events-none absolute left-1/2 -translate-x-1/2 bottom-6 w-56 max-w-[70vw] rounded-lg bg-ink text-white text-xs p-2 hidden group-hover:block z-20 font-normal">{text}</span>
  </span>
)

export const Skeleton = ({ h = 'h-24', className = '' }) => <div className={`animate-pulse bg-white/70 rounded-2xl ${h} ${className}`} />

export const Empty = ({ children }) => <div className="text-center text-mute py-10 text-sm">{children}</div>

export const ErrorBox = ({ error }) => error ? <div className="bg-brick-soft text-brick rounded-xl p-3 text-sm">{error.message || String(error)}</div> : null

export function StatusPill({ status }) {
  if (status === 'On Track') return <span className="px-2 py-0.5 rounded-md text-xs font-bold bg-[#DCEBDD] text-ok">On Track</span>
  if (status === 'Below Target') return <span className="px-2 py-0.5 rounded-md text-xs font-bold bg-brick-soft text-brick">Below Target</span>
  return <span className="text-mute text-xs">–</span>
}

export function PeriodPicker({ value, onChange }) {
  const ps = presets()
  const [custom, setCustom] = useState(false)
  const active = ps.find((p) => p.from === value.from && p.to === value.to)?.key
  return (
    <div className="flex flex-wrap items-center gap-2">
      {ps.map((p) => <Chip key={p.key} active={active === p.key} onClick={() => { setCustom(false); onChange({ from: p.from, to: p.to }) }}>{p.label}</Chip>)}
      <Chip active={!active || custom} onClick={() => setCustom(true)}>Custom</Chip>
      {(custom || !active) && (
        <span className="flex items-center gap-1">
          <input type="date" className={inputCls + ' !min-h-[40px] w-auto'} value={value.from} onChange={(e) => onChange({ ...value, from: e.target.value })} />
          <span>–</span>
          <input type="date" className={inputCls + ' !min-h-[40px] w-auto'} value={value.to} onChange={(e) => onChange({ ...value, to: e.target.value })} />
        </span>
      )}
    </div>
  )
}

export function Delta({ cur, prev, dir, isPct }) {
  if (cur === null || cur === undefined || prev === null || prev === undefined) return null
  const d = cur - prev
  if (Math.abs(d) < 1e-9) return <span className="text-xs text-mute">sama dgn periode lalu</span>
  const better = dir === 'max' ? d < 0 : d > 0
  const txt = isPct ? `${d > 0 ? '+' : ''}${Math.round(d * 100)} pt` : `${d > 0 ? '+' : ''}${Math.round(d).toLocaleString('id-ID')} mnt`
  return <span className={`text-xs font-semibold ${better ? 'text-ok' : 'text-brick'}`}>{d > 0 ? '▲' : '▼'} {txt} vs periode lalu</span>
}

export const pctOrNum = (key, v) => ['frt', 'avgResolution'].includes(key) ? (v === null || v === undefined ? '–' : `${Math.round(v * 10) / 10} mnt`) : fmtPct(v)

export const CARA_HITUNG = {
  frt: 'Waktu masuk → waktu dibalas, hanya menit di jam operasional CS pada hari kerja (hari libur seperti Minggu & tanggal libur tidak dihitung). Waktu tunggu customer menurut jam kalender ditampilkan terpisah. Case tanpa jam masuk tidak dihitung.',
  slaResponse: 'Case dengan FRT jam kerja ≤ target channel (Critical: maks 30 menit) ÷ case yang sudah direspons. Channel CSAT Form & Review Online tidak dihitung.',
  avgResolution: 'Rata-rata (Waktu Resolved − Waktu Masuk) untuk case yang sudah resolved, tanpa menghitung hari libur CS.',
  resolutionSla: 'Case resolved dalam target level (Minor 1 hari, Major 2 hari, Critical 3 hari; hari libur CS tidak dihitung) ÷ case resolved.',
  sameDay: 'Resolved di tanggal yang sama (komplain yang masuk di hari libur / di luar jam operasional dihitung dari hari kerja berikutnya) ÷ komplain yang tanggal selesainya diketahui, termasuk yang masih open setelah harinya lewat.',
  fcr: 'Case resolved tanpa customer follow-up ulang ÷ case yang kolom Follow-up Ulang-nya diisi.',
  compSuccess: 'Komplain valid yang mendapat kompensasi (selain Tidak Ada) ÷ komplain valid.',
  reopen: 'Case yang pernah dibuka ulang ÷ case Closed.',
  csat: 'Rating 4–5 dari survei per case (customer yang komplain) ÷ total rating. Survei dikirim CS setelah case Closed.',
  per1000: 'Total komplain ÷ total transaksi periode × 1.000. Transaksi diisi per bulan di Pengaturan, diprorata per hari.',
}
