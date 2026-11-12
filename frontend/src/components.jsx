import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { fmtDT, fmtMin, api, useApp, compressImage } from './lib.jsx'
import { LevelBadge, StatusBadge, inputCls, Btn } from './ui.jsx'

export function useNow(ms = 30000) {
  const [n, setN] = useState(Date.now())
  useEffect(() => { const t = setInterval(() => setN(Date.now()), ms); return () => clearInterval(t) }, [ms])
  return n
}

export function SlaChip({ c, now }) {
  const age = (now - new Date(c.waktuMasuk).getTime()) / 60000
  if (c.status === 'Open') {
    const over = age > (c.targetFrtMin || 5)
    return <span className={`text-xs font-semibold px-2 py-0.5 rounded-md ${over ? 'bg-brick text-white' : 'bg-[#F6E6C6] text-[#7A5410]'}`}>
      {over ? 'Lewat target balas · ' : ''}{fmtMin(age)} sejak masuk
    </span>
  }
  if (c.status === 'Responded' && c.targetResolutionMin) {
    const left = c.targetResolutionMin - age
    return <span className={`text-xs font-semibold px-2 py-0.5 rounded-md ${left < 0 ? 'bg-brick text-white' : left < 240 ? 'bg-[#F6E6C6] text-[#7A5410]' : 'bg-[#E9E5DF]'}`}>
      {left < 0 ? `Lewat SLA ${fmtMin(-left)}` : `Sisa ${fmtMin(left)}`}
    </span>
  }
  return null
}

export function CaseCard({ c, now, action }) {
  return (
    <div className={`bg-white rounded-2xl border p-4 ${c.level === 'Critical' ? 'border-brick border-l-4' : 'border-line'}`}>
      <Link to={`/case/${c.caseId}`} className="block">
        <div className="flex flex-wrap items-center gap-2 mb-1">
          <span className="font-bold">{c.caseId}</span><LevelBadge level={c.level} /><StatusBadge status={c.status} />
          <SlaChip c={c} now={now} />
          {!c.dataOk && <span className="text-xs text-warn font-semibold">⚠ Cek data</span>}
        </div>
        <div className="text-sm font-semibold">{c.subJenis} · {c.outletName}</div>
        <div className="text-sm text-mute line-clamp-2">{c.ringkasan}</div>
        <div className="text-xs text-mute mt-1">{c.channel} · {fmtDT(c.waktuMasuk)} · PJ {c.penanggungJawab}</div>
      </Link>
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

/** Combobox dengan pencarian fuzzy sederhana. items: [{value,label,sub,badge,keywords}] */
export function Combo({ items, value, onChange, placeholder, recent = [], renderBadge }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const ref = useRef()
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h)
  }, [])
  const sel = items.find((i) => i.value === value)
  const list = useMemo(() => {
    const t = q.trim().toLowerCase()
    if (!t) {
      const rec = recent.map((r) => items.find((i) => i.value === r)).filter(Boolean)
      return [...rec.map((r) => ({ ...r, recent: true })), ...items.filter((i) => !recent.includes(i.value))]
    }
    const words = t.split(/\s+/)
    return items
      .map((i) => {
        const hay = (i.label + ' ' + (i.keywords || '') + ' ' + (i.sub || '')).toLowerCase()
        const score = words.reduce((s, w) => s + (i.label.toLowerCase().includes(w) ? 3 : hay.includes(w) ? 1 : -100), 0)
        return { ...i, score }
      })
      .filter((i) => i.score > 0).sort((a, b) => b.score - a.score)
  }, [q, items, recent])
  return (
    <div className="relative" ref={ref}>
      <input className={inputCls} placeholder={sel ? sel.label : placeholder} value={open ? q : sel ? sel.label : ''}
        onFocus={() => { setOpen(true); setQ('') }} onChange={(e) => { setQ(e.target.value); setOpen(true) }} />
      {open && (
        <div className="absolute z-30 mt-1 w-full max-h-72 overflow-y-auto bg-white border border-line rounded-xl shadow-lg">
          {list.length === 0 && <div className="p-3 text-sm text-mute">Tidak ketemu. Coba kata lain.</div>}
          {list.slice(0, 60).map((i) => (
            <button type="button" key={i.value} className={`w-full text-left px-3 py-2.5 hover:bg-cream border-b border-line/50 last:border-0 ${i.value === value ? 'bg-brick-soft' : ''}`}
              onClick={() => { onChange(i.value); setOpen(false); setQ('') }}>
              <div className="flex items-center gap-2"><span className="font-medium">{i.label}</span>{renderBadge?.(i)}{i.recent && <span className="text-[10px] text-mute">terakhir</span>}</div>
              {i.sub && <div className="text-xs text-mute">{i.sub}</div>}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export const levelItemBadge = (i) => i.level ? <LevelBadge level={i.level} /> : null

export function PhotoPick({ value, onChange, label = 'Upload screenshot' }) {
  const { notify } = useApp()
  const ref = useRef()
  const [busy, setBusy] = useState(false)
  const pick = async (f) => {
    if (!f) return
    setBusy(true)
    try {
      const blob = await compressImage(f)
      const fd = new FormData(); fd.append('file', blob, 'bukti.jpg')
      const r = await api('/uploads', { method: 'POST', form: fd })
      onChange(r.url)
    } catch (e) { notify(e.message, 'err') } finally { setBusy(false) }
  }
  return (
    <div className="flex items-center gap-3">
      {value && <a href={value} target="_blank" rel="noreferrer"><img src={value} className="w-16 h-16 object-cover rounded-lg border border-line" alt="bukti" /></a>}
      <Btn kind="ghost" size="sm" type="button" disabled={busy} onClick={() => ref.current.click()}>{busy ? 'Mengunggah…' : value ? 'Ganti screenshot' : label}</Btn>
      <input ref={ref} type="file" accept="image/*" hidden onChange={(e) => pick(e.target.files[0])} />
    </div>
  )
}
