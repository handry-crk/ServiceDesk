import { useEffect, useMemo, useState } from 'react'
import { useParams, useSearchParams, useNavigate } from 'react-router-dom'
import { api, useApp, useAsync, fmtDT, fmtMin, fmtRp, toLocalInput, fromLocalInput, WRITERS, LEAD, waNumber, waLink, surveyMessage } from '../lib.jsx'
import { Btn, Card, Chip, Field, Sheet, Skeleton, ErrorBox, LevelBadge, StatusBadge, inputCls } from '../ui.jsx'
import { SlaChip, useNow, Combo, levelItemBadge } from '../components.jsx'

const EV = { created: 'Case dibuat', responded: 'Sudah dibalas', resolved: 'Resolved', closed: 'Closed', reopened: 'Dibuka ulang', note: 'Catatan', level_changed: 'Level diubah', time_corrected: 'Waktu dikoreksi', voucher_issued: 'Voucher diterbitkan', edited: 'Data diubah', csat: 'CSAT customer' }
const CC_ROOT = 'Factory/Operasional (cek root cause)'

const copy = async (t, notify, msg = 'Tersalin') => { try { await navigator.clipboard.writeText(t); notify(msg) } catch { notify('Gagal menyalin', 'err') } }

export default function CaseDetail() {
  const { id } = useParams()
  const [sp, setSp] = useSearchParams()
  const nav = useNavigate()
  const { masters, can, notify } = useApp()
  const now = useNow()
  const { data: c, loading, error, reload, setData } = useAsync(() => api('/cases/' + id), [id])
  const [sheet, setSheet] = useState(sp.get('aksi') || null)
  const close = () => { setSheet(null); if (sp.get('aksi')) setSp({}) }
  const writer = can(...WRITERS)
  const lead = can(...LEAD)
  const limited = can('Manager Area', 'Ops/QC')

  const act = async (path, body, msg) => {
    try { const r = await api(`/cases/${id}/${path}`, { method: 'POST', body }); notify(msg); close(); await reload(); return r }
    catch (e) { notify(e.message, 'err') }
  }
  if (loading && !c) return <Skeleton h="h-96" />
  if (error) return <ErrorBox error={error} />
  const crit = c.level === 'Critical'

  const Row = ({ k, v }) => <div className="flex justify-between gap-3 py-1.5 border-b border-line/60 last:border-0 text-sm"><span className="text-mute">{k}</span><span className="text-right font-medium">{v ?? '–'}</span></div>

  return (
    <div className="max-w-4xl mx-auto">
      <button className="text-sm text-mute mb-2" onClick={() => nav(-1)}>← Kembali</button>
      <Card className={`p-4 mb-4 ${crit ? 'border-brick border-2' : ''}`}>
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <h1 className="text-2xl font-extrabold">{c.caseId}</h1><LevelBadge level={c.level} /><StatusBadge status={c.status} /><SlaChip c={c} now={now} />
          {c.kompensasiOutsideStandard && <span className="text-xs px-2 py-0.5 rounded-md bg-[#FBE3C8] text-[#8A4B00] font-bold">Kompensasi di luar standard</span>}
        </div>
        <div className="font-semibold">{c.subJenis || 'Sub jenis belum diisi'} · {c.outletName}</div>
        <p className="mt-1 whitespace-pre-wrap">{c.ringkasan}</p>
        {c.photos?.length > 0 && <div className="flex gap-2 mt-3">{c.photos.map((p) => <a key={p} href={p} target="_blank" rel="noreferrer"><img src={p} className="w-20 h-20 object-cover rounded-xl border border-line" alt="" /></a>)}</div>}
        {crit && c.status === 'Open' && <div className="mt-3 rounded-xl bg-brick text-white p-3 text-sm font-semibold">Critical — balas &lt; 30 menit dan eskalasi ke Manager / Direksi.</div>}
        {c.dataIssues?.length > 0 && <div className="flex flex-wrap gap-1 mt-3">{c.dataIssues.map((i) => <span key={i} className={`text-xs px-2 py-0.5 rounded-md ${i.startsWith('Info:') ? 'bg-cream text-mute' : 'bg-[#FBF1DC] text-[#7A5410]'}`}>{i.replace('Info: ', '')}</span>)}</div>}
        {writer && (
          <div className="flex flex-wrap gap-2 mt-4 no-print">
            {c.status === 'Open' && <Btn kind="ok" size="lg" onClick={() => act('respond', undefined, 'Ditandai sudah dibalas')}>Sudah dibalas</Btn>}
            {['Open', 'Responded'].includes(c.status) && <Btn size="lg" onClick={() => setSheet('resolve')}>Selesai (Resolved)</Btn>}
            {c.status === 'Resolved' && <Btn size="lg" onClick={() => setSheet('close')}>Closed (customer confirm)</Btn>}
            {['Resolved', 'Closed'].includes(c.status) && <Btn kind="ghost" onClick={() => setSheet('reopen')}>Buka ulang</Btn>}
            <Btn kind="ghost" onClick={() => setSheet('note')}>Tambah catatan</Btn>
            <Btn kind="ghost" onClick={() => setSheet('level')}>Ubah level</Btn>
            <Btn kind="ghost" onClick={() => setSheet('edit')}>Ubah data</Btn>
            {lead && <Btn kind="ghost" onClick={() => setSheet('time')}>Koreksi waktu</Btn>}
          </div>
        )}
        {limited && <div className="flex flex-wrap gap-2 mt-4"><Btn kind="ghost" onClick={() => setSheet('rootcause')}>Isi root cause / cost center</Btn><Btn kind="ghost" onClick={() => setSheet('note')}>Tambah catatan</Btn></div>}
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card className="p-4">
          <h3 className="font-bold mb-2">Klasifikasi (CRM.STD.001)</h3>
          <Row k="Jenis" v={c.jenis} /><Row k="Level standard" v={c.levelStandard} /><Row k="Level dipakai" v={c.level} />
          {c.levelChangeReason && <Row k="Alasan ubah level" v={c.levelChangeReason} />}
          <Row k="Penanggung jawab" v={c.penanggungJawab} /><Row k="Cost center" v={c.costCenter} />
          {c.costCenterFinal && <Row k="Cost center final" v={c.costCenterFinal} />}
          <Row k="PIC Dept" v={c.picDept} /><Row k="Root cause" v={c.rootCause} />
          <Row k="Kompensasi" v={c.kompensasiLabel} /><Row k="Nilai" v={c.nilaiKompensasi ? fmtRp(c.nilaiKompensasi) : '–'} />
          {c.voucherCode && <Row k="Kode voucher" v={<span>{c.voucherCode} <span className="text-xs text-mute">({c.voucher?.status})</span></span>} />}
        </Card>
        <Card className="p-4">
          <h3 className="font-bold mb-2">Waktu & SLA</h3>
          <Row k="Masuk" v={fmtDT(c.waktuMasuk) + (c.hasTime === false ? ' (tanpa jam)' : '')} />
          <Row k="First response" v={fmtDT(c.waktuFirstResponse)} /><Row k="Resolved" v={fmtDT(c.waktuResolved)} /><Row k="Closed" v={fmtDT(c.waktuClosed)} />
          <Row k="FRT" v={<span className={c.slaResponseOk === false ? 'text-brick' : c.slaResponseOk ? 'text-ok' : ''}>{fmtMin(c.frtMin)} / target {c.targetFrtMin} mnt</span>} />
          <Row k="FRT jam kerja" v={fmtMin(c.frtWorkMin)} />
          <Row k="Resolusi" v={<span className={c.resolutionSlaOk === false ? 'text-brick' : c.resolutionSlaOk ? 'text-ok' : ''}>{fmtMin(c.resolutionMin)}{c.targetResolutionMin ? ` / target ${fmtMin(c.targetResolutionMin)}` : ''}</span>} />
          <Row k="Same day" v={c.sameDay === null ? '–' : c.sameDay ? 'Ya' : 'Tidak'} /><Row k="Follow-up ulang" v={c.followUpUlang} />
          <Row k="Dibuka ulang" v={c.reopenCount ? `${c.reopenCount}×` : 'Tidak'} /><Row k="CSAT" v={c.csat ? `${c.csat}/5` : '–'} />
        </Card>
        <Card className="p-4">
          <h3 className="font-bold mb-2">Customer & sumber</h3>
          <Row k="Channel" v={c.channel} /><Row k="Brand" v={c.brand} /><Row k="Tipe" v={c.tipe} /><Row k="Valid" v={c.valid} />
          <Row k="No. pesanan" v={c.orderNo} /><Row k="Nama" v={c.customerName} /><Row k="No. HP" v={c.customerPhone} />
          <Row k="CS agent" v={c.csAgent} /><Row k="Sumber" v={c.source} />
          {c.notes && <Row k="Catatan impor" v={c.notes} />}
          {c.surveyToken && writer && <div className="mt-3 space-y-1">
            <Btn size="sm" kind={c.surveySentAt ? 'ghost' : 'soft'} onClick={() => setSheet('survey')}>{c.surveySentAt ? 'Kirim ulang survei CSAT' : 'Kirim survei CSAT'}</Btn>
            {c.surveySentAt && <div className="text-xs text-mute">Survei terkirim {fmtDT(c.surveySentAt)} via {c.surveySentVia === 'whatsapp' ? 'WhatsApp' : 'salin pesan'}{c.csat ? ` · dijawab ${c.csat}/5` : ' · belum dijawab'}</div>}
          </div>}
        </Card>
        <Card className="p-4">
          <h3 className="font-bold mb-2">Riwayat</h3>
          <ol className="space-y-3">
            {c.events.map((e) => (
              <li key={e.id} className="text-sm border-l-2 border-brick/40 pl-3">
                <div className="font-semibold">{EV[e.type] || e.type} <span className="text-mute font-normal">· {e.by}</span></div>
                <div className="text-xs text-mute">{fmtDT(e.at)}</div>
                {e.payload?.text && <div>{e.payload.text}</div>}
                {e.payload?.reason && <div className="text-mute">Alasan: {e.payload.reason}</div>}
                {e.payload?.kompensasi && <div className="text-mute">{e.payload.kompensasi}{e.payload.nilai ? ` · ${fmtRp(e.payload.nilai)}` : ''}</div>}
                {e.payload?.kode && <div className="text-mute">Kode {e.payload.kode}</div>}
                {e.type === 'level_changed' && <div className="text-mute">{e.payload.from} → {e.payload.to}</div>}
                {e.type === 'time_corrected' && <div className="text-mute">{e.payload.field}</div>}
              </li>
            ))}
            {c.events.length === 0 && <li className="text-sm text-mute">Data impor dari sheet lama.</li>}
          </ol>
        </Card>
      </div>

      <ResolveSheet open={sheet === 'resolve'} onClose={close} c={c} masters={masters} onDone={async (body) => {
        const r = await act('resolve', body, 'Case resolved')
        if (r?.voucherWarning) notify(r.voucherWarning, 'err')
        if (r?.voucher) setSheet('voucher')
      }} />
      <Sheet open={sheet === 'voucher'} onClose={close} title="Voucher diterbitkan">
        {c.voucher && <VoucherMsg c={c} notify={notify} masters={masters} />}
      </Sheet>
      <CloseSheet open={sheet === 'close'} onClose={close} c={c} onDone={async (b) => { const r = await act('close', b, 'Case closed'); if (r && writer) setSheet('survey') }} />
      <SurveySheet open={sheet === 'survey'} onClose={close} c={c} notify={notify} onSent={async (via, phone) => {
        try {
          if (phone && phone !== c.customerPhone) await api('/cases/' + id, { method: 'PATCH', body: { customerPhone: phone } })
          await api(`/cases/${id}/survey-sent`, { method: 'POST', body: { via } }); close(); reload()
        } catch (e) { notify(e.message, 'err') }
      }} />
      <SimpleSheet open={sheet === 'reopen'} onClose={close} title="Buka ulang case" label="Alasan dibuka ulang" onDone={(t) => act('reopen', { reason: t }, 'Case dibuka ulang')} />
      <SimpleSheet open={sheet === 'note'} onClose={close} title="Tambah catatan" label="Catatan" onDone={(t) => act('note', { text: t }, 'Catatan tersimpan')} />
      <LevelSheet open={sheet === 'level'} onClose={close} c={c} onDone={(b) => act('change-level', b, 'Level diubah')} />
      <TimeSheet open={sheet === 'time'} onClose={close} c={c} onDone={(b) => act('correct-time', b, 'Waktu dikoreksi')} />
      <EditSheet open={sheet === 'edit' || sheet === 'rootcause'} limited={sheet === 'rootcause' || limited} onClose={close} c={c} masters={masters}
        onDone={async (b) => { try { setData(await api('/cases/' + id, { method: 'PATCH', body: b })); notify('Tersimpan'); close(); reload() } catch (e) { notify(e.message, 'err') } }} />
    </div>
  )
}

function SurveySheet({ open, onClose, c, notify, onSent }) {
  const url = `${location.origin}/survei/${c.surveyToken}`
  const [phone, setPhone] = useState(c.customerPhone || '')
  const [msg, setMsg] = useState('')
  useEffect(() => { if (open) { setPhone(c.customerPhone || ''); setMsg(surveyMessage(c, url)) } }, [open, c.customerPhone, c.customerName, url])
  const wa = waNumber(phone)
  return (
    <Sheet open={open} onClose={onClose} title="Kirim survei CSAT ke customer">
      <div className="space-y-4">
        <p className="text-sm text-mute">Customer cukup sekali tap emoji 1–5. Hasilnya masuk ke CSAT komplain di dashboard.</p>
        <Field label="No. WhatsApp customer" hint={phone && !wa ? 'Nomor tidak valid. Contoh: 0812xxxxxxx' : 'Diisi otomatis dari case; disimpan ke case bila diubah.'}>
          <input className={inputCls} inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="08xxxxxxxxxx" />
        </Field>
        <Field label="Pesan"><textarea className={inputCls + ' min-h-[150px] py-2 text-sm'} value={msg} onChange={(e) => setMsg(e.target.value)} /></Field>
        <a href={wa ? waLink(phone, msg) : undefined} target="_blank" rel="noreferrer"
          onClick={(e) => { if (!wa) { e.preventDefault(); return } onSent('whatsapp', phone) }}>
          <Btn className="w-full" size="lg" kind="ok" disabled={!wa}>Kirim lewat WhatsApp</Btn>
        </a>
        <Btn className="w-full" kind="ghost" onClick={async () => { try { await navigator.clipboard.writeText(msg); notify('Pesan survei tersalin. Tempel di channel customer (IG DM, chat platform, dll).') } catch { notify('Gagal menyalin', 'err'); return } onSent('copy', phone) }}>Salin pesan (untuk IG DM, TikTok, chat platform)</Btn>
        <button className="text-sm text-mute underline w-full" onClick={onClose}>Nanti saja</button>
      </div>
    </Sheet>
  )
}

function VoucherMsg({ c, notify, masters }) {
  const msg = `Halo Kak, mohon maaf atas ketidaknyamanannya 🙏 Sebagai permintaan maaf, kami berikan ${c.voucher.jenis} dengan kode *${c.voucher.kode}*. Tunjukkan kode ini saat pembelian berikutnya ya. Terima kasih sudah memberi masukan untuk Cimol Bojot AA.`
  return (
    <div className="space-y-3">
      <div className="text-3xl font-extrabold tracking-wider text-center py-3 bg-cream rounded-xl">{c.voucher.kode}</div>
      <div className="text-sm text-mute">{c.voucher.jenis} · otomatis tertaut ke {c.caseId}</div>
      <textarea readOnly className={inputCls + ' min-h-[120px] py-2 text-sm'} value={msg} />
      <Btn className="w-full" onClick={() => copy(msg, notify, 'Pesan untuk customer tersalin')}>Salin pesan untuk customer</Btn>
    </div>
  )
}

function ResolveSheet({ open, onClose, c, masters, onDone }) {
  const sj = masters?.subJenis.find((s) => s.name === c.subJenis)
  // Level Belum Diatur (mis. Delivery / Ekspedisi): semua pilihan ditampilkan, ditandai di luar standard
  const komp = useMemo(() => (masters?.kompensasi || []).filter((k) => !c.level || k.level === c.level || k.level === 'Semua').sort((a, b) => (b.standard ? 1 : 0) - (a.standard ? 1 : 0)), [masters, c.level])
  const [rc, setRc] = useState(c.rootCause || '')
  const [pic, setPic] = useState(c.picDept || '')
  const [k, setK] = useState('')
  const [nilai, setNilai] = useState('')
  useEffect(() => { if (open) { setRc(c.rootCause || ''); setPic(c.picDept || '') } }, [open, c.rootCause, c.picDept])
  const sel = komp.find((x) => x.key === k)
  return (
    <Sheet open={open} onClose={onClose} title={`Selesaikan ${c.caseId}`}>
      <div className="space-y-4">
        <Field label="Root cause" required>
          <div className="flex flex-wrap gap-2 mb-2">{(sj?.rootCauses || []).map((r) => <Chip key={r} active={rc === r} onClick={() => setRc(r)}>{r}</Chip>)}</div>
          <input className={inputCls} value={rc} onChange={(e) => setRc(e.target.value)} placeholder="Atau tulis sendiri" />
        </Field>
        <Field label="PIC Dept"><select className={inputCls} value={pic} onChange={(e) => setPic(e.target.value)}>{masters?.picDept.map((p) => <option key={p}>{p}</option>)}</select></Field>
        {masters?.standardDoc?.considerations && <div className="text-xs bg-cream rounded-xl p-3"><b>Pertimbangan pemberian complimentary ({masters.standardDoc.code} bag. 5):</b> {masters.standardDoc.considerations.join(' · ')}.</div>}
        <Field label={`Bentuk kompensasi (level ${c.level || 'belum diatur'})`} required>
          <div className="grid gap-2">
            {komp.map((x) => (
              <button type="button" key={x.key} onClick={() => { setK(x.key); setNilai(x.nilai || '') }}
                className={`text-left rounded-xl border px-3 py-2.5 ${k === x.key ? 'border-brick bg-brick-soft' : 'border-line'}`}>
                <div className="font-semibold text-sm flex items-center gap-2">{x.label}{(!x.standard || !c.level) && <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#FBE3C8] text-[#8A4B00] font-bold">Di luar standard</span>}</div>
                {x.voucherJenis && <div className="text-xs text-mute">Kode {x.voucherJenis} berikutnya otomatis dipakai</div>}
              </button>
            ))}
          </div>
        </Field>
        {sel && <Field label="Nilai kompensasi (Rp)" hint="Default dari matriks, bisa diubah."><input className={inputCls} inputMode="numeric" value={nilai} onChange={(e) => setNilai(e.target.value.replace(/\D/g, ''))} /></Field>}
        <Btn className="w-full" size="lg" disabled={!rc.trim() || !k} onClick={() => onDone({ rootCause: rc, picDept: pic, kompensasiKey: k, nilaiKompensasi: nilai === '' ? null : Number(nilai) })}>Tandai Resolved</Btn>
      </div>
    </Sheet>
  )
}

function CloseSheet({ open, onClose, c, onDone }) {
  const [fu, setFu] = useState('')
  const [cc, setCc] = useState(c.costCenterFinal || '')
  const needCC = c.level === 'Critical' && c.costCenter === CC_ROOT
  return (
    <Sheet open={open} onClose={onClose} title={`Close ${c.caseId}`}>
      <div className="space-y-4">
        <Field label="Customer follow-up ulang?" required hint="Ya = customer menghubungi lagi soal masalah yang sama sebelum selesai.">
          <div className="flex gap-2"><Chip active={fu === 'N'} onClick={() => setFu('N')}>Tidak (N)</Chip><Chip active={fu === 'Y'} onClick={() => setFu('Y')}>Ya (Y)</Chip></div>
        </Field>
        {needCC && <Field label="Cost center final" required hint="Wajib untuk Critical benda asing / keracunan / tidak matang / spoiled, setelah root cause diketahui.">
          <div className="flex gap-2"><Chip active={cc === 'Factory'} onClick={() => setCc('Factory')}>Factory</Chip><Chip active={cc === 'Operasional'} onClick={() => setCc('Operasional')}>Operasional</Chip></div>
        </Field>}
        <Btn className="w-full" size="lg" disabled={!fu || (needCC && !cc)} onClick={() => onDone({ followUpUlang: fu, costCenterFinal: cc || null })}>Tandai Closed</Btn>
        <p className="text-xs text-mute">Setelah Closed, kirim link survei CSAT (tombol “Salin link survei CSAT”) agar CSAT terisi.</p>
      </div>
    </Sheet>
  )
}

function SimpleSheet({ open, onClose, title, label, onDone }) {
  const [t, setT] = useState('')
  return (
    <Sheet open={open} onClose={onClose} title={title}>
      <Field label={label}><textarea className={inputCls + ' min-h-[100px] py-2'} value={t} onChange={(e) => setT(e.target.value)} /></Field>
      <Btn className="w-full mt-4" disabled={!t.trim()} onClick={() => { onDone(t); setT('') }}>Simpan</Btn>
    </Sheet>
  )
}

function LevelSheet({ open, onClose, c, onDone }) {
  const [lv, setLv] = useState(c.level || '')
  const [r, setR] = useState('')
  return (
    <Sheet open={open} onClose={onClose} title="Ubah level">
      <div className="space-y-4">
        <div className="text-sm">Level standard untuk <b>{c.subJenis}</b>: <LevelBadge level={c.levelStandard} /></div>
        <div className="flex gap-2">{['Minor', 'Major', 'Critical'].map((l) => <Chip key={l} active={lv === l} onClick={() => setLv(l)}>{l}</Chip>)}</div>
        <Field label="Alasan" required><input className={inputCls} value={r} onChange={(e) => setR(e.target.value)} /></Field>
        <Btn className="w-full" disabled={!lv || !r.trim()} onClick={() => onDone({ level: lv, reason: r })}>Simpan</Btn>
      </div>
    </Sheet>
  )
}

function TimeSheet({ open, onClose, c, onDone }) {
  const [f, setF] = useState('waktuFirstResponse')
  const [v, setV] = useState('')
  const [r, setR] = useState('')
  useEffect(() => { setV(c[f] ? toLocalInput(c[f]) : '') }, [f, c])
  const labels = { waktuMasuk: 'Waktu masuk', waktuFirstResponse: 'First response', waktuResolved: 'Resolved', waktuClosed: 'Closed' }
  return (
    <Sheet open={open} onClose={onClose} title="Koreksi waktu (CS Lead)">
      <div className="space-y-4">
        <div className="flex flex-wrap gap-2">{Object.entries(labels).map(([k, l]) => <Chip key={k} active={f === k} onClick={() => setF(k)}>{l}</Chip>)}</div>
        <input type="datetime-local" className={inputCls} value={v} max={toLocalInput()} onChange={(e) => setV(e.target.value)} />
        {f !== 'waktuMasuk' && <Btn kind="link" onClick={() => setV('')}>Kosongkan</Btn>}
        <Field label="Alasan koreksi" required hint="Tercatat di audit log."><input className={inputCls} value={r} onChange={(e) => setR(e.target.value)} /></Field>
        <Btn className="w-full" disabled={!r.trim()} onClick={() => onDone({ field: f, value: fromLocalInput(v), reason: r })}>Simpan koreksi</Btn>
      </div>
    </Sheet>
  )
}

function EditSheet({ open, onClose, c, masters, onDone, limited }) {
  const [b, setB] = useState({})
  useEffect(() => { if (open) setB({ ringkasan: c.ringkasan, orderNo: c.orderNo || '', customerName: c.customerName || '', customerPhone: c.customerPhone || '', subJenis: c.subJenis, outletId: c.outletId, channel: c.channel, tipe: c.tipe, valid: c.valid, rootCause: c.rootCause || '', costCenterFinal: c.costCenterFinal || '', picDept: c.picDept || '' }) }, [open, c])
  const subs = (masters?.subJenis || []).map((s) => ({ value: s.name, label: s.name, sub: s.contoh, keywords: s.keywords, level: s.level }))
  const outlets = (masters?.outlets || []).map((o) => ({ value: o.id, label: o.name, sub: o.area }))
  const set = (k) => (e) => setB({ ...b, [k]: e.target ? e.target.value : e })
  const submit = () => {
    const keys = limited ? ['rootCause', 'costCenterFinal'] : Object.keys(b)
    onDone(Object.fromEntries(keys.filter((k) => b[k] !== (c[k] ?? '')).map((k) => [k, b[k]])))
  }
  return (
    <Sheet open={open} onClose={onClose} title={limited ? 'Root cause & cost center' : 'Ubah data case'} wide>
      <div className="grid gap-3 sm:grid-cols-2">
        {!limited && <>
          <div className="sm:col-span-2"><Field label="Ringkasan"><textarea className={inputCls + ' py-2 min-h-[80px]'} value={b.ringkasan || ''} onChange={set('ringkasan')} /></Field></div>
          <Field label="Sub jenis" hint="Mengubah sub jenis akan menghitung ulang level & PJ."><Combo items={subs} value={b.subJenis} onChange={set('subJenis')} renderBadge={levelItemBadge} /></Field>
          <Field label="Outlet"><Combo items={outlets} value={b.outletId} onChange={set('outletId')} /></Field>
          <Field label="Channel"><select className={inputCls} value={b.channel} onChange={set('channel')}>{masters?.channels.map((x) => <option key={x.name}>{x.name}</option>)}</select></Field>
          <Field label="Tipe"><select className={inputCls} value={b.tipe} onChange={set('tipe')}>{masters?.tipe.map((x) => <option key={x}>{x}</option>)}</select></Field>
          <Field label="Komplain valid"><select className={inputCls} value={b.valid} onChange={set('valid')}><option>Y</option><option>N</option></select></Field>
          <Field label="PIC Dept"><select className={inputCls} value={b.picDept} onChange={set('picDept')}><option value="">–</option>{masters?.picDept.map((x) => <option key={x}>{x}</option>)}</select></Field>
          <Field label="No. pesanan"><input className={inputCls} value={b.orderNo || ''} onChange={set('orderNo')} /></Field>
          <Field label="Nama customer"><input className={inputCls} value={b.customerName || ''} onChange={set('customerName')} /></Field>
          <Field label="No. HP customer"><input className={inputCls} value={b.customerPhone || ''} onChange={set('customerPhone')} /></Field>
        </>}
        <Field label="Root cause"><input className={inputCls} value={b.rootCause || ''} onChange={set('rootCause')} /></Field>
        <Field label="Cost center final"><select className={inputCls} value={b.costCenterFinal || ''} onChange={set('costCenterFinal')}><option value="">–</option><option>Factory</option><option>Operasional</option><option>Team Frozen</option></select></Field>
      </div>
      <Btn className="w-full mt-4" onClick={submit}>Simpan</Btn>
    </Sheet>
  )
}
