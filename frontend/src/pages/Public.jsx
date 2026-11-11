import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../lib.jsx'
import { Btn, Chip, inputCls, ErrorBox } from '../ui.jsx'

const FACES = ['😡', '🙁', '😐', '🙂', '😍']

function Scale({ value, onChange }) {
  return (
    <div className="flex justify-between gap-1">
      {FACES.map((f, i) => (
        <button type="button" key={i} onClick={() => onChange(i + 1)}
          className={`flex-1 aspect-square max-w-[60px] rounded-2xl text-3xl border-2 transition ${value === i + 1 ? 'border-brick bg-brick-soft scale-105' : 'border-line bg-white'}`}>{f}<div className="text-xs text-mute">{i + 1}</div></button>
      ))}
    </div>
  )
}

const Wrap = ({ children }) => (
  <div className="min-h-screen bg-cream flex justify-center p-4">
    <div className="w-full max-w-md">
      <div className="bg-brick text-white rounded-3xl p-5 mb-4"><div className="text-sm opacity-90">Cimol Bojot AA</div><h1 className="text-xl font-extrabold">Gimana pengalamanmu, aa & teteh?</h1></div>
      {children}
    </div>
  </div>
)

export function SurveiOutlet() {
  const { outletId } = useParams()
  const [outlets, setOutlets] = useState([])
  const [f, setF] = useState({ outlet: '', outletId: outletId || '', phone: '', puasPelayanan: 0, rasa: 0, kebersihan: 0, beliLagi: '', kritikSaran: '', ratingKeseluruhan: 0, lamaTunggu: '' })
  const [step, setStep] = useState(0)
  const [err, setErr] = useState(null)
  const [done, setDone] = useState(false)
  useEffect(() => { api('/public/outlets').then((o) => { setOutlets(o); if (outletId) { const x = o.find((y) => y.id === outletId); if (x) setF((f) => ({ ...f, outlet: x.name })) } }).catch(() => {}) }, [outletId])
  const set = (k) => (v) => setF({ ...f, [k]: v?.target ? v.target.value : v })
  const submit = async () => {
    setErr(null)
    try { await api('/public/csat', { method: 'POST', body: f }); setDone(true) } catch (e) { setErr(e) }
  }
  if (done) return <Wrap><div className="bg-white rounded-3xl p-8 text-center"><div className="text-5xl mb-3">🙏</div><div className="text-xl font-bold">Terima kasih!</div><p className="text-mute mt-2">Masukanmu langsung dibaca tim Customer Service kami.</p></div></Wrap>
  const steps = [
    { ok: f.outlet, el: <>
      <Q t="Beli di cabang mana?">{outletId && f.outlet ? <div className="font-bold">{f.outlet}</div> : <>
        <input list="ol" className={inputCls} value={f.outlet} onChange={(e) => { const x = outlets.find((o) => o.name === e.target.value); setF({ ...f, outlet: e.target.value, outletId: x?.id || '' }) }} placeholder="Ketik nama cabang" />
        <datalist id="ol">{outlets.map((o) => <option key={o.id} value={o.name} />)}</datalist></>}</Q>
      <Q t="Nomor HP (opsional)"><input className={inputCls} inputMode="tel" value={f.phone} onChange={set('phone')} placeholder="08xxxxxxxxxx" /></Q>
      <Q t="Berapa lama menunggu sampai pesanan disajikan?"><div className="flex flex-wrap gap-2">{['Kurang dari 1 menit', '1-2 menit', '3-5 menit', 'Lebih dari 5 menit'].map((x) => <Chip key={x} active={f.lamaTunggu === x} onClick={() => set('lamaTunggu')(x)}>{x}</Chip>)}</div></Q>
    </> },
    { ok: f.puasPelayanan && f.rasa && f.kebersihan, el: <>
      <Q t="Seberapa puas dengan pelayanan mitra kami?"><Scale value={f.puasPelayanan} onChange={set('puasPelayanan')} /></Q>
      <Q t="Bagaimana kualitas rasanya?"><Scale value={f.rasa} onChange={set('rasa')} /></Q>
      <Q t="Bagaimana kebersihan gerobak/outlet?"><Scale value={f.kebersihan} onChange={set('kebersihan')} /></Q>
    </> },
    { ok: f.ratingKeseluruhan && f.beliLagi, el: <>
      <Q t="Rating keseluruhan (pelayanan, kebersihan, rasa)"><Scale value={f.ratingKeseluruhan} onChange={set('ratingKeseluruhan')} /></Q>
      <Q t="Bersedia beli lagi?"><div className="flex gap-2"><Chip active={f.beliLagi === 'Ya'} onClick={() => set('beliLagi')('Ya')}>Ya</Chip><Chip active={f.beliLagi === 'Tidak'} onClick={() => set('beliLagi')('Tidak')}>Tidak</Chip></div></Q>
      <Q t="Kritik & saran"><textarea className={inputCls + ' min-h-[100px] py-2'} value={f.kritikSaran} onChange={set('kritikSaran')} /></Q>
    </> },
  ]
  return (
    <Wrap>
      <div className="bg-white rounded-3xl p-5 space-y-5">
        <div className="flex gap-1">{steps.map((_, i) => <div key={i} className={`h-1.5 flex-1 rounded-full ${i <= step ? 'bg-brick' : 'bg-line'}`} />)}</div>
        {steps[step].el}
        <ErrorBox error={err} />
        <div className="flex gap-2">
          {step > 0 && <Btn kind="ghost" onClick={() => setStep(step - 1)}>Kembali</Btn>}
          {step < steps.length - 1 ? <Btn className="flex-1" disabled={!steps[step].ok} onClick={() => setStep(step + 1)}>Lanjut</Btn>
            : <Btn className="flex-1" disabled={!steps[step].ok} onClick={submit}>Kirim</Btn>}
        </div>
      </div>
    </Wrap>
  )
}

const Q = ({ t, children }) => <div><div className="font-semibold mb-2">{t}</div>{children}</div>

export function SurveiCase() {
  const { token } = useParams()
  const [info, setInfo] = useState(null)
  const [err, setErr] = useState(null)
  const [rating, setRating] = useState(0)
  const [comment, setComment] = useState('')
  const [done, setDone] = useState(false)
  useEffect(() => { api('/public/survey/' + token).then(setInfo).catch(setErr) }, [token])
  const send = async (r) => {
    setRating(r)
    try { await api('/public/survey/' + token, { method: 'POST', body: { rating: r, comment } }); setDone(true) } catch (e) { setErr(e) }
  }
  return (
    <Wrap>
      <div className="bg-white rounded-3xl p-5 space-y-4">
        <ErrorBox error={err} />
        {info && (done || info.done ? <div className="text-center py-6"><div className="text-5xl">🙏</div><div className="font-bold text-lg mt-2">Terima kasih atas penilaiannya!</div></div> : <>
          <div className="font-semibold">Seberapa puas dengan penanganan keluhanmu (#{info.caseId}) oleh tim kami?</div>
          <Scale value={rating} onChange={send} />
          <textarea className={inputCls + ' py-2'} placeholder="Komentar (opsional, isi sebelum memilih rating)" value={comment} onChange={(e) => setComment(e.target.value)} />
        </>)}
      </div>
    </Wrap>
  )
}
