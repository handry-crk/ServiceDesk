import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { fmtDT, fmtMin, fmtD, api, useApp, compressImage } from './lib.jsx'
import { LevelBadge, StatusBadge, inputCls, Btn } from './ui.jsx'

export function useNow(ms = 30000) {
  const [n, setN] = useState(Date.now())
  useEffect(() => { const t = setInterval(() => setN(Date.now()), ms); return () => clearInterval(t) }, [ms])
  return n
}

export function SlaChip({ c, now }) {
  const age = (now - new Date(c.waktuMasuk).getTime()) / 60000
  const cls = (bad, warn) => `text-xs font-semibold px-2 py-0.5 rounded-md ${bad ? 'bg-brick text-white' : warn ? 'bg-[#F6E6C6] text-[#7A5410]' : 'bg-[#E9E5DF]'}`
  if (c.status === 'Open') {
    const due = c.frtDueAt ? new Date(c.frtDueAt).getTime() : new Date(c.waktuMasuk).getTime() + (c.targetFrtMin || 5) * 6e4
    const over = now > due
    const closed = !over && due - now > (c.targetFrtMin || 5) * 6e4 + 6e4
    return <span className={cls(over, true)}>
      {over ? `Lewat target balas · ${fmtMin(age)} sejak masuk` : closed ? `CS libur/tutup · target balas ${fmtDT(c.frtDueAt)}` : `${fmtMin(age)} sejak masuk`}
    </span>
  }
  if (c.status === 'Responded' && c.targetResolutionMin) {
    const left = c.resolutionDueAt ? (new Date(c.resolutionDueAt).getTime() - now) / 6e4 : c.targetResolutionMin - age
    return <span className={cls(left < 0, left < 240)}>{left < 0 ? `Lewat SLA ${fmtMin(-left)}` : `Sisa ${fmtMin(left)}`}</span>
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
          {c.desk && <span className="text-[11px] px-1.5 py-0.5 rounded-md bg-cream text-mute font-semibold">{c.desk === 'Online' ? 'Online' : 'Offline'}</span>}
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

export function KodeLookup({ onDone }) {
  const { notify, masters } = useApp()
  const [kode, setKode] = useState('')
  const [v, setV] = useState(null)
  const [err, setErr] = useState(null)
  const [outlet, setOutlet] = useState('')
  const cek = async () => {
    setErr(null); setV(null)
    try { const r = await api('/vouchers/lookup/' + encodeURIComponent(kode.trim().toUpperCase())); setV(r); setOutlet(r.case?.outletName || '') }
    catch (e) { setErr(e.message) }
  }
  const pakai = async () => {
    try { await api(`/vouchers/${v.kode}/status`, { method: 'POST', body: { status: 'Terpakai', outlet } }); notify(`${v.kode} ditandai terpakai / diterima`); setV(null); setKode(''); onDone?.() }
    catch (e) { notify(e.message, 'err') }
  }
  const expired = v?.kadaluarsa && v.kadaluarsa < new Date(Date.now() + 7 * 3600e3).toISOString().slice(0, 10)
  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <input className={inputCls + ' font-mono uppercase'} value={kode} onChange={(e) => setKode(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && kode.trim() && cek()} placeholder="Ketik kode, mis. CMP-RP-2611-0007" />
        <Btn onClick={cek} disabled={!kode.trim()}>Cek</Btn>
      </div>
      {err && <div className="text-sm text-brick">{err}</div>}
      {v && <div className="rounded-xl border border-line p-3 text-sm space-y-1">
        <div className="flex flex-wrap items-center gap-2"><span className="font-mono font-bold text-base">{v.kode}</span>
          <span className={`text-xs px-2 py-0.5 rounded-md font-semibold ${v.status === 'Diterbitkan' ? 'bg-[#FBF1DC] text-[#7A5410]' : v.status === 'Terpakai' ? 'bg-[#E3F1E6] text-[#1F6B3A]' : 'bg-[#F3E1DF] text-brick'}`}>{v.status === 'Diterbitkan' ? 'Belum dipakai' : v.status}</span></div>
        <div><b>{v.label || v.jenis}</b>{v.nilai ? ` · Rp${Number(v.nilai).toLocaleString('id-ID')}` : ''}</div>
        {v.case && <div className="text-mute">Case <Link className="underline" to={'/case/' + v.case.caseId}>{v.case.caseId}</Link> · {v.case.outletName} · {v.case.subJenis}{v.case.customerName ? ` · ${v.case.customerName}` : ''}</div>}
        <div className="text-mute">Diterbitkan {fmtDT(v.tanggalDiterbitkan)} · {v.kadaluarsa ? <span className={expired ? 'text-brick font-semibold' : ''}>berlaku s/d {fmtD(v.kadaluarsa)}{expired ? ' (sudah lewat)' : ''}</span> : 'tanpa batas waktu'}</div>
        {v.status === 'Terpakai' && <div>Dipakai {fmtDT(v.tanggalDipakai)}{v.outletPemakaian ? ` di ${v.outletPemakaian}` : ''}{v.dipakaiOleh ? ` · dicatat ${v.dipakaiOleh}` : ''}</div>}
        {v.status === 'Diterbitkan' && !expired && <div className="flex flex-wrap gap-2 items-center pt-2">
          <select className={inputCls + ' !min-h-[40px] !w-auto max-w-[220px]'} value={outlet} onChange={(e) => setOutlet(e.target.value)}>
            <option value="">Outlet pemakaian…</option>{(masters?.outlets || []).map((o) => <option key={o.id}>{o.name}</option>)}</select>
          <Btn kind="ok" onClick={pakai}>Tandai terpakai / sudah diterima</Btn>
        </div>}
      </div>}
    </div>
  )
}
