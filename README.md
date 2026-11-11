# CRK Service Desk

Aplikasi komplain & dashboard **Service Excellence CRM/CS CRK Group**. Menggantikan input manual di Google Sheet *Service Excellence Reporting CRK Okt 2026*. Klasifikasi, SLA, dan kompensasi mengikuti **CRM.STD.001 Revisi 00 (efektif 20 Oktober 2026)**.

Stack: React + Tailwind + Recharts (frontend) · FastAPI (backend) · MongoDB · APScheduler. Satu service: FastAPI menyajikan React di `/` dan API di `/api`.

## Fitur
- **Catat komplain ≤ 60 detik**: 5 isian (channel, outlet, sub jenis, ringkasan, waktu masuk). Level, jenis, penanggung jawab, cost center, target FRT & SLA otomatis. Sub jenis bisa dicari dengan kata sehari-hari ("mentah" → Undercooked). Cek duplikat sebelum simpan. Input suara & foto bukti (dikompres di HP).
- **Tombol status, bukan ketik jam**: *Sudah dibalas* → *Selesai (Resolved)* → *Closed*. Waktu dicap server (WIB). Koreksi waktu hanya oleh CS Lead, wajib alasan, masuk audit log.
- **Kompensasi sesuai matriks 5.1**: pilihan difilter per level. Refund/Tidak Ada tetap bisa dipilih, ditandai *Di luar standard*. Voucher otomatis mengambil kode berikutnya dari stok dan menyiapkan pesan WA untuk customer.
- **Inbox**: Critical dulu, lalu yang paling dekat batas SLA. Draft dari CSAT (rating ≤ 2 / tidak mau beli lagi) dan review online Critical bisa langsung dijadikan case.
- **Dashboard**: headline Fase 1 vs target dan vs periode sebelumnya, volume, 9 service metric, per level/jenis/sub jenis, tren mingguan, FRT per jam masuk, channel, outlet, PIC, kompensasi, kualitas data.
- **Mode Meeting**: 7 slide (navigasi panah ← →), VoC Top 5 dengan action yang menempel ke sub jenis, action tracker lintas meeting, insight untuk management (ada saran otomatis), kunci snapshot, Unduh PDF (print A4 landscape), Salin ringkasan WA.
- **CSAT outlet** (`/survei-outlet`, `/survei-outlet/{outletId}` untuk QR per gerobak) pengganti Google Form, dengan pencocokan nama outlet otomatis + alias. **Survei 1-tap per case** (`/survei/{token}`).
- **Review & Rating online** GoFood/GrabFood, **Kode Voucher**, **Pengaturan** (matriks standard, target, channel, jam operasional CS, outlet, user & peran, transaksi bulanan, impor sheet lama, backup, audit log).
- **Peran**: Admin, CS Lead, CS Agent, Manager Area (hanya areanya), Ops/QC, Viewer (nomor HP disamarkan). Login nama + PIN 6 digit, 5× salah → kunci 15 menit.
- **Jobs (WIB)**: alert Critical belum dibalas (tiap 5 menit), ringkasan pagi 08.00, rekap mingguan Senin 08.30, voucher hangus 00.10, backup Minggu 02.00.
- **Integrasi**: `GET /api/public-metrics/service?from=&to=` dengan header `X-API-Key`. Export Excel dengan urutan kolom Case Log lama.

## Jalankan lokal
```bash
# backend
cd backend && pip install -r requirements.txt
USE_MOCK_DB=true DATA_DIR=./data DEFAULT_ADMIN_PIN=111111 uvicorn app.main:app --reload
# frontend (terminal lain)
cd frontend && npm install && npm run dev      # http://localhost:5173, proxy /api ke :8000
```
Login: **Admin** / PIN dari `DEFAULT_ADMIN_PIN`. Tes: `cd backend && pytest -q`.

## Deploy ke Railway
1. Push repo ini ke GitHub (mis. `handry-crk/ServiceDesk`, privat).
2. Railway → **New Project → Deploy from GitHub repo** → pilih repo. Railway membaca `railway.json` dan `Dockerfile` (build React + FastAPI dalam satu image).
3. **+ New → Database → MongoDB** (atau MongoDB Atlas untuk backup otomatis). Salin connection string ke variable `MONGO_URL` di service aplikasi.
4. Isi variables sesuai `.env.example`: `USE_MOCK_DB=false`, `SECRET_KEY`, `DEFAULT_ADMIN_PIN`, `METRICS_API_KEY`, `PUBLIC_BASE_URL`, `TZ=Asia/Jakarta`, email (opsional).
5. Service → **Settings → Volumes → Add Volume** di `/data` (foto bukti & backup). Redeploy.
6. **Settings → Networking → Generate Domain** (atau custom domain `cs.cimolbojotaa.com`). Isi `PUBLIC_BASE_URL` dengan domain itu.
7. Login sebagai Admin → **Pengaturan**: cek jam operasional CS, target, matriks kompensasi, isi area outlet, buat user CS → **Impor sheet lama** (File → Download → .xlsx) → *Cek dulu* → *Impor sekarang*.
8. Jalan paralel 1 minggu, lalu CS berhenti input di sheet.

## Catatan angka vs sheet lama
Diuji dengan data sheet per 11 Nov 2026 (98 case). Periode 08–31 Okt: contact 55, komplain 44, open 2, Critical 15, biaya Rp336.100, per level Minor 4 / Major 24 / Critical 15 — **sama persis** dengan tab Dashboard. FRT dan % SLA Response sedikit berbeda karena aplikasi mengikuti aturan tab Panduan: case tanpa jam masuk (mis. FRZ-10) tidak dihitung FRT-nya, dan channel CSAT Form tidak masuk % SLA Response.

Temuan saat impor: FRZ-16/FRZ-20 dan FRZ-17/FRZ-21 kemungkinan duplikat; FRZ-05, FRZ-08, FRZ-10 tercatat Closed sebelum Resolved; FRZ-27 memakai sub jenis "Double Resi" yang tidak ada di standard; outlet "Online Frozen (Tiktok 1)" belum ada di Master Data.
