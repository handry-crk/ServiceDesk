import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, useApp, useAsync, fmtD, presets, todayWIB, MEETING_EDITORS } from '../lib.jsx'
import { Btn, Card, Empty, ErrorBox, Field, Sheet, Skeleton, PeriodPicker, inputCls } from '../ui.jsx'

export default function Meetings() {
  const { can, notify } = useApp()
  const nav = useNavigate()
  const { data, loading, error } = useAsync(() => api('/meetings'), [])
  const lw = presets().find((p) => p.key === 'lastweek')
  const [open, setOpen] = useState(false)
  const [f, setF] = useState({ date: todayWIB(), periodStart: lw.from, periodEnd: lw.to, attendees: '' })
  const create = async () => {
    try { const m = await api('/meetings', { method: 'POST', body: f }); nav('/meeting/' + m.id) } catch (e) { notify(e.message, 'err') }
  }
  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div><h1 className="text-2xl font-extrabold">Meeting Service Excellence</h1><p className="text-sm text-mute">Mode presentasi: headline, VoC Top 5, action tracker, insight untuk management.</p></div>
        {can(...MEETING_EDITORS) && <Btn onClick={() => setOpen(true)}>+ Buat meeting</Btn>}
      </div>
      <ErrorBox error={error} />
      {loading ? <Skeleton /> : (
        <div className="grid gap-3 md:grid-cols-2">
          {data?.length === 0 && <Empty>Belum ada meeting. Buat meeting pertama untuk periode minggu lalu.</Empty>}
          {data?.map((m) => (
            <Link key={m.id} to={'/meeting/' + m.id}>
              <Card className="p-4 hover:border-brick">
                <div className="flex items-center gap-2"><div className="font-bold">{m.title}</div>{m.locked && <span className="text-xs px-2 py-0.5 rounded bg-cream">Terkunci</span>}</div>
                <div className="text-sm text-mute">Periode {fmtD(m.periodStart)} – {fmtD(m.periodEnd)}</div>
              </Card>
            </Link>
          ))}
        </div>
      )}
      <Sheet open={open} onClose={() => setOpen(false)} title="Buat meeting">
        <div className="space-y-4">
          <Field label="Tanggal meeting"><input type="date" className={inputCls} value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
          <Field label="Periode data"><PeriodPicker value={{ from: f.periodStart, to: f.periodEnd }} onChange={(v) => setF({ ...f, periodStart: v.from, periodEnd: v.to })} /></Field>
          <Field label="Peserta (opsional)"><input className={inputCls} value={f.attendees} onChange={(e) => setF({ ...f, attendees: e.target.value })} /></Field>
          <Btn className="w-full" onClick={create}>Buat & buka</Btn>
        </div>
      </Sheet>
    </div>
  )
}
