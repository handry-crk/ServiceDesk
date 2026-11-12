import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, useAsync, fmtNum, fmtPct, fmtRp, fmtMin, fmtD, fmtDT, presets } from '../lib.jsx'
import { Card, ErrorBox, Skeleton, PeriodPicker, Info, Delta, StatusPill, LevelBadge, StatusBadge } from '../ui.jsx'
import { ChartCard, HBar, Weekly } from './Dashboard.jsx'

const BRICK = '#B42F27', MUTE = '#8A8178'
const LEVEL_COLOR = { Minor: '#9C948B', Major: '#C98A1B', Critical: BRICK }

function Tile({ label, value, sub, info, children }) {
  return (
    <Card className="p-4">
      <div className="text-sm text-mute font-semibold">{label}{info && <Info text={info} />}</div>
      <div className="text-3xl font-extrabold tabnum my-1">{value}</div>
      {sub && <div className="text-xs text-mute">{sub}</div>}
      {children}
    </Card>
  )
}

function Table({ head, rows }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-mute"><tr>{head.map((h) => <th key={h} className="py-1 pr-2 font-semibold">{h}</th>)}</tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  )
}

export function FrozenBody({ d }) {
  const m = d.metrics, v = d.volume, b = d.batch
  const row = (k) => d.table.find((r) => r.key === k)
  const ccTeam = d.costCenters.filter((r) => r.name === 'Team Frozen').reduce((s, r) => s + r.count, 0)
  const ccFactory = d.costCenters.filter((r) => r.name.startsWith('Factory')).reduce((s, r) => s + r.count, 0)
  const pctF = (x) => fmtPct(x)
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Tile label="Komplain frozen" value={fmtNum(v.komplain)} sub={`${v.open} masih open · ${v.critical} Critical`}>
          <div className="mt-2"><DeltaCount cur={v.komplain} prev={d.prevVolume.komplain} /></div>
        </Tile>
        <Tile label="% SLA Response" value={fmtPct(m.slaResponse)} sub={`FRT rata-rata ${m.frt === null ? '–' : fmtNum(m.frt) + ' mnt'}`}>
          <div className="flex items-center gap-2 mt-2"><StatusPill status={row('slaResponse')?.status} /><Delta cur={m.slaResponse} prev={d.prev.slaResponse} dir="min" isPct /></div>
        </Tile>
        <Tile label="% Same-Day Resolution" value={fmtPct(m.sameDay)} sub={`Resolusi rata-rata ${fmtMin(m.avgResolution)}`}>
          <div className="flex items-center gap-2 mt-2"><StatusPill status={row('sameDay')?.status} /><Delta cur={m.sameDay} prev={d.prev.sameDay} dir="min" isPct /></div>
        </Tile>
        <Tile label="Kode produksi terisi" value={b.rate === null ? '–' : fmtPct(b.rate)}
          sub={b.needed ? `${b.filled} dari ${b.needed} komplain produk` : 'Belum ada komplain produk'}
          info="Komplain produk = cacat produksi, penurunan mutu, kontaminasi, matang/mentah, keracunan, missing/wrong item, kesalahan kemasan. Tanpa kode produksi batch bermasalah tidak bisa ditelusuri ke Factory.">
          {b.rate !== null && <div className="h-2 rounded-full bg-cream mt-3 overflow-hidden"><div className="h-full rounded-full" style={{ width: `${Math.round(b.rate * 100)}%`, background: b.rate >= 0.8 ? '#2F7D4F' : BRICK }} /></div>}
        </Tile>
      </div>

      <Card className="p-4">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-x-4 gap-y-3">
          {[['Biaya kompensasi', fmtRp(v.biaya)], ['Di luar standard', `${fmtRp(v.biayaLuarStandard)} (${v.countLuarStandard})`],
            ['Cost center Team Frozen', `${ccTeam} case`], ['Cost center Factory', `${ccFactory} case`],
            ['Pcs kurang / rusak', d.qty.cases ? `${fmtNum(d.qty.pcsKurang)} pcs` : '–', `Dari ${d.qty.cases} case yang mengisi qty dipesan & diterima.`],
            ['CSAT komplain', fmtPct(m.csat), `${m.csatN} rating dari ${m.csatSent} survei terkirim.`]]
            .map(([l, val, info]) => <div key={l}><div className="text-xs text-mute">{l}{info && <Info text={info} />}</div><div className="text-lg font-bold tabnum">{val}</div></div>)}
        </div>
      </Card>

      {Object.keys(d.insights).length > 0 && (
        <Card className="p-4 bg-cream/60">
          <h3 className="font-bold mb-2">Catatan otomatis</h3>
          <ul className="list-disc pl-5 space-y-1 text-sm">{Object.values(d.insights).map((t) => <li key={t}>{t}</li>)}</ul>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Masalah frozen (sub jenis)">
          {d.subJenis.length ? <HBar rows={d.subJenis} colorBy={(r) => LEVEL_COLOR[r.levelStandard] || MUTE} /> : <Empty />}
        </ChartCard>
        <ChartCard title="Per toko online">
          <Table head={['Toko', 'Case', 'Open', 'FRT', '% Same-day']} rows={d.stores.map((r) => (
            <tr key={r.name} className="border-t border-line tabnum"><td className="py-1.5 pr-2">{r.name}</td><td>{r.count}</td><td>{r.open}</td><td>{fmtMin(r.avgFrt)}</td><td>{fmtPct(r.sameDay)}</td></tr>))} />
        </ChartCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Per ekspedisi" info="Ekspedisi diambil dari isian case (atau catatan sheet lama). Banyak case 'Belum diisi' = minta CS mengisi ekspedisi.">
          {d.couriers.length ? <HBar rows={d.couriers} colorBy={(r) => r.name === 'Belum diisi' ? '#D8D0C4' : '#8E6B5E'} /> : <Empty />}
        </ChartCard>
        <ChartCard title="Per produk (top 10)">
          {d.products.length ? <HBar rows={d.products} colorBy={(r) => r.name === 'Belum diisi' ? '#D8D0C4' : BRICK} /> : <Empty />}
        </ChartCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Kode produksi berulang" info="Kode produksi yang muncul di ≥ 2 komplain pada periode ini — kandidat batch bermasalah untuk dicek Factory / QC.">
          {b.repeat.length === 0 ? <p className="text-sm text-mute">{b.filled ? 'Tidak ada kode produksi yang muncul di lebih dari 1 komplain.' : 'Belum ada kode produksi yang diisi.'}</p> :
            <Table head={['Kode produksi', 'Komplain', 'Masalah', 'Produk', 'Case']} rows={b.repeat.map((r) => (
              <tr key={r.kode} className="border-t border-line"><td className="py-1.5 pr-2 font-bold">{r.kode}</td><td className="tabnum text-brick font-bold">{r.count}</td><td>{r.subJenis}</td><td className="text-mute">{r.produk || '–'}</td>
                <td className="text-xs">{r.cases.map((id) => <Link key={id} to={'/case/' + id} className="underline mr-1">{id}</Link>)}</td></tr>))} />}
        </ChartCard>
        <ChartCard title="Root cause & PIC">
          <Table head={['Root cause', 'Case']} rows={d.rootCauses.map((r) => <tr key={r.name} className="border-t border-line"><td className={`py-1.5 pr-2 ${r.name === 'Belum diisi' ? 'text-mute' : ''}`}>{r.name}</td><td className="tabnum">{r.count}</td></tr>)} />
          <div className="flex flex-wrap gap-2 mt-3">{d.picDept.map((r) => <span key={r.name} className="rounded-lg bg-cream px-2 py-1 text-xs">{r.name}: <b>{r.count}</b></span>)}</div>
        </ChartCard>
      </div>

      <Card className="p-4">
        <h3 className="font-bold mb-2">Tren mingguan frozen</h3>
        <div className="grid gap-4 md:grid-cols-3">
          <div><div className="text-sm font-semibold">Komplain</div><Weekly weeks={d.weeks} k="komplain" name="Komplain" fmt={fmtNum} /></div>
          <div><div className="text-sm font-semibold">% SLA Response</div><Weekly weeks={d.weeks} k="slaResponse" name="SLA Response" fmt={pctF} target={d.targets.slaResponse.target} /></div>
          <div><div className="text-sm font-semibold">% Same-Day</div><Weekly weeks={d.weeks} k="sameDay" name="Same-Day" fmt={pctF} target={d.targets.sameDay.target} /></div>
        </div>
      </Card>

      <Card className="p-4">
        <h3 className="font-bold mb-2">Komplain frozen masih open ({d.open.length})</h3>
        {d.open.length === 0 ? <p className="text-sm text-ok font-semibold">Tidak ada yang open ✓</p> :
          <Table head={['Case', 'Masuk', 'Toko', 'Masalah', 'Level', 'Status', 'Kode produksi']} rows={d.open.map((c) => (
            <tr key={c.caseId} className="border-t border-line">
              <td className="py-1.5 pr-2"><Link className="font-bold underline" to={'/case/' + c.caseId}>{c.caseId}</Link></td>
              <td className="text-xs">{fmtDT(c.waktuMasuk)}</td><td>{c.outletName}</td><td>{c.subJenis}</td>
              <td><LevelBadge level={c.level} /></td><td><StatusBadge status={c.status} /></td><td className={c.kodeProduksi ? '' : 'text-mute'}>{c.kodeProduksi || '–'}</td>
            </tr>))} />}
      </Card>
    </div>
  )
}

function DeltaCount({ cur, prev }) {
  if (prev === undefined || prev === null) return null
  const d = cur - prev
  if (!d) return <span className="text-xs text-mute">sama dgn periode lalu</span>
  return <span className={`text-xs font-semibold ${d < 0 ? 'text-ok' : 'text-brick'}`}>{d > 0 ? '▲' : '▼'} {d > 0 ? '+' : ''}{d} case vs periode lalu</span>
}

const Empty = () => <p className="text-sm text-mute">Belum ada data.</p>

export default function Frozen() {
  const p = presets().find((x) => x.key === 'month')
  const [period, setPeriod] = useState({ from: p.from, to: p.to })
  const { data: d, loading, error } = useAsync(() => api('/dashboard/frozen', { params: period }), [period.from, period.to])
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <PeriodPicker value={period} onChange={setPeriod} />
        {d && <span className="text-sm text-mute">Toko Online Frozen (Shopee, TikTok) · dibandingkan {fmtD(d.period.prevFrom)} – {fmtD(d.period.prevTo)}</span>}
      </div>
      <ErrorBox error={error} />
      {loading && !d ? <div className="grid gap-3"><Skeleton /><Skeleton h="h-64" /></div> : d && <div className={loading ? 'opacity-60 transition' : 'transition'}><FrozenBody d={d} /></div>}
    </div>
  )
}
