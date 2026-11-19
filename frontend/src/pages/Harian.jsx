import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, useApp, useAsync, fmtD, fmtNum, todayWIB, addDays, WRITERS } from '../lib.jsx'
import { Btn, Card, ErrorBox, Field, Skeleton, Info, inputCls } from '../ui.jsx'
import { ModeTabs } from './Rekap.jsx'

export default function Harian() {
  const { notify, can } = useApp()
  const today = todayWIB()
  const [days, setDays] = useState(14)
  const { data, loading, error, reload } = useAsync(() => api('/daily', { params: { from: addDays(today, -(days - 1)), to: today } }), [days])
  const [f, setF] = useState({ tanggal: today, transaksi: '', komplain: '', catatan: '' })
  const [busy, setBusy] = useState(false)
  const writer = can(...WRITERS)
  const row = data?.rows.find((r) => r.tanggal === f.tanggal)
  // saat ganti tanggal: tampilkan isian yang sudah ada
  useEffect(() => { if (data) setF((x) => ({ ...x, transaksi: row?.transaksi ?? '', komplain: row?.komplain ?? '', catatan: row?.catatan ?? '' })) }, [f.tanggal, !!data, row?.transaksi, row?.komplain])
  const num = (v) => (v === '' || v === null || v === undefined ? null : Number(v))
  const save = async () => {
    setBusy(true)
    try { await api('/daily', { method: 'PUT', body: { tanggal: f.tanggal, transaksi: num(f.transaksi), komplain: num(f.komplain), catatan: f.catatan } }); notify(`Data ${fmtD(f.tanggal)} tersimpan`); reload() }
    catch (e) { notify(e.message, 'err') } finally { setBusy(false) }
  }
  const s = data?.summary
  return (
    <div className="max-w-4xl mx-auto">
      <ModeTabs mode="harian" />
      <h1 className="text-2xl font-extrabold mb-1">Data harian</h1>
      <p className="text-sm text-mute mb-4">Isi jumlah transaksi dan jumlah komplain yang diterima tiap hari. Dipakai untuk komplain per 1.000 transaksi dan untuk mengecek apakah semua komplain sudah direkap.</p>

      {writer && <Card className="p-4 mb-4">
        <div className="grid gap-3 sm:grid-cols-[auto_1fr_1fr]">
          <Field label="Tanggal"><input type="date" className={inputCls} value={f.tanggal} max={today} onChange={(e) => setF({ ...f, tanggal: e.target.value || today })} /></Field>
          <Field label="Jumlah transaksi" hint="Total transaksi hari itu (POS outlet + marketplace + platform online)."><input className={inputCls} inputMode="numeric" value={f.transaksi} onChange={(e) => setF({ ...f, transaksi: e.target.value.replace(/\D/g, '') })} placeholder="mis. 1850" /></Field>
          <Field label="Jumlah komplain diterima" hint="Hitungan komplain yang masuk hari itu di semua channel, sudah direkap atau belum."><input className={inputCls} inputMode="numeric" value={f.komplain} onChange={(e) => setF({ ...f, komplain: e.target.value.replace(/\D/g, '') })} placeholder="mis. 6" /></Field>
        </div>
        <div className="mt-3"><Field label="Catatan (opsional)"><input className={inputCls} value={f.catatan} onChange={(e) => setF({ ...f, catatan: e.target.value })} placeholder="mis. promo 11.11, 3 outlet tutup" /></Field></div>
        {row && f.komplain !== '' && Number(f.komplain) !== row.tercatat && <div className={`text-sm mt-3 rounded-xl p-3 ${Number(f.komplain) > row.tercatat ? 'bg-[#FBF1DC] text-[#7A5410]' : 'bg-cream text-mute'}`}>
          Tercatat di aplikasi untuk {fmtD(f.tanggal)}: <b>{row.tercatat}</b> komplain. {Number(f.komplain) > row.tercatat ? <>{Number(f.komplain) - row.tercatat} komplain belum direkap. <Link to="/catat" className="underline font-semibold">Rekap sekarang</Link></> : 'Lebih banyak dari hitungan manual: cek kemungkinan duplikat atau perbarui angkanya.'}
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
        <Card className="overflow-x-auto">
          <div className="p-4 pb-2 flex flex-wrap items-center gap-2"><h3 className="font-bold mr-2">Riwayat</h3>
            {[14, 30, 60].map((n) => <button key={n} onClick={() => setDays(n)} className={`px-3 h-8 rounded-lg border text-sm font-semibold ${days === n ? 'border-brick bg-brick-soft text-brick' : 'border-line bg-white'}`}>{n} hari</button>)}</div>
          <table className="w-full text-sm">
            <thead className="text-left text-mute"><tr>{['Tanggal', 'Transaksi', 'Komplain diterima', 'Tercatat', 'Selisih', 'Per 1.000 trx', 'Critical', 'Catatan', ''].map((h) => <th key={h} className="px-3 py-2 font-semibold whitespace-nowrap">{h}{h === 'Selisih' && <Info text="Komplain diterima (manual) − komplain yang sudah tercatat di aplikasi. Positif = ada yang belum direkap." />}</th>)}</tr></thead>
            <tbody>{data.rows.map((r) => (
              <tr key={r.tanggal} className={`border-t border-line tabnum ${r.tanggal === f.tanggal ? 'bg-brick-soft/40' : ''}`}>
                <td className="px-3 py-2 whitespace-nowrap font-semibold">{fmtD(r.tanggal)}</td>
                <td className={`px-3 py-2 ${r.transaksi == null ? 'text-mute' : ''}`}>{r.transaksi == null ? 'belum diisi' : fmtNum(r.transaksi)}</td>
                <td className={`px-3 py-2 ${r.komplain == null ? 'text-mute' : ''}`}>{r.komplain == null ? 'belum diisi' : r.komplain}</td>
                <td className="px-3 py-2">{r.tercatat}</td>
                <td className={`px-3 py-2 font-semibold ${r.selisih > 0 ? 'text-brick' : r.selisih === 0 ? 'text-ok' : ''}`}>{r.selisih == null ? '–' : r.selisih > 0 ? `${r.selisih} belum direkap` : r.selisih === 0 ? 'cocok' : r.selisih}</td>
                <td className="px-3 py-2">{r.per1000 == null ? '–' : fmtNum(r.per1000)}</td>
                <td className={`px-3 py-2 ${r.critical ? 'text-brick font-bold' : ''}`}>{r.critical}</td>
                <td className="px-3 py-2 text-xs text-mute max-w-[200px] truncate" title={r.catatan || ''}>{r.catatan || ''}</td>
                <td className="px-3 py-2">{writer && <button className="text-xs text-brick underline" onClick={() => { setF({ ...f, tanggal: r.tanggal }); window.scrollTo({ top: 0, behavior: 'smooth' }) }}>{r.transaksi == null && r.komplain == null ? 'Isi' : 'Ubah'}</button>}</td>
              </tr>))}</tbody>
          </table>
        </Card>
      </>}
    </div>
  )
}
