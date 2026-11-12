import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, useApp, useAsync, fmtDT, fmtNum, presets, toLocalInput, fromLocalInput, WRITERS } from '../lib.jsx'
import { Btn, Card, Chip, ErrorBox, Skeleton, PeriodPicker, LevelBadge, Sheet, Field, inputCls, Empty, Info } from '../ui.jsx'
import { Combo, levelItemBadge } from '../components.jsx'
import { HBar } from './Dashboard.jsx'

const STATUS = ['Belum diproses', 'Sudah dibalas', 'Diteruskan ke Outlet', 'Selesai']

function ReviewTab() {
  const { masters, can, notify } = useApp()
  const nav = useNavigate()
  const p = presets().find((x) => x.key === '30')
  const [period, setPeriod] = useState({ from: p.from, to: p.to })
  const [f, setF] = useState({ status: '', level: '', platform: '' })
  const { data, loading, error, reload } = useAsync(() => api('/reviews', { params: { ...period, ...f } }), [period.from, period.to, f.status, f.level, f.platform])
  const [add, setAdd] = useState(false)
  const [nr, setNr] = useState({ platform: 'GoFood', tanggal: toLocalInput(), outletId: '', rating: 0, review: '', subJenis: '', orderNo: '' })
  const writer = can(...WRITERS)
  const bySub = useMemo(() => {
    const m = {}; (data || []).forEach((r) => { m[r.subJenis || '-'] = (m[r.subJenis || '-'] || 0) + 1 })
    return Object.entries(m).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count).slice(0, 8)
  }, [data])
  const setStatus = async (r, s) => { try { await api('/reviews/' + r.id, { method: 'PATCH', body: { statusTindakLanjut: s } }); reload() } catch (e) { notify(e.message, 'err') } }
  const toCase = async (r) => { try { const x = await api(`/reviews/${r.id}/to-case`, { method: 'POST' }); notify('Case ' + x.caseId + ' dibuat', 'ok', { label: 'Buka', fn: () => nav('/case/' + x.caseId) }); reload() } catch (e) { notify(e.message, 'err') } }
  const subs = (masters?.subJenis || []).map((s) => ({ value: s.name, label: s.name, keywords: s.keywords, level: s.level }))
  const outlets = (masters?.outlets || []).map((o) => ({ value: o.id, label: o.name }))
  return (
    <>
      <div className="flex flex-wrap gap-2 mb-3 items-center"><PeriodPicker value={period} onChange={setPeriod} />{writer && <Btn size="sm" onClick={() => setAdd(true)}>+ Review</Btn>}</div>
      <div className="flex flex-wrap gap-2 mb-3">
        {['', ...(masters?.reviewPlatforms || ['GoFood', 'GrabFood', 'ShopeeFood'])].map((x) => <Chip key={x} active={f.platform === x} onClick={() => setF({ ...f, platform: x })}>{x || 'Semua platform'}</Chip>)}
        {['', 'Critical', 'Major', 'Minor'].map((x) => <Chip key={'l' + x} active={f.level === x} onClick={() => setF({ ...f, level: x })}>{x || 'Semua level'}</Chip>)}
        <select className={inputCls + ' !min-h-[40px] !w-auto'} value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}><option value="">Semua status</option>{STATUS.map((s) => <option key={s}>{s}</option>)}</select>
      </div>
      <ErrorBox error={error} />
      {loading && !data ? <Skeleton h="h-64" /> : (
        <>
          <Card className="p-4 mb-4"><div className="font-bold">Sub jenis review komplain ({data.length})</div><HBar rows={bySub} /></Card>
          <div className="grid gap-3 md:grid-cols-2">
            {data.length === 0 && <Empty>Tidak ada review.</Empty>}
            {data.map((r) => (
              <Card key={r.id} className="p-4">
                <div className="flex flex-wrap items-center gap-2 text-sm"><b>{r.platform}</b><span>★{r.rating}</span><LevelBadge level={r.level} /><span className="text-xs text-mute">{r.id}</span></div>
                <div className="text-sm font-semibold mt-1">{r.subJenis} · {r.outletName}</div>
                <div className="text-sm text-mute">{r.review}</div>
                <div className="text-xs text-mute mt-1">{fmtDT(r.tanggal)}{r.orderNo ? ` · ${r.orderNo}` : ''}{r.linkedCaseId ? ` · case ${r.linkedCaseId}` : ''}</div>
                {writer && <div className="flex flex-wrap gap-1 mt-2">
                  {STATUS.map((s) => <button key={s} onClick={() => setStatus(r, s)} className={`text-xs px-2.5 py-1.5 rounded-lg font-semibold ${r.statusTindakLanjut === s ? 'bg-brick text-white' : 'bg-cream'}`}>{s}</button>)}
                  {!r.linkedCaseId && <button onClick={() => toCase(r)} className="text-xs px-2.5 py-1.5 rounded-lg font-semibold bg-brick-soft text-brick">Jadikan case</button>}
                </div>}
              </Card>
            ))}
          </div>
        </>
      )}
      <Sheet open={add} onClose={() => setAdd(false)} title="Tambah review online">
        <div className="space-y-3">
          <div className="flex gap-2">{(masters?.reviewPlatforms || ['GoFood', 'GrabFood', 'ShopeeFood']).map((x) => <Chip key={x} active={nr.platform === x} onClick={() => setNr({ ...nr, platform: x })}>{x}</Chip>)}</div>
          <Field label="Tanggal"><input type="datetime-local" className={inputCls} value={nr.tanggal} onChange={(e) => setNr({ ...nr, tanggal: e.target.value })} /></Field>
          <Field label="Outlet"><Combo items={outlets} value={nr.outletId} onChange={(v) => setNr({ ...nr, outletId: v })} /></Field>
          <Field label="Rating"><div className="flex gap-2">{[1, 2, 3, 4, 5].map((x) => <Chip key={x} active={nr.rating === x} onClick={() => setNr({ ...nr, rating: x })}>★{x}</Chip>)}</div></Field>
          <Field label="Review"><textarea className={inputCls + ' py-2'} value={nr.review} onChange={(e) => setNr({ ...nr, review: e.target.value })} /></Field>
          <Field label="Sub jenis"><Combo items={subs} value={nr.subJenis} onChange={(v) => setNr({ ...nr, subJenis: v })} renderBadge={levelItemBadge} /></Field>
          <Field label="No. pesanan"><input className={inputCls} value={nr.orderNo} onChange={(e) => setNr({ ...nr, orderNo: e.target.value })} /></Field>
          <Btn className="w-full" disabled={!nr.outletId || !nr.rating || !nr.subJenis} onClick={async () => {
            try { await api('/reviews', { method: 'POST', body: { ...nr, tanggal: fromLocalInput(nr.tanggal) } }); setAdd(false); notify('Review tersimpan'); reload() } catch (e) { notify(e.message, 'err') }
          }}>Simpan</Btn>
        </div>
      </Sheet>
    </>
  )
}

function RatingTab() {
  const { masters } = useApp()
  const { data, loading, error } = useAsync(() => api('/ratings'), [])
  const [plat, setPlat] = useState('GoFood')
  const [month, setMonth] = useState('')
  const months = useMemo(() => [...new Set((data || []).filter((r) => r.platform === plat).map((r) => r.bulan))].sort().reverse(), [data, plat])
  const m = month || months[0]
  const rows = (data || []).filter((r) => r.platform === plat && r.bulan === m)
  const tot = rows.reduce((a, r) => ({ n: a.n + (r.jumlahRating || 0), s: a.s + (r.totalSkor || 0), low: a.low + (r.ratingLe3 || 0) }), { n: 0, s: 0, low: 0 })
  const trend = months.slice().reverse().map((mm) => {
    const rs = (data || []).filter((r) => r.platform === plat && r.bulan === mm)
    const n = rs.reduce((a, r) => a + (r.jumlahRating || 0), 0), s = rs.reduce((a, r) => a + (r.totalSkor || 0), 0)
    return { name: mm, avg: n ? Math.round((s / n) * 100) / 100 : null }
  })
  if (loading) return <Skeleton h="h-64" />
  return (
    <>
      <ErrorBox error={error} />
      <div className="flex flex-wrap gap-2 mb-3">{(masters?.reviewPlatforms || ['GoFood', 'GrabFood', 'ShopeeFood']).map((x) => <Chip key={x} active={plat === x} onClick={() => { setPlat(x); setMonth('') }}>{x}</Chip>)}
        <select className={inputCls + ' !min-h-[40px] !w-auto'} value={m || ''} onChange={(e) => setMonth(e.target.value)}>{months.map((x) => <option key={x}>{x}</option>)}</select></div>
      {plat === 'GrabFood' && <p className="text-xs text-mute mb-2">Export GrabFood hanya berisi rata-rata rating harian, jadi Jumlah Rating = jumlah hari outlet punya rating.</p>}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <Card className="p-4"><div className="text-xs text-mute">Rata-rata</div><div className="text-2xl font-extrabold">{tot.n ? (tot.s / tot.n).toFixed(2).replace('.', ',') : '–'}</div></Card>
        <Card className="p-4"><div className="text-xs text-mute">Jumlah rating</div><div className="text-2xl font-extrabold">{fmtNum(tot.n)}</div></Card>
        <Card className="p-4"><div className="text-xs text-mute">Rating ≤ 3</div><div className="text-2xl font-extrabold">{fmtNum(tot.low)}</div></Card>
      </div>
      <Card className="p-4 mb-4"><div className="font-bold">Rata-rata per bulan</div><HBar rows={trend} dataKey="avg" name="Rata-rata" fmt={(v) => v?.toLocaleString('id-ID')} /></Card>
      <Card className="overflow-x-auto">
        <table className="w-full text-sm"><thead className="bg-brick text-white text-left"><tr>{['Outlet', 'Jumlah', 'Rata-rata', '≤ 3'].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr></thead>
          <tbody>{rows.sort((a, b) => (a.avgRating ?? 9) - (b.avgRating ?? 9)).map((r) => <tr key={r.outletName} className="border-t border-line tabnum"><td className="px-3 py-1.5">{r.outletName}</td><td className="px-3">{r.jumlahRating}</td><td className={`px-3 font-semibold ${r.avgRating < 4.7 ? 'text-brick' : ''}`}>{r.avgRating?.toLocaleString('id-ID')}</td><td className="px-3">{r.ratingLe3}</td></tr>)}</tbody></table>
      </Card>
    </>
  )
}

export default function Reviews() {
  const [tab, setTab] = useState('review')
  return (
    <div>
      <h1 className="text-2xl font-extrabold mb-3">Review & Rating Online Food Aggregator</h1>
      <div className="flex gap-2 mb-4"><Chip active={tab === 'review'} onClick={() => setTab('review')}>Review komplain</Chip><Chip active={tab === 'rating'} onClick={() => setTab('rating')}>Rating per outlet</Chip></div>
      {tab === 'review' ? <ReviewTab /> : <RatingTab />}
    </div>
  )
}
