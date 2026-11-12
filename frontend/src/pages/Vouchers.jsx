import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, useApp, useAsync, fmtDT, LEAD, WRITERS } from '../lib.jsx'
import { Btn, Card, Chip, ErrorBox, Skeleton, Sheet, Field, inputCls } from '../ui.jsx'
import { KodeLookup } from '../components.jsx'

const ST = { Tersedia: 'bg-[#DCEBDD] text-ok', Diterbitkan: 'bg-[#F6E6C6] text-[#7A5410]', Terpakai: 'bg-[#E9E5DF] text-mute', Hangus: 'bg-brick-soft text-brick' }

export default function Vouchers() {
  const { masters, can, notify } = useApp()
  const [f, setF] = useState({ status: 'Diterbitkan', jenis: '' })
  const { data, loading, error, reload } = useAsync(() => api('/vouchers', { params: f }), [f.status, f.jenis])
  const [imp, setImp] = useState(false)
  const [ni, setNi] = useState({ jenis: 'Voucher Diskon 5K', codes: '', folder: '' })
  const [use, setUse] = useState(null)
  const [outlet, setOutlet] = useState('')
  if (loading && !data) return <Skeleton h="h-64" />
  return (
    <div>
      <div className="flex items-center justify-between mb-3"><h1 className="text-2xl font-extrabold">Kode Voucher</h1>{can(...LEAD) && <Btn size="sm" onClick={() => setImp(true)}>+ Tambah kode</Btn>}</div>
      <ErrorBox error={error} />
      <Card className="p-4 mb-4"><h3 className="font-bold mb-2">Cek / pakai kode complimentary</h3><KodeLookup onDone={reload} /></Card>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
        {data?.stock.map((s) => (
          <Card key={s.jenis} className={`p-4 ${s.Tersedia < 10 ? 'border-brick' : ''}`}>
            <div className="text-sm font-semibold">{s.jenis}</div>
            <div className="text-3xl font-extrabold">{s.Tersedia}<span className="text-sm font-normal text-mute"> tersedia</span></div>
            <div className="text-xs text-mute">Diterbitkan {s.Diterbitkan} · Terpakai {s.Terpakai} · Hangus {s.Hangus}</div>
            {s.Tersedia < 10 && <div className="text-xs text-brick font-bold mt-1">Stok menipis</div>}
            {s.folder && <a className="text-xs text-brick underline" href={s.folder} target="_blank" rel="noreferrer">Folder e-voucher</a>}
          </Card>
        ))}
      </div>
      <div className="flex flex-wrap gap-2 mb-3">
        {['', 'Tersedia', 'Diterbitkan', 'Terpakai', 'Hangus'].map((s) => <Chip key={s} active={f.status === s} onClick={() => setF({ ...f, status: s })}>{s || 'Semua'}</Chip>)}
        <select className={inputCls + ' !min-h-[40px] w-auto'} value={f.jenis} onChange={(e) => setF({ ...f, jenis: e.target.value })}><option value="">Semua jenis</option>{masters?.voucherJenis.map((j) => <option key={j}>{j}</option>)}</select>
      </div>
      <Card className="overflow-x-auto">
        <table className="w-full text-sm"><thead className="bg-brick text-white text-left"><tr>{['Kode', 'Jenis', 'Status', 'Case', 'Diterbitkan', 'Dipakai', 'Outlet', 'Catatan', ''].map((h) => <th key={h} className="px-3 py-2">{h}</th>)}</tr></thead>
          <tbody>
            {data?.rows.map((v) => (
              <tr key={v.kode} className="border-t border-line">
                <td className="px-3 py-2 font-mono font-bold">{v.kode}</td><td className="px-3">{v.jenis}</td>
                <td className="px-3"><span className={`px-2 py-0.5 rounded text-xs font-bold ${ST[v.status]}`}>{v.status}</span></td>
                <td className="px-3">{v.caseId ? <Link className="text-brick" to={'/case/' + v.caseId}>{v.caseId}</Link> : '–'}</td>
                <td className="px-3 whitespace-nowrap">{fmtDT(v.tanggalDiterbitkan)}</td><td className="px-3 whitespace-nowrap">{fmtDT(v.tanggalDipakai)}</td>
                <td className="px-3">{v.outletPemakaian || '–'}</td><td className="px-3 text-mute">{v.catatan}</td>
                <td className="px-3">{can(...WRITERS) && v.status === 'Diterbitkan' && <Btn size="sm" kind="soft" onClick={() => { setUse(v); setOutlet('') }}>Tandai terpakai</Btn>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Sheet open={imp} onClose={() => setImp(false)} title="Tambah kode voucher">
        <div className="space-y-3">
          <Field label="Jenis"><select className={inputCls} value={ni.jenis} onChange={(e) => setNi({ ...ni, jenis: e.target.value })}>{masters?.voucherJenis.map((j) => <option key={j}>{j}</option>)}</select></Field>
          <Field label="Kode (satu per baris)"><textarea className={inputCls + ' min-h-[140px] py-2 font-mono'} value={ni.codes} onChange={(e) => setNi({ ...ni, codes: e.target.value })} /></Field>
          <Field label="Link folder e-voucher (opsional)"><input className={inputCls} value={ni.folder} onChange={(e) => setNi({ ...ni, folder: e.target.value })} /></Field>
          <Btn className="w-full" onClick={async () => { const r = await api('/vouchers/import', { method: 'POST', body: ni }); notify(`${r.added} kode ditambah, ${r.skipped} dilewati`); setImp(false); reload() }}>Simpan</Btn>
        </div>
      </Sheet>
      <Sheet open={!!use} onClose={() => setUse(null)} title={`Tandai ${use?.kode} terpakai`}>
        <Field label="Outlet pemakaian"><select className={inputCls} value={outlet} onChange={(e) => setOutlet(e.target.value)}><option value="">Pilih</option>{masters?.outlets.map((o) => <option key={o.id}>{o.name}</option>)}</select></Field>
        <Btn className="w-full mt-4" onClick={async () => { await api(`/vouchers/${use.kode}/status`, { method: 'POST', body: { status: 'Terpakai', outlet } }); setUse(null); reload() }}>Simpan</Btn>
      </Sheet>
    </div>
  )
}
