import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, useApp, useAsync, fmtDT, fmtMin, fmtRp, download, presets } from '../lib.jsx'
import { Btn, Card, Empty, ErrorBox, Skeleton, LevelBadge, StatusBadge, PeriodPicker, inputCls } from '../ui.jsx'
import { CaseCard, useNow } from '../components.jsx'

export default function Cases() {
  const { masters } = useApp()
  const [sp, setSp] = useSearchParams()
  const p30 = presets().find((p) => p.key === '30')
  const [period, setPeriod] = useState({ from: sp.get('from') || p30.from, to: sp.get('to') || p30.to })
  const [f, setF] = useState(() => Object.fromEntries(['status', 'level', 'jenis', 'subJenis', 'channel', 'outletId', 'area', 'picDept', 'kompensasi', 'agent', 'q', 'luarStandard', 'dataIssue'].map((k) => [k, sp.get(k) || ''])))
  const [showF, setShowF] = useState(false)
  const now = useNow()
  const params = { from: period.from, to: period.to, ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)) }
  const { data, loading, error } = useAsync(() => api('/cases', { params }), [JSON.stringify(params)])
  const set = (k, v) => { const n = { ...f, [k]: v }; setF(n); setSp(Object.fromEntries(Object.entries({ ...n, ...period }).filter(([, x]) => x))) }
  const sel = (k, label, opts) => (
    <select className={inputCls + ' !min-h-[40px]'} value={f[k]} onChange={(e) => set(k, e.target.value)}>
      <option value="">{label}: semua</option>{opts.map((o) => typeof o === 'string' ? <option key={o}>{o}</option> : <option key={o.v} value={o.v}>{o.l}</option>)}
    </select>
  )
  const active = Object.values(f).filter(Boolean).length
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h1 className="text-2xl font-extrabold">Case</h1>
        <div className="flex gap-2">
          <Btn kind="ghost" size="sm" onClick={() => setShowF(!showF)}>Filter{active ? ` (${active})` : ''}</Btn>
          <Btn kind="ghost" size="sm" onClick={() => download('/export/cases.xlsx', { from: period.from, to: period.to }, `case-log-${period.from}-${period.to}.xlsx`)}>Export Excel</Btn>
        </div>
      </div>
      <div className="mb-3"><PeriodPicker value={period} onChange={setPeriod} /></div>
      <input className={inputCls + ' mb-3'} placeholder="Cari Case ID, ringkasan, outlet, no. pesanan…" value={f.q} onChange={(e) => set('q', e.target.value)} />
      {showF && masters && (
        <Card className="p-3 mb-3 grid gap-2 sm:grid-cols-3 lg:grid-cols-4">
          {sel('status', 'Status', ['Open', 'Responded', 'Resolved', 'Closed'])}
          {sel('level', 'Level', ['Minor', 'Major', 'Critical'])}
          {sel('jenis', 'Jenis', [...new Set(masters.subJenis.map((s) => s.jenis))])}
          {sel('subJenis', 'Sub jenis', masters.subJenis.map((s) => s.name))}
          {sel('channel', 'Channel', masters.channels.map((c) => c.name))}
          {sel('outletId', 'Outlet', masters.outlets.map((o) => ({ v: o.id, l: o.name })))}
          {sel('area', 'Area', masters.areas)}
          {sel('picDept', 'PIC Dept', masters.picDept)}
          {sel('kompensasi', 'Kompensasi', ['Apologize', 'Voucher', 'Replacement', 'Complimentary', 'Cover Pengobatan', 'Refund', 'Tidak Ada'])}
          {sel('agent', 'Agent', masters.agents)}
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="w-5 h-5" checked={!!f.luarStandard} onChange={(e) => set('luarStandard', e.target.checked ? 'true' : '')} />Kompensasi di luar standard</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="w-5 h-5" checked={!!f.dataIssue} onChange={(e) => set('dataIssue', e.target.checked ? 'true' : '')} />Cek Data ≠ OK</label>
          {active > 0 && <Btn kind="link" onClick={() => { setF(Object.fromEntries(Object.keys(f).map((k) => [k, '']))); setSp({}) }}>Reset filter</Btn>}
        </Card>
      )}
      <ErrorBox error={error} />
      {loading && !data ? <Skeleton h="h-64" /> : data && (
        <>
          <div className="text-sm text-mute mb-2">{data.length} case</div>
          {data.length === 0 && <Empty>Tidak ada case untuk filter ini.</Empty>}
          <div className="md:hidden grid gap-3">{data.map((c) => <CaseCard key={c.caseId} c={c} now={now} />)}</div>
          <Card className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-brick text-white text-left">
                <tr>{['Case', 'Masuk', 'Outlet', 'Sub jenis', 'Level', 'Status', 'FRT', 'Resolusi', 'Kompensasi', 'Cek data'].map((h) => <th key={h} className="px-3 py-2 font-semibold whitespace-nowrap">{h}</th>)}</tr>
              </thead>
              <tbody>
                {data.map((c) => (
                  <tr key={c.caseId} className="border-t border-line hover:bg-cream">
                    <td className="px-3 py-2 font-bold"><Link to={`/case/${c.caseId}`} className="text-brick">{c.caseId}</Link></td>
                    <td className="px-3 py-2 whitespace-nowrap">{fmtDT(c.waktuMasuk)}<div className="text-xs text-mute">{c.channel}</div></td>
                    <td className="px-3 py-2">{c.outletName}</td>
                    <td className="px-3 py-2">{c.subJenis || '–'}</td>
                    <td className="px-3 py-2"><LevelBadge level={c.level} /></td>
                    <td className="px-3 py-2"><StatusBadge status={c.status} /></td>
                    <td className={`px-3 py-2 whitespace-nowrap ${c.slaResponseOk === false ? 'text-brick font-semibold' : ''}`}>{fmtMin(c.frtMin)}</td>
                    <td className={`px-3 py-2 whitespace-nowrap ${c.resolutionSlaOk === false ? 'text-brick font-semibold' : ''}`}>{fmtMin(c.resolutionMin)}</td>
                    <td className="px-3 py-2">{c.kompensasiLabel || '–'}{c.nilaiKompensasi ? <div className="text-xs text-mute">{fmtRp(c.nilaiKompensasi)}</div> : null}{c.kompensasiOutsideStandard && <div className="text-[11px] text-warn font-bold">Di luar standard</div>}</td>
                    <td className="px-3 py-2 text-xs">{c.dataOk ? <span className="text-ok font-semibold">OK</span> : <span className="text-warn">{c.dataIssues.filter((i) => !i.startsWith('Info:')).join('; ')}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  )
}
