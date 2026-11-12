import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { api, useApp, useAsync, fmtNum, fmtPct, fmtRp, fmtD, fmtDT, presets, WRITERS } from '../lib.jsx'
import { Card, ErrorBox, Skeleton, PeriodPicker, Info, LevelBadge, Btn, Chip, inputCls } from '../ui.jsx'
import { KodeLookup } from '../components.jsx'

const BRICK = '#B42F27', MUTE = '#8A8178', GRID = '#EDE6D9'
const ST_CLS = { Terpakai: 'bg-[#E3F1E6] text-[#1F6B3A]', Diterbitkan: 'bg-[#FBF1DC] text-[#7A5410]', Hangus: 'bg-[#F3E1DF] text-brick', 'Tanpa kode': 'bg-cream text-mute' }
const ST_LABEL = { Diterbitkan: 'Belum dipakai', Terpakai: 'Terpakai / diterima' }

function Tile({ label, value, sub, info, tone }) {
  return (
    <Card className="p-4">
      <div className="text-sm text-mute font-semibold">{label}{info && <Info text={info} />}</div>
      <div className={`text-3xl font-extrabold tabnum my-1 ${tone || ''}`}>{value}</div>
      {sub && <div className="text-xs text-mute">{sub}</div>}
    </Card>
  )
}

export function GroupTable({ title, rows, nameLabel }) {
  return (
    <Card className="p-4 overflow-x-auto">
      <h3 className="font-bold mb-2">{title}</h3>
      <table className="w-full text-sm">
        <thead className="text-left text-mute"><tr>{[nameLabel, 'Case', 'Biaya', 'Kode', 'Terpakai', 'Luar std'].map((h) => <th key={h} className="py-1 pr-2 font-semibold">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.name} className="border-t border-line tabnum">
            <td className="py-1.5 pr-2">{['Minor', 'Major', 'Critical'].includes(r.name) ? <LevelBadge level={r.name} /> : r.name}</td>
            <td>{r.count}</td><td>{fmtRp(r.biaya)}</td><td>{r.voucher}</td><td>{r.voucher ? `${r.terpakai} (${fmtPct(r.terpakai / r.voucher)})` : '–'}</td>
            <td className={r.luarStandard ? 'text-[#8A4B00] font-semibold' : ''}>{r.luarStandard}</td>
          </tr>))}
          {rows.length === 0 && <tr><td colSpan={6} className="py-3 text-mute">Belum ada data.</td></tr>}
        </tbody>
      </table>
    </Card>
  )
}

export function KompSummary({ d }) {
  const s = d.summary
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <Tile label="Case diberi complimentary" value={fmtNum(s.cases)} sub={`${fmtPct(s.pctDiberi)} komplain diberi complimentary (${s.komplainDiberi}/${s.komplainTotal}) · ${s.luarStandard} di luar standard`} />
      <Tile label="Biaya complimentary" value={fmtRp(s.biaya)} sub={`Di luar standard ${fmtRp(s.biayaLuarStandard)}`} />
      <Tile label="Voucher terpakai" value={fmtPct(s.redemption)} info="Terpakai ÷ (terpakai + hangus). Voucher yang masih aktif belum dihitung."
        sub={`${s.terpakai} terpakai · ${s.hangus} hangus · ${s.aktif} masih aktif${s.avgHariDipakai != null ? ` · rata² dipakai ${fmtNum(s.avgHariDipakai)} hari` : ''}`} />
      <Tile label="Kode belum dipakai" value={fmtNum(s.aktif)} tone={s.segeraHangus ? 'text-brick' : ''}
        sub={`Nilai ${fmtRp(s.nilaiAktif)} · ${s.segeraHangus} hangus ≤ 7 hari${s.tanpaKode ? ` · ${s.tanpaKode} case lama tanpa kode` : ''}`} info={`Kode voucher / porsi pengganti / kit berlaku ${d.expiryDays} hari sejak diterbitkan; refund & cover pengobatan tanpa batas. Ingatkan customer sebelum hangus.`} />
    </div>
  )
}

function WeekTip({ active, payload, label, weeks }) {
  if (!active || !payload?.length) return null
  const w = weeks.find((y) => y.week === label)
  return <div className="bg-white border border-line rounded-xl shadow px-3 py-2 text-xs"><div className="font-semibold">{label}: {fmtD(w.start)} – {fmtD(w.end)}</div>Biaya <b>{fmtRp(w.biaya)}</b> · {w.count} case</div>
}

export default function Kompensasi({ brand, area, line }) {
  const { can, notify } = useApp()
  const p = presets().find((x) => x.key === 'month')
  const [period, setPeriod] = useState({ from: p.from, to: p.to })
  const [st, setSt] = useState('')
  const [q, setQ] = useState('')
  const { data: d, loading, error, reload } = useAsync(() => api('/kompensasi-tracker', { params: { ...period, brand, area, line } }), [period.from, period.to, brand, area, line])
  const rows = useMemo(() => (d?.rows || []).filter((r) => (!st || r.status === st || (st === 'segera' && r.sisaHari != null && r.sisaHari <= 7))
    && (!q || `${r.caseId} ${r.outlet} ${r.kode || ''} ${r.subJenis}`.toLowerCase().includes(q.toLowerCase()))), [d, st, q])
  const markUsed = async (r) => {
    try { await api(`/vouchers/${r.kode}/status`, { method: 'POST', body: { status: 'Terpakai' } }); notify(`${r.kode} ditandai terpakai`); reload() }
    catch (e) { notify(e.message, 'err') }
  }
  return (
    <div className="space-y-4">
      <Card className="p-4">
        <h3 className="font-bold mb-1">Cek / pakai kode complimentary</h3>
        <p className="text-xs text-mute mb-2">Setiap complimentary (voucher, porsi pengganti, complimentary kit, refund, cover pengobatan) punya kode. Saat customer menukar di outlet atau refund sudah ditransfer, cek kodenya di sini lalu tandai terpakai.</p>
        <KodeLookup onDone={reload} />
      </Card>
      <PeriodPicker value={period} onChange={setPeriod} />
      <ErrorBox error={error} />
      {loading && !d ? <Skeleton h="h-64" /> : d && <div className={`space-y-4 ${loading ? 'opacity-60' : ''}`}>
        <KompSummary d={d} />
        <div className="grid gap-4 lg:grid-cols-2">
          <GroupTable title="Per bentuk complimentary" rows={d.byJenis} nameLabel="Bentuk" />
          <GroupTable title="Per level komplain" rows={d.byLevel} nameLabel="Level" />
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <GroupTable title="Outlet terbanyak diberi complimentary" rows={d.byOutlet} nameLabel="Outlet" />
          <Card className="p-4">
            <h3 className="font-bold mb-2">Biaya per minggu</h3>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={d.weeks} margin={{ left: 0, right: 8, top: 10, bottom: 0 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="week" tick={{ fontSize: 12, fill: MUTE }} tickLine={false} axisLine={{ stroke: GRID }} />
                <YAxis tick={{ fontSize: 12, fill: MUTE }} tickLine={false} axisLine={false} width={56} tickFormatter={(v) => v >= 1000 ? `${Math.round(v / 1000)}rb` : v} />
                <Tooltip content={<WeekTip weeks={d.weeks} />} cursor={{ fill: '#F5F0E6' }} />
                <Bar dataKey="biaya" fill={BRICK} radius={[4, 4, 0, 0]} maxBarSize={36} />
              </BarChart>
            </ResponsiveContainer>
            <div className="flex flex-wrap gap-2 mt-2">{d.byCostCenter.map((r) => <span key={r.name} className="rounded-lg bg-cream px-2 py-1 text-xs">Cost center {r.name}: <b>{fmtRp(r.biaya)}</b> ({r.count})</span>)}</div>
          </Card>
        </div>
        <Card className="overflow-x-auto">
          <div className="p-4 pb-2 flex flex-wrap items-center gap-2">
            <h3 className="font-bold mr-2">Daftar complimentary ({rows.length})</h3>
            {[['', 'Semua'], ['Diterbitkan', 'Belum dipakai'], ['segera', 'Hangus ≤ 7 hari'], ['Terpakai', 'Terpakai'], ['Hangus', 'Hangus'], ['Tanpa kode', 'Tanpa kode']].map(([k, l]) => <Chip key={k} active={st === k} onClick={() => setSt(k)} className="!min-h-[34px] text-xs">{l}</Chip>)}
            <input className={inputCls + ' !min-h-[36px] w-48 ml-auto'} placeholder="Cari case / outlet / kode" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <table className="w-full text-sm">
            <thead className="text-left text-mute"><tr>{['Tanggal', 'Case', 'Outlet', 'Masalah', 'Level', 'Complimentary', 'Nilai', 'Kode', 'Status', 'Kadaluarsa / dipakai', ''].map((h) => <th key={h} className="px-3 py-2 font-semibold whitespace-nowrap">{h}</th>)}</tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.caseId} className="border-t border-line align-top">
                <td className="px-3 py-2 whitespace-nowrap">{fmtD(r.tanggal)}</td>
                <td className="px-3 py-2 whitespace-nowrap"><Link className="underline font-semibold" to={'/case/' + r.caseId}>{r.caseId}</Link></td>
                <td className="px-3 py-2">{r.outlet}</td><td className="px-3 py-2">{r.subJenis}</td><td className="px-3 py-2"><LevelBadge level={r.level === 'Belum Diatur' ? null : r.level} /></td>
                <td className="px-3 py-2">{r.label}{r.luarStandard && <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded bg-[#FBE3C8] text-[#8A4B00] font-bold">Luar std</span>}</td>
                <td className="px-3 py-2 tabnum whitespace-nowrap">{fmtRp(r.nilai)}</td>
                <td className="px-3 py-2 font-mono text-xs">{r.kode || '–'}</td>
                <td className="px-3 py-2 whitespace-nowrap"><span className={`text-xs px-2 py-0.5 rounded-md font-semibold ${ST_CLS[r.status] || 'bg-cream'}`}>{ST_LABEL[r.status] || r.status}</span></td>
                <td className="px-3 py-2 text-xs whitespace-nowrap">{r.status === 'Terpakai' ? <>dipakai {fmtDT(r.dipakai)}{r.outletPemakaian ? ` · ${r.outletPemakaian}` : ''}</> : r.noExpiry && r.status === 'Diterbitkan' ? <span className="text-mute">tanpa batas (proses manual)</span> : r.kadaluarsa ? <span className={r.sisaHari != null && r.sisaHari <= 7 ? 'text-brick font-semibold' : ''}>{fmtD(r.kadaluarsa)}{r.sisaHari != null ? ` (${r.sisaHari} hari lagi)` : ''}</span> : '–'}</td>
                <td className="px-3 py-2">{r.status === 'Diterbitkan' && can(...WRITERS) && <Btn size="sm" kind="ghost" onClick={() => markUsed(r)}>Tandai terpakai</Btn>}</td>
              </tr>))}
              {rows.length === 0 && <tr><td colSpan={11} className="px-3 py-4 text-mute">Tidak ada data.</td></tr>}
            </tbody>
          </table>
        </Card>
      </div>}
    </div>
  )
}
