import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import Compare from './Compare.jsx'
import Frozen from './Frozen.jsx'
import Kompensasi from './Kompensasi.jsx'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, CartesianGrid, Cell, LabelList } from 'recharts'
import { api, useApp, useAsync, fmtNum, fmtPct, fmtRp, fmtMin, presets, fmtD } from '../lib.jsx'
import { Card, ErrorBox, Skeleton, PeriodPicker, StatusPill, Info, Delta, CARA_HITUNG, LevelBadge, inputCls } from '../ui.jsx'

const BRICK = '#B42F27', MUTE = '#8A8178', GRID = '#EDE6D9'
const LEVEL_COLOR = { Minor: '#9C948B', Major: '#C98A1B', Critical: BRICK }
const axis = { fontSize: 12, fill: MUTE }

export function Tip({ active, payload, label, fmt = fmtNum, labelFmt }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-white border border-line rounded-xl shadow px-3 py-2 text-xs">
      <div className="font-semibold mb-1">{labelFmt ? labelFmt(label) : label}</div>
      {payload.map((p) => <div key={p.dataKey} className="text-ink">{p.name}: <b>{fmt(p.value, p.dataKey)}</b></div>)}
    </div>
  )
}

export const ChartCard = ({ title, insight, children, info, className = '' }) => (
  <Card className={`p-4 ${className}`}>
    <h3 className="font-bold mb-1">{title}{info && <Info text={info} />}</h3>
    {children}
    {insight && <p className="text-sm text-mute mt-2">{insight}</p>}
  </Card>
)

export function Headline({ d }) {
  const tiles = [
    { k: 'frt', label: 'FRT rata-rata', v: d.metrics.frt === null ? '–' : `${fmtNum(d.metrics.frt)} mnt`, sub: `Jam kerja: ${d.metrics.frtWork === null ? '–' : fmtNum(d.metrics.frtWork) + ' mnt'}${d.metrics.frtSystem != null ? ` · sistem: ${fmtNum(d.metrics.frtSystem)} mnt` : ''}${d.metrics.manualPct ? ` · ${fmtPct(d.metrics.manualPct)} jam manual` : ''}` },
    { k: 'slaResponse', label: '% SLA Response', v: fmtPct(d.metrics.slaResponse) },
    { k: 'sameDay', label: '% Same-Day Resolution', v: fmtPct(d.metrics.sameDay) },
    { k: 'csat', label: 'CSAT komplain (% puas)', v: fmtPct(d.metrics.csat),
      sub: d.metrics.csatN ? `${d.metrics.csatN} rating · respons ${fmtPct(d.metrics.csatResponse)} dari ${d.metrics.csatSent} survei terkirim` : (d.metrics.csatSent ? `${d.metrics.csatSent} survei terkirim, belum ada jawaban` : 'Belum ada survei case terkirim'),
      extra: { label: 'CSAT outlet (form)', v: fmtPct(d.metrics.csatOutlet), n: d.metrics.csatOutletN, prev: d.prev?.csatOutlet } },
  ]
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      {tiles.map((t) => {
        const row = d.table.find((r) => r.key === t.k)
        const tg = d.targets[t.k]
        return (
          <Card key={t.k} className="p-4">
            <div className="text-sm text-mute font-semibold">{t.label}<Info text={CARA_HITUNG[t.k]} /></div>
            <div className="text-3xl font-extrabold tabnum my-1">{t.v}</div>
            {t.sub && <div className="text-xs text-mute">{t.sub}</div>}
            <div className="flex flex-wrap items-center gap-2 mt-2">
              <span className="text-xs text-mute">Target {tg.dir === 'max' ? '≤' : '≥'} {t.k === 'frt' ? `${tg.target} mnt` : fmtPct(tg.target)}</span>
              <StatusPill status={row?.status} />
            </div>
            <div className="mt-1"><Delta cur={d.metrics[t.k]} prev={d.prev[t.k]} dir={tg.dir} isPct={t.k !== 'frt'} /></div>
            {t.extra && <div className="mt-3 pt-3 border-t border-line">
              <div className="text-xs text-mute font-semibold">{t.extra.label}<Info text="Rating keseluruhan 4–5 dari form survei outlet (pembeli umum di gerobak), bukan dari customer yang komplain." /></div>
              <div className="flex items-baseline gap-2"><span className="text-xl font-extrabold tabnum">{t.extra.v}</span><span className="text-xs text-mute">{t.extra.n ? `${t.extra.n} respons` : 'belum ada respons'}</span></div>
              <Delta cur={d.metrics.csatOutlet} prev={t.extra.prev} dir="min" isPct />
            </div>}
          </Card>
        )
      })}
    </div>
  )
}

export function Volume({ d }) {
  const v = d.volume
  const items = [
    ['Total customer contact', fmtNum(v.contact)], ['Inquiry', fmtNum(v.inquiry)], ['Komplain', fmtNum(v.komplain)],
    ['Komplain valid', fmtNum(v.komplainValid)], ['Masih open', fmtNum(v.open)],
    ['Komplain per 1.000 trx', v.per1000 === null ? <Link to="/pengaturan?tab=transaksi" className="text-sm text-brick underline">Isi total transaksi</Link> : fmtNum(v.per1000), CARA_HITUNG.per1000],
    ['Biaya kompensasi', fmtRp(v.biaya)], ['Di luar standard', <span key="x">{fmtRp(v.biayaLuarStandard)} <span className="text-sm text-mute">({v.countLuarStandard} case)</span></span>],
    ['Komplain Critical', <span key="c" className="text-brick">{v.critical}</span>],
  ]
  return (
    <Card className="p-4">
      <h3 className="font-bold mb-3">Volume</h3>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-x-4 gap-y-3">
        {items.map(([l, val, info]) => <div key={l}><div className="text-xs text-mute">{l}{info && <Info text={info} />}</div><div className="text-xl font-bold tabnum">{val}</div></div>)}
      </div>
    </Card>
  )
}

export function MetricsTable({ d }) {
  return (
    <Card className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-brick text-white text-left"><tr>{['Kelompok', 'Metric', 'Aktual', 'Target', 'Status'].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr></thead>
        <tbody>
          {d.table.map((r) => {
            const isMin = ['frt', 'avgResolution'].includes(r.key)
            const f = (x) => x === null || x === undefined ? '–' : isMin ? `${fmtNum(x)} mnt` : fmtPct(x)
            return (
              <tr key={r.key} className="border-t border-line">
                <td className="px-3 py-2 text-mute">{r.group}</td>
                <td className="px-3 py-2 font-medium">{r.label}<Info text={CARA_HITUNG[r.key]} /></td>
                <td className="px-3 py-2 font-bold tabnum">{f(r.actual)}</td>
                <td className="px-3 py-2 tabnum">{r.dir === 'max' ? '≤' : '≥'} {f(r.target)}</td>
                <td className="px-3 py-2"><StatusPill status={r.status} /></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </Card>
  )
}

export function LevelTable({ d }) {
  return (
    <Card className="overflow-x-auto">
      <h3 className="font-bold p-4 pb-2">Komplain per level (CRM.STD.001)</h3>
      <table className="w-full text-sm">
        <thead className="text-left text-mute"><tr>{['Level', 'Jumlah', '%', 'Masih open', '% Same-day', 'Penanggung jawab', 'Biaya'].map((h) => <th key={h} className="px-3 py-2 font-semibold">{h}</th>)}</tr></thead>
        <tbody>
          {d.levels.map((r) => (
            <tr key={r.name} className="border-t border-line">
              <td className="px-3 py-2"><LevelBadge level={r.name === 'Belum Terklasifikasi' ? null : r.name} /></td>
              <td className="px-3 py-2 font-bold tabnum">{r.count}</td><td className="px-3 py-2 tabnum">{fmtPct(r.pct)}</td>
              <td className="px-3 py-2 tabnum">{r.open}</td><td className="px-3 py-2 tabnum">{fmtPct(r.sameDay)}</td>
              <td className="px-3 py-2">{r.pj}</td><td className="px-3 py-2 tabnum">{fmtRp(r.biaya)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

export function MemberTable({ d }) {
  const tg = d.targets.frt?.target
  const rows = d.members || []
  return (
    <Card className="overflow-x-auto">
      <h3 className="font-bold p-4 pb-1">First response per member<Info text="Dihitung per orang yang menekan Sudah dibalas (data impor sheet lama: kolom CS agent). FRT = waktu dibalas − waktu masuk. Sistem = jam tombol benar-benar ditekan." /></h3>
      <p className="text-xs text-mute px-4 pb-2">Target FRT rata-rata ≤ {tg} mnt · target per channel tetap dipakai untuk % SLA.</p>
      <table className="w-full text-sm">
        <thead className="text-left text-mute"><tr>{['Member', 'Dibalas', 'FRT rata-rata', 'Median', 'Jam kerja', '% SLA', 'Telat', 'Critical telat', 'FRT sistem', '% jam manual'].map((h) => <th key={h} className="px-3 py-2 font-semibold whitespace-nowrap">{h}</th>)}</tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.name} className="border-t border-line tabnum">
            <td className="px-3 py-2 font-semibold">{r.name}</td><td className="px-3 py-2">{r.count}</td>
            <td className={`px-3 py-2 font-bold ${r.onTarget === false ? 'text-brick' : r.onTarget ? 'text-ok' : ''}`}>{fmtMin(r.avgFrt)}</td>
            <td className="px-3 py-2">{fmtMin(r.medianFrt)}</td><td className="px-3 py-2">{fmtMin(r.avgFrtWork)}</td>
            <td className="px-3 py-2">{fmtPct(r.slaResponse)}</td><td className="px-3 py-2">{r.late}</td>
            <td className={`px-3 py-2 ${r.criticalLate ? 'text-brick font-bold' : ''}`}>{r.criticalLate}/{r.critical}</td>
            <td className="px-3 py-2">{fmtMin(r.frtSystem)}</td><td className="px-3 py-2">{fmtPct(r.manualPct)}</td>
          </tr>))}
          {rows.length === 0 && <tr><td colSpan={10} className="px-3 py-4 text-mute">Belum ada case yang dibalas.</td></tr>}
        </tbody>
      </table>
    </Card>
  )
}

export function LevelBreakdown({ d, meeting }) {
  const [open, setOpen] = useState('Critical')
  const ld = d.levelDetail
  if (!ld) return null
  return (
    <Card className="p-4">
      <h3 className="font-bold mb-1">Breakdown komplain per level & tren</h3>
      <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr] mt-2">
        <div className="space-y-2">
          {ld.levels.map((lv) => {
            const isOpen = meeting || open === lv.level
            const max = Math.max(...lv.subJenis.map((x) => x.count), 1)
            return (
              <div key={lv.level} className="rounded-xl border border-line">
                <button type="button" onClick={() => setOpen(isOpen && !meeting ? null : lv.level)} className="w-full flex flex-wrap items-center gap-2 px-3 py-2 text-left">
                  <LevelBadge level={lv.level === 'Belum Terklasifikasi' ? null : lv.level} />
                  <span className="font-extrabold tabnum">{lv.count} case</span><span className="text-xs text-mute">{fmtPct(lv.pct)} · {lv.open} open · same-day {fmtPct(lv.sameDay)} · {fmtRp(lv.biaya)}</span>
                  {!meeting && <span className="ml-auto text-mute">{isOpen ? '▾' : '▸'}</span>}
                </button>
                {isOpen && <div className="px-3 pb-3 space-y-1.5">
                  {lv.subJenis.map((x) => (
                    <div key={x.name} className="grid grid-cols-[minmax(0,1fr)_2fr_auto] items-center gap-2 text-sm" title={x.outlets.join(', ')}>
                      <span className="truncate">{x.name}</span>
                      <div className="h-3 rounded bg-cream"><div className="h-3 rounded" style={{ width: `${(x.count / max) * 100}%`, background: LEVEL_COLOR[lv.level] || MUTE }} /></div>
                      <span className="tabnum font-semibold w-16 text-right">{x.count} <span className="text-xs text-mute font-normal">{fmtPct(x.pct)}</span></span>
                    </div>))}
                </div>}
              </div>
            )
          })}
          {ld.levels.length === 0 && <p className="text-sm text-mute">Belum ada komplain.</p>}
        </div>
        <div>
          <div className="text-sm font-semibold mb-1">Tren mingguan per level</div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={ld.weeks} margin={{ left: 0, right: 8, top: 10, bottom: 0 }} barCategoryGap="25%">
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="week" tick={axis} tickLine={false} axisLine={{ stroke: GRID }} />
              <YAxis tick={axis} tickLine={false} axisLine={false} width={32} allowDecimals={false} />
              <Tooltip content={<LevelTip weeks={ld.weeks} />} cursor={{ fill: '#F5F0E6' }} />
              {['Minor', 'Major', 'Critical'].map((k, i) => <Bar key={k} dataKey={k} stackId="l" fill={LEVEL_COLOR[k]} stroke="#fff" strokeWidth={1} radius={i === 2 ? [4, 4, 0, 0] : 0} maxBarSize={36} />)}
            </BarChart>
          </ResponsiveContainer>
          <div className="flex gap-3 text-xs text-mute">{['Minor', 'Major', 'Critical'].map((k) => <span key={k} className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm" style={{ background: LEVEL_COLOR[k] }} />{k}</span>)}</div>
          <table className="w-full text-xs mt-3">
            <thead className="text-left text-mute"><tr><th className="py-1">Minggu</th><th>Minor</th><th>Major</th><th>Critical</th><th>Isi Critical</th></tr></thead>
            <tbody>{ld.weeks.map((w) => <tr key={w.week} className="border-t border-line tabnum align-top"><td className="py-1 font-semibold whitespace-nowrap">{w.week} <span className="text-mute font-normal">{fmtD(w.start)}</span></td><td>{w.Minor}</td><td>{w.Major}</td><td className={w.Critical ? 'text-brick font-bold' : ''}>{w.Critical}</td>
              <td>{Object.entries(w.criticalDetail).map(([k, v]) => `${k} ${v}`).join(', ') || '–'}</td></tr>)}</tbody>
          </table>
        </div>
      </div>
      <ul className="mt-3 text-sm space-y-0.5">{ld.levels.filter((l) => l.level !== 'Minor').map((l) => <li key={l.level}>• {l.summary}</li>)}</ul>
    </Card>
  )
}

function LevelTip({ active, payload, label, weeks }) {
  if (!active || !payload?.length) return null
  const w = weeks.find((x) => x.week === label)
  return (
    <div className="bg-white border border-line rounded-xl shadow px-3 py-2 text-xs">
      <div className="font-semibold mb-1">{label}: {fmtD(w.start)} – {fmtD(w.end)}</div>
      {[...payload].reverse().map((p) => <div key={p.dataKey}>{p.dataKey}: <b>{p.value}</b></div>)}
      {Object.keys(w.criticalDetail).length > 0 && <div className="mt-1 text-brick">Critical: {Object.entries(w.criticalDetail).map(([k, v]) => `${k} ${v}`).join(', ')}</div>}
    </div>
  )
}

export function HBar({ rows, dataKey = 'count', name = 'Jumlah', height, color = BRICK, colorBy, fmt = fmtNum, link }) {
  const h = height || Math.max(160, rows.length * 34 + 30)
  return (
    <ResponsiveContainer width="100%" height={h}>
      <BarChart data={rows} layout="vertical" margin={{ left: 0, right: 40, top: 4, bottom: 4 }} barCategoryGap={6}>
        <XAxis type="number" hide />
        <YAxis type="category" dataKey="name" width={170} tick={{ ...axis, fill: '#2B2522' }} tickLine={false} axisLine={false} />
        <Tooltip content={<Tip fmt={fmt} />} cursor={{ fill: '#F5F0E6' }} />
        <Bar dataKey={dataKey} name={name} radius={[0, 4, 4, 0]} maxBarSize={22} onClick={link ? (e) => link(e) : undefined} cursor={link ? 'pointer' : undefined}>
          {rows.map((r) => <Cell key={r.name} fill={colorBy ? colorBy(r) : color} />)}
          <LabelList dataKey={dataKey} position="right" formatter={fmt} style={{ fontSize: 12, fill: '#2B2522' }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export function Weekly({ weeks, k, name, fmt, target }) {
  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={weeks} margin={{ left: 0, right: 16, top: 10, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="week" tick={axis} tickLine={false} axisLine={{ stroke: GRID }} />
        <YAxis tick={axis} tickLine={false} axisLine={false} width={44} tickFormatter={fmt} />
        <Tooltip content={<Tip fmt={fmt} labelFmt={(w) => { const x = weeks.find((y) => y.week === w); return x ? `${w}: ${fmtD(x.start)} – ${fmtD(x.end)}` : w }} />} />
        <Line type="monotone" dataKey={k} name={name} stroke={BRICK} strokeWidth={2} dot={{ r: 4, fill: BRICK, stroke: '#fff', strokeWidth: 2 }} connectNulls />
        {target !== undefined && <Line dataKey={() => target} name="Target" stroke={MUTE} strokeDasharray="4 4" strokeWidth={1.5} dot={false} />}
      </LineChart>
    </ResponsiveContainer>
  )
}

export function HourChart({ hours }) {
  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={hours} margin={{ left: 0, right: 8, top: 10, bottom: 0 }} barCategoryGap={2}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="hour" tick={axis} tickLine={false} axisLine={{ stroke: GRID }} interval={1} />
        <YAxis tick={axis} tickLine={false} axisLine={false} width={44} />
        <Tooltip content={<Tip labelFmt={(h) => `Jam ${String(h).padStart(2, '0')}.00–${String(h).padStart(2, '0')}.59`} fmt={(v, k) => k === 'avgFrt' ? fmtMin(v) : fmtNum(v)} />} cursor={{ fill: '#F5F0E6' }} />
        <Bar dataKey="avgFrt" name="FRT rata-rata" radius={[4, 4, 0, 0]} maxBarSize={18}>
          {hours.map((h) => <Cell key={h.hour} fill={h.hour >= 19 || h.hour < 8 ? BRICK : '#D9A39E'} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export function DashboardBody({ d, meeting }) {
  const pctF = (v) => fmtPct(v)
  return (
    <div className="space-y-4">
      <Headline d={d} />
      <Volume d={d} />
      <div className="grid gap-4 lg:grid-cols-2">
        <MetricsTable d={d} />
        <LevelTable d={d} />
      </div>
      <LevelBreakdown d={d} />
      <MemberTable d={d} />
      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Komplain per sub jenis (top 10)" insight={d.insights.subJenis}>
          <HBar rows={d.subJenis.slice(0, 10)} colorBy={(r) => LEVEL_COLOR[r.levelStandard] || MUTE}
            link={meeting ? undefined : (e) => (location.href = `/case?subJenis=${encodeURIComponent(e.name)}&from=${d.period.from}&to=${d.period.to}`)} />
          <div className="flex gap-3 text-xs text-mute mt-1">{Object.entries(LEVEL_COLOR).map(([k, c]) => <span key={k} className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm" style={{ background: c }} />{k}</span>)}<span className="flex items-center gap-1"><span className="w-3 h-3 rounded-sm" style={{ background: MUTE }} />Belum diatur</span></div>
        </ChartCard>
        <ChartCard title="FRT rata-rata per jam masuk" insight={d.insights.hour} info="Merah tua = chat masuk ≥ 19.00 atau < 08.00.">
          <HourChart hours={d.hours} />
        </ChartCard>
      </div>
      <Card className="p-4">
        <h3 className="font-bold mb-2">Tren mingguan <span className="text-xs text-mute font-normal">(blok 7 hari dari awal periode)</span></h3>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <div><div className="text-sm font-semibold">Komplain</div><Weekly weeks={d.weeks} k="komplain" name="Komplain" fmt={fmtNum} /></div>
          <div><div className="text-sm font-semibold">FRT (menit)</div><Weekly weeks={d.weeks} k="frt" name="FRT" fmt={fmtNum} target={d.targets.frt.target} /></div>
          <div><div className="text-sm font-semibold">% SLA Response</div><Weekly weeks={d.weeks} k="slaResponse" name="SLA Response" fmt={pctF} target={d.targets.slaResponse.target} /></div>
          <div><div className="text-sm font-semibold">% Same-Day</div><Weekly weeks={d.weeks} k="sameDay" name="Same-Day" fmt={pctF} target={d.targets.sameDay.target} /></div>
        </div>
        <div className="overflow-x-auto mt-3">
          <table className="w-full text-sm">
            <thead className="text-left text-mute"><tr>{['Minggu', 'Periode', 'Contact', 'Komplain', 'FRT', '% SLA', '% Same-day', 'CSAT', 'Critical'].map((h) => <th key={h} className="px-2 py-1 font-semibold">{h}</th>)}</tr></thead>
            <tbody>{d.weeks.map((w) => <tr key={w.week} className="border-t border-line tabnum"><td className="px-2 py-1 font-semibold">{w.week}</td><td className="px-2 py-1">{fmtD(w.start)} – {fmtD(w.end)}</td><td className="px-2 py-1">{w.contact}</td><td className="px-2 py-1">{w.komplain}</td><td className="px-2 py-1">{w.frt === null ? '–' : fmtNum(w.frt)}</td><td className="px-2 py-1">{fmtPct(w.slaResponse)}</td><td className="px-2 py-1">{fmtPct(w.sameDay)}</td><td className="px-2 py-1">{fmtPct(w.csat)}</td><td className="px-2 py-1">{w.critical}</td></tr>)}</tbody>
          </table>
        </div>
      </Card>
      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Sumber komplain (channel)" insight={d.insights.channel}>
          {d.sourceGroups?.length > 0 && <div className="flex flex-wrap gap-2 mb-3">{d.sourceGroups.map((g) => (
            <div key={g.name} className="rounded-xl bg-cream px-3 py-2"><div className="text-xs text-mute">{g.name}</div><div className="font-bold tabnum">{g.count} <span className="text-xs font-normal text-mute">({fmtPct(g.pct)})</span></div></div>
          ))}</div>}
          <table className="w-full text-sm"><thead className="text-left text-mute"><tr>{['Channel', 'Kelompok', 'Case', 'FRT rata-rata', '% SLA'].map((h) => <th key={h} className="py-1 font-semibold">{h}</th>)}</tr></thead>
            <tbody>{d.channels.map((r) => <tr key={r.name} className="border-t border-line tabnum"><td className="py-1.5">{r.name}</td><td className="text-xs text-mute">{r.group}</td><td>{r.count}</td><td>{fmtMin(r.avgFrt)}</td><td>{fmtPct(r.slaResponse)}</td></tr>)}</tbody></table>
        </ChartCard>
        <ChartCard title="Kompensasi" insight={d.insights.kompensasi}>
          <table className="w-full text-sm"><thead className="text-left text-mute"><tr>{['Bentuk', 'Case', 'Biaya'].map((h) => <th key={h} className="py-1 font-semibold">{h}</th>)}</tr></thead>
            <tbody>{d.kompensasi.map((r) => <tr key={r.name} className="border-t border-line tabnum"><td className="py-1.5">{r.name}{['Refund', 'Tidak Ada'].includes(r.name) && <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-[#FBE3C8] text-[#8A4B00] font-bold">Di luar standard</span>}</td><td>{r.count}</td><td>{fmtRp(r.biaya)}</td></tr>)}</tbody></table>
        </ChartCard>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Outlet terbanyak komplain (top 10)">
          <table className="w-full text-sm"><thead className="text-left text-mute"><tr>{['Outlet', 'Case', 'Critical', 'Sub jenis terbanyak'].map((h) => <th key={h} className="py-1 font-semibold">{h}</th>)}</tr></thead>
            <tbody>{d.outlets.map((r) => <tr key={r.name} className="border-t border-line"><td className="py-1.5">{r.name}</td><td className="tabnum">{r.count}</td><td className={`tabnum ${r.critical ? 'text-brick font-bold' : ''}`}>{r.critical}</td><td className="text-mute">{r.topSub}</td></tr>)}</tbody></table>
        </ChartCard>
        <ChartCard title="PIC Dept">
          <HBar rows={d.picDept} color="#8E6B5E" />
        </ChartCard>
      </div>
      <Card className="p-4 flex flex-wrap items-center gap-3">
        <div className="font-bold">Kualitas data</div>
        {d.volume.dataIssues === 0 ? <span className="text-ok font-semibold">Semua case OK ✓</span> :
          <Link className="text-warn font-semibold underline" to={`/case?dataIssue=true&from=${d.period.from}&to=${d.period.to}`}>{d.volume.dataIssues} case perlu dicek (Cek Data ≠ OK)</Link>}
      </Card>
    </div>
  )
}

export default function Dashboard() {
  const { masters } = useApp()
  const p = presets().find((x) => x.key === 'month')
  const [period, setPeriod] = useState({ from: p.from, to: p.to })
  const [brand, setBrand] = useState('')
  const [area, setArea] = useState('')
  const [sp, setSp] = useSearchParams()
  const [line, setLine] = useState('')
  const view = ['komparasi', 'frozen', 'complimentary'].includes(sp.get('view')) ? sp.get('view') : 'periode'
  const { data: d, loading, error } = useAsync(() => view === 'periode' ? api('/dashboard', { params: { ...period, brand, area, line } }) : Promise.resolve(null), [period.from, period.to, brand, area, line, view])
  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
        <div><h1 className="text-2xl font-extrabold">Dashboard Service Excellence</h1>
          {d && view === 'periode' && <p className="text-sm text-mute">{fmtD(d.period.from)} – {fmtD(d.period.to)} · dibandingkan {fmtD(d.period.prevFrom)} – {fmtD(d.period.prevTo)}</p>}</div>
        {!['frozen'].includes(view) && <div className="flex flex-wrap gap-2">
          <select className={inputCls + ' !min-h-[40px] w-auto'} value={line} onChange={(e) => setLine(e.target.value)} title="Lini bisnis"><option value="">Semua lini</option><option value="outlet">Outlet & gerobak</option><option value="frozen">Frozen food</option></select>
          <select className={inputCls + ' !min-h-[40px] w-auto'} value={brand} onChange={(e) => setBrand(e.target.value)}><option value="">Semua brand</option>{masters?.brands.map((b) => <option key={b}>{b}</option>)}</select>
          <select className={inputCls + ' !min-h-[40px] w-auto'} value={area} onChange={(e) => setArea(e.target.value)}><option value="">Semua area</option>{masters?.areas.map((b) => <option key={b}>{b}</option>)}</select>
        </div>}
      </div>
      <div className="flex flex-wrap gap-1 mb-4 bg-white border border-line rounded-xl p-1 w-fit">
        {[['periode', 'Ringkasan periode'], ['komparasi', 'Komparasi week / month'], ['frozen', 'Frozen food'], ['complimentary', 'Tracker complimentary']].map(([k, l]) => (
          <button key={k} onClick={() => setSp(k === 'periode' ? {} : { view: k })} className={`px-4 min-h-[40px] rounded-lg text-sm font-semibold ${view === k ? 'bg-brick text-white' : 'hover:bg-cream'}`}>{l}</button>
        ))}
      </div>
      {view === 'frozen' ? <Frozen /> : view === 'complimentary' ? <Kompensasi brand={brand} area={area} line={line} /> : view === 'komparasi' ? <Compare brand={brand} area={area} line={line} /> : <>
      <div className="mb-4"><PeriodPicker value={period} onChange={setPeriod} /></div>
      <ErrorBox error={error} />
      {loading && !d ? <div className="grid gap-3"><Skeleton /><Skeleton h="h-64" /></div> : d && <div className={loading ? 'opacity-60 transition' : 'transition'}><DashboardBody d={d} /></div>}
      </>}
    </div>
  )
}
