import { useMemo, useState } from 'react'
import { ResponsiveContainer, ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, Cell } from 'recharts'
import { api, useAsync, fmtNum, fmtPct, fmtRp, fmtD, todayWIB } from '../lib.jsx'
import { Card, Chip, ErrorBox, Skeleton, Info, CARA_HITUNG, inputCls } from '../ui.jsx'
import { Tip } from './Dashboard.jsx'

const BRICK = '#B42F27', MUTE = '#8A8178', GRID = '#EDE6D9'

// kind: count | rp | min | pct ; dir: max = makin kecil makin baik
const METRICS = [
  { key: 'komplain', label: 'Komplain', src: 'volume', kind: 'count', dir: 'max', group: 'Volume' },
  { key: 'critical', label: 'Komplain Critical', src: 'volume', kind: 'count', dir: 'max', group: 'Volume' },
  { key: 'open', label: 'Masih open', src: 'volume', kind: 'count', dir: 'max', group: 'Volume' },
  { key: 'per1000', label: 'Komplain per 1.000 trx', src: 'volume', kind: 'dec', dir: 'max', group: 'Volume', info: CARA_HITUNG.per1000 },
  { key: 'biaya', label: 'Biaya kompensasi', src: 'volume', kind: 'rp', dir: 'max', group: 'Volume' },
  { key: 'biayaLuarStandard', label: 'Biaya di luar standard', src: 'volume', kind: 'rp', dir: 'max', group: 'Volume' },
  { key: 'frt', label: 'FRT rata-rata', src: 'metrics', kind: 'min', dir: 'max', group: 'Response', target: true, info: CARA_HITUNG.frt },
  { key: 'frtWork', label: 'FRT jam kerja', src: 'metrics', kind: 'min', dir: 'max', group: 'Response' },
  { key: 'slaResponse', label: '% SLA Response', src: 'metrics', kind: 'pct', dir: 'min', group: 'Response', target: true, info: CARA_HITUNG.slaResponse },
  { key: 'avgResolution', label: 'Avg Resolution Time', src: 'metrics', kind: 'min', dir: 'max', group: 'Resolution', target: true, info: CARA_HITUNG.avgResolution },
  { key: 'resolutionSla', label: '% Resolution sesuai SLA', src: 'metrics', kind: 'pct', dir: 'min', group: 'Resolution', target: true, info: CARA_HITUNG.resolutionSla },
  { key: 'sameDay', label: '% Same-Day Resolution', src: 'metrics', kind: 'pct', dir: 'min', group: 'Resolution', target: true, info: CARA_HITUNG.sameDay },
  { key: 'fcr', label: 'First Contact Resolution', src: 'metrics', kind: 'pct', dir: 'min', group: 'Resolution', target: true, info: CARA_HITUNG.fcr },
  { key: 'compSuccess', label: 'Complimentary Success Rate', src: 'metrics', kind: 'pct', dir: 'min', group: 'Quality', target: true },
  { key: 'reopen', label: 'Reopen Rate', src: 'metrics', kind: 'pct', dir: 'max', group: 'Quality', target: true },
  { key: 'csat', label: 'CSAT komplain (% puas)', src: 'metrics', kind: 'pct', dir: 'min', group: 'Quality', target: true },
  { key: 'csatN', label: 'Rating survei case', src: 'metrics', kind: 'count', dir: 'min', group: 'Quality' },
  { key: 'csatResponse', label: '% respons survei case', src: 'metrics', kind: 'pct', dir: 'min', group: 'Quality' },
  { key: 'csatOutlet', label: 'CSAT outlet (form)', src: 'metrics', kind: 'pct', dir: 'min', group: 'Quality' },
]

const val = (p, m) => p[m.src]?.[m.key] ?? null
const fmt = (kind, v) => v === null || v === undefined ? '–' : kind === 'pct' ? fmtPct(v) : kind === 'rp' ? fmtRp(v) : kind === 'min' ? `${fmtNum(v)} mnt` : fmtNum(v)

function delta(m, cur, prev, p, pp) {
  if (cur === null || prev === null || cur === undefined || prev === undefined) return null
  // volume di periode berjalan dibandingkan per hari, supaya periode yang belum penuh tidak terlihat "membaik"
  const perDay = ['count', 'rp'].includes(m.kind) && p && pp && (p.partial || pp.partial)
  if (perDay) { cur = cur / p.days; prev = prev / pp.days }
  const d = cur - prev
  if (Math.abs(d) < 1e-9) return { txt: '=', cls: 'text-mute' }
  const better = m.dir === 'max' ? d < 0 : d > 0
  let txt
  if (m.kind === 'pct') txt = `${d > 0 ? '+' : ''}${Math.round(d * 100)} pt`
  else if (prev !== 0 && ['count', 'rp', 'min', 'dec'].includes(m.kind)) txt = `${d > 0 ? '+' : ''}${Math.round((d / prev) * 100)}%`
  else txt = `${d > 0 ? '+' : ''}${fmtNum(d)}`
  return { txt: `${d > 0 ? '▲' : '▼'} ${txt}${perDay ? ' /hari' : ''}`, cls: better ? 'text-ok' : 'text-brick' }
}

function meets(m, v, targets) {
  const t = targets[m.key]
  if (!m.target || !t || v === null || v === undefined) return null
  return t.dir === 'max' ? (m.key === 'reopen' ? v < t.target : v <= t.target) : v >= t.target
}

/** meeting: { end, snapshot } — dipakai di Mode Meeting: tanggal akhir = akhir periode meeting,
 *  dan bila meeting terkunci, angka diambil dari snapshot (tidak berubah lagi). */
export default function Compare({ brand, area, line, meeting }) {
  const [mode, setMode] = useState('week')
  const [n, setN] = useState(meeting ? 6 : 8)
  const [end, setEnd] = useState(meeting?.end || todayWIB())
  const [sel, setSel] = useState('komplain')
  const snap = meeting?.snapshot?.[mode]
  const { data, loading, error } = useAsync(
    () => snap ? Promise.resolve(snap) : api('/dashboard/compare', { params: { mode, n, end, brand, area, line } }),
    [mode, n, end, brand, area, line, !!snap])
  const m = METRICS.find((x) => x.key === sel)
  const chart = useMemo(() => (data?.periods || []).map((p) => ({ name: p.label, v: val(p, m), partial: p.partial })), [data, m])
  const target = data?.targets?.[sel]?.target
  const maxSub = Math.max(1, ...(data?.subJenis || []).flatMap((s) => s.counts))
  const nOpts = mode === 'week' ? [4, 8, 12] : [3, 6, 12]

  return (
    <div className="space-y-4">
      <Card className="p-4 flex flex-wrap items-center gap-2 no-print">
        <Chip active={mode === 'week'} onClick={() => { setMode('week'); setN(meeting ? 6 : 8) }}>Week by week</Chip>
        <Chip active={mode === 'month'} onClick={() => { setMode('month'); setN(6) }}>Month by month</Chip>
        {meeting ? <span className="text-sm text-mute ml-2">{snap ? 'Snapshot saat meeting dikunci' : `s.d. ${fmtD(end)} (akhir periode meeting)`}</span> : <>
        <span className="mx-1 text-line">|</span>
        {nOpts.map((x) => <Chip key={x} active={n === x} onClick={() => setN(x)}>{x} {mode === 'week' ? 'minggu' : 'bulan'}</Chip>)}
        <span className="mx-1 text-line">|</span>
        <label className="text-sm flex items-center gap-2">s.d.<input type="date" className={inputCls + ' !min-h-[40px] w-auto'} value={end} max={todayWIB()} onChange={(e) => setEnd(e.target.value || todayWIB())} /></label>
        </>}
        <span className="text-xs text-mute w-full">Minggu = Senin–Minggu. Periode terakhir yang belum penuh ditandai “berjalan” — bandingkan dengan hati-hati.</span>
      </Card>
      <ErrorBox error={error} />
      {loading && !data ? <Skeleton h="h-96" /> : data && (
        <div className={loading ? 'opacity-60 space-y-4' : 'space-y-4'}>
          <Card className="p-4">
            <div className="flex flex-wrap gap-2 mb-3">
              {METRICS.map((x) => <Chip key={x.key} active={sel === x.key} onClick={() => setSel(x.key)} className="!min-h-[34px] text-xs">{x.label}</Chip>)}
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={chart} margin={{ left: 0, right: 16, top: 16, bottom: 0 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12, fill: MUTE }} tickLine={false} axisLine={{ stroke: GRID }} interval={0} angle={chart.length > 8 ? -30 : 0} textAnchor={chart.length > 8 ? 'end' : 'middle'} height={chart.length > 8 ? 56 : 30} />
                <YAxis tick={{ fontSize: 12, fill: MUTE }} tickLine={false} axisLine={false} width={56} tickFormatter={(v) => m.kind === 'pct' ? fmtPct(v) : m.kind === 'rp' ? (v >= 1e6 ? `${fmtNum(v / 1e6)} jt` : `${fmtNum(v / 1e3)} rb`) : fmtNum(v)} />
                <Tooltip content={<Tip fmt={(v, k) => k === 'v' ? fmt(m.kind, v) : fmt(m.kind, v)} />} cursor={{ fill: '#F5F0E6' }} />
                {['count', 'rp', 'dec'].includes(m.kind)
                  ? <Bar dataKey="v" name={m.label} radius={[4, 4, 0, 0]} maxBarSize={44}>{chart.map((c, i) => <Cell key={i} fill={c.partial ? '#D9A39E' : BRICK} />)}</Bar>
                  : <Line dataKey="v" name={m.label} stroke={BRICK} strokeWidth={2} dot={{ r: 4, fill: BRICK, stroke: '#fff', strokeWidth: 2 }} connectNulls />}
                {target !== undefined && m.target && <Line dataKey={() => target} name="Target" stroke={MUTE} strokeDasharray="4 4" strokeWidth={1.5} dot={false} />}
              </ComposedChart>
            </ResponsiveContainer>
            {['count', 'rp', 'dec'].includes(m.kind) && chart.some((c) => c.partial) && <p className="text-xs text-mute">Batang muda = periode berjalan (belum penuh).</p>}
          </Card>

          <Card className="overflow-x-auto">
            <table className={`w-full text-sm ${meeting ? '' : 'min-w-[720px]'}`}>
              <thead>
                <tr className="bg-brick text-white text-left">
                  <th className="px-3 py-2 sticky left-0 bg-brick">Metric</th><th className="px-3 py-2">Target</th>
                  {data.periods.map((p) => <th key={p.key} className={`${meeting ? 'px-2' : 'px-3'} py-2 whitespace-nowrap text-right`}>{p.label}{p.partial && <div className="text-[10px] font-normal opacity-90">berjalan · {p.days} hari</div>}</th>)}
                </tr>
              </thead>
              <tbody>
                {METRICS.map((x, i) => {
                  const t = data.targets[x.key]
                  const newGroup = i === 0 || METRICS[i - 1].group !== x.group
                  return (
                    <tr key={x.key} className={`border-t ${newGroup ? 'border-ink/20' : 'border-line'} ${sel === x.key ? 'bg-brick-soft/40' : ''} cursor-pointer hover:bg-cream`} onClick={() => setSel(x.key)}>
                      <td className="px-3 py-2 font-medium sticky left-0 bg-white whitespace-nowrap">{newGroup && <div className="text-[10px] uppercase tracking-wide text-mute">{x.group}</div>}{x.label}{x.info && <Info text={x.info} />}</td>
                      <td className="px-3 py-2 text-mute whitespace-nowrap">{x.target && t ? `${t.dir === 'max' ? '≤' : '≥'} ${fmt(x.kind, t.target)}` : '–'}</td>
                      {data.periods.map((p, j) => {
                        const v = val(p, x)
                        const dl = j > 0 ? delta(x, v, val(data.periods[j - 1], x), p, data.periods[j - 1]) : null
                        const ok = meets(x, v, data.targets)
                        return (
                          <td key={p.key} className={`${meeting ? 'px-2' : 'px-3'} py-2 text-right tabnum whitespace-nowrap ${p.partial ? 'bg-cream/60' : ''}`}>
                            <div className={`font-semibold ${ok === false ? 'text-brick' : ok ? 'text-ok' : ''}`}>{fmt(x.kind, v)}</div>
                            {dl && <div className={`text-[11px] ${dl.cls}`}>{dl.txt}</div>}
                          </td>
                        )
                      })}
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <p className="text-xs text-mute p-3">Angka hijau/merah = memenuhi/di bawah target. ▲▼ = perubahan dibanding kolom sebelumnya; hijau berarti membaik. Persentase berubah dalam poin (pt), angka lain dalam %. Untuk periode berjalan, volume & biaya dibandingkan rata-rata per hari (/hari).</p>
          </Card>

          {data.sources?.length > 0 && <Card className="overflow-x-auto">
            <h3 className="font-bold p-4 pb-2">Komplain per sumber per {data.mode === 'week' ? 'minggu' : 'bulan'}</h3>
            <table className={`w-full text-sm ${meeting ? '' : 'min-w-[720px]'}`}>
              <thead className="text-left text-mute">
                <tr><th className="px-3 py-1 sticky left-0 bg-white">Sumber</th>{data.periods.map((p) => <th key={p.key} className="px-2 py-1 text-right whitespace-nowrap">{p.label}</th>)}<th className="px-3 py-1 text-right">Total</th></tr>
              </thead>
              <tbody>
                {data.sources.map((s) => (
                  <tr key={s.name} className={`border-t ${s.isGroup ? 'border-ink/20 bg-cream/50 font-semibold' : 'border-line'}`}>
                    <td className={`py-1.5 sticky left-0 whitespace-nowrap ${s.isGroup ? 'px-3 bg-cream' : 'pl-7 pr-3 bg-white text-mute'}`}>{s.name}</td>
                    {s.counts.map((v, i) => {
                      const prev = i > 0 ? s.counts[i - 1] : null
                      return <td key={i} className="px-2 py-1.5 text-right tabnum">{v || '·'}{s.isGroup && prev !== null && v !== prev && !data.periods[i].partial && <span className={`ml-1 text-[10px] ${v > prev ? 'text-brick' : 'text-ok'}`}>{v > prev ? '▲' : '▼'}</span>}</td>
                    })}
                    <td className="px-3 py-1.5 text-right font-bold tabnum">{s.total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-xs text-mute p-3">Baris tebal = kelompok sumber (Chat & Sosmed, Marketplace, Online Food Aggregator); baris di bawahnya = channel. ▲ naik / ▼ turun dibanding periode sebelumnya.</p>
          </Card>}

          <Card className="overflow-x-auto">
            <h3 className="font-bold p-4 pb-2">Komplain per sub jenis per {data.mode === 'week' ? 'minggu' : 'bulan'}</h3>
            <table className="w-full text-sm min-w-[720px]">
              <thead className="text-left text-mute">
                <tr><th className="px-3 py-1 sticky left-0 bg-white">Sub jenis</th>{data.periods.map((p) => <th key={p.key} className="px-2 py-1 text-right whitespace-nowrap">{p.label}</th>)}<th className="px-3 py-1 text-right">Total</th></tr>
              </thead>
              <tbody>
                {data.subJenis.length === 0 && <tr><td className="px-3 py-4 text-mute" colSpan={data.periods.length + 2}>Belum ada komplain.</td></tr>}
                {data.subJenis.map((s) => (
                  <tr key={s.name} className="border-t border-line">
                    <td className="px-3 py-1.5 sticky left-0 bg-white whitespace-nowrap">{s.name}</td>
                    {s.counts.map((v, i) => (
                      <td key={i} className="px-1 py-1 text-right">
                        <span className="inline-block min-w-[36px] px-2 py-1 rounded-md tabnum" style={{ background: v ? `rgba(180,47,39,${0.12 + 0.68 * (v / maxSub)})` : 'transparent', color: v / maxSub > 0.55 ? '#fff' : '#2B2522' }}>{v || '·'}</span>
                      </td>
                    ))}
                    <td className="px-3 py-1.5 text-right font-bold tabnum">{s.total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-xs text-mute p-3">Warna makin pekat = makin banyak. Dipakai untuk melihat issue yang naik atau turun dari periode ke periode.</p>
          </Card>
        </div>
      )}
    </div>
  )
}
