import { useMemo, useState } from 'react'
import { api, useApp, useAsync, fmtDT, fmtPct, presets, WRITERS } from '../lib.jsx'
import { Btn, Card, Chip, ErrorBox, Skeleton, PeriodPicker, Sheet, Field, inputCls, Empty } from '../ui.jsx'
import { Combo } from '../components.jsx'
import { HBar } from './Dashboard.jsx'

export default function Csat() {
  const { masters, can, notify } = useApp()
  const p = presets().find((x) => x.key === '30')
  const [period, setPeriod] = useState({ from: p.from, to: p.to })
  const [unmatched, setUnmatched] = useState(false)
  const { data, loading, error, reload } = useAsync(() => api('/csat', { params: { ...period, unmatched: unmatched || undefined } }), [period.from, period.to, unmatched])
  const [match, setMatch] = useState(null)
  const [oid, setOid] = useState('')
  const [alias, setAlias] = useState(true)
  const [linkOpen, setLinkOpen] = useState(false)
  const [linkOutlet, setLinkOutlet] = useState('')

  const stats = useMemo(() => {
    if (!data) return null
    const rated = data.filter((r) => r.ratingKeseluruhan)
    const by = {}
    data.forEach((r) => { const k = r.outletName || '(belum cocok)'; by[k] = by[k] || { name: k, n: 0, sum: 0 }; by[k].n++; by[k].sum += r.ratingKeseluruhan || 0 })
    const wait = {}
    data.forEach((r) => { if (r.lamaTunggu) r.lamaTunggu.split(',').forEach((w) => { const k = w.trim(); wait[k] = (wait[k] || 0) + 1 }) })
    return {
      n: data.length, puas: rated.length ? rated.filter((r) => r.ratingKeseluruhan >= 4).length / rated.length : null,
      beli: data.length ? data.filter((r) => r.beliLagi === 'Ya').length / data.length : null,
      low: Object.values(by).map((x) => ({ name: x.name, count: x.n, avg: Math.round((x.sum / x.n) * 100) / 100 })).sort((a, b) => a.avg - b.avg).slice(0, 8),
      wait: Object.entries(wait).map(([name, count]) => ({ name, count })),
    }
  }, [data])
  const outlets = (masters?.outlets || []).map((o) => ({ value: o.id, label: o.name, sub: o.area }))
  const url = `${location.origin}/survei-outlet${linkOutlet ? '/' + linkOutlet : ''}`

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h1 className="text-2xl font-extrabold">CSAT Outlet</h1>
        <Btn kind="ghost" size="sm" onClick={() => setLinkOpen(true)}>Link & QR survei</Btn>
      </div>
      <div className="flex flex-wrap gap-2 mb-4"><PeriodPicker value={period} onChange={setPeriod} /><Chip active={unmatched} onClick={() => setUnmatched(!unmatched)}>Outlet belum cocok</Chip></div>
      <ErrorBox error={error} />
      {loading && !data ? <Skeleton h="h-64" /> : stats && (
        <>
          <div className="grid grid-cols-3 gap-3 mb-4">
            <Card className="p-4"><div className="text-xs text-mute">Respons</div><div className="text-2xl font-extrabold">{stats.n}</div></Card>
            <Card className="p-4"><div className="text-xs text-mute">Rating 4–5</div><div className="text-2xl font-extrabold">{fmtPct(stats.puas)}</div></Card>
            <Card className="p-4"><div className="text-xs text-mute">Bersedia beli lagi</div><div className="text-2xl font-extrabold">{fmtPct(stats.beli)}</div></Card>
          </div>
          <div className="grid gap-4 md:grid-cols-2 mb-4">
            <Card className="p-4"><div className="font-bold mb-1">Rata-rata rating terendah per outlet</div><HBar rows={stats.low} dataKey="avg" name="Rata-rata" fmt={(v) => v?.toLocaleString('id-ID')} /></Card>
            <Card className="p-4"><div className="font-bold mb-1">Lama menunggu</div><HBar rows={stats.wait} color="#8E6B5E" /></Card>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {data.length === 0 && <Empty>Tidak ada respons.</Empty>}
            {data.map((r) => (
              <Card key={r.id} className="p-4">
                <div className="flex flex-wrap items-center gap-2 text-sm"><b>★ {r.ratingKeseluruhan}</b><span className="text-mute">Pelayanan {r.puasPelayanan} · Rasa {r.rasa} · Kebersihan {r.kebersihan}</span>{r.beliLagi === 'Tidak' && <span className="text-brick text-xs font-bold">Tidak beli lagi</span>}</div>
                <div className="text-sm font-semibold mt-1">{r.outletName || <span className="text-warn">“{r.outletText}” belum cocok</span>}</div>
                {r.kritikSaran && <div className="text-sm text-mute">{r.kritikSaran}</div>}
                <div className="text-xs text-mute mt-1">{fmtDT(r.timestamp)}{r.linkedCaseId ? ` · case ${r.linkedCaseId}` : ''}</div>
                {can(...WRITERS) && !r.outletId && <Btn size="sm" kind="soft" className="mt-2" onClick={() => { setMatch(r); setOid('') }}>Cocokkan outlet</Btn>}
              </Card>
            ))}
          </div>
        </>
      )}
      <Sheet open={!!match} onClose={() => setMatch(null)} title="Cocokkan outlet">
        {match && <div className="space-y-4">
          <div className="bg-cream rounded-xl p-3 text-sm">Teks dari customer: “{match.outletText}”</div>
          <Field label="Outlet"><Combo items={outlets} value={oid} onChange={setOid} placeholder="Cari outlet" /></Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="w-5 h-5" checked={alias} onChange={(e) => setAlias(e.target.checked)} />Simpan teks ini sebagai alias outlet (berikutnya otomatis cocok)</label>
          <Btn className="w-full" disabled={!oid} onClick={async () => { await api(`/csat/${match.id}/match`, { method: 'POST', body: { outletId: oid, addAlias: alias } }); notify('Outlet dicocokkan'); setMatch(null); reload() }}>Simpan</Btn>
        </div>}
      </Sheet>
      <Sheet open={linkOpen} onClose={() => setLinkOpen(false)} title="Link & QR survei outlet">
        <div className="space-y-3">
          <Field label="Outlet (opsional, agar customer tidak perlu memilih)"><Combo items={outlets} value={linkOutlet} onChange={setLinkOutlet} placeholder="Semua outlet" /></Field>
          <div className="bg-cream rounded-xl p-3 text-sm break-all">{url}</div>
          <img alt="QR" className="mx-auto w-48 h-48" src={`https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=${encodeURIComponent(url)}`} />
          <p className="text-xs text-mute">QR dibuat oleh layanan qrserver.com. Cetak dan tempel di gerobak, atau salin link ke bio/struk.</p>
          <Btn className="w-full" onClick={() => navigator.clipboard.writeText(url).then(() => notify('Link tersalin'))}>Salin link</Btn>
        </div>
      </Sheet>
    </div>
  )
}
