import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, useApp, useAsync, fmtDT, WRITERS } from '../lib.jsx'
import { Btn, Card, Empty, ErrorBox, Sheet, Skeleton, LevelBadge, Field, inputCls } from '../ui.jsx'
import { CaseCard, Combo, useNow, levelItemBadge } from '../components.jsx'

function Section({ title, count, children, tone }) {
  const [open, setOpen] = useState(true)
  return (
    <section className="mb-6">
      <button className="flex items-center gap-2 mb-3" onClick={() => setOpen(!open)}>
        <h2 className="text-lg font-bold">{title}</h2>
        <span className={`min-w-[28px] h-7 px-2 rounded-full text-sm font-bold flex items-center justify-center ${tone || 'bg-white border border-line'}`}>{count}</span>
        <span className="text-mute text-sm">{open ? '▾' : '▸'}</span>
      </button>
      {open && <div className="grid gap-3 md:grid-cols-2">{children}</div>}
    </section>
  )
}

export default function Inbox() {
  const { can, notify, masters } = useApp()
  const nav = useNavigate()
  const now = useNow()
  const { data, loading, error, reload } = useAsync(() => api('/inbox'), [])
  const [triage, setTriage] = useState(null)
  const [sub, setSub] = useState('')
  const writer = can(...WRITERS)

  const respond = async (c) => {
    try { await api(`/cases/${c.caseId}/respond`, { method: 'POST' }); notify(`${c.caseId} ditandai sudah dibalas`); reload() }
    catch (e) { notify(e.message, 'err') }
  }
  const csatAction = async (id, action, subJenis) => {
    try {
      const r = await api(`/csat/${id}/triage`, { method: 'POST', body: { action, subJenis } })
      setTriage(null); reload()
      if (r.caseId) { notify(`Case ${r.caseId} dibuat dari CSAT`, 'ok', { label: 'Buka', fn: () => nav('/case/' + r.caseId) }) }
    } catch (e) { notify(e.message, 'err') }
  }
  const reviewAction = async (r, action) => {
    try {
      if (action === 'case') {
        const x = await api(`/reviews/${r.id}/to-case`, { method: 'POST' })
        notify(`Case ${x.caseId} dibuat dari review`, 'ok', { label: 'Buka', fn: () => nav('/case/' + x.caseId) })
      } else await api(`/reviews/${r.id}`, { method: 'PATCH', body: { triage: 'tidak_perlu' } })
      reload()
    } catch (e) { notify(e.message, 'err') }
  }

  if (loading && !data) return <div className="space-y-3"><Skeleton /><Skeleton /><Skeleton /></div>
  if (error) return <ErrorBox error={error} />
  const subItems = (masters?.subJenis || []).map((s) => ({ value: s.name, label: s.name, sub: s.contoh, keywords: s.keywords, level: s.level }))
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div><h1 className="text-2xl font-extrabold">Inbox</h1><p className="text-sm text-mute">Diurutkan: Critical dulu, lalu yang paling dekat batas SLA.</p></div>
        {writer && <Link to="/catat"><Btn>+ Catat komplain</Btn></Link>}
      </div>

      <Section title="Belum dibalas" count={data.open.length} tone={data.open.length ? 'bg-brick text-white' : ''}>
        {data.open.length === 0 && <Empty>Semua chat sudah dibalas. 👍</Empty>}
        {data.open.map((c) => <CaseCard key={c.caseId} c={c} now={now}
          action={writer && <Btn kind="ok" className="w-full" onClick={() => respond(c)}>Sudah dibalas</Btn>} />)}
      </Section>

      <Section title="Menunggu penyelesaian" count={data.responded.length}>
        {data.responded.length === 0 && <Empty>Tidak ada.</Empty>}
        {data.responded.map((c) => <CaseCard key={c.caseId} c={c} now={now}
          action={writer && <Btn kind="soft" className="w-full" onClick={() => nav(`/case/${c.caseId}?aksi=resolve`)}>Selesai (Resolved)…</Btn>} />)}
      </Section>

      <Section title="Menunggu konfirmasi customer" count={data.resolved.length + (data.resolvedOlder || 0)}>
        {data.resolved.length === 0 && <Empty>Tidak ada.</Empty>}
        {data.resolvedOlder > 0 && <Link to="/case?status=Resolved" className="md:col-span-2 text-sm text-brick underline">{data.resolvedOlder} case Resolved lebih dari 14 hari belum di-Closed — lihat di menu Case</Link>}
        {data.resolved.map((c) => <CaseCard key={c.caseId} c={c} now={now}
          action={writer && <Btn kind="ghost" className="w-full" onClick={() => nav(`/case/${c.caseId}?aksi=close`)}>Closed (customer confirm)…</Btn>} />)}
      </Section>

      <Section title="Draft dari CSAT & Review" count={data.csatDrafts.length + data.reviewDrafts.length}>
        {data.csatDrafts.length + data.reviewDrafts.length === 0 && <Empty>Tidak ada CSAT/review jelek yang menunggu.</Empty>}
        {data.csatDrafts.map((r) => (
          <Card key={r.id} className="p-4">
            <div className="flex items-center gap-2 mb-1 text-sm"><span className="font-bold">CSAT</span>
              <span className="px-2 rounded-md bg-brick-soft text-brick text-xs font-bold">Rating {r.ratingKeseluruhan} · Pelayanan {r.puasPelayanan}</span>
              {r.beliLagi === 'Tidak' && <span className="text-xs text-brick font-semibold">Tidak mau beli lagi</span>}</div>
            <div className="text-sm font-semibold">{r.outletName || <span className="text-warn">Outlet belum cocok: “{r.outletText}”</span>}</div>
            <div className="text-sm text-mute line-clamp-3">{r.kritikSaran || '(tanpa komentar)'}</div>
            <div className="text-xs text-mute mt-1">{fmtDT(r.timestamp)}</div>
            {writer && <div className="flex gap-2 mt-3">
              {r.outletId ? <Btn size="sm" onClick={() => { setTriage(r); setSub('') }}>Jadikan case</Btn> : <Link to="/csat"><Btn size="sm" kind="soft">Cocokkan outlet</Btn></Link>}
              <Btn size="sm" kind="ghost" onClick={() => csatAction(r.id, 'tidak_perlu')}>Tidak perlu</Btn>
            </div>}
          </Card>
        ))}
        {data.reviewDrafts.map((r) => (
          <Card key={r.id} className="p-4">
            <div className="flex items-center gap-2 mb-1 text-sm"><span className="font-bold">{r.platform}</span><span>★{r.rating}</span><LevelBadge level={r.level} /></div>
            <div className="text-sm font-semibold">{r.subJenis} · {r.outletName}</div>
            <div className="text-sm text-mute line-clamp-3">{r.review}</div>
            <div className="text-xs text-mute mt-1">{fmtDT(r.tanggal)} · {r.statusTindakLanjut}</div>
            {writer && <div className="flex gap-2 mt-3">
              <Btn size="sm" onClick={() => reviewAction(r, 'case')}>Jadikan case</Btn>
              <Btn size="sm" kind="ghost" onClick={() => reviewAction(r, 'skip')}>Tidak perlu</Btn>
            </div>}
          </Card>
        ))}
      </Section>

      <Sheet open={!!triage} onClose={() => setTriage(null)} title="Jadikan case dari CSAT">
        {triage && <div className="space-y-4">
          <div className="text-sm bg-cream rounded-xl p-3">“{triage.kritikSaran || 'tanpa komentar'}” — {triage.outletName}</div>
          <Field label="Sub Jenis Komplain" required>
            <Combo items={subItems} value={sub} onChange={setSub} placeholder="Ketik: lama, kembalian, kasar…" renderBadge={levelItemBadge} />
          </Field>
          <Btn className="w-full" disabled={!sub} onClick={() => csatAction(triage.id, 'jadi_case', sub)}>Buat case</Btn>
        </div>}
      </Sheet>
    </div>
  )
}
