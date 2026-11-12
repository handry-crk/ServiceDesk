import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, useApp, useAsync, fmtDT, fmtD, fmtNum, download, LEAD } from '../lib.jsx'
import { Btn, Card, Chip, ErrorBox, Field, Sheet, Skeleton, inputCls, LevelBadge } from '../ui.jsx'

const TABS = [['standard', 'Standard CRM.STD.001'], ['target', 'Target & SLA'], ['outlet', 'Outlet'], ['user', 'User'], ['transaksi', 'Transaksi bulanan'], ['impor', 'Impor sheet lama'], ['sistem', 'Sistem']]
const c = inputCls + ' !min-h-[36px] text-sm'

function useSave() {
  const { notify, loadMasters } = useApp()
  return async (kind, value, extra = {}) => {
    try { const r = await api('/masters/' + kind, { method: 'PUT', body: { value, ...extra } }); await loadMasters(); notify(`Tersimpan. ${r.recomputed} case dihitung ulang.`) }
    catch (e) { notify(e.message, 'err') }
  }
}

function Standard() {
  const { masters } = useApp()
  const save = useSave()
  const [sj, setSj] = useState(masters.subJenis)
  const [kp, setKp] = useState(masters.kompensasi)
  const [pj, setPj] = useState(masters.penanggungJawab)
  const upd = (arr, set, i, k, v) => set(arr.map((x, j) => j === i ? { ...x, [k]: v } : x))
  return (
    <div className="space-y-6">
      {masters.standardDoc && <Card className="p-4 text-sm">
        <div className="font-bold">{masters.standardDoc.code} — {masters.standardDoc.title}</div>
        <div className="text-mute">Revisi {masters.standardDoc.revision} · efektif {fmtD(masters.standardDoc.effective)} · referensi: {masters.standardDoc.reference}</div>
        <div className="text-mute mt-1">Bila standard direvisi, ubah matriks di bawah lalu Simpan; semua case dihitung ulang otomatis.</div>
      </Card>}
      <Card className="p-4 overflow-x-auto">
        <div className="flex items-center justify-between mb-2"><h3 className="font-bold">Matriks klasifikasi (4.4)</h3><Btn size="sm" onClick={() => save('subJenis', sj)}>Simpan</Btn></div>
        <table className="w-full text-sm min-w-[900px]"><thead className="text-left text-mute"><tr><th className="p-1">Sub jenis</th><th className="p-1">Jenis</th><th className="p-1">Level</th><th className="p-1">Contoh</th><th className="p-1">Kata kunci pencarian</th><th className="p-1">Aktif</th></tr></thead>
          <tbody>{sj.map((s, i) => (
            <tr key={i} className="border-t border-line">
              <td className="p-1"><input className={c} value={s.name} onChange={(e) => upd(sj, setSj, i, 'name', e.target.value)} /></td>
              <td className="p-1"><input className={c} value={s.jenis} onChange={(e) => upd(sj, setSj, i, 'jenis', e.target.value)} /></td>
              <td className="p-1"><select className={c} value={s.level} onChange={(e) => upd(sj, setSj, i, 'level', e.target.value)}>{['Minor', 'Major', 'Critical', 'Belum Diatur'].map((l) => <option key={l}>{l}</option>)}</select></td>
              <td className="p-1"><input className={c} value={s.contoh} onChange={(e) => upd(sj, setSj, i, 'contoh', e.target.value)} /></td>
              <td className="p-1"><input className={c} value={s.keywords} onChange={(e) => upd(sj, setSj, i, 'keywords', e.target.value)} /></td>
              <td className="p-1 text-center"><input type="checkbox" className="w-5 h-5" checked={s.active !== false} onChange={(e) => upd(sj, setSj, i, 'active', e.target.checked)} /></td>
            </tr>))}</tbody></table>
        <Btn kind="link" onClick={() => setSj([...sj, { name: '', jenis: 'Di Luar Standard', level: 'Belum Diatur', contoh: '', keywords: '', picOutlet: 'Ops / Outlet', picFrozen: 'Ops / Outlet', rootCauses: [], active: true }])}>+ Sub jenis</Btn>
      </Card>
      <Card className="p-4 overflow-x-auto">
        <div className="flex items-center justify-between mb-2"><h3 className="font-bold">Matriks kompensasi (5.1)</h3><Btn size="sm" onClick={() => save('kompensasi', kp)}>Simpan</Btn></div>
        <table className="w-full text-sm min-w-[700px]"><thead className="text-left text-mute"><tr><th className="p-1">Level</th><th className="p-1">Label</th><th className="p-1">Bentuk dasar</th><th className="p-1">Nilai default (Rp)</th><th className="p-1">Sesuai standard</th><th className="p-1">Jenis voucher</th></tr></thead>
          <tbody>{kp.map((k, i) => (
            <tr key={k.key} className="border-t border-line">
              <td className="p-1">{k.level === 'Semua' ? 'Semua' : <LevelBadge level={k.level} />}</td>
              <td className="p-1"><input className={c} value={k.label} onChange={(e) => upd(kp, setKp, i, 'label', e.target.value)} /></td>
              <td className="p-1 text-mute">{k.jenis}</td>
              <td className="p-1"><input className={c} inputMode="numeric" value={k.nilai} onChange={(e) => upd(kp, setKp, i, 'nilai', Number(e.target.value.replace(/\D/g, '') || 0))} /></td>
              <td className="p-1 text-center"><input type="checkbox" className="w-5 h-5" checked={!!k.standard} onChange={(e) => upd(kp, setKp, i, 'standard', e.target.checked)} /></td>
              <td className="p-1 text-mute">{k.voucherJenis || '–'}</td>
            </tr>))}</tbody></table>
        <p className="text-xs text-mute mt-2">Bila Direksi memutuskan Refund masuk standard, centang “Sesuai standard” pada baris Refund.</p>
      </Card>
      <Card className="p-4">
        <div className="flex items-center justify-between mb-2"><h3 className="font-bold">Penanggung jawab per level</h3><Btn size="sm" onClick={() => save('penanggungJawab', pj)}>Simpan</Btn></div>
        <div className="grid sm:grid-cols-4 gap-2">{Object.keys(pj).map((k) => <Field key={k} label={k}><input className={c} value={pj[k]} onChange={(e) => setPj({ ...pj, [k]: e.target.value })} /></Field>)}</div>
      </Card>
    </div>
  )
}

function Target() {
  const { masters } = useApp()
  const save = useSave()
  const [t, setT] = useState(masters.targets)
  const [rt, setRt] = useState(masters.resolutionTarget)
  const [cf, setCf] = useState(masters.criticalFrt)
  const [ch, setCh] = useState(masters.channels)
  const [st, setSt] = useState(masters.settings)
  const pctKeys = ['slaResponse', 'resolutionSla', 'sameDay', 'fcr', 'compSuccess', 'reopen', 'csat']
  return (
    <div className="space-y-6">
      <Card className="p-4">
        <div className="flex items-center justify-between mb-2"><h3 className="font-bold">Target metric (fase 1)</h3><Btn size="sm" onClick={() => save('targets', t)}>Simpan</Btn></div>
        <div className="grid sm:grid-cols-3 gap-3">{Object.entries(t).map(([k, v]) => (
          <Field key={k} label={v.label} hint={v.dir === 'max' ? 'Semakin kecil semakin baik' : 'Minimal'}>
            <input className={c} inputMode="decimal" value={pctKeys.includes(k) ? Math.round(v.target * 100) : v.target}
              onChange={(e) => { const n = Number(e.target.value.replace(',', '.')) || 0; setT({ ...t, [k]: { ...v, target: pctKeys.includes(k) ? n / 100 : n } }) }} />
          </Field>))}</div>
        <p className="text-xs text-mute mt-2">Persentase diisi angka 0–100.</p>
      </Card>
      <Card className="p-4">
        <div className="flex items-center justify-between mb-2"><h3 className="font-bold">Target penyelesaian per level (menit)</h3><Btn size="sm" onClick={() => save('resolutionTarget', rt, { criticalFrt: cf })}>Simpan</Btn></div>
        <div className="grid sm:grid-cols-4 gap-3">
          {Object.keys(rt).map((k) => <Field key={k} label={k}><input className={c} inputMode="numeric" value={rt[k]} onChange={(e) => setRt({ ...rt, [k]: Number(e.target.value) || 0 })} /></Field>)}
          <Field label="First response Critical"><input className={c} inputMode="numeric" value={cf} onChange={(e) => setCf(Number(e.target.value) || 0)} /></Field>
        </div>
      </Card>
      <Card className="p-4">
        <div className="flex items-center justify-between mb-2"><h3 className="font-bold">Target FRT per channel (menit)</h3><Btn size="sm" onClick={() => save('channels', ch)}>Simpan</Btn></div>
        <div className="grid sm:grid-cols-3 gap-3">{ch.map((x, i) => (
          <div key={x.name} className="flex items-end gap-2"><Field label={x.name}><input className={c} inputMode="numeric" value={x.targetFrt} onChange={(e) => setCh(ch.map((y, j) => j === i ? { ...y, targetFrt: Number(e.target.value) || 0 } : y))} /></Field>
            <label className="text-xs flex items-center gap-1 pb-2"><input type="checkbox" checked={x.countInSla} onChange={(e) => setCh(ch.map((y, j) => j === i ? { ...y, countInSla: e.target.checked } : y))} />SLA</label></div>))}</div>
      </Card>
      <Card className="p-4">
        <div className="flex items-center justify-between mb-2"><h3 className="font-bold">Jam operasional CS, notifikasi & integritas waktu</h3><Btn size="sm" onClick={() => save('settings', st)}>Simpan</Btn></div>
        <div className="grid sm:grid-cols-4 gap-3">
          <Field label="Jam mulai"><input type="time" className={c} value={st.opStart} onChange={(e) => setSt({ ...st, opStart: e.target.value })} /></Field>
          <Field label="Jam selesai"><input type="time" className={c} value={st.opEnd} onChange={(e) => setSt({ ...st, opEnd: e.target.value })} /></Field>
          <Field label="Alert Critical setelah (menit)"><input className={c} value={st.alertCriticalAfterMin} onChange={(e) => setSt({ ...st, alertCriticalAfterMin: Number(e.target.value) || 20 })} /></Field>
          <Field label="Voucher hangus setelah (hari)"><input className={c} value={st.voucherExpiryDays} onChange={(e) => setSt({ ...st, voucherExpiryDays: Number(e.target.value) || 30 })} /></Field>
          <div className="sm:col-span-4 pt-2 border-t border-line font-bold text-sm">Integritas waktu (anti mundur-jam)</div>
          <Field label="Mundur jam dibalas langsung diterima s/d (menit)" hint="Lebih dari ini perlu screenshot + persetujuan"><input className={c} inputMode="numeric" value={st.frGraceMin} onChange={(e) => setSt({ ...st, frGraceMin: Number(e.target.value) || 0 })} /></Field>
          <Field label="Batas CS mundurkan jam dibalas (menit)" hint="Lebih dari ini hanya CRM Supervisor"><input className={c} inputMode="numeric" value={st.frMaxBackMin} onChange={(e) => setSt({ ...st, frMaxBackMin: Number(e.target.value) || 0 })} /></Field>
          <Field label="CS boleh ubah jam dibalas dalam (jam)" hint="Sekali per case"><input className={c} inputMode="numeric" value={st.frEditHours} onChange={(e) => setSt({ ...st, frEditHours: Number(e.target.value) || 0 })} /></Field>
          <Field label="Waktu masuk wajib alasan bila lebih dari (menit)"><input className={c} inputMode="numeric" value={st.masukLagReasonMin} onChange={(e) => setSt({ ...st, masukLagReasonMin: Number(e.target.value) || 0 })} /></Field>
          <Field label="Alert bila jam manual CS di atas (%)"><input className={c} inputMode="numeric" value={Math.round((st.manualAlertPct ?? 0.15) * 100)} onChange={(e) => setSt({ ...st, manualAlertPct: (Number(e.target.value) || 0) / 100 })} /></Field>
          <Field label="Audit acak per CS per minggu (case)"><input className={c} inputMode="numeric" value={st.auditSamplePerCs} onChange={(e) => setSt({ ...st, auditSamplePerCs: Number(e.target.value) || 0 })} /></Field>
          <div className="sm:col-span-4"><Field label="Email penerima alert & rekap (pisahkan koma)"><input className={c} value={(st.emailRecipients || []).join(', ')} onChange={(e) => setSt({ ...st, emailRecipients: e.target.value.split(',').map((x) => x.trim()).filter(Boolean) })} /></Field></div>
        </div>
      </Card>
    </div>
  )
}

function Outlets() {
  const { masters, loadMasters, notify } = useApp()
  const [q, setQ] = useState('')
  const [edit, setEdit] = useState(null)
  const rows = masters.outlets.filter((o) => o.name.toLowerCase().includes(q.toLowerCase()) || o.area.toLowerCase().includes(q.toLowerCase()))
  const saveO = async () => {
    try {
      const body = { ...edit, aliases: typeof edit.aliases === 'string' ? edit.aliases.split(',').map((x) => x.trim()).filter(Boolean) : edit.aliases }
      if (edit.id) await api('/outlets/' + edit.id, { method: 'PATCH', body }); else await api('/outlets', { method: 'POST', body })
      await loadMasters(); setEdit(null); notify('Outlet tersimpan')
    } catch (e) { notify(e.message, 'err') }
  }
  return (
    <Card className="p-4">
      <div className="flex gap-2 mb-3"><input className={inputCls} placeholder="Cari outlet/area" value={q} onChange={(e) => setQ(e.target.value)} /><Btn onClick={() => setEdit({ name: '', type: 'gerobak', area: 'Belum diatur', brand: 'Cimol Bojot AA', aliases: '', active: true })}>+ Outlet</Btn></div>
      <div className="text-xs text-mute mb-2">{masters.outlets.filter((o) => o.area === 'Belum diatur').length} outlet belum punya area — isi agar filter area & akses Manager Area berjalan.</div>
      <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="text-left text-mute"><tr>{['Nama', 'Tipe', 'Area', 'Brand', 'Alias', 'Aktif', ''].map((h) => <th key={h} className="p-2">{h}</th>)}</tr></thead>
        <tbody>{rows.map((o) => <tr key={o.id} className="border-t border-line"><td className="p-2 font-medium">{o.name}</td><td className="p-2">{o.type}</td><td className={`p-2 ${o.area === 'Belum diatur' ? 'text-warn' : ''}`}>{o.area}</td><td className="p-2">{o.brand}</td><td className="p-2 text-xs text-mute">{(o.aliases || []).join(', ')}</td><td className="p-2">{o.active ? '✓' : '–'}</td><td className="p-2"><Btn size="sm" kind="ghost" onClick={() => setEdit({ ...o, aliases: (o.aliases || []).join(', ') })}>Ubah</Btn></td></tr>)}</tbody></table></div>
      <Sheet open={!!edit} onClose={() => setEdit(null)} title={edit?.id ? 'Ubah outlet' : 'Tambah outlet'}>
        {edit && <div className="space-y-3">
          <Field label="Nama"><input className={inputCls} value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
          <Field label="Tipe"><select className={inputCls} value={edit.type} onChange={(e) => setEdit({ ...edit, type: e.target.value })}>{['gerobak', 'kios', 'central_kitchen', 'online_frozen'].map((x) => <option key={x}>{x}</option>)}</select></Field>
          <Field label="Area"><select className={inputCls} value={edit.area} onChange={(e) => setEdit({ ...edit, area: e.target.value })}>{masters.areas.map((x) => <option key={x}>{x}</option>)}</select></Field>
          <Field label="Brand"><input className={inputCls} value={edit.brand} onChange={(e) => setEdit({ ...edit, brand: e.target.value })} /></Field>
          <Field label="Alias (pisahkan koma)" hint="Nama lain yang sering ditulis customer di CSAT/review."><input className={inputCls} value={edit.aliases} onChange={(e) => setEdit({ ...edit, aliases: e.target.value })} /></Field>
          <label className="flex items-center gap-2"><input type="checkbox" className="w-5 h-5" checked={edit.active} onChange={(e) => setEdit({ ...edit, active: e.target.checked })} />Aktif</label>
          <Btn className="w-full" onClick={saveO}>Simpan</Btn>
        </div>}
      </Sheet>
    </Card>
  )
}

function Registrations({ onChange }) {
  const { notify } = useApp()
  const [tab, setTab] = useState('pending')
  const { data, reload } = useAsync(() => api('/registrations', { params: { status: tab === 'all' ? undefined : tab } }), [tab])
  const act = async (r, kind) => {
    try {
      let body = {}
      if (kind === 'reject') { const reason = prompt(`Alasan menolak ${r.name}? (opsional)`); if (reason === null) return; body = { reason } }
      await api(`/registrations/${r.id}/${kind}`, { method: 'POST', body })
      notify(kind === 'approve' ? `${r.name} disetujui sebagai ${r.roleLabel}` : `${r.name} ditolak`); reload(); onChange?.()
    } catch (e) { notify(e.message, 'err') }
  }
  const ST = { pending: 'Menunggu', verify: 'Verifikasi email', approved: 'Disetujui', rejected: 'Ditolak' }
  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h3 className="font-bold">Pendaftaran member baru</h3>
        <div className="flex gap-2">{[['pending', 'Menunggu'], ['verify', 'Verifikasi email'], ['approved', 'Disetujui'], ['rejected', 'Ditolak']].map(([k, l]) => <Chip key={k} active={tab === k} onClick={() => setTab(k)} className="!min-h-[34px] text-xs">{l}</Chip>)}</div>
      </div>
      {data && <div className="grid grid-cols-3 gap-2 mb-3">{data.slots.map((q) => (
        <div key={q.role} className={`rounded-xl px-3 py-2 ${q.available ? 'bg-cream' : 'bg-brick-soft'}`}>
          <div className="text-xs text-mute">{q.label}</div>
          <div className="font-extrabold text-lg tabnum">{q.used}/{q.slots} <span className="text-xs font-normal text-mute">{q.available ? `sisa ${q.available}` : 'penuh'}{q.pending ? ` · ${q.pending} menunggu` : ''}</span></div>
        </div>))}</div>}
      <p className="text-xs text-mute mb-3">Link pendaftaran untuk dibagikan ke tim: <b className="break-all">{location.origin}/daftar</b>. Hanya email kantor; kuota dihitung dari user aktif.</p>
      {data?.rows.length === 0 && <div className="text-sm text-mute py-4 text-center">Tidak ada pendaftaran {ST[tab]?.toLowerCase()}.</div>}
      <div className="space-y-2">{data?.rows.map((r) => (
        <div key={r.id} className="border border-line rounded-xl p-3 flex flex-wrap items-center gap-3">
          <div className="flex-1 min-w-[200px]">
            <div className="font-semibold">{r.name} <span className="text-xs font-normal text-mute">· {r.roleLabel}</span></div>
            <div className="text-sm text-mute">{r.email}{r.phone ? ` · ${r.phone}` : ''}</div>
            <div className="text-xs text-mute">{fmtDT(r.createdAt)} · {r.emailVerified ? 'email terverifikasi' : 'email belum diverifikasi (server email belum aktif)'}{r.decidedBy ? ` · diputuskan ${r.decidedBy}` : ''}{r.reason ? ` · ${r.reason}` : ''}</div>
          </div>
          {r.status === 'pending' && data.canApprove && <div className="flex gap-2">
            <Btn size="sm" kind="ok" onClick={() => act(r, 'approve')}>Setujui</Btn>
            <Btn size="sm" kind="ghost" onClick={() => act(r, 'reject')}>Tolak</Btn>
          </div>}
          {r.status === 'pending' && !data.canApprove && <span className="text-xs text-mute">Menunggu Admin</span>}
        </div>))}</div>
    </Card>
  )
}

function Users() {
  const { masters, notify, user } = useApp()
  const { data, reload } = useAsync(() => api('/users'), [])
  const { data: rq, reload: reloadRoles } = useAsync(() => api('/roles'), [])
  const [nu, setNu] = useState(null)
  const [showOff, setShowOff] = useState(false)
  const roles = (rq?.roles || []).filter((r) => r.role !== 'Admin' || user.role === 'Admin')
  const refresh = () => { reload(); reloadRoles() }
  const act = async (u, body, msg) => { try { await api('/users/' + u.id, { method: 'PATCH', body }); notify(msg); refresh() } catch (e) { notify(e.message, 'err') } }
  const rows = (data || []).filter((u) => showOff || u.active)
  return (
    <div className="space-y-4">
      <Registrations onChange={refresh} />
      <Card className="p-4">
        <div className="flex flex-wrap justify-between gap-2 mb-3"><h3 className="font-bold">User & peran</h3>
          <div className="flex gap-2 items-center"><label className="text-xs flex items-center gap-1"><input type="checkbox" checked={showOff} onChange={(e) => setShowOff(e.target.checked)} />Tampilkan nonaktif</label>
            <Btn size="sm" onClick={() => setNu({ name: '', email: '', role: 'CS Agent', pin: '', areas: [] })}>+ User</Btn></div></div>
        <div className="text-xs text-mute mb-3">Kuota: CRM Supervisor 1 · Marketing Team Leader 1 · Customer Service 5 (user aktif). Manager Area, Ops/QC, Viewer tanpa kuota, dibuat Admin/CRM Supervisor.</div>
        <div className="overflow-x-auto"><table className="w-full text-sm"><tbody>{rows.map((u) => (
          <tr key={u.id} className={`border-t border-line ${u.active ? '' : 'opacity-50'}`}>
            <td className="p-2"><div className="font-semibold">{u.name}{u.locked && <span className="ml-2 text-xs text-brick">terkunci</span>}</div><div className="text-xs text-mute">{u.email || 'login dengan nama'}</div></td>
            <td className="p-2">{u.roleLabel}</td><td className="p-2 text-xs text-mute">{u.areas.join(', ')}</td><td className="p-2">{u.active ? 'Aktif' : 'Nonaktif'}</td>
            <td className="p-2 text-right space-x-1 whitespace-nowrap">
              <Btn size="sm" kind="ghost" onClick={() => { const p = prompt(`PIN baru 6 digit untuk ${u.name}`); if (p) act(u, { pin: p }, 'PIN direset') }}>Reset PIN</Btn>
              {u.locked && <Btn size="sm" kind="ghost" onClick={() => act(u, { unlock: true }, 'Kunci dibuka')}>Buka kunci</Btn>}
              {u.id !== user.id && <Btn size="sm" kind="ghost" onClick={() => act(u, { active: !u.active }, u.active ? 'Dinonaktifkan' : 'Diaktifkan')}>{u.active ? 'Nonaktifkan' : 'Aktifkan'}</Btn>}
            </td></tr>))}</tbody></table></div>
        <Sheet open={!!nu} onClose={() => setNu(null)} title="Tambah user">
          {nu && <div className="space-y-3">
            <Field label="Nama"><input className={inputCls} value={nu.name} onChange={(e) => setNu({ ...nu, name: e.target.value })} /></Field>
            <Field label="Email kantor" hint={`Dipakai untuk login. Wajib @${rq?.domain || 'citarasakuliner.com'}.`}><input className={inputCls} type="email" value={nu.email} onChange={(e) => setNu({ ...nu, email: e.target.value })} /></Field>
            <Field label="Peran"><div className="flex flex-wrap gap-2">{roles.map((r) => {
              const full = r.slots && r.used >= r.slots
              return <Chip key={r.role} active={nu.role === r.role} disabled={full} className={full ? 'opacity-50' : ''} onClick={() => setNu({ ...nu, role: r.role })}>{r.label}{r.slots ? ` (${r.used}/${r.slots})` : ''}</Chip>
            })}</div></Field>
            {nu.role === 'Manager Area' && <Field label="Area"><div className="flex flex-wrap gap-2">{masters.areas.map((a) => <Chip key={a} active={nu.areas.includes(a)} onClick={() => setNu({ ...nu, areas: nu.areas.includes(a) ? nu.areas.filter((x) => x !== a) : [...nu.areas, a] })}>{a}</Chip>)}</div></Field>}
            <Field label="PIN awal (6 digit)"><input className={inputCls} inputMode="numeric" maxLength={6} value={nu.pin} onChange={(e) => setNu({ ...nu, pin: e.target.value.replace(/\D/g, '') })} /></Field>
            <Btn className="w-full" disabled={!nu.name || nu.pin.length !== 6} onClick={async () => { try { await api('/users', { method: 'POST', body: nu }); setNu(null); refresh(); notify('User dibuat') } catch (e) { notify(e.message, 'err') } }}>Simpan</Btn>
          </div>}
        </Sheet>
      </Card>
    </div>
  )
}

function Transaksi() {
  const { notify } = useApp()
  const { data, reload } = useAsync(() => api('/monthly'), [])
  const [m, setM] = useState(new Date().toISOString().slice(0, 7))
  const [v, setV] = useState('')
  return (
    <Card className="p-4">
      <h3 className="font-bold mb-1">Total transaksi per bulan</h3>
      <p className="text-sm text-mute mb-3">Dari POS / marketplace. Dipakai untuk Komplain per 1.000 transaksi (diprorata per hari bila periode tidak sebulan penuh).</p>
      <div className="flex flex-wrap gap-2 items-end mb-4">
        <Field label="Bulan"><input type="month" className={c} value={m} onChange={(e) => setM(e.target.value)} /></Field>
        <Field label="Total transaksi"><input className={c} inputMode="numeric" value={v} onChange={(e) => setV(e.target.value.replace(/\D/g, ''))} /></Field>
        <Btn disabled={!v} onClick={async () => { await api('/monthly/' + m, { method: 'PUT', body: { totalTransaksi: Number(v) } }); notify('Tersimpan'); setV(''); reload() }}>Simpan</Btn>
      </div>
      <table className="w-full text-sm"><tbody>{data?.map((x) => <tr key={x.month} className="border-t border-line"><td className="p-2">{x.month}</td><td className="p-2 font-semibold tabnum">{fmtNum(x.totalTransaksi)}</td></tr>)}</tbody></table>
    </Card>
  )
}

function Impor() {
  const { notify, loadMasters } = useApp()
  const [file, setFile] = useState(null)
  const [rep, setRep] = useState(null)
  const [busy, setBusy] = useState(false)
  const run = async (dry) => {
    setBusy(true)
    try { const fd = new FormData(); fd.append('file', file); fd.append('dryRun', dry ? 'true' : 'false'); setRep(await api('/import/sheet', { method: 'POST', form: fd })); if (!dry) { await loadMasters(); notify('Impor selesai') } }
    catch (e) { notify(e.message, 'err') } finally { setBusy(false) }
  }
  return (
    <Card className="p-4 space-y-3">
      <h3 className="font-bold">Impor dari Google Sheet lama</h3>
      <ol className="text-sm text-mute list-decimal pl-5 space-y-1">
        <li>Buka “Service Excellence Reporting CRK Okt 2026” → File → Download → Microsoft Excel (.xlsx).</li>
        <li>Pilih file di bawah, klik <b>Cek dulu</b> untuk melihat laporan tanpa menyimpan.</li>
        <li>Bila sudah sesuai, klik <b>Impor sekarang</b>. Case ID yang sudah ada dilewati (aman diulang).</li>
      </ol>
      <input type="file" accept=".xlsx" onChange={(e) => { setFile(e.target.files[0]); setRep(null) }} />
      <div className="flex gap-2"><Btn kind="ghost" disabled={!file || busy} onClick={() => run(true)}>{busy ? 'Memproses…' : 'Cek dulu'}</Btn><Btn disabled={!file || busy || !rep?.dryRun} onClick={() => run(false)}>Impor sekarang</Btn></div>
      {rep && (
        <div className="bg-cream rounded-xl p-3 text-sm space-y-2">
          <div className="font-bold">{rep.dryRun ? 'Pratinjau (belum disimpan)' : 'Hasil impor'}</div>
          <div>Case: <b>{rep.cases.imported}</b> diimpor, {rep.cases.skippedExisting} sudah ada · CSAT {rep.csat.imported} · Review {rep.reviews.imported} · Rating {rep.ratings.imported} baris · Voucher {rep.vouchers.imported}</div>
          {rep.duplicates.length > 0 && <div><b>Mungkin duplikat:</b> {rep.duplicates.join('; ')}</div>}
          {rep.outletCreated.length > 0 && <div><b>Outlet baru dibuat:</b> {rep.outletCreated.join(', ')}</div>}
          {rep.outletMatched.length > 0 && <div><b>Outlet dicocokkan otomatis:</b> {[...new Set(rep.outletMatched)].join('; ')}</div>}
          {rep.errors.length > 0 && <div className="text-brick"><b>Perlu dicek:</b> {rep.errors.join('; ')}</div>}
          {rep.cases.issues.length > 0 && <details><summary className="cursor-pointer font-semibold">{rep.cases.issues.length} case dengan catatan Cek Data</summary>
            <ul className="mt-1 space-y-0.5">{rep.cases.issues.map((i) => <li key={i.caseId}><b>{i.caseId}</b>: {i.issues.join('; ')}</li>)}</ul></details>}
          <p className="text-xs text-mute">Catatan cara hitung: aplikasi tidak menghitung FRT untuk case tanpa jam masuk dan tidak memasukkan channel CSAT Form ke % SLA Response (sesuai tab Panduan), jadi angka FRT/SLA bisa sedikit berbeda dari tab Dashboard sheet lama.</p>
        </div>
      )}
    </Card>
  )
}

function Sistem() {
  const { notify, can, loadMasters } = useApp()
  const { data: backups, reload } = useAsync(() => api('/admin/backups'), [])
  const { data: audit } = useAsync(() => api('/admin/audit'), [])
  return (
    <div className="space-y-4">
      <Card className="p-4">
        <h3 className="font-bold mb-2">Backup</h3>
        <p className="text-sm text-mute mb-2">Otomatis tiap Minggu 02.00 WIB, 8 terakhir disimpan di volume /data. Untuk keamanan penuh, pakai MongoDB Atlas dengan backup otomatis.</p>
        <Btn size="sm" onClick={async () => { await api('/admin/backup', { method: 'POST' }); notify('Backup dibuat'); reload() }}>Backup sekarang</Btn>
        <ul className="text-sm mt-2">{backups?.map((b) => <li key={b}><button className="text-brick underline" onClick={() => download('/admin/backups/' + b, null, b)}>{b}</button></li>)}</ul>
      </Card>
      <Card className="p-4 flex flex-wrap gap-2">
        <Btn size="sm" kind="ghost" onClick={async () => { const r = await api('/admin/recompute', { method: 'POST' }); notify(`${r.recomputed} case dihitung ulang`) }}>Hitung ulang semua case</Btn>
        {can('Admin') && <Btn size="sm" kind="ghost" onClick={async () => { try { const r = await api('/admin/seed-demo', { method: 'POST' }); notify(`${r.created} case contoh dibuat`); loadMasters() } catch (e) { notify(e.message, 'err') } }}>Isi data contoh (DB kosong saja)</Btn>}
      </Card>
      <Card className="p-4 overflow-x-auto">
        <h3 className="font-bold mb-2">Audit log</h3>
        <table className="w-full text-sm"><tbody>{audit?.map((a, i) => <tr key={i} className="border-t border-line align-top"><td className="p-2 whitespace-nowrap">{fmtDT(a.when)}</td><td className="p-2">{a.who}</td><td className="p-2">{a.what}</td><td className="p-2 text-mute">{a.reason}</td></tr>)}</tbody></table>
      </Card>
    </div>
  )
}

export default function Settings() {
  const { can, masters } = useApp()
  const [sp, setSp] = useSearchParams()
  const tab = sp.get('tab') || 'standard'
  if (!can(...LEAD)) return <ErrorBox error={{ message: 'Hanya Admin / CS Lead yang bisa membuka Pengaturan.' }} />
  if (!masters) return <Skeleton />
  return (
    <div>
      <h1 className="text-2xl font-extrabold mb-3">Pengaturan</h1>
      <div className="flex flex-wrap gap-2 mb-4">{TABS.map(([k, l]) => <Chip key={k} active={tab === k} onClick={() => setSp({ tab: k })}>{l}</Chip>)}</div>
      {tab === 'standard' && <Standard />}{tab === 'target' && <Target />}{tab === 'outlet' && <Outlets />}
      {tab === 'user' && <Users />}{tab === 'transaksi' && <Transaksi />}{tab === 'impor' && <Impor />}{tab === 'sistem' && <Sistem />}
    </div>
  )
}
