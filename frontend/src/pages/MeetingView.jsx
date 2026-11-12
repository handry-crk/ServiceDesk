import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, useApp, useAsync, fmtD, fmtPct, fmtNum, fmtRp, todayWIB, WRITERS, LEAD, MEETING_EDITORS } from '../lib.jsx'
import { Btn, ErrorBox, Skeleton, LevelBadge, inputCls } from '../ui.jsx'
import { Headline, MetricsTable, LevelTable, HBar, HourChart, Weekly, MemberTable, LevelBreakdown } from './Dashboard.jsx'
import { KompSummary, GroupTable } from './Kompensasi.jsx'
import Compare from './Compare.jsx'
import { IntegrityBody } from './Integritas.jsx'

const STATUSES = ['Open', 'On Progress', 'Done', 'Dropped']
const ST_CLS = { Open: 'bg-brick-soft text-brick', 'On Progress': 'bg-[#F6E6C6] text-[#7A5410]', Done: 'bg-[#DCEBDD] text-ok', Dropped: 'bg-[#E9E5DF] text-mute' }

function Slide({ n, title, children, refs }) {
  return (
    <section ref={(el) => (refs.current[n] = el)} className="slide print-break bg-white rounded-3xl border border-line p-5 md:p-8 mb-6 min-h-[80vh] text-[18px] scroll-mt-20">
      <div className="flex items-baseline gap-3 mb-5"><span className="text-brick font-extrabold text-sm">{String(n + 1).padStart(2, '0')}</span><h2 className="text-2xl md:text-3xl font-extrabold">{title}</h2></div>
      {children}
    </section>
  )
}

function ActionRow({ a, subJenis, masters, editable, onSaved }) {
  const [v, setV] = useState(a || { rootCause: '', action: '', picDept: '', status: 'Open', deadline: '' })
  const [dirty, setDirty] = useState(false)
  useEffect(() => { setV(a || { rootCause: '', action: '', picDept: '', status: 'Open', deadline: '' }); setDirty(false) }, [a])
  const set = (k) => (e) => { setV({ ...v, [k]: e.target.value }); setDirty(true) }
  const save = async () => {
    const body = { subJenis, rootCause: v.rootCause, action: v.action, picDept: v.picDept, status: v.status, deadline: v.deadline || null }
    if (a?.id) await api('/voc-actions/' + a.id, { method: 'PATCH', body })
    else await api('/voc-actions', { method: 'POST', body })
    setDirty(false); onSaved()
  }
  if (!editable) return <><td className="p-2 text-base">{v.rootCause || '–'}</td><td className="p-2 text-base">{v.picDept || '–'}</td><td className="p-2 text-base">{v.action || '–'}</td><td className="p-2"><span className={`px-2 py-0.5 rounded text-xs font-bold ${ST_CLS[v.status]}`}>{v.status}</span></td><td className="p-2 text-base">{fmtD(v.deadline)}</td></>
  const c = inputCls + ' !min-h-[38px] text-sm'
  return (
    <>
      <td className="p-1.5"><textarea rows={2} className={c + ' py-1'} value={v.rootCause || ''} onChange={set('rootCause')} /></td>
      <td className="p-1.5"><select className={c} value={v.picDept || ''} onChange={set('picDept')}><option value="">–</option>{masters?.picDept.map((p) => <option key={p}>{p}</option>)}</select></td>
      <td className="p-1.5"><textarea rows={2} className={c + ' py-1'} value={v.action || ''} onChange={set('action')} /></td>
      <td className="p-1.5"><select className={c} value={v.status} onChange={set('status')}>{STATUSES.map((s) => <option key={s}>{s}</option>)}</select></td>
      <td className="p-1.5"><input type="date" className={c} value={v.deadline || ''} onChange={set('deadline')} />{dirty && <Btn size="sm" className="mt-1 w-full no-print" disabled={!v.action} onClick={save}>Simpan</Btn>}</td>
    </>
  )
}

export default function MeetingView() {
  const { id } = useParams()
  const { masters, can, notify } = useApp()
  const { data, loading, error, reload } = useAsync(() => api('/meetings/' + id), [id])
  const [ins, setIns] = useState([])
  const [cur, setCur] = useState(0)
  const refs = useRef([])
  const editable = can(...MEETING_EDITORS) && data && !data.meeting.locked

  useEffect(() => { if (data) setIns(data.meeting.insights?.length ? data.meeting.insights : []) }, [data])
  useEffect(() => {
    const h = (e) => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return
      if (['ArrowRight', 'PageDown', 'ArrowDown'].includes(e.key)) { e.preventDefault(); go(cur + 1) }
      if (['ArrowLeft', 'PageUp', 'ArrowUp'].includes(e.key)) { e.preventDefault(); go(cur - 1) }
    }
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h)
  })
  const go = (n) => { const k = Math.max(0, Math.min(refs.current.length - 1, n)); setCur(k); refs.current[k]?.scrollIntoView({ behavior: 'smooth' }) }

  if (loading && !data) return <div className="p-6"><Skeleton h="h-96" /></div>
  if (error) return <div className="p-6"><ErrorBox error={error} /></div>
  const { meeting: m, dashboard: d, top5, openActions, reviews, csat } = data

  const saveIns = async (rows) => {
    try { await api('/meetings/' + id, { method: 'PATCH', body: { insights: rows } }); notify('Insight tersimpan') } catch (e) { notify(e.message, 'err') }
  }
  const suggest = async () => {
    const s = await api(`/meetings/${id}/suggest`, { method: 'POST' })
    setIns(s); saveIns(s)
  }
  const lock = async () => { if (confirm('Kunci meeting? Angka akan dibekukan sebagai snapshot.')) { await api(`/meetings/${id}/lock`, { method: 'POST' }); reload() } }
  const updateAction = async (a, status) => { await api('/voc-actions/' + a.id, { method: 'PATCH', body: { status } }); reload() }
  const wa = () => {
    const x = d.metrics, v = d.volume
    const lines = [
      `*${m.title}*`, `Periode ${fmtD(d.period.from)} – ${fmtD(d.period.to)}`, '',
      `Komplain ${v.komplain} (Critical ${v.critical}), open ${v.open}`,
      `FRT ${x.frt ?? '-'} mnt · SLA Response ${fmtPct(x.slaResponse)} · Same-Day ${fmtPct(x.sameDay)} · FCR ${fmtPct(x.fcr)} · CSAT ${fmtPct(x.csat)}`,
      `Biaya kompensasi ${fmtRp(v.biaya)} (di luar standard ${fmtRp(v.biayaLuarStandard)})`,
      ...(d.sourceGroups?.length ? [`Sumber: ${d.sourceGroups.map((g) => `${g.name} ${g.count}`).join(' · ')}`] : []),
      ...(d.channels?.some((c) => c.group === 'Online Food Aggregator') ? [`Aggregator: ${d.channels.filter((c) => c.group === 'Online Food Aggregator').map((c) => `${c.name} ${c.count}`).join(' · ')}`] : []),
      ...(reviews.count ? [`Review online: ${Object.entries(reviews.byPlatform || {}).map(([k, n]) => `${k} ${n}`).join(' · ')} (Critical ${reviews.critical}, belum diproses ${reviews.belumDiproses})`] : []),
      '', '*Top 5 issue*',
      ...top5.map((t) => `${t.rank}. ${t.name} — ${t.count} (${fmtPct(t.pct)})${t.action?.action ? ` → ${t.action.action} [${t.action.picDept || '-'}, ${t.action.status}]` : ''}`),
      '', '*Insight*', ...ins.filter((i) => i.whatHappened).map((i, k) => `${k + 1}. ${i.whatHappened}${i.action ? ` → ${i.action} (${i.pic || '-'})` : ''}`),
    ]
    navigator.clipboard.writeText(lines.join('\n')).then(() => notify('Ringkasan WA tersalin'))
  }
  const SLIDES = ['Headline & service metrics', 'Komplain per level & tren', 'Komparasi week by week & month by month', 'Voice of Customer — Top 5', 'Action tracker', 'Insight untuk management', 'Review online & CSAT outlet', 'Tracker complimentary', 'Integritas waktu', 'Kualitas data & keputusan']

  return (
    <div className="bg-cream min-h-screen">
      <div className="no-print sticky top-0 z-30 bg-brick text-white">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center gap-2">
          <Link to="/meeting" className="text-sm opacity-90">←</Link>
          <div className="font-bold truncate flex-1">{m.title} <span className="font-normal opacity-80 text-sm">· {fmtD(d.period.from)} – {fmtD(d.period.to)}{m.locked ? ' · terkunci' : ''}</span></div>
          <select className="bg-white/15 rounded-lg px-2 py-1 text-sm hidden md:block" value={cur} onChange={(e) => go(Number(e.target.value))}>{SLIDES.map((s, i) => <option key={i} value={i} className="text-ink">{i + 1}. {s}</option>)}</select>
          <button className="px-2 py-1 rounded-lg hover:bg-white/15" onClick={() => go(cur - 1)}>‹</button>
          <button className="px-2 py-1 rounded-lg hover:bg-white/15" onClick={() => go(cur + 1)}>›</button>
          <button className="text-sm px-3 py-1.5 rounded-lg bg-white/15" onClick={wa}>Salin WA</button>
          <button className="text-sm px-3 py-1.5 rounded-lg bg-white/15" onClick={() => window.print()}>Unduh PDF</button>
          {can(...LEAD) && !m.locked && <button className="text-sm px-3 py-1.5 rounded-lg bg-white text-brick font-bold" onClick={lock}>Kunci</button>}
        </div>
      </div>
      <div className="max-w-7xl mx-auto px-3 md:px-6 py-6">
        <Slide n={0} title={SLIDES[0]} refs={refs}>
          <Headline d={d} />
          <div className="mt-4"><MetricsTable d={d} /></div>
          {d.members && <div className="mt-4"><MemberTable d={d} /></div>}
          {data.prevMeetingDate && <p className="text-sm text-mute mt-3">Meeting terkunci sebelumnya: {fmtD(data.prevMeetingDate)}.</p>}
        </Slide>
        <Slide n={1} title={SLIDES[1]} refs={refs}>
          <div className="grid gap-4 lg:grid-cols-2">
            <LevelTable d={d} />
            <div className="bg-white rounded-2xl border border-line p-4"><div className="font-bold mb-2">Jenis komplain</div><HBar rows={d.jenis} /></div>
          </div>
          <div className="mt-4"><LevelBreakdown d={d} meeting /></div>
          {d.sourceGroups?.length > 0 && (
            <div className="bg-white rounded-2xl border border-line p-4 mt-4">
              <div className="font-bold mb-3">Sumber komplain</div>
              <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
                <div className="grid grid-cols-2 gap-2 content-start">{d.sourceGroups.map((g) => (
                  <div key={g.name} className={`rounded-xl px-3 py-2 ${g.name === 'Online Food Aggregator' ? 'bg-brick-soft' : 'bg-cream'}`}>
                    <div className="text-xs text-mute">{g.name}</div>
                    <div className="text-2xl font-extrabold tabnum">{g.count} <span className="text-sm font-normal text-mute">{fmtPct(g.pct)}</span></div>
                    <div className="text-xs text-mute">FRT {g.avgFrt === null ? '–' : `${fmtNum(g.avgFrt)} mnt`} · SLA {fmtPct(g.slaResponse)} · Critical {g.critical}</div>
                  </div>
                ))}</div>
                <table className="w-full text-sm self-start"><thead className="text-left text-mute"><tr>{['Channel', 'Case', 'FRT', '% SLA', 'Critical'].map((h) => <th key={h} className="py-1 font-semibold">{h}</th>)}</tr></thead>
                  <tbody>{d.channels.map((r) => <tr key={r.name} className="border-t border-line tabnum"><td className="py-1.5">{r.name}<span className="text-xs text-mute ml-2">{r.group}</span></td><td>{r.count}</td><td>{r.avgFrt === null ? '–' : `${fmtNum(r.avgFrt)} mnt`}</td><td>{fmtPct(r.slaResponse)}</td><td className={r.critical ? 'text-brick font-bold' : ''}>{r.critical}</td></tr>)}</tbody></table>
              </div>
            </div>
          )}
          <div className="grid gap-4 md:grid-cols-3 mt-4">
            <div className="bg-white rounded-2xl border border-line p-4"><div className="font-bold">Komplain per minggu</div><Weekly weeks={d.weeks} k="komplain" name="Komplain" fmt={fmtNum} /></div>
            <div className="bg-white rounded-2xl border border-line p-4"><div className="font-bold">% SLA Response</div><Weekly weeks={d.weeks} k="slaResponse" name="SLA" fmt={fmtPct} target={d.targets.slaResponse.target} /></div>
            <div className="bg-white rounded-2xl border border-line p-4"><div className="font-bold">FRT per jam masuk</div><HourChart hours={d.hours} /><p className="text-sm text-mute">{d.insights.hour}</p></div>
          </div>
        </Slide>
        <Slide n={2} title={SLIDES[2]} refs={refs}>
          <Compare meeting={{ end: d.period.to, snapshot: m.locked ? d.compare : null }} />
        </Slide>
        <Slide n={3} title={SLIDES[3]} refs={refs}>
          <p className="text-sm text-mute mb-3">Action menempel ke sub jenis, jadi tetap ada walau urutan Top 5 berubah minggu depan.</p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px]">
              <thead className="bg-brick text-white text-left text-sm"><tr>{['#', 'Sub jenis', 'Volume', '%', 'Root cause', 'PIC', 'Action', 'Status', 'Deadline'].map((h) => <th key={h} className="p-2">{h}</th>)}</tr></thead>
              <tbody>
                {top5.map((t) => (
                  <tr key={t.name} className="border-t border-line align-top">
                    <td className="p-2 font-extrabold text-brick text-xl">{t.rank}</td>
                    <td className="p-2"><div className="font-bold">{t.name}</div><LevelBadge level={t.levelStandard} /></td>
                    <td className="p-2 font-bold text-xl tabnum">{t.count}</td><td className="p-2 tabnum">{fmtPct(t.pct)}</td>
                    <ActionRow a={t.action} subJenis={t.name} masters={masters} editable={editable} onSaved={() => { notify('Action tersimpan'); reload() }} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Slide>
        <Slide n={4} title={SLIDES[4]} refs={refs}>
          {openActions.length === 0 ? <p className="text-mute">Tidak ada action yang masih terbuka.</p> : (
            <div className="grid gap-3 md:grid-cols-2">
              {openActions.map((a) => {
                const overdue = a.deadline && a.deadline < todayWIB()
                return (
                  <div key={a.id} className={`rounded-2xl border p-4 ${overdue ? 'border-brick bg-brick-soft/40' : 'border-line'}`}>
                    <div className="flex items-center gap-2 text-sm mb-1"><b>{a.subJenis || a.topic}</b>{overdue && <span className="text-brick font-bold text-xs">LEWAT DEADLINE</span>}</div>
                    <div className="text-lg font-semibold">{a.action}</div>
                    <div className="text-sm text-mute">{a.picDept || '-'}{a.picName ? ` · ${a.picName}` : ''} · deadline {fmtD(a.deadline)}</div>
                    {a.updates?.length > 0 && <div className="text-xs text-mute mt-1">Update terakhir: {a.updates[a.updates.length - 1].text}</div>}
                    {can(...MEETING_EDITORS, 'Manager Area', 'Ops/QC') && <div className="flex flex-wrap gap-1 mt-2 no-print">{STATUSES.map((s) => <button key={s} onClick={() => updateAction(a, s)} className={`text-xs px-2.5 py-1.5 rounded-lg font-bold ${a.status === s ? ST_CLS[s] + ' ring-2 ring-ink/20' : 'bg-cream'}`}>{s}</button>)}</div>}
                  </div>
                )
              })}
            </div>
          )}
        </Slide>
        <Slide n={5} title={SLIDES[5]} refs={refs}>
          {editable && <div className="flex gap-2 mb-3 no-print"><Btn kind="soft" onClick={suggest}>Saran otomatis dari data</Btn><Btn kind="ghost" onClick={() => setIns([...ins, { whatHappened: '', why: '', businessImpact: '', action: '', pic: '' }])}>+ Baris</Btn><Btn onClick={() => saveIns(ins)}>Simpan insight</Btn></div>}
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px]">
              <thead className="bg-brick text-white text-left text-sm"><tr>{['#', 'What happened', 'Why', 'Business impact', 'Action', 'PIC'].map((h) => <th key={h} className="p-2">{h}</th>)}</tr></thead>
              <tbody>
                {ins.length === 0 && <tr><td colSpan={6} className="p-4 text-mute">Belum ada insight. Klik “Saran otomatis dari data” lalu sunting bersama.</td></tr>}
                {ins.map((r, i) => (
                  <tr key={i} className="border-t border-line align-top">
                    <td className="p-2 font-extrabold text-brick">{i + 1}</td>
                    {['whatHappened', 'why', 'businessImpact', 'action', 'pic'].map((k) => (
                      <td key={k} className="p-1.5">{editable
                        ? <textarea rows={3} className={inputCls + ' text-sm py-1'} value={r[k] || ''} onChange={(e) => setIns(ins.map((x, j) => j === i ? { ...x, [k]: e.target.value } : x))} />
                        : <span className="text-base">{r[k]}</span>}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Slide>
        <Slide n={6} title={SLIDES[6]} refs={refs}>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border border-line p-4">
              <div className="font-bold mb-2">Review online (GoFood / GrabFood / ShopeeFood)</div>
              <div className="text-4xl font-extrabold">{reviews.count}<span className="text-base font-normal text-mute"> review komplain</span></div>
              {Object.keys(reviews.byPlatform || {}).length > 0 && <div className="flex flex-wrap gap-2 mt-2">{Object.entries(reviews.byPlatform).map(([k, v]) => <span key={k} className="px-2 py-1 rounded-lg bg-cream text-sm">{k} <b>{v}</b></span>)}</div>}
              <div className="text-sm mt-1">Critical <b className="text-brick">{reviews.critical}</b> · Belum diproses <b>{reviews.belumDiproses}</b></div>
              <ul className="mt-3 text-sm space-y-1">{reviews.bySubJenis.map(([k, v]) => <li key={k} className="flex justify-between border-b border-line/60 py-1"><span>{k}</span><b>{v}</b></li>)}</ul>
            </div>
            <div className="rounded-2xl border border-line p-4">
              <div className="font-bold mb-2">CSAT outlet (form)</div>
              <div className="text-4xl font-extrabold">{fmtPct(csat.puas)}<span className="text-base font-normal text-mute"> rating 4–5</span></div>
              <div className="text-sm mt-1">{csat.count} respons · rata-rata {csat.avg ?? '–'} · bersedia beli lagi {fmtPct(csat.beliLagi)}</div>
            </div>
          </div>
        </Slide>
        <Slide n={7} title={SLIDES[7]} refs={refs}>
          {d.komp ? <div className="space-y-4"><KompSummary d={d.komp} /><div className="grid gap-4 lg:grid-cols-2"><GroupTable title="Per bentuk complimentary" rows={d.komp.byJenis} nameLabel="Bentuk" /><GroupTable title="Per level komplain" rows={d.komp.byLevel} nameLabel="Level" /></div></div> : <div className="text-mute">Belum ada data.</div>}
        </Slide>
        <Slide n={8} title={SLIDES[8]} refs={refs}>
          {d.integrity ? <IntegrityBody d={d.integrity} compact /> : <div className="text-mute">Belum ada data integritas.</div>}
        </Slide>
        <Slide n={9} title={SLIDES[9]} refs={refs}>
          <div className="text-lg">{d.volume.dataIssues === 0 ? '✓ Semua case periode ini lolos Cek Data.' : <>⚠ <b>{d.volume.dataIssues}</b> case perlu dicek sebelum angka dipakai. <Link className="text-brick underline no-print" to={`/case?dataIssue=true&from=${d.period.from}&to=${d.period.to}`}>Lihat daftar</Link></>}</div>
          <div className="mt-4 text-lg">Kompensasi di luar CRM.STD.001: <b>{d.volume.countLuarStandard}</b> case, {fmtRp(d.volume.biayaLuarStandard)}.</div>
          {d.insights.kompensasi && <p className="text-mute mt-1">{d.insights.kompensasi}</p>}
          <div className="mt-6 text-sm text-mute">Peserta: {m.attendees || '–'}</div>
        </Slide>
      </div>
    </div>
  )
}
