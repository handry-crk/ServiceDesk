"""Bulk input: banyak case sekaligus dari tabel (tempel dari Excel / Google Sheets, atau upload .xlsx / .csv).

Alur: preview (dryRun) → perbaiki baris yang error → simpan. Jam diketik manual tanpa bukti chat per baris,
jadi case bulk bertanda 'bulk' dan masuk prioritas audit acak mingguan.
"""
import csv
import io
import re
from datetime import datetime, time as dtime, date, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .auth import require, WRITERS
from .core import get_db, now, as_utc
from .logic import load_ctx
from .services import match_outlet, find_duplicates, audit
from .routes_rekap import RekapIn, do_rekap, quick_outlet, QuickOutletIn, _norm
from . import standards as S

router = APIRouter(prefix="/api")
WIB = timezone(timedelta(hours=7))
MAX_ROWS = 300

COLS = [  # (kunci, judul di template, alias header)
    ("tanggal", "Tanggal", ["tanggal", "tgl", "tanggal masuk", "date"]),
    ("masuk", "Jam Masuk", ["jam masuk", "waktu masuk", "masuk"]),
    ("dibalas", "Jam Dibalas", ["jam dibalas", "waktu dibalas", "dibalas", "first response", "jam balas"]),
    ("selesai", "Jam Selesai", ["jam selesai", "waktu selesai", "selesai", "resolved", "waktu resolved"]),
    ("channel", "Channel", ["channel", "sumber", "source"]),
    ("outlet", "Outlet", ["outlet", "toko", "nama outlet"]),
    ("subJenis", "Sub Jenis", ["sub jenis", "sub jenis komplain", "masalah", "jenis komplain"]),
    ("ringkasan", "Ringkasan", ["ringkasan", "ringkasan masalah", "detail", "keterangan", "kronologi"]),
    ("rootCause", "Root Cause", ["root cause", "penyebab", "akar masalah"]),
    ("kompensasi", "Kompensasi", ["kompensasi", "complimentary", "bentuk kompensasi"]),
    ("nilai", "Nilai (Rp)", ["nilai", "nilai (rp)", "nilai kompensasi", "biaya"]),
    ("status", "Status", ["status"]),
    ("customerName", "Nama Customer", ["nama customer", "nama", "customer"]),
    ("customerPhone", "No HP", ["no hp", "no. hp", "hp", "whatsapp", "no wa", "no. wa"]),
    ("orderNo", "No Pesanan", ["no pesanan", "no. pesanan", "order", "order id"]),
    ("platform", "Platform Online", ["platform online", "platform", "platform review"]),
    ("rating", "Rating", ["rating", "bintang"]),
    ("order", "Jam Order", ["jam order", "waktu order", "jam pesan", "waktu pesan", "jam order customer"]),
]
REQUIRED = ("tanggal", "masuk", "dibalas", "channel", "outlet", "subJenis", "ringkasan")
_D1 = re.compile(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})")
_D2 = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_T = re.compile(r"(\d{1,2})[:.](\d{2})(?:[:.]\d{2})?\s*([AaPp][Mm])?")


CH_ALIAS = {"wa": "WhatsApp", "whatsap": "WhatsApp", "wasap": "WhatsApp", "ig": "IG DM", "instagram": "IG DM", "dmig": "IG DM",
            "tiktok": "TikTok DM", "dmtiktok": "TikTok DM", "komentar": "Social Comment", "comment": "Social Comment",
            "marketplace": "Marketplace Chat", "shopee": "Marketplace Chat", "tokopedia": "Marketplace Chat",
            "tiktokshop": "Marketplace Chat", "gojek": "GoFood", "grab": "GrabFood", "livechat": "Live Chat"}


def _key(h):
    return re.sub(r"[^a-z0-9() ]", "", (h or "").lower().replace(".", "")).strip()


def _date(s):
    s = (s or "").strip()
    m = _D2.search(s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _D1.search(s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return date(y + 2000 if y < 100 else y, mo, d)
    return None


def _time(s):
    s = (s or "").strip()
    s2 = _D2.sub("", _D1.sub("", s)).strip()
    m = _T.search(s2)
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), (m.group(3) or "").lower()
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return dtime(h, mi)


def _dt(cell, base_date):
    """Sel boleh berisi jam saja (pakai tanggal baris) atau tanggal + jam."""
    if not (cell or "").strip():
        return None
    t = _time(cell)
    if t is None:
        raise ValueError
    d = _date(cell) or base_date
    if d is None:
        raise ValueError
    return datetime(d.year, d.month, d.day, t.hour, t.minute, tzinfo=WIB)


def parse_table(text):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not text.strip():
        return [], []
    delim = "\t" if "\t" in text.split("\n")[0] else (";" if text.split("\n")[0].count(";") > text.split("\n")[0].count(",") else ",")
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any((c or "").strip() for c in r)]
    alias = {a: k for k, _, al in COLS for a in al}
    head = [alias.get(_key(h)) for h in rows[0]]
    if sum(1 for h in head if h) >= 4:
        body = rows[1:]
    else:  # tanpa header → urutan kolom template
        head, body = [k for k, _, _ in COLS], rows
    out = []
    for i, r in enumerate(body):
        d = {h: (r[j].strip() if j < len(r) else "") for j, h in enumerate(head) if h}
        d["_row"] = i + 1
        out.append(d)
    return out, head


def _best(name, options):
    """Cocokkan teks bebas ke daftar nama (persis → tanpa spasi/tanda → mengandung)."""
    n = _norm(name)
    if not n:
        return None
    for o in options:
        if _norm(o) == n:
            return o
    hit = [o for o in options if n in _norm(o) or _norm(o) in n]
    return hit[0] if len(hit) == 1 else None


async def _check(rows, ctx, u):
    db = get_db()
    channels = [c for c in ctx["channels"] if c != "CSAT Form"]
    subs = list(ctx["subJenis"])
    t = now()
    seen, out = set(), []
    for r in rows:
        err, warn, v = [], [], {}
        plat = _best(r.get("platform"), S.REVIEW_PLATFORMS) if r.get("platform") else None
        if r.get("platform") and not plat:
            err.append(f"Platform Online '{r['platform']}' tidak dikenal (GoFood / GrabFood / ShopeeFood)")
        if plat and not r.get("channel"):
            r["channel"] = "Review Online"
        rating = None
        if r.get("rating"):
            dg = re.sub(r"[^\d]", "", r["rating"])[:1]
            rating = int(dg) if dg and 1 <= int(dg) <= 5 else None
            if rating is None:
                err.append("Rating harus 1–5")
        for k in REQUIRED:
            if k == "dibalas" and plat and not r.get("selesai") and not r.get("kompensasi"):
                continue   # review yang belum ditindaklanjuti boleh tanpa jam dibalas
            if not r.get(k):
                err.append(f"{dict((a, b) for a, b, _ in COLS)[k]} kosong")
        base = _date(r.get("tanggal")) or _date(r.get("masuk"))
        if r.get("tanggal") and not base:
            err.append("Tanggal tidak terbaca (pakai dd/mm/yyyy)")
        for k, label in (("masuk", "Jam Masuk"), ("dibalas", "Jam Dibalas"), ("selesai", "Jam Selesai")):
            try:
                v[k] = _dt(r.get(k), base)
            except ValueError:
                v[k] = None
                err.append(f"{label} tidak terbaca (pakai 10.05 atau 10:05)")
        od = None
        if r.get("order"):
            try:
                od = _dt(r["order"], base)
                if v.get("masuk") and od > v["masuk"]:
                    if _date(r["order"]):
                        err.append("Jam Order setelah Jam Masuk")
                    else:
                        od -= timedelta(days=1)   # order kemarin malam, komplain hari ini
            except ValueError:
                err.append("Jam Order tidak terbaca (pakai 10.05 atau 10:05)")
        m, f, s = v.get("masuk"), v.get("dibalas"), v.get("selesai")
        if m and f and f < m and not _date(r.get("dibalas")):
            f = v["dibalas"] = f + timedelta(days=1)   # dibalas lewat tengah malam
        if f and s and s < f and not _date(r.get("selesai")):
            s = v["selesai"] = s + timedelta(days=1)
        for label, x in (("Jam Masuk", m), ("Jam Dibalas", f), ("Jam Selesai", s)):
            if x and as_utc(x) > t:
                err.append(f"{label} di masa depan")
        if m and f and (f - m) > timedelta(days=7):
            warn.append("Dibalas lebih dari 7 hari setelah masuk — cek tanggal")
        ch = _best(CH_ALIAS.get(_norm(r.get("channel")), r.get("channel")), channels)
        if r.get("channel") and not ch:
            err.append(f"Channel '{r['channel']}' tidak dikenal")
        if ch == "Review Online" and not plat and not r.get("platform"):
            err.append("Platform Online kosong (wajib untuk channel Review Online)")
        sj = _best(r.get("subJenis"), subs)
        if r.get("subJenis") and not sj:
            err.append(f"Sub Jenis '{r['subJenis']}' tidak dikenal")
        o = await match_outlet(r.get("outlet")) if r.get("outlet") else None
        if r.get("outlet") and not o:
            warn.append(f"Outlet '{r['outlet']}' belum terdaftar — dibuat otomatis, menunggu verifikasi")
        elif o and _norm(o["name"]) != _norm(r["outlet"]):
            warn.append(f"Outlet dibaca sebagai '{o['name']}'")
        st = (r.get("status") or "").lower()
        closed = "close" in st or "konfirm" in st
        done = closed or bool(s) or any(x in st for x in ("selesai", "resolved", "done")) or \
            (not st and bool(r.get("kompensasi") or r.get("rootCause")))
        if "proses" in st or "open" in st:
            done = closed = False
        komp = None
        if done:
            level = (ctx["subJenis"].get(sj) or {}).get("level") if sj else None
            pool = [k for k in ctx["kompensasi"].values()]
            pref = [k for k in pool if k["level"] in (level, "Semua")] or pool
            txt = _norm(r.get("kompensasi"))
            if not txt:
                err.append("Kompensasi kosong (case selesai). Isi mis. Apologize / Replacement / Refund / Tidak Ada")
            else:
                for group in (pref, pool):
                    komp = next((k for k in group if _norm(k["label"]) == txt), None) or \
                        next((k for k in group if _norm(k["jenis"]) == txt), None) or \
                        next((k for k in group if txt in _norm(k["label"]) or _norm(k["label"]).startswith(txt)), None)
                    if komp:
                        break
                if not komp:
                    err.append(f"Kompensasi '{r['kompensasi']}' tidak dikenal")
                elif komp["level"] not in (level, "Semua"):
                    warn.append(f"Kompensasi '{komp['label']}' di luar standard level {level or 'belum diatur'}")
            if not r.get("rootCause"):
                err.append("Root Cause kosong (case selesai)")
        nilai = None
        if r.get("nilai"):
            digits = re.sub(r"[^\d]", "", r["nilai"].split(",")[0])
            nilai = int(digits) if digits else None
        if o and sj and m:
            sig = (o["id"], sj, m.isoformat())
            if sig in seen:
                err.append("Baris dobel di tabel ini (outlet, sub jenis, dan jam masuk sama)")
            seen.add(sig)
            dups = await find_duplicates(o["id"], sj, as_utc(m), r.get("orderNo") or None)
            if dups:
                warn.append("Mungkin sudah tercatat: " + ", ".join(dups))
                v["dup"] = dups
        out.append({"row": r["_row"], "ok": not err, "errors": err, "warnings": warn, "dup": bool(v.get("dup")),
                    "data": {"masuk": m.isoformat() if m else None, "dibalas": f.isoformat() if f else None,
                             "selesai": s.isoformat() if s else None, "channel": ch, "outletId": o["id"] if o else None,
                             "outlet": o["name"] if o else r.get("outlet"), "subJenis": sj, "ringkasan": r.get("ringkasan"),
                             "rootCause": r.get("rootCause") or None, "kompensasiKey": komp["key"] if komp else None,
                             "kompensasi": komp["label"] if komp else None, "nilai": nilai,
                             "status": "Closed" if (closed and done) else "Selesai" if done else "Diproses",
                             "customerName": r.get("customerName") or None, "customerPhone": r.get("customerPhone") or None,
                             "orderNo": r.get("orderNo") or None, "order": od.isoformat() if od else None,
                             "platform": plat if ch == "Review Online" else None, "rating": rating if ch == "Review Online" else None,
                             "frtMin": round((f - m).total_seconds() / 60) if (m and f) else None}})
    return out


class BulkIn(BaseModel):
    text: str
    dryRun: bool = True
    includeDup: bool = False


@router.post("/cases/bulk")
async def bulk(body: BulkIn, u=Depends(require(*WRITERS))):
    rows, head = parse_table(body.text)
    if not rows:
        raise HTTPException(400, "Tabel kosong. Tempel baris dari Excel / Google Sheets, termasuk baris judul kolom.")
    if len(rows) > MAX_ROWS:
        raise HTTPException(400, f"Maksimal {MAX_ROWS} baris sekali simpan. Bagi menjadi beberapa bagian.")
    ctx = await load_ctx()
    checked = await _check(rows, ctx, u)
    summary = {"rows": len(checked), "ok": sum(1 for r in checked if r["ok"]), "error": sum(1 for r in checked if not r["ok"]),
               "warning": sum(1 for r in checked if r["ok"] and r["warnings"]), "dup": sum(1 for r in checked if r["ok"] and r["dup"])}
    if body.dryRun:
        return {"dryRun": True, "summary": summary, "rows": checked, "columns": [h for h in head if h]}
    created, failed, skipped = [], [], 0
    for r in checked:
        d = r["data"]
        if not r["ok"]:
            continue
        if r["dup"] and not body.includeDup:
            skipped += 1
            continue
        try:
            oid = d["outletId"]
            if not oid:
                oid = (await quick_outlet(QuickOutletIn(name=d["outlet"]), u))["id"]
            done = d["status"] != "Diproses" and bool(d["dibalas"])
            rk = RekapIn(channel=d["channel"], outletId=oid, subJenis=d["subJenis"], ringkasan=d["ringkasan"],
                         waktuMasuk=d["masuk"], waktuFirstResponse=d["dibalas"],
                         waktuResolved=(d["selesai"] or d["dibalas"]) if done else None,
                         rootCause=d["rootCause"] if done else None, kompensasiKey=d["kompensasiKey"] if done else None,
                         nilaiKompensasi=d["nilai"] if done else None, closed=d["status"] == "Closed", followUpUlang="N",
                         orderNo=d["orderNo"], customerName=d["customerName"], customerPhone=d["customerPhone"], waktuOrder=d.get("order"), reviewPlatform=d.get("platform"), rating=d.get("rating"), force=True)
            c = await do_rekap(rk, u, evidence_override="bulk")
            created.append({"row": r["row"], "caseId": c["caseId"], "kode": c.get("voucherCode")})
        except HTTPException as e:
            failed.append({"row": r["row"], "error": e.detail if isinstance(e.detail, str) else str(e.detail)})
    await audit(u, "bulk input", None, f"{len(created)} case dibuat, {len(failed)} gagal, {skipped} dilewati (duplikat)")
    return {"dryRun": False, "summary": summary, "created": created, "failed": failed, "skippedDup": skipped,
            "errorRows": [r for r in checked if not r["ok"]]}


@router.post("/cases/bulk/file")
async def bulk_file(file: UploadFile = File(...), u=Depends(require(*WRITERS))):
    """Ubah .xlsx / .csv menjadi teks tabel untuk dipreview."""
    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(400, "File terlalu besar (maks 5 MB).")
    name = (file.filename or "").lower()
    if name.endswith((".csv", ".tsv", ".txt")):
        return {"text": data.decode("utf-8-sig", errors="replace")}
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(400, "File tidak terbaca. Pakai .xlsx atau .csv.")
    ws = wb[wb.sheetnames[0]]

    def cell(v):
        if v is None:
            return ""
        if isinstance(v, datetime):
            return v.strftime("%d/%m/%Y %H:%M") if (v.hour or v.minute) else v.strftime("%d/%m/%Y")
        if isinstance(v, date):
            return v.strftime("%d/%m/%Y")
        if isinstance(v, dtime):
            return v.strftime("%H:%M")
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v).replace("\t", " ").replace("\n", " ").strip()
    lines = ["\t".join(cell(v) for v in row) for row in ws.iter_rows(values_only=True) if any(v not in (None, "") for v in row)]
    return {"text": "\n".join(lines[:MAX_ROWS + 1])}


@router.get("/cases/bulk/template")
async def bulk_template(u=Depends(require(*WRITERS))):
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    ctx = await load_ctx()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bulk Input"
    ws.append([t for _, t, _ in COLS])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="B42F27")
    ws.append(["16/11/2026", "10.02", "10.05", "10.30", "WhatsApp", "Jagakarsa", "Missing Item", "Pesan 10 pcs, diterima 8 pcs",
               "Ketelitian Crew", "Replacement (porsi baru)", "", "Selesai", "Budi", "081211112222", "", "", "", "09.40"])
    ws.append(["16/11/2026", "13.40", "13.44", "", "GoFood", "Kios Margonda", "Speed of Service", "Pesanan lama dibuat",
               "", "", "", "Diproses", "", "", "F-1234567890", "", "", "13.05"])
    ws.append(["16/11/2026", "19.20", "20.05", "", "Review Online", "Kios Margonda", "Missing Item", "Pesan 3 yang datang 2",
               "", "", "", "Diproses", "", "", "F-3308407390", "GoFood", "1", ""])
    for i, w in enumerate([12, 10, 11, 11, 16, 24, 26, 40, 22, 28, 11, 11, 16, 15, 16, 15, 8, 11]):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i + 1)].width = w
    ref = wb.create_sheet("Pilihan")
    ch = [c for c in ctx["channels"] if c != "CSAT Form"]
    sj = sorted(ctx["subJenis"].values(), key=lambda x: x.get("order", 0))
    kp = sorted(ctx["kompensasi"].values(), key=lambda x: x.get("order", 0))
    ref.append(["Channel", "Sub Jenis", "Level", "Kompensasi", "Untuk level", "Status"])
    for c in ref[1]:
        c.font = Font(bold=True)
    for i in range(max(len(ch), len(sj), len(kp), 3)):
        ref.append([ch[i] if i < len(ch) else None, sj[i]["name"] if i < len(sj) else None, sj[i].get("level") if i < len(sj) else None,
                    kp[i]["label"] if i < len(kp) else None, kp[i]["level"] if i < len(kp) else None,
                    ["Diproses", "Selesai", "Closed"][i] if i < 3 else None])
    for col, w in zip("ABCDEF", (20, 40, 12, 52, 12, 12)):
        ref.column_dimensions[col].width = w
    note = wb.create_sheet("Petunjuk")
    for line in ["Isi 1 baris = 1 komplain di sheet 'Bulk Input'. Hapus 3 baris contoh.",
                 "Review online (GoFood / GrabFood / ShopeeFood): kolomnya sama dengan komplain biasa, cukup isi Channel = Review Online dan Platform Online (+ Rating).",
                 "Wajib: Tanggal, Jam Masuk, Jam Dibalas, Channel, Outlet, Sub Jenis, Ringkasan.",
                 "Jam Masuk = jam pesan pertama customer; Jam Dibalas = jam balasan pertama CS (lihat di chat).",
                 "Status Selesai / Closed wajib mengisi Root Cause dan Kompensasi. Jam Selesai kosong = sama dengan Jam Dibalas.",
                 "Outlet yang belum terdaftar dibuat otomatis dan menunggu verifikasi CRM Supervisor.",
                 "Ejaan Channel, Sub Jenis, dan Kompensasi mengikuti sheet 'Pilihan'.",
                 "Setelah selesai: blok semua baris (termasuk judul) → salin → tempel di Service Desk → Catat → Bulk input. Atau upload file ini."]:
        note.append([line])
    note.column_dimensions["A"].width = 120
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="template-bulk-input-service-desk.xlsx"'})
