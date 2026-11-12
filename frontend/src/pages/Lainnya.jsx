import { Link } from 'react-router-dom'
import { useApp, LEAD, roleLabel } from '../lib.jsx'
import { Card } from '../ui.jsx'

export default function Lainnya() {
  const { can, user, logout } = useApp()
  const items = [
    { to: '/csat', t: 'CSAT Outlet', d: 'Respons form survei outlet, cocokkan outlet, link/QR survei.' },
    { to: '/review', t: 'Review & Rating Online', d: 'Review komplain GoFood/GrabFood, status tindak lanjut, rating per outlet.' },
    { to: '/voucher', t: 'Kode Voucher', d: 'Stok voucher kompensasi, status diterbitkan/terpakai.' },
    ...(can('Admin', 'CS Lead', 'Marketing TL') ? [{ to: '/integritas', t: 'Integritas waktu', d: 'Pengajuan koreksi jam dibalas, pengawasan per CS, audit acak mingguan.' }] : []),
    ...(can(...LEAD) ? [{ to: '/pengaturan', t: 'Pengaturan', d: 'Standard CRM.STD.001, target, outlet, user, transaksi bulanan, impor sheet lama, backup.' }] : []),
  ]
  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-extrabold mb-4">Lainnya</h1>
      <div className="grid gap-3 sm:grid-cols-2">
        {items.map((i) => <Link key={i.to} to={i.to}><Card className="p-4 h-full hover:border-brick"><div className="font-bold">{i.t}</div><div className="text-sm text-mute">{i.d}</div></Card></Link>)}
      </div>
      <div className="mt-6 text-sm text-mute">Masuk sebagai <b>{user.name}</b> ({roleLabel(user.role)}). <button className="text-brick underline" onClick={logout}>Keluar</button></div>
    </div>
  )
}
