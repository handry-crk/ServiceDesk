import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, useApp, download, fmtDT, fmtMin, WRITERS } from '../lib.jsx'
import { Btn, Card, ErrorBox, inputCls } from '../ui.jsx'
import { ModeTabs } from './Rekap.jsx'

export default function Bulk() {
  const { notify, can, loadMasters } = useApp()
  const [text, setText] = useState('')
  const [pv, setPv] = useState(null)
  const [res, setRes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [incDup, setIncDup] = useState(false)
  const [onlyBad, setOnlyBad] = useState(false)
  const fileRef = useRef()
  if (!can(...WRITERS)) return <ErrorBox error={{ message: 'Peran Anda tidak bisa mencatat case.' }} />

  const run = async (dryRun, t = text) => {
    setBusy(true); setErr(null)
    try {
      const r = await api('/cases/bulk', { method: 'POST', body: { text: t, dryRun, includeDup: incDup } })
      if (dryRun) { setPv(r); setRes(null) } else {
        setRes(r); setPv(null); await loadMasters()
        notify(`${r.created.length} case tersimpan`)
        // sisakan hanya baris yang error supaya bisa diperbaiki
        const lines = t.split('\n'); const bad = new Set(r.errorRows.map((x) => x.row))
        const hasHead = lines.length > r.summary.rows
        setText(bad.size ? [...(hasHead ? [lines[0]] : []), ...lines.slice(hasHead ? 1 : 0).filter((_, i) => bad.has(i + 1))].join('\n') : '')
      }
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }
  const upload = async (f) => {
    if (!f) return
    try {
      const fd = new FormData(); fd.append('file', f)
      const r = await api('/cases/bulk/file', { method: 'POST', form: fd })
      setText(r.text); run(true, r.text)
    } catch (e) { notify(e.message, 'err') }
    fileRef.current.value = ''
  }
  const s = pv?.summary
  const toSave = s ? s.ok - (incDup ? 0 : s.dup) : 0
  const shown = (pv?.rows || []).filter((r) => !onlyBad || !r.ok || r.warnings.length)

  return (
    <div className="max-w-6xl mx-auto">
      <ModeTabs mode="bulk" />
      <h1 className="text-2xl font-extrabold mb-1">Bulk input</h1>
      <p className="text-sm text-mute mb-4">Masukkan banyak komplain sekaligus dari Excel / Google Sheets. 1 baris = 1 komplain. Dicek dulu, baru disimpan.</p>

      <Card className="p-4 space-y-3">
        <div className="flex flex-wrap gap-2 items-center">
          <Btn kind="ghost" size="sm" onClick={() => download('/cases/bulk/template', null, 'template-bulk-input-service-desk.xlsx')}>Unduh template Excel</Btn>
          <Btn kind="ghost" size="sm" onClick={() => fileRef.current.click()}>Upload .xlsx / .csv</Btn>
          <input ref={fileRef} type="file" accept=".xlsx,.csv,.tsv,.txt" hidden onChange={(e) => upload(e.target.files[0])} />
          <span className="text-xs text-mute">atau blok baris di Excel / Google Sheets (termasuk judul kolom) → salin → tempel di bawah.</span>
        </div>
        <textarea className={inputCls + ' min-h-[160px] py-2 text-xs font-mono whitespace-pre'} wrap="off" value={text} onChange={(e) => { setText(e.target.value); setPv(null) }}
          placeholder={'Tanggal\tJam Masuk\tJam Dibalas\tJam Selesai\tChannel\tOutlet\tSub Jenis\tRingkasan\tRoot Cause\tKompensasi\tNilai (Rp)\tStatus\tNama Customer\tNo HP\tNo Pesanan\tJam Order\n16/11/2026\t10.02\t10.05\t10.30\tWhatsApp\tJagakarsa\tMissing Item\tPesan 10 diterima 8\tKetelitian Crew\tReplacement\t\tSelesai'} />
        <div className="text-xs text-mute">Wajib: Tanggal, Jam Masuk, Jam Dibalas, Channel, Outlet, Sub Jenis, Ringkasan. Status <b>Selesai</b> / <b>Closed</b> wajib Root Cause & Kompensasi. Outlet yang belum terdaftar dibuat otomatis (menunggu verifikasi). Maksimal 300 baris.</div>
        <ErrorBox error={err} />
        <Btn disabled={!text.trim() || busy} onClick={() => run(true)}>{busy && !pv ? 'Memeriksa…' : 'Periksa data'}</Btn>
      </Card>

      {res && <Card className="p-4 mt-4 border-ok border-2">
        <div className="font-extrabold text-lg">✓ {res.created.length} case tersimpan{res.skippedDup ? ` · ${res.skippedDup} dilewati (sudah tercatat)` : ''}{res.failed.length ? ` · ${res.failed.length} gagal` : ''}</div>
        <div className="flex flex-wrap gap-1.5 mt-2">{res.created.map((x) => <Link key={x.caseId} to={'/case/' + x.caseId} className="text-xs bg-cream rounded-lg px-2 py-1 underline">{x.caseId}{x.kode ? ` · ${x.kode}` : ''}</Link>)}</div>
        {res.failed.map((x) => <div key={x.row} className="text-sm text-brick mt-1">Baris {x.row}: {x.error}</div>)}
        {res.errorRows.length > 0 && <div className="text-sm text-[#7A5410] mt-2">{res.errorRows.length} baris yang error belum tersimpan dan masih ada di kotak di atas — perbaiki lalu periksa lagi.</div>}
        <div className="text-xs text-mute mt-2">Jam pada bulk input diisi manual tanpa bukti chat, jadi case ini masuk prioritas audit acak mingguan. Kode complimentary sudah terbit; kirim ke customer dari halaman case.</div>
      </Card>}

      {pv && <Card className="mt-4 overflow-hidden">
        <div className="p-4 flex flex-wrap items-center gap-3">
          <div className="font-bold">{s.rows} baris</div>
          <span className="text-sm px-2 py-0.5 rounded-md bg-[#E3F1E6] text-[#1F6B3A] font-semibold">{s.ok} siap disimpan</span>
          {s.error > 0 && <span className="text-sm px-2 py-0.5 rounded-md bg-[#F3E1DF] text-brick font-semibold">{s.error} error</span>}
          {s.warning > 0 && <span className="text-sm px-2 py-0.5 rounded-md bg-[#FBF1DC] text-[#7A5410] font-semibold">{s.warning} perlu dicek</span>}
          <label className="text-sm flex items-center gap-1.5"><input type="checkbox" checked={onlyBad} onChange={(e) => setOnlyBad(e.target.checked)} />Tampilkan yang bermasalah saja</label>
          {s.dup > 0 && <label className="text-sm flex items-center gap-1.5"><input type="checkbox" checked={incDup} onChange={(e) => setIncDup(e.target.checked)} />Tetap simpan {s.dup} baris yang mungkin sudah tercatat</label>}
          <Btn className="ml-auto" disabled={busy || toSave <= 0} onClick={() => run(false)}>{busy ? 'Menyimpan…' : `Simpan ${toSave} case`}</Btn>
        </div>
        {s.error > 0 && <div className="px-4 pb-3 text-xs text-mute">Baris yang error tidak ikut disimpan. Perbaiki di kotak di atas (atau di Excel) lalu klik Periksa data lagi — atau simpan dulu yang sudah benar.</div>}
        <div className="overflow-x-auto"><table className="w-full text-sm">
          <thead className="bg-brick text-white text-left"><tr>{['#', 'Hasil', 'Masuk', 'Dibalas', 'FRT', 'Channel', 'Outlet', 'Sub jenis', 'Ringkasan', 'Status', 'Kompensasi'].map((h) => <th key={h} className="px-2 py-2 whitespace-nowrap">{h}</th>)}</tr></thead>
          <tbody>{shown.map((r) => { const d = r.data; return (
            <tr key={r.row} className={`border-t border-line align-top ${!r.ok ? 'bg-[#F3E1DF]/50' : r.warnings.length ? 'bg-[#FBF1DC]/50' : ''}`}>
              <td className="px-2 py-1.5 tabnum">{r.row}</td>
              <td className="px-2 py-1.5 min-w-[200px]">{r.ok && !r.warnings.length && <span className="text-ok font-semibold">OK</span>}
                {r.errors.map((e) => <div key={e} className="text-brick text-xs font-semibold">✗ {e}</div>)}
                {r.warnings.map((e) => <div key={e} className="text-[#7A5410] text-xs">! {e}</div>)}</td>
              <td className="px-2 py-1.5 text-xs whitespace-nowrap">{d.masuk ? fmtDT(d.masuk) : '–'}</td><td className="px-2 py-1.5 text-xs whitespace-nowrap">{d.dibalas ? fmtDT(d.dibalas) : '–'}</td>
              <td className="px-2 py-1.5 tabnum whitespace-nowrap">{d.frtMin == null ? '–' : fmtMin(d.frtMin)}</td>
              <td className="px-2 py-1.5">{d.channel || '–'}</td><td className="px-2 py-1.5">{d.outlet || '–'}</td><td className="px-2 py-1.5">{d.subJenis || '–'}</td>
              <td className="px-2 py-1.5 max-w-[240px] truncate" title={d.ringkasan}>{d.ringkasan}</td><td className="px-2 py-1.5">{d.status}</td><td className="px-2 py-1.5">{d.kompensasi || '–'}</td>
            </tr>) })}</tbody>
        </table></div>
      </Card>}
    </div>
  )
}
