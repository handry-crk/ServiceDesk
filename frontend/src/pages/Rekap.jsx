import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, useApp, useAsync, toLocalInput, fromLocalInput, fmtDT, fmtMin, workMinutes, WRITERS } from '../lib.jsx'
import { Btn, Card, Chip, Field, inputCls, ErrorBox, LevelBadge, StatusBadge, Sheet } from '../ui.jsx'
import { Combo, levelItemBadge, PhotoPick, subJenisItems, FrozenSubChips } from '../components.jsx'
import { VoucherMsg } from './CaseDetail.jsx'

const ls = { get: (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d } catch { return d } }, set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)) } catch {} } }
const EMPTY = { produkFrozen: false, outletId: '', subJenis: '', ringkasan: '', masuk: '', dibalas: '', selesai: '', status: 'selesai', rootCause: '', kompensasiKey: '', nilai: '', followUpUlang: 'N', orderNo: '', customerName: '', customerPhone: '', produk: '', kodeProduksi: '', ekspedisi: '' }

export default function Rekap() {
  const { masters, loadMasters, notify, can } = useApp()
  const [channel, setChannel] = useState(() => ls.get('sd_last_channel', 'WhatsApp'))
  const [chat, setChat] = useState('')
  const [parsed, setParsed] = useState(null)
  const [parseErr, setParseErr] = useState(null)
  const [cust, setCust] = useState(null)
  const [f, setF] = useState(EMPTY)
  const [photo, setPhoto] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [dup, setDup] = useState(null)
  const [saved, setSaved] = useState(null)
  const [newOutlet, setNewOutlet] = useState(null)
  const timer = useRef()
  const mine = useAsync(() => api('/rekap/mine'), [])
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }))

  const outlets = useMemo(() => (masters?.outlets || []).filter((o) => o.active).map((o) => ({ value: o.id, label: o.name + (o.pending ? ' (menunggu verifikasi)' : ''), sub: `${o.area} · ${o.type.replace('_', ' ')}`, keywords: (o.aliases || []).join(' ') })), [masters])
  const chGroups = useMemo(() => {
    const g = {}
    ;(masters?.channels || []).filter((c) => !['CSAT Form', 'Review Online'].includes(c.name)).forEach((c) => { (g[c.group || 'Lainnya'] = g[c.group || 'Lainnya'] || []).push(c.name) })
    return Object.entries(g)
  }, [masters])
  const sj = masters?.subJenis.find((s) => s.name === f.subJenis)
  const outlet = masters?.outlets.find((o) => o.id === f.outletId)
  const ch = masters?.channels.find((c) => c.name === channel)
  const frozenStore = outlet?.type === 'online_frozen'
  const frozen = frozenStore || !!f.produkFrozen
  const subs = subJenisItems(masters, frozen)
  const level = sj?.level
  const komp = (masters?.kompensasi || []).filter((k) => !level || k.level === level || k.level === 'Semua').sort((a, b) => (b.standard ? 1 : 0) - (a.standard ? 1 : 0))
  const tfrt = level === 'Critical' ? Math.min(ch?.targetFrt || 5, masters?.criticalFrt || 30) : ch?.targetFrt

  // baca chat otomatis setelah ditempel
  const readChat = async (text, customer) => {
    if (!text.trim()) { setParsed(null); setParseErr(null); return }
    try {
      const r = await api('/wa/parse', { method: 'POST', body: { text, customer } })
      setParsed(r); setParseErr(null); setCust(r.customer)
      setF((x) => ({ ...x, masuk: r.masuk ? toLocalInput(r.masuk) : x.masuk, dibalas: r.dibalas ? toLocalInput(r.dibalas) : x.dibalas,
        ringkasan: x.ringkasan || r.customerText || '', customerPhone: x.customerPhone || r.customerPhone || '',
        customerName: x.customerName || (!r.customerPhone ? r.customer : '') }))
    } catch (e) { setParsed(null); setParseErr(e.message) }
  }
  useEffect(() => { clearTimeout(timer.current); timer.current = setTimeout(() => readChat(chat, null), 400); return () => clearTimeout(timer.current) }, [chat])

  const fromChat = parsed?.masuk && parsed?.dibalas && f.masuk === toLocalInput(parsed.masuk) && f.dibalas === toLocalInput(parsed.dibalas)
  const done = f.status !== 'proses'
  const frt = f.masuk && f.dibalas ? workMinutes(fromLocalInput(f.masuk), fromLocalInput(f.dibalas), masters?.settings) : null
  const missing = [!f.outletId && 'outlet', !f.subJenis && 'sub jenis', !f.ringkasan.trim() && 'ringkasan', !f.masuk && 'jam masuk', !f.dibalas && 'jam dibalas',
    !fromChat && !photo && 'screenshot chat', done && !f.rootCause.trim() && 'root cause', done && !f.kompensasiKey && 'kompensasi'].filter(Boolean)

  if (!can(...WRITERS)) return <ErrorBox error={{ message: 'Peran Anda tidak bisa mencatat case.' }} />

  const addOutlet = async () => {
    try {
      const o = await api('/outlets/quick', { method: 'POST', body: { name: newOutlet } })
      await loadMasters(); set('outletId', o.id); setNewOutlet(null)
      notify(o.existing ? `Outlet sudah ada: ${o.name}` : `Outlet "${o.name}" ditambahkan, menunggu verifikasi CRM Supervisor`)
    } catch (e) { notify(e.message, 'err') }
  }

  const submit = async (force = false) => {
    setBusy(true); setErr(null)
    try {
      const body = {
        channel, outletId: f.outletId, subJenis: f.subJenis, ringkasan: f.ringkasan, waktuMasuk: fromLocalInput(f.masuk), waktuFirstResponse: fromLocalInput(f.dibalas),
        waktuResolved: done ? fromLocalInput(f.selesai || toLocalInput()) : null, rootCause: done ? f.rootCause : null, kompensasiKey: done ? f.kompensasiKey : null,
        nilaiKompensasi: done && f.nilai !== '' ? Number(f.nilai) : null, closed: f.status === 'closed', followUpUlang: f.followUpUlang,
        chatText: chat || null, chatCustomer: cust, photo, orderNo: f.orderNo || null, customerName: f.customerName || null, customerPhone: f.customerPhone || null,
        produk: frozen ? f.produk || null : null, kodeProduksi: frozen ? f.kodeProduksi || null : null, ekspedisi: frozen ? f.ekspedisi || null : null, produkFrozen: !frozenStore && f.produkFrozen ? true : null, force,
      }
      const r = await api('/cases/rekap', { method: 'POST', body })
      ls.set('sd_last_channel', channel)
      setSaved(r); setDup(null)
      if (r.voucherWarning) notify(r.voucherWarning, 'err')
      setF({ ...EMPTY }); setChat(''); setParsed(null); setPhoto(null); setCust(null)
      mine.reload(); window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e) {
      if (e.status === 409) setDup(e.detail)
      else setErr(e)
    } finally { setBusy(false) }
  }

  return (
    <div className="max-w-3xl mx-auto">
      <ModeTabs />
      <h1 className="text-2xl font-extrabold mb-1">Rekap komplain</h1>
      <p className="text-sm text-mute mb-4">Selesaikan komplain dulu (WhatsApp, Douke, chat marketplace), lalu rekap di sini. Tempel chat-nya: jam masuk & jam dibalas terisi otomatis dan chat menjadi bukti. Chat tidak bisa disalin? Lewati langkah 1, isi jam sendiri dan lampirkan screenshot.</p>

      {saved && <Card className="p-4 mb-4 border-ok border-2">
        <div className="flex flex-wrap items-center gap-2"><span className="font-extrabold text-lg">✓ {saved.caseId} tersimpan</span><LevelBadge level={saved.level} /><StatusBadge status={saved.status} />
          <span className="text-sm text-mute">FRT {fmtMin(saved.frtMin)} · {saved.timeEvidence === 'chat' ? 'jam dari chat' : 'jam manual + screenshot'}</span>
          <Link to={'/case/' + saved.caseId} className="text-sm text-brick underline ml-auto">Buka case</Link></div>
        {saved.voucher && <div className="mt-3"><VoucherMsg c={saved} notify={notify} masters={masters} /></div>}
        <button className="text-xs text-mute underline mt-2" onClick={() => setSaved(null)}>Tutup</button>
      </Card>}

      <Card className="p-4 space-y-5">
        <Field label="1. Tempel chat (opsional)" hint="WhatsApp Web/Desktop: blok pesan dari awal sampai selesai → Salin → tempel. Douke / platform lain: salin percakapan beserta nama dan tanggal-jam tiap pesan. Bila tidak terbaca, isi jam di langkah 3 dan lampirkan screenshot.">
          <textarea className={inputCls + ' min-h-[120px] py-2 text-sm font-mono'} value={chat} onChange={(e) => setChat(e.target.value)} placeholder={'[10.02, 16/11/2026] +62 812-xxxx: Kak cimol saya kurang 2\n[10.04, 16/11/2026] CS Cimol Bojot AA: Mohon maaf kak…'} />
        </Field>
        {parseErr && <div className="text-sm text-brick -mt-3">{parseErr}</div>}
        {parsed && <div className="rounded-xl bg-cream p-3 text-sm -mt-2 space-y-2">
          <div>{parsed.messages} pesan terbaca. Siapa customer-nya?</div>
          <div className="flex flex-wrap gap-2">{parsed.senders.map((s) => <Chip key={s} active={cust === s} onClick={() => readChat(chat, s)} className="!min-h-[34px] text-xs">{s}</Chip>)}</div>
          <div className="text-xs text-mute">Masuk {fmtDT(parsed.masuk)} · dibalas {parsed.dibalas ? fmtDT(parsed.dibalas) : <b className="text-brick">belum ada balasan CS di chat</b>} · pesan terakhir {fmtDT(parsed.terakhir)}</div>
        </div>}

        <Field label="2. Channel" required>
          <div className="space-y-2">{chGroups.map(([g, list]) => (
            <div key={g}><div className="text-xs text-mute mb-1">{g}</div>
              <div className="flex flex-wrap gap-2">{list.map((c) => <Chip key={c} active={channel === c} onClick={() => setChannel(c)}>{c}</Chip>)}</div></div>))}</div>
        </Field>
        <Field label="Outlet" required>
          <Combo items={outlets} value={f.outletId} onChange={(v) => set('outletId', v)} placeholder="Ketik nama outlet…" recent={ls.get('sd_recent_outlets', [])} />
          {newOutlet === null ? <button type="button" className="text-xs text-brick underline mt-1" onClick={() => setNewOutlet('')}>Outlet belum ada di daftar? Tambah sekarang</button>
            : <div className="flex gap-2 mt-2"><input className={inputCls + ' !min-h-[40px]'} autoFocus value={newOutlet} onChange={(e) => setNewOutlet(e.target.value)} placeholder="Nama outlet, mis. Gerobak Pasar Minggu" />
              <Btn size="sm" disabled={newOutlet.trim().length < 3} onClick={addOutlet}>Tambah</Btn><Btn size="sm" kind="ghost" onClick={() => setNewOutlet(null)}>Batal</Btn></div>}
          {outlet?.pending && <div className="text-xs text-[#7A5410] mt-1">Outlet ini menunggu verifikasi CRM Supervisor. Case tetap tersimpan.</div>}
        </Field>
        {f.outletId && !frozenStore && <label className="flex items-start gap-2 text-sm rounded-xl border border-line p-3 bg-white"><input type="checkbox" className="w-5 h-5 mt-0.5" checked={f.produkFrozen} onChange={(e) => set('produkFrozen', e.target.checked)} /><span><b>Komplain produk Cimol Frozen</b> (kemasan beku) yang dibeli di outlet / agen / channel ini<span className="block text-xs text-mute">Centang agar ditangani CS Online / Marketplace dan masuk dashboard & aturan frozen (PIC, cost center, kode produksi).</span></span></label>}
        <Field label="Sub Jenis Komplain" required hint="Bisa cari dengan kata sehari-hari: “kurang”, “pecah”, “bocor”, “telat”.">{frozen && <FrozenSubChips masters={masters} value={f.subJenis} onChange={(v) => set('subJenis', v)} />}<Combo items={subs} value={f.subJenis} onChange={(v) => set('subJenis', v)} placeholder={frozen ? 'Atau ketik masalahnya…' : 'Ketik masalahnya…'} renderBadge={levelItemBadge} /></Field>
        <Field label="Ringkasan masalah" required hint="Terisi dari pesan customer; rapikan seperlunya."><textarea className={inputCls + ' min-h-[72px] py-2'} value={f.ringkasan} onChange={(e) => set('ringkasan', e.target.value)} /></Field>
        {ch?.orderRequired && <Field label={`No. Pesanan ${channel}`}><input className={inputCls} value={f.orderNo} onChange={(e) => set('orderNo', e.target.value.trim())} /></Field>}
        {frozen && <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Produk"><input className={inputCls} list="rk-products" value={f.produk} onChange={(e) => set('produk', e.target.value)} /><datalist id="rk-products">{(masters?.frozenProducts || []).map((p) => <option key={p} value={p} />)}</datalist></Field>
          <Field label="Ekspedisi"><select className={inputCls} value={f.ekspedisi} onChange={(e) => set('ekspedisi', e.target.value)}><option value="">–</option>{(masters?.couriers || []).map((x) => <option key={x}>{x}</option>)}</select></Field>
          <Field label="Kode produksi"><input className={inputCls} value={f.kodeProduksi} onChange={(e) => set('kodeProduksi', e.target.value.toUpperCase())} /></Field>
        </div>}

        <div>
          <div className="text-sm font-semibold mb-2">3. Waktu</div>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Masuk" required><input type="datetime-local" className={inputCls} value={f.masuk} max={toLocalInput()} onChange={(e) => set('masuk', e.target.value)} /></Field>
            <Field label="Dibalas pertama" required><input type="datetime-local" className={inputCls} value={f.dibalas} min={f.masuk} max={toLocalInput()} onChange={(e) => set('dibalas', e.target.value)} /></Field>
            {done && <Field label="Selesai" hint="Kosong = sekarang"><input type="datetime-local" className={inputCls} value={f.selesai} min={f.dibalas} max={toLocalInput()} onChange={(e) => set('selesai', e.target.value)} />
              {parsed?.terakhir && <button type="button" className="text-xs text-brick underline mt-1" onClick={() => set('selesai', toLocalInput(parsed.terakhir))}>Pakai jam pesan terakhir</button>}</Field>}
          </div>
          {frt != null && <div className="text-sm mt-2">FRT jam kerja <b>{fmtMin(frt)}</b> (target {tfrt} mnt) — {frt <= tfrt ? <span className="text-ok font-semibold">sesuai SLA</span> : <span className="text-brick font-semibold">lewat SLA</span>}</div>}
          <div className={`text-sm mt-2 rounded-xl p-3 ${fromChat ? 'bg-[#E3F1E6] text-[#1F6B3A]' : 'bg-[#FBF1DC] text-[#7A5410]'}`}>
            {fromChat ? '✓ Jam masuk & dibalas sesuai chat yang ditempel — langsung diterima.' : 'Jam diisi manual (atau berbeda dari chat): lampirkan screenshot chat yang memperlihatkan jamnya.'}
            {!fromChat && <div className="mt-2"><PhotoPick value={photo} onChange={setPhoto} /></div>}
          </div>
        </div>

        <div>
          <div className="text-sm font-semibold mb-2">4. Penyelesaian</div>
          <div className="flex flex-wrap gap-2 mb-3">{[['proses', 'Masih diproses'], ['selesai', 'Selesai'], ['closed', 'Selesai & customer sudah konfirmasi']].map(([k, l]) => <Chip key={k} active={f.status === k} onClick={() => set('status', k)}>{l}</Chip>)}</div>
          {done && <div className="space-y-3">
            <Field label="Root cause" required>
              <div className="flex flex-wrap gap-2 mb-2">{(sj?.rootCauses || []).map((r) => <Chip key={r} active={f.rootCause === r} onClick={() => set('rootCause', r)} className="!min-h-[34px] text-xs">{r}</Chip>)}</div>
              <input className={inputCls} value={f.rootCause} onChange={(e) => set('rootCause', e.target.value)} placeholder="Atau tulis sendiri" />
            </Field>
            <Field label={`Kompensasi${level ? ` (level ${level})` : ''}`} required>
              <div className="grid sm:grid-cols-2 gap-2">{komp.map((x) => (
                <button type="button" key={x.key} onClick={() => setF((y) => ({ ...y, kompensasiKey: x.key, nilai: x.nilai || '' }))}
                  className={`text-left rounded-xl border px-3 py-2 text-sm ${f.kompensasiKey === x.key ? 'border-brick bg-brick-soft' : 'border-line'}`}>
                  {x.label}{(!x.standard || !level) && <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded bg-[#FBE3C8] text-[#8A4B00] font-bold">Luar std</span>}
                </button>))}</div>
            </Field>
            {f.kompensasiKey && <Field label="Nilai (Rp)"><input className={inputCls} inputMode="numeric" value={f.nilai} onChange={(e) => set('nilai', e.target.value.replace(/\D/g, ''))} /></Field>}
            {f.status === 'closed' && <Field label="Customer follow-up ulang (menghubungi lagi soal yang sama)?"><div className="flex gap-2"><Chip active={f.followUpUlang === 'N'} onClick={() => set('followUpUlang', 'N')}>Tidak</Chip><Chip active={f.followUpUlang === 'Y'} onClick={() => set('followUpUlang', 'Y')}>Ya</Chip></div></Field>}
          </div>}
        </div>

        <details className="text-sm"><summary className="font-semibold text-brick cursor-pointer">Data customer (opsional)</summary>
          <div className="grid gap-3 sm:grid-cols-2 mt-2">
            <Field label="Nama customer"><input className={inputCls} value={f.customerName} onChange={(e) => set('customerName', e.target.value)} /></Field>
            <Field label="No. WhatsApp"><input className={inputCls} inputMode="tel" value={f.customerPhone} onChange={(e) => set('customerPhone', e.target.value)} /></Field>
            {!ch?.orderRequired && <Field label="No. Pesanan"><input className={inputCls} value={f.orderNo} onChange={(e) => set('orderNo', e.target.value)} /></Field>}
          </div>
        </details>

        <ErrorBox error={err} />
        {dup && <div className="rounded-xl border border-warn bg-[#FBF1DC] p-3 text-sm">
          <div className="font-semibold mb-2">{dup.message}</div>
          <div className="flex gap-2"><Btn size="sm" onClick={() => submit(true)}>Tetap simpan</Btn>{dup.duplicates?.map((d) => <Link key={d} to={'/case/' + d}><Btn size="sm" kind="ghost">Buka {d}</Btn></Link>)}</div>
        </div>}
        {missing.length > 0 && <div className="text-xs text-mute">Belum diisi: {missing.join(', ')}</div>}
        <Btn size="lg" className="w-full" disabled={missing.length > 0 || busy} onClick={() => submit(false)}>{busy ? 'Menyimpan…' : 'Simpan rekap'}</Btn>
      </Card>

      <Card className="p-4 mt-4">
        <h3 className="font-bold mb-2">Rekap Anda hari ini ({mine.data?.length || 0})</h3>
        {(mine.data || []).length === 0 ? <p className="text-sm text-mute">Belum ada.</p> :
          <div className="divide-y divide-line">{mine.data.map((c) => (
            <Link key={c.caseId} to={'/case/' + c.caseId} className="flex flex-wrap items-center gap-2 py-2 text-sm">
              <span className="font-bold">{c.caseId}</span><LevelBadge level={c.level} /><StatusBadge status={c.status} />
              <span className="truncate">{c.subJenis} · {c.outletName}</span><span className="ml-auto text-xs text-mute">FRT {fmtMin(c.frtMin)} · {c.timeEvidence === 'chat' ? 'chat' : c.timeEvidence === 'bulk' ? 'bulk' : 'screenshot'}</span>
            </Link>))}</div>}
      </Card>
    </div>
  )
}

export function ModeTabs({ live, mode }) {
  const cur = mode || (live ? 'live' : 'rekap')
  const tabs = [['rekap', '/catat', 'Rekap chat'], ['bulk', '/catat?mode=bulk', 'Bulk input'], ['live', '/catat?mode=live', 'Catat real time']]
  return (
    <div className="flex flex-wrap gap-1 mb-4 bg-white border border-line rounded-xl p-1 w-fit">
      {tabs.map(([k, to, l]) => <Link key={k} to={to} className={`px-3 md:px-4 min-h-[38px] flex items-center rounded-lg text-sm font-semibold ${cur === k ? 'bg-brick text-white' : 'hover:bg-cream'}`}>{l}</Link>)}
    </div>
  )
}
