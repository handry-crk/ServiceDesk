import { useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, useApp, toLocalInput, fromLocalInput, compressImage, WRITERS } from '../lib.jsx'
import { Btn, Card, Chip, Field, inputCls, ErrorBox, LevelBadge } from '../ui.jsx'
import { Combo, levelItemBadge } from '../components.jsx'

const ls = { get: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d } catch { return d } }, set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)) } catch {} } }
const MAIN_CH = ['WhatsApp', 'IG DM', 'TikTok DM', 'Marketplace Chat', 'Live Chat', 'Social Comment', 'Email']

export default function Catat() {
  const { masters, notify, can } = useApp()
  const nav = useNavigate()
  const [channel, setChannel] = useState(() => ls.get('sd_last_channel', 'WhatsApp'))
  const [outletId, setOutletId] = useState('')
  const [subJenis, setSubJenis] = useState('')
  const [ringkasan, setRingkasan] = useState('')
  const [waktu, setWaktu] = useState(null) // null = sekarang
  const [more, setMore] = useState(false)
  const [extra, setExtra] = useState({ brand: '', tipe: 'Komplain', orderNo: '', customerName: '', customerPhone: '' })
  const [photos, setPhotos] = useState([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [dup, setDup] = useState(null)
  const [listening, setListening] = useState(false)
  const fileRef = useRef()

  const outlets = useMemo(() => (masters?.outlets || []).filter((o) => o.active).map((o) => ({ value: o.id, label: o.name, sub: `${o.area} · ${o.type.replace('_', ' ')}`, keywords: (o.aliases || []).join(' ') })), [masters])
  const subs = useMemo(() => (masters?.subJenis || []).filter((s) => s.active !== false && s.name !== 'Lainnya: Rasa / Porsi').map((s) => ({ value: s.name, label: s.name, sub: s.contoh, keywords: s.keywords, level: s.level })), [masters])
  const recentOutlets = ls.get('sd_recent_outlets', [])
  const sj = masters?.subJenis.find((s) => s.name === subJenis)
  const outlet = masters?.outlets.find((o) => o.id === outletId)
  const ch = masters?.channels.find((c) => c.name === channel)
  const level = sj?.level
  const pj = masters?.penanggungJawab?.[level] || '-'
  const tfrt = level === 'Critical' ? Math.min(ch?.targetFrt || 5, masters?.criticalFrt || 30) : ch?.targetFrt
  const frozen = outlet?.type === 'online_frozen'
  const cc = !level ? '-' : level === 'Minor' ? (frozen && subJenis === 'Kesalahan Kemasan' ? 'Factory' : 'Operasional') : level === 'Major' ? (frozen ? 'Team Frozen' : 'Operasional') : level === 'Critical' ? ((['Kontaminasi', 'Keracunan', 'Undercooked'].includes(subJenis) || (frozen && subJenis === 'Penurunan Mutu (tidak dapat dikonsumsi)')) ? 'Factory/Operasional (cek root cause)' : 'Operasional') : 'Belum Diatur'
  const sla = { Minor: '1 hari', Major: '2 hari', Critical: '3 hari' }[level] || 'belum diatur'

  if (!can(...WRITERS)) return <ErrorBox error={{ message: 'Peran Anda tidak bisa mencatat case.' }} />

  const speak = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) return notify('Browser ini belum mendukung input suara.', 'err')
    const r = new SR(); r.lang = 'id-ID'; r.interimResults = false
    r.onresult = (e) => setRingkasan((t) => (t ? t + ' ' : '') + e.results[0][0].transcript)
    r.onend = () => setListening(false)
    setListening(true); r.start()
  }

  const addPhotos = async (files) => {
    for (const f of [...files].slice(0, 3 - photos.length)) {
      try {
        const blob = await compressImage(f)
        const fd = new FormData(); fd.append('file', blob, 'foto.jpg')
        const r = await api('/uploads', { method: 'POST', form: fd })
        setPhotos((p) => [...p, r.url])
      } catch (e) { notify(e.message, 'err') }
    }
  }

  const submit = async (force = false) => {
    setBusy(true); setErr(null)
    try {
      const body = { channel, outletId, subJenis, ringkasan, waktuMasuk: waktu ? fromLocalInput(waktu) : null, photos, force, ...Object.fromEntries(Object.entries(extra).filter(([, v]) => v)) }
      const c = await api('/cases', { method: 'POST', body })
      ls.set('sd_last_channel', channel)
      ls.set('sd_recent_outlets', [outletId, ...recentOutlets.filter((x) => x !== outletId)].slice(0, 5))
      notify(`Tersimpan: ${c.caseId}${c.level === 'Critical' ? ' — CRITICAL, balas < 30 menit' : ''}`, 'ok', {
        label: 'Sudah dibalas', fn: async () => { await api(`/cases/${c.caseId}/respond`, { method: 'POST' }); notify(`${c.caseId} ditandai sudah dibalas`) },
      })
      setOutletId(''); setSubJenis(''); setRingkasan(''); setWaktu(null); setPhotos([]); setDup(null)
      setExtra({ brand: '', tipe: 'Komplain', orderNo: '', customerName: '', customerPhone: '' })
      if (c.level === 'Critical') nav('/case/' + c.caseId)
    } catch (e) {
      if (e.status === 409) setDup(e.detail)
      else setErr(e)
    } finally { setBusy(false) }
  }

  const quick = (min) => setWaktu(toLocalInput(new Date(Date.now() - min * 60000).toISOString()))
  const ok = channel && outletId && subJenis && ringkasan.trim()

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-extrabold mb-1">Catat komplain</h1>
      <p className="text-sm text-mute mb-4">5 isian saja. Level, PJ, cost center, dan target SLA terisi otomatis.</p>
      <Card className="p-4 space-y-5">
        <Field label="Channel" required>
          <div className="flex flex-wrap gap-2">{MAIN_CH.map((c) => <Chip key={c} active={channel === c} onClick={() => setChannel(c)}>{c}</Chip>)}</div>
        </Field>
        <Field label="Outlet" required><Combo items={outlets} value={outletId} onChange={setOutletId} placeholder="Ketik nama outlet…" recent={recentOutlets} /></Field>
        <Field label="Sub Jenis Komplain" required hint="Bisa cari dengan kata sehari-hari: “mentah”, “kurang”, “salah”, “rambut”, “lama”.">
          <Combo items={subs} value={subJenis} onChange={setSubJenis} placeholder="Ketik masalahnya…" renderBadge={levelItemBadge} />
        </Field>
        {sj && (
          <div className={`rounded-xl p-3 text-sm ${level === 'Critical' ? 'bg-brick text-white' : 'bg-cream'}`}>
            {level === 'Critical' && <div className="font-bold mb-1">Critical — balas &lt; 30 menit dan eskalasi ke Manager / Direksi</div>}
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              <span>Level <b>{level || 'Belum Diatur'}</b></span><span>SLA <b>{sla}</b></span><span>PJ <b>{pj}</b></span>
              <span>Cost center <b>{cc}</b></span><span>Target balas <b>{tfrt} mnt</b></span>
            </div>
          </div>
        )}
        <Field label="Ringkasan masalah" required>
          <div className="relative">
            <textarea className={inputCls + ' min-h-[96px] py-2 pr-12'} value={ringkasan} onChange={(e) => setRingkasan(e.target.value)} placeholder="Contoh: pesan 16 pcs, yang dibuat 8 pcs" />
            <button type="button" onClick={speak} className={`absolute right-2 top-2 w-9 h-9 rounded-full ${listening ? 'bg-brick text-white animate-pulse' : 'bg-cream'}`} title="Bicara">🎤</button>
          </div>
        </Field>
        <Field label="Waktu masuk" required>
          <div className="flex flex-wrap gap-2 items-center">
            <Chip active={!waktu} onClick={() => setWaktu(null)}>Sekarang</Chip>
            <Chip onClick={() => quick(15)}>−15 mnt</Chip><Chip onClick={() => quick(60)}>−1 jam</Chip>
            <input type="datetime-local" className={inputCls + ' w-auto !min-h-[40px]'} value={waktu || ''} max={toLocalInput()} onChange={(e) => setWaktu(e.target.value || null)} />
          </div>
        </Field>

        <button type="button" className="text-sm font-semibold text-brick" onClick={() => setMore(!more)}>{more ? '▾' : '▸'} Detail tambahan (opsional)</button>
        {more && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Brand"><select className={inputCls} value={extra.brand} onChange={(e) => setExtra({ ...extra, brand: e.target.value })}>
              <option value="">{outlet?.brand || 'Cimol Bojot AA'}</option>{(masters?.brands || []).map((b) => <option key={b}>{b}</option>)}</select></Field>
            <Field label="Tipe"><select className={inputCls} value={extra.tipe} onChange={(e) => setExtra({ ...extra, tipe: e.target.value })}>{masters?.tipe.map((t) => <option key={t}>{t}</option>)}</select></Field>
            <Field label="No. Pesanan"><input className={inputCls} value={extra.orderNo} onChange={(e) => setExtra({ ...extra, orderNo: e.target.value })} /></Field>
            <Field label="Nama customer"><input className={inputCls} value={extra.customerName} onChange={(e) => setExtra({ ...extra, customerName: e.target.value })} /></Field>
            <Field label="No. HP customer"><input className={inputCls} inputMode="tel" value={extra.customerPhone} onChange={(e) => setExtra({ ...extra, customerPhone: e.target.value })} /></Field>
            <Field label={`Foto bukti (${photos.length}/3)`}>
              <div className="flex gap-2 items-center flex-wrap">
                {photos.map((p) => <img key={p} src={p} className="w-14 h-14 rounded-lg object-cover border border-line" alt="" />)}
                {photos.length < 3 && <Btn kind="ghost" size="sm" type="button" onClick={() => fileRef.current.click()}>+ Foto</Btn>}
                <input ref={fileRef} type="file" accept="image/*" multiple hidden onChange={(e) => addPhotos(e.target.files)} />
              </div>
            </Field>
          </div>
        )}
        <ErrorBox error={err} />
        {dup && (
          <div className="rounded-xl border border-warn bg-[#FBF1DC] p-3 text-sm">
            <div className="font-semibold mb-2">{dup.message}</div>
            <div className="flex gap-2">
              <Btn size="sm" onClick={() => submit(true)}>Tetap simpan</Btn>
              {dup.duplicates?.map((d) => <Btn key={d} size="sm" kind="ghost" onClick={() => nav('/case/' + d)}>Buka {d}</Btn>)}
            </div>
          </div>
        )}
        <Btn size="lg" className="w-full" disabled={!ok || busy} onClick={() => submit(false)}>{busy ? 'Menyimpan…' : 'Simpan case'}</Btn>
      </Card>
    </div>
  )
}
