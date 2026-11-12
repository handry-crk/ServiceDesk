import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, useApp, useAsync, fmtDT, fmtMin, fmtPct, fmtD, presets, LEAD } from '../lib.jsx'
import { Btn, Card, ErrorBox, Skeleton, PeriodPicker, Info, inputCls } from '../ui.jsx'
import { TimeRequestBox } from './CaseDetail.jsx'

const TABS = [['pengajuan', 'Pengajuan jam'], ['cs', 'Per CS'], ['audit', 'Audit acak']]

export default function Integritas() {
  const { can } = useApp()
  const [sp, setSp] = useSearchParams()
  const tab = TABS.some(([k]) => k === sp.get('tab')) ? sp.get('tab') : 'pengajuan'
  if (!can('Admin', 'CS Lead', 'Marketing TL')) return <ErrorBox error={{ message: 'Halaman ini untuk CRM Supervisor, Marketing TL, dan Admin.' }} />
  return (
    <div>
      <h1 className="text-2xl font-extrabold">Integritas waktu</h1>
      <p className="text-sm text-mute mb-4">Memastikan jam masuk & jam dibalas sesuai chat asli: pengajuan koreksi, pengawasan per CS, dan audit acak mingguan.</p>
      <div className="flex flex-wrap gap-1 mb-4 bg-white border border-line rounded-xl p-1 w-fit">
        {TABS.map(([k, l]) => <button key={k} onClick={() => setSp(k === 'pengajuan' ? {} : { tab: k })} className={`px-4 min-h-[40px] rounded-lg text-sm font-semibold ${tab === k ? 'bg-brick text-white' : 'hover:bg-cream'}`}>{l}</button>)}
      </div>
      {tab === 'pengajuan' && <Requests lead={can(...LEAD)} />}
      {tab === 'cs' && <PerCs />}
      {tab === 'audit' && <Audits lead={can(...LEAD)} />}
    </div>
  )
}

function Requests({ lead }) {
  const { notify, user } = useApp()
  const { data, loading, error, reload } = useAsync(() => lead ? api('/time-requests') : Promise.resolve([]), [lead])
  if (!lead) return <Card className="p-4 text-sm text-mute">Persetujuan pengajuan dilakukan CRM Supervisor / Admin.</Card>
  if (loading && !data) return <Skeleton />
  const decide = async (c, d, note) => {
    try { await api(`/cases/${c.caseId}/time-request/${d}`, { method: 'POST', body: { note } }); notify(d === 'approve' ? 'Disetujui' : 'Ditolak'); reload() }
    catch (e) { notify(e.message, 'err') }
  }
  return (
    <div className="space-y-3">
      <ErrorBox error={error} />
      {data?.length === 0 && <Card className="p-4 text-ok font-semibold">Tidak ada pengajuan yang menunggu ✓</Card>}
      {data?.map((c) => (
        <Card key={c.caseId} className="p-4">
          <div className="flex flex-wrap items-center gap-2"><Link to={'/case/' + c.caseId} className="font-extrabold underline">{c.caseId}</Link>
            <span className="text-sm text-mute">{c.subJenis} · {c.outletName} · {c.channel} · masuk {fmtDT(c.waktuMasuk)}</span></div>
          <TimeRequestBox c={c} lead me={user} onDecide={(d, note) => decide(c, d, note)} />
        </Card>
      ))}
    </div>
  )
}

function PerCs() {
  const p = presets().find((x) => x.key === 'month')
  const [period, setPeriod] = useState({ from: p.from, to: p.to })
  const { data: d, loading, error } = useAsync(() => api('/integrity', { params: { frm: period.from, to: period.to } }), [period.from, period.to])
  return (
    <div className="space-y-4">
      <PeriodPicker value={period} onChange={setPeriod} />
      <ErrorBox error={error} />
      {loading && !d ? <Skeleton h="h-64" /> : d && <IntegrityBody d={d} />}
    </div>
  )
}

export function IntegrityBody({ d, compact }) {
  const t = d.total, s = d.settings
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Card className="p-4"><div className="text-sm text-mute font-semibold">Jam dibalas diisi manual<Info text={`Case yang jam dibalasnya diisi/diubah manual (bukan saat tombol ditekan). Alert bila seorang CS > ${Math.round(s.manualAlertPct * 100)}%.`} /></div>
          <div className="text-3xl font-extrabold tabnum my-1">{fmtPct(t.manualPct)}</div><div className="text-xs text-mute">{t.manual} dari {t.responded} case dibalas</div></Card>
        <Card className="p-4"><div className="text-sm text-mute font-semibold">FRT dilaporkan vs sistem<Info text="Sistem = waktu masuk sampai CS benar-benar menekan tombol. Selisih besar = banyak jam dimundurkan." /></div>
          <div className="text-3xl font-extrabold tabnum my-1">{fmtMin(t.frtReported)}</div><div className="text-xs text-mute">sistem: {fmtMin(t.frtSystem)}</div></Card>
        <Card className="p-4"><div className="text-sm text-mute font-semibold">SLA lolos karena jam manual</div>
          <div className={`text-3xl font-extrabold tabnum my-1 ${t.rescued ? 'text-brick' : ''}`}>{t.rescued}</div><div className="text-xs text-mute">{t.pending} pengajuan menunggu</div></Card>
        <Card className="p-4"><div className="text-sm text-mute font-semibold">Audit acak</div>
          <div className="text-3xl font-extrabold tabnum my-1">{t.auditOk + t.auditBad ? fmtPct(t.auditOk / (t.auditOk + t.auditBad)) : '–'}</div>
          <div className="text-xs text-mute">{t.auditOk} cocok · <span className={t.auditBad ? 'text-brick font-semibold' : ''}>{t.auditBad} tidak cocok</span> · {t.auditOpen} belum dicek</div></Card>
      </div>
      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-brick text-white text-left"><tr>{['CS', 'Dibalas', '% manual', 'Rata² mundur', 'SLA lolos krn manual', 'FRT lapor / sistem', 'Telat catat', 'Pengajuan ✓ / ✗', 'Audit ✓ / ✗', 'Perhatian'].map((h) => <th key={h} className="px-3 py-2 whitespace-nowrap">{h}</th>)}</tr></thead>
          <tbody>{d.rows.map((r) => (
            <tr key={r.name} className={`border-t border-line tabnum ${r.flags.length ? 'bg-[#FBF1DC]/60' : ''}`}>
              <td className="px-3 py-2 font-semibold">{r.name}</td><td className="px-3 py-2">{r.responded}</td>
              <td className={`px-3 py-2 ${r.manualPct > s.manualAlertPct ? 'text-brick font-bold' : ''}`}>{fmtPct(r.manualPct)}</td>
              <td className="px-3 py-2">{fmtMin(r.avgBackdate)}</td><td className={`px-3 py-2 ${r.rescued ? 'text-brick font-bold' : ''}`}>{r.rescued}</td>
              <td className="px-3 py-2 whitespace-nowrap">{fmtMin(r.frtReported)} / {fmtMin(r.frtSystem)}</td>
              <td className="px-3 py-2">{r.lateEntry}{r.avgLag ? <span className="text-xs text-mute"> (±{fmtMin(r.avgLag)})</span> : ''}</td>
              <td className="px-3 py-2">{r.approved} / <span className={r.rejected ? 'text-brick font-bold' : ''}>{r.rejected}</span>{r.pending ? <span className="text-xs text-mute"> +{r.pending} menunggu</span> : ''}</td>
              <td className="px-3 py-2">{r.auditOk} / <span className={r.auditBad ? 'text-brick font-bold' : ''}>{r.auditBad}</span></td>
              <td className="px-3 py-2 text-xs">{r.flags.length ? r.flags.join('; ') : <span className="text-ok">OK</span>}</td>
            </tr>))}
            {d.rows.length === 0 && <tr><td colSpan={10} className="px-3 py-4 text-mute">Belum ada case di periode ini.</td></tr>}
          </tbody>
        </table>
      </Card>
      {!compact && <p className="text-xs text-mute">Aturan: mundur jam dibalas ≤ {s.frGraceMin} mnt langsung diterima; sampai {s.frMaxBackMin} mnt perlu screenshot + persetujuan; lebih dari itu hanya CRM Supervisor. CS mengubah jam dibalas maksimal sekali dalam {s.frEditHours} jam. Waktu masuk &gt; {s.masukLagReasonMin} mnt sebelum dicatat wajib alasan. Periode yang dikunci di meeting tidak bisa diubah waktunya (kecuali Admin). Ubah angka di Pengaturan.</p>}
    </div>
  )
}

function Audits({ lead }) {
  const { notify } = useApp()
  const { data, loading, error, reload } = useAsync(() => api('/audits'), [])
  const [i, setI] = useState(0)
  const make = async () => { try { const r = await api('/audits', { method: 'POST', body: {} }); notify(r.created ? 'Sampel audit minggu lalu dibuat' : 'Audit minggu lalu sudah ada'); setI(0); reload() } catch (e) { notify(e.message, 'err') } }
  if (loading && !data) return <Skeleton />
  const a = data?.[i]
  return (
    <div className="space-y-4">
      <ErrorBox error={error} />
      <Card className="p-4 text-sm space-y-2">
        <p>Setiap Senin pagi sistem memilih case acak per CS dari minggu lalu (separuh dari case berjam manual). CRM Supervisor membuka chat asli lalu menandai <b>cocok</b> / <b>tidak cocok</b>. Hasilnya masuk laporan per CS dan slide meeting.</p>
        <div className="flex flex-wrap items-center gap-2">
          {lead && <Btn size="sm" onClick={make}>Buat sampel minggu lalu</Btn>}
          {data?.length > 0 && <select className={inputCls + ' !min-h-[36px] !w-auto'} value={i} onChange={(e) => setI(Number(e.target.value))}>
            {data.map((x, k) => <option key={x.id} value={k}>Minggu {fmtD(x.weekStart)} – {fmtD(x.weekEnd)}</option>)}</select>}
        </div>
      </Card>
      {!a ? <Card className="p-4 text-sm text-mute">Belum ada audit.</Card> : <AuditTable a={a} lead={lead} onSaved={reload} notify={notify} />}
    </div>
  )
}

function AuditTable({ a, lead, onSaved, notify }) {
  const [notes, setNotes] = useState({})
  const save = async (it, result) => {
    try { await api(`/audits/${a.id}/items/${it.caseId}`, { method: 'POST', body: { result, note: notes[it.caseId] || null } }); onSaved() }
    catch (e) { notify(e.message, 'err') }
  }
  const done = a.items.filter((x) => x.result).length
  return (
    <Card className="overflow-x-auto">
      <div className="p-4 pb-2 font-bold">{done} dari {a.items.length} case sudah dicek</div>
      <table className="w-full text-sm">
        <thead className="text-left text-mute"><tr>{['CS', 'Case', 'Channel', 'Masuk', 'Dibalas', 'FRT', 'Hasil'].map((h) => <th key={h} className="px-3 py-2 font-semibold">{h}</th>)}</tr></thead>
        <tbody>{a.items.map((it) => (
          <tr key={it.caseId} className="border-t border-line align-top">
            <td className="px-3 py-2 font-semibold">{it.cs}</td>
            <td className="px-3 py-2"><Link className="underline" to={'/case/' + it.caseId}>{it.caseId}</Link>{it.manual && <div className="text-[10px] text-mute">jam manual</div>}</td>
            <td className="px-3 py-2">{it.channel}</td><td className="px-3 py-2 text-xs">{fmtDT(it.waktuMasuk)}</td><td className="px-3 py-2 text-xs">{fmtDT(it.waktuFirstResponse)}</td>
            <td className="px-3 py-2 tabnum">{fmtMin(it.frtMin)}</td>
            <td className="px-3 py-2 min-w-[240px]">
              {it.result ? <div><span className={`font-bold ${it.result === 'tidak' ? 'text-brick' : 'text-ok'}`}>{it.result === 'tidak' ? 'Tidak cocok' : 'Cocok'}</span>
                <span className="text-xs text-mute"> · {it.checkedBy}</span>{it.note && <div className="text-xs">{it.note}</div>}</div>
                : lead ? <div className="space-y-1">
                  <div className="flex gap-2"><Btn size="sm" kind="ok" onClick={() => save(it, 'cocok')}>Cocok</Btn><Btn size="sm" kind="ghost" disabled={!(notes[it.caseId] || '').trim()} onClick={() => save(it, 'tidak')}>Tidak cocok</Btn></div>
                  <input className={inputCls + ' !min-h-[34px] text-xs'} placeholder="Bila tidak cocok: jam sebenarnya di chat" value={notes[it.caseId] || ''} onChange={(e) => setNotes({ ...notes, [it.caseId]: e.target.value })} />
                </div> : <span className="text-mute">Belum dicek</span>}
            </td>
          </tr>))}
          {a.items.length === 0 && <tr><td colSpan={7} className="px-3 py-4 text-mute">Tidak ada case dibalas pada minggu ini.</td></tr>}
        </tbody>
      </table>
    </Card>
  )
}
