import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, useApp, useAsync, fmtD, fmtNum, todayWIB, addDays, WRITERS } from '../lib.jsx'
import { Btn, Card, ErrorBox, Field, Skeleton, Info, inputCls } from '../ui.jsx'
import { ModeTabs } from './Rekap.jsx'

export default function Harian() {
  const { notify, can, masters } = useApp()
  const SC = masters?.salesChannels || []
  const groups = [...new Set(SC.map((x) => x.group))]
  const today = todayWIB()
  const [days, setDays] = useState(14)
  const { data, loading, error, reload } = useAsync(() => api('/daily', { params: { from: addDays(today, -(days - 1)), to: today } }), [days])
  const [f, setF] = useState({ tanggal: today, trx: {}, kom: {}, catatan: '' })
  const [busy, setBusy] = useState(false)
  const writer = can(...WRITERS)
  const row = data?.rows.find((r) => r.tanggal === f.tanggal)
  // saat ganti tanggal: tampilkan isian yang sudah ada
  useEffect(() => {
    if (!data) return
    // data lama tanpa rincian channel → tampil di Outlet / Kios
    const trx = row?.trx && Object.keys(row.trx).length ? row.trx : (row?.transaksi != null ? { 'Outlet / Kios': row.transaksi } : {})
    const kom = row?.kom && Object.keys(row.kom).length ? row.kom : (row?.komplain != null ? { 'Outlet / Kios': row.komplain } : {})
    setF((x) => ({ ...x, trx: { ...trx }, kom: { ...kom }, catatan: row?.catatan ?? '' }))
  }, [f.tanggal, !!data, row?.transaksi, row?.komplain])
  const sum = (o) => Object.values(o).reduce((a, v) => a + (Number(v) || 0), 0)
  const any = (o) => Object.values(o).some((v) => v !== '' && v != null)
  const totTrx = sum(f.trx), totKom = sum(f.kom)
  const setCell = (k, name, v) => setF((x) => ({ ...x, [k]: { ...x[k], [name]: v.replace(/\D/g, '') } }))
  const save = async () => {
    setBusy(true)
    const pack = (o) => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== '' && v != null).map(([k, v]) => [k, Number(v)]))
    try { await api('/daily', { method: 'PUT', body: { tanggal: f.tanggal, trx: pack(f.trx), kom: pack(f.kom), catatan: f.catatan } }); notify(`Data ${fmtD(f.tanggal)} tersimpan`); reload() }
    catch (e) { notify(e.message, 'err') } finally { setBusy(false) }
  }
  const s = data?.summary
  return (
    <div className="max-w-5xl mx-auto">
      <ModeTabs mode="harian" />
      <h1 className="text-2xl font-extrabold mb-1">Data harian</h1>
      <p className="text-sm text-mute mb-4">Isi jumlah transaksi dan jumlah komplain yang diterima tiap hari per sales channel (Offline, Online Aggregator, Marketplace). Dipakai untuk komplain per 1.000 transaksi dan untuk mengecek apakah semua komplain sudah direkap.</p>

      {writer && <Card className="p-4 mb-4">
        <div className="flex flex-wrap items-end gap-3 mb-3">
          <Field label="Tanggal"><input type="date" className={inputCls + ' !w-auto'} value={f.tanggal} max={today} onChange={(e) => setF({ ...f, tanggal: e.target.value || today })} /></Field>
          <div className="text-sm text-mute pb-2">Total: <b className="text-ink tabnum">{fmtNum(totTrx)}</b> transaksi · <b className="text-ink tabnum">{totKom}</b> komplain diterima</div>
        </div>
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead className="text-left text-mute"><tr><th className="py-1 pr-2 font-semibold">Sales channel</th><th className="py-1 pr-2 font-semibold">Jumlah transaksi</th><th className="py-1 pr-2 font-semibold">Komplain diterima<Info text="Hitungan komplain yang masuk hari itu untuk channel ini, sudah direkap atau belum." /></th><th className="py-1 font-semibold">Tercatat</th></tr></thead>
          <tbody>{groups.map((g) => [
            <tr key={g}><td colSpan={4} className="pt-3 pb-1 text-xs font-bold uppercase tracking-wide text-mute">{g}</td></tr>,
            ...SC.filter((x) => x.group === g).map((x) => (
              <tr key={x.name} className="border-t border-line">
                <td className="py-1.5 pr-2 font-medium whitespace-nowrap">{x.name}</td>
                <td className="py-1.5 pr-2"><input className={inputCls + ' !min-h-[38px] max-w-[150px]'} inputMode="numeric" value={f.trx[x.name] ?? ''} onChange={(e) => setCell('trx', x.name, e.target.value)} placeholder="0" /></td>
                <td className="py-1.5 pr-2"><input className={inputCls + ' !min-h-[38px] max-w-[110px]'} inputMode="numeric" value={f.kom[x.name] ?? ''} onChange={(e) => setCell('kom', x.name, e.target.value)} placeholder="0" /></td>
                <td className={`py-1.5 tabnum ${f.kom[x.name] !== undefined && f.kom[x.name] !== '' && Number(f.kom[x.name]) > (row?.rec?.[x.name] || 0) ? 'text-brick font-bold' : 'text-mute'}`}>{row?.rec?.[x.name] || 0}</td>
              </tr>))])}</tbody>
        </table></div>
        <div className="mt-3"><Field label="Catatan (opsional)"><input className={inputCls} value={f.catatan} onChange={(e) => setF({ ...f, catatan: e.target.value })} placeholder="mis. promo 11.11, 3 outlet tutup" /></Field></div>
        {row && any(f.kom) && totKom !== row.tercatat && <div className={`text-sm mt-3 rounded-xl p-3 ${totKom > row.tercatat ? 'bg-[#FBF1DC] text-[#7A5410]' : 'bg-cream text-mute'}`}>
          Tercatat di aplikasi untuk {fmtD(f.tanggal)}: <b>{row.tercatat}</b> komplain. {totKom > row.tercatat ? <>{totKom - row.tercatat} komplain belum direkap. <Link to="/catat" className="underline font-semibold">Rekap sekarang</Link></> : 'Lebih banyak dari hitungan manual: cek kemungkinan duplikat atau perbarui angkanya.'}
        </div>}
        <Btn className="mt-3" disabled={busy} onClick={save}>{busy ? 'Menyimpan…' : 'Simpan'}</Btn>
      </Card>}

      <ErrorBox error={error} />
      {loading && !data ? <Skeleton h="h-64" /> : data && <>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
          {[['Transaksi', fmtNum(s.transaksi), `${s.hariTerisi} dari ${s.hari} hari terisi`],
            ['Komplain diterima (manual)', fmtNum(s.komplainManual), `Tercatat di aplikasi: ${s.tercatat}`],
            ['Belum direkap', fmtNum(s.belumDirekap), 'Selisih hitungan manual − tercatat', s.belumDirekap ? 'text-brick' : ''],
            ['Komplain per 1.000 transaksi', s.per1000 == null ? '–' : fmtNum(s.per1000), 'Dari hari yang transaksinya terisi']].map(([l, v, sub, tone]) => (
            <Card key={l} className="p-4"><div className="text-sm text-mute font-semibold">{l}</div><div className={`text-2xl md:text-3xl font-extrabold tabnum my-1 ${tone || ''}`}>{v}</div><div className="text-xs text-mute">{sub}</div></Card>))}
        </div>
        <Card className="overflow-x-auto mb-4">
          <h3 className="font-bold p-4 pb-2">Per sales channel ({days} hari terakhir)</h3>
          <table className="w-full text-sm">
            <thead className="text-left text-mute"><tr>{['Sales channel', 'Transaksi', 'Komplain diterima', 'Tercatat', 'Komplain per 1.000 trx'].map((h) => <th key={h} className="px-3 py-2 font-semibold whitespace-nowrap">{h}</th>)}</tr></thead>
            <tbody>{data.channels.map((r) => (
              <tr key={r.kind + r.name} className={`border-t border-line tabnum ${r.kind === 'total' ? 'font-extrabold bg-cream' : r.kind === 'group' ? 'font-bold' : ''}`}>
                <td className={`px-3 py-2 ${r.kind === 'channel' ? 'pl-8 font-normal' : ''}`}>{r.name}</td>
                <td className="px-3 py-2">{r.transaksi == null ? '–' : fmtNum(r.transaksi)}</td><td className="px-3 py-2">{r.komplain}</td><td className="px-3 py-2">{r.tercatat}</td>
                <td className="px-3 py-2">{r.per1000 == null ? '–' : fmtNum(r.per1000)}</td>
              </tr>))}</tbody>
          </table>
        </Card>
        <Card className="overflow-x-auto">
          <div className="p-4 pb-2 flex flex-wrap items-center gap-2"><h3 className="font-bold mr-2">Riwayat harian</h3>
            {[14, 30, 60].map((n) => <button key={n} onClick={() => setDays(n)} className={`px-3 h-8 rounded-lg border text-sm font-semibold ${days === n ? 'border-brick bg-brick-soft text-brick' : 'border-line bg-white'}`}>{n} hari</button>)}</div>
          <table className="w-full text-sm">
            <thead className="text-left text-mute"><tr>{['Tanggal', 'Offline trx / komplain', 'Aggregator trx / komplain', 'Marketplace trx / komplain', 'Total trx', 'Komplain diterima', 'Tercatat', 'Selisih', 'Per 1.000 trx', 'Catatan', ''].map((h) => <th key={h} className="px-3 py-2 font-semibold whitespace-nowrap">{h}{h === 'Selisih' && <Info text="Komplain diterima (manual) − komplain yang sudah tercatat di aplikasi. Positif = ada yang belum direkap." />}</th>)}</tr></thead>
            <tbody>{data.rows.map((r) => (
              <tr key={r.tanggal} className={`border-t border-line tabnum ${r.tanggal === f.tanggal ? 'bg-brick-soft/40' : ''}`}>
                <td className="px-3 py-2 whitespace-nowrap font-semibold">{fmtD(r.tanggal)}</td>
                {['Offline', 'Online Aggregator', 'Marketplace'].map((g) => { const x = r.groups?.[g] || {}; return <td key={g} className="px-3 py-2 whitespace-nowrap">{x.transaksi == null ? <span className="text-mute">–</span> : fmtNum(x.transaksi)} / <span className={x.tercatat ? 'font-semibold' : ''}>{x.komplain ?? x.tercatat ?? 0}</span></td> })}
                <td className={`px-3 py-2 ${r.transaksi == null ? 'text-mute' : ''}`}>{r.transaksi == null ? 'belum diisi' : fmtNum(r.transaksi)}</td>
                <td className={`px-3 py-2 ${r.komplain == null ? 'text-mute' : ''}`}>{r.komplain == null ? 'belum diisi' : r.komplain}</td>
                <td className="px-3 py-2">{r.tercatat}</td>
                <td className={`px-3 py-2 font-semibold ${r.selisih > 0 ? 'text-brick' : r.selisih === 0 ? 'text-ok' : ''}`}>{r.selisih == null ? '–' : r.selisih > 0 ? `${r.selisih} belum direkap` : r.selisih === 0 ? 'cocok' : r.selisih}</td>
                <td className="px-3 py-2">{r.per1000 == null ? '–' : fmtNum(r.per1000)}</td>
                <td className="px-3 py-2 text-xs text-mute max-w-[200px] truncate" title={r.catatan || ''}>{r.catatan || ''}</td>
                <td className="px-3 py-2">{writer && <button className="text-xs text-brick underline" onClick={() => { setF({ ...f, tanggal: r.tanggal }); window.scrollTo({ top: 0, behavior: 'smooth' }) }}>{r.transaksi == null && r.komplain == null ? 'Isi' : 'Ubah'}</button>}</td>
              </tr>))}</tbody>
          </table>
        </Card>
      </>}
    </div>
  )
}
