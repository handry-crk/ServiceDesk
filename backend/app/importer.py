"""Impor sekali jalan dari XLSX 'Service Excellence Reporting CRK Okt 2026' (File → Download → .xlsx)."""
import hashlib
import io
from datetime import timedelta, datetime

from openpyxl import load_workbook

from . import standards as S
from .core import get_db, now, parse_sheet_time, parse_rupiah, wib_date, as_utc, log
from .logic import load_ctx, compute_case
from .services import new_id, match_outlet, survey_token, audit
from .routes_other import prep_review, csat_needs_triage

MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
MONTHS.update({"mei": 5, "agu": 8, "agt": 8, "okt": 10, "des": 12})


def _rows(ws, header_first):
    """Cari baris header (sel A == header_first) lalu kembalikan baris data sesudahnya."""
    rows = list(ws.iter_rows(values_only=True))
    for i, r in enumerate(rows):
        if r and str(r[0] or "").strip() == header_first:
            return [list(x) for x in rows[i + 1:] if x and any(v not in (None, "") for v in x)]
    return []


def _s(v):
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _int(v):
    try:
        return int(_float(v))
    except (TypeError, ValueError):
        return None


def _float(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if "," in s and "." in s:
        s = s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _get(r, i):
    return r[i] if i < len(r) else None


async def _outlet_for(name, ctx, report, dry):
    if not name or name.strip("-– ") == "":
        return None
    by_name = {o["name"].lower(): o for o in ctx["outlets"].values()}
    o = by_name.get(name.lower())
    if o:
        return o
    for x in ctx["outlets"].values():
        if name.lower() in [a.lower() for a in x.get("aliases") or []]:
            return x
    o = await match_outlet(name)
    if o:
        report["outletMatched"].append(f"{name} → {o['name']}")
        return o
    o = {"id": new_id(), "name": name, "type": S.outlet_type(name), "area": S.guess_area(name),
         "brand": "Cimol Bojot AA", "aliases": [], "active": True}
    report["outletCreated"].append(name)
    ctx["outlets"][o["id"]] = o
    if not dry:
        await get_db().outlets.insert_one(dict(o))
    return o


def _komp(bentuk, level, ctx):
    if not bentuk:
        return {}
    cands = [k for k in ctx["kompensasi"].values() if k["jenis"].lower() == bentuk.lower()]
    for k in cands:
        if k["level"] == level:
            return {"kompensasiKey": k["key"]}
    for k in cands:
        if k["level"] == "Semua":
            return {"kompensasiKey": k["key"]}
    return {"kompensasiJenis": bentuk, "kompensasiLabel": bentuk, "kompensasiForceOutside": bool(level)}


async def import_workbook(data: bytes, dry_run=True, user=None):
    db = get_db()
    wb = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    ctx = await load_ctx()
    report = {"dryRun": dry_run, "sheets": wb.sheetnames, "cases": {"imported": 0, "skippedExisting": 0, "issues": []},
              "csat": {"imported": 0, "skipped": 0}, "reviews": {"imported": 0, "skipped": 0},
              "ratings": {"imported": 0}, "vouchers": {"imported": 0, "skipped": 0},
              "outletCreated": [], "outletMatched": [], "duplicates": [], "errors": []}

    # ---- Master Data: outlet tambahan
    if "Master Data" in wb.sheetnames:
        for r in _rows(wb["Master Data"], "Channel"):
            name = _s(_get(r, 9))
            if name:
                await _outlet_for(name, ctx, report, dry_run)

    # ---- Case Log
    imported = []
    if "Case Log" in wb.sheetnames:
        existing = {c["caseId"] async for c in db.cases.find({}, {"caseId": 1})}
        for r in _rows(wb["Case Log"], "Case ID"):
            cid = _s(_get(r, 0))
            if not cid or cid.upper().startswith("TOTAL"):
                continue
            if cid in existing:
                report["cases"]["skippedExisting"] += 1
                continue
            masuk, has_time = parse_sheet_time(_get(r, 1))
            if not masuk:
                report["errors"].append(f"{cid}: Waktu Masuk kosong/tidak terbaca ({_get(r, 1)!r}) — dilewati")
                continue
            fr, _ = parse_sheet_time(_get(r, 2))
            rs, _ = parse_sheet_time(_get(r, 3))
            cl, _ = parse_sheet_time(_get(r, 4))
            outlet = await _outlet_for(_s(_get(r, 7)), ctx, report, dry_run)
            sub = _s(_get(r, 10))
            if sub == "Etika dan Pelayanan MO":
                sub = "Hospitality"
            if sub and sub not in ctx["subJenis"]:
                report["errors"].append(f"{cid}: Sub jenis '{sub}' tidak ada di standard — dikosongkan")
                sub = None
            level = _s(_get(r, 9))
            level = level if level in ("Minor", "Major", "Critical") else None
            status = _s(_get(r, 18)) or ("Closed" if cl else "Resolved" if rs else "Responded" if fr else "Open")
            reopen = _s(_get(r, 20))
            c = {
                "caseId": cid, "waktuMasuk": masuk, "hasTime": has_time, "waktuFirstResponse": fr,
                "waktuResolved": rs, "waktuClosed": cl, "channel": _s(_get(r, 5)) or "WhatsApp",
                "brand": _s(_get(r, 6)) or "Cimol Bojot AA", "outletId": outlet["id"] if outlet else None,
                "outletName": outlet["name"] if outlet else _s(_get(r, 7)),
                "outletType": outlet["type"] if outlet else None, "tipe": _s(_get(r, 8)) or "Komplain",
                "level": level, "subJenis": sub, "valid": _s(_get(r, 11)) or "Y", "ringkasan": _s(_get(r, 12)) or "",
                "rootCause": _s(_get(r, 13)), "picDept": _s(_get(r, 14)),
                "nilaiKompensasi": parse_rupiah(_get(r, 16)) or 0,
                "penanggungJawab": _s(_get(r, 17)), "pjImported": bool(_s(_get(r, 17))), "status": status,
                "followUpUlang": _s(_get(r, 19)), "reopenCount": 1 if reopen == "Y" else 0,
                "csat": _int(_get(r, 21)), "csAgent": _s(_get(r, 22)), "notes": _s(_get(r, 23)),
                "source": "import", "createdBy": user["name"] if user else "import", "createdAt": now(),
                "surveyToken": survey_token(), "photos": [],
            }
            if level and sub and ctx["subJenis"][sub]["level"] != level:
                c["levelChangeReason"] = None  # akan ditandai Cek Data
            c.update(_komp(_s(_get(r, 15)), level, ctx))
            imported.append(c)
        # deteksi duplikat di antara data impor
        for i, a in enumerate(imported):
            for b in imported[:i]:
                if a["outletId"] == b["outletId"] and a.get("subJenis") == b.get("subJenis") and a["hasTime"] and \
                        b["hasTime"] and abs((as_utc(a["waktuMasuk"]) - as_utc(b["waktuMasuk"])).total_seconds()) <= 1800:
                    a["possibleDuplicateOf"] = b["caseId"]
                    report["duplicates"].append(f"{a['caseId']} ↔ {b['caseId']} ({a['outletName']}, {a.get('subJenis')})")
                    break
        for c in imported:
            compute_case(c, ctx)
            if c.get("kompensasiForceOutside"):
                c["kompensasiOutsideStandard"] = True
            real = [x for x in c["dataIssues"] if not x.startswith("Info:")]
            if real:
                report["cases"]["issues"].append({"caseId": c["caseId"], "issues": real})
            c["updatedAt"] = now()
            if not dry_run:
                await db.cases.insert_one(c)
            report["cases"]["imported"] += 1

    # ---- CSAT (respons Google Form)
    if "CSAT" in wb.sheetnames:
        existing = {x["id"] async for x in db.csat.find({}, {"id": 1})}
        for r in _rows(wb["CSAT"], "Timestamp"):
            ts, _ = parse_sheet_time(_get(r, 0))
            if not ts:
                continue
            phone = _s(_get(r, 2))
            rid = "F" + hashlib.md5(f"{ts.isoformat()}|{phone}".encode()).hexdigest()[:10]
            if rid in existing:
                report["csat"]["skipped"] += 1
                continue
            text = _s(_get(r, 1))
            o = await match_outlet(text)
            x = {"id": rid, "timestamp": ts, "tanggal": wib_date(ts).isoformat(), "outletText": text,
                 "outletId": o["id"] if o else None, "outletName": o["name"] if o else None, "phone": phone,
                 "puasPelayanan": _int(_get(r, 3)), "rasa": _int(_get(r, 4)), "kebersihan": _int(_get(r, 5)),
                 "beliLagi": _s(_get(r, 6)), "kritikSaran": _s(_get(r, 7)), "ratingKeseluruhan": _int(_get(r, 8)),
                 "lamaTunggu": _s(_get(r, 9)), "linkedCaseId": None, "source": "google_form"}
            x["needsTriage"] = csat_needs_triage(x)
            # respons lama: anggap sudah ditangani di Case Log, kecuali CS memilih ulang
            x["triage"] = "tidak_perlu"
            if not dry_run:
                await db.csat.insert_one(x)
            report["csat"]["imported"] += 1

    # ---- Review Online
    if "Review Online" in wb.sheetnames:
        existing = {x["id"] async for x in db.reviews.find({}, {"id": 1})}
        for r in _rows(wb["Review Online"], "ID"):
            rid = _s(_get(r, 0))
            if not rid:
                continue
            if rid in existing:
                report["reviews"]["skipped"] += 1
                continue
            t, _ = parse_sheet_time(_get(r, 2))
            outlet_name = _s(_get(r, 3))
            x = {"id": rid, "platform": _s(_get(r, 1)), "tanggal": t, "outletName": outlet_name,
                 "rating": _int(_get(r, 4)), "review": _s(_get(r, 5)), "subJenis": _s(_get(r, 6)),
                 "klasifikasiSumber": _s(_get(r, 7)), "tag": _s(_get(r, 8)), "orderNo": _s(_get(r, 9)),
                 "statusTindakLanjut": _s(_get(r, 10)) or "Belum diproses"}
            await prep_review(x, ctx)
            if not dry_run:
                await db.reviews.insert_one(x)
            report["reviews"]["imported"] += 1

    # ---- Rating Online
    if "Rating Online" in wb.sheetnames:
        for r in _rows(wb["Rating Online"], "Platform"):
            plat, bulan = _s(_get(r, 0)), _s(_get(r, 1))
            if not plat or not bulan:
                continue
            if isinstance(_get(r, 1), datetime):
                b = _get(r, 1).strftime("%Y-%m")
            else:
                parts = bulan.lower().split()
                b = f"{parts[-1]}-{MONTHS.get(parts[0][:3], 0):02d}" if len(parts) == 2 else bulan
            jr, ts = _get(r, 3), _get(r, 4)
            x = {"platform": plat, "bulan": b, "outletName": _s(_get(r, 2)), "jumlahRating": _int(jr),
                 "totalSkor": _float(ts),
                 "ratingLe3": _int(_get(r, 5)), "transaksi": _int(_get(r, 7)),
                 "grossSales": parse_rupiah(_get(r, 8)), "netSales": parse_rupiah(_get(r, 9))}
            x["avgRating"] = round(x["totalSkor"] / x["jumlahRating"], 2) if x["jumlahRating"] and x["totalSkor"] else None
            if not dry_run:
                await db.ratings.update_one({"platform": plat, "bulan": b, "outletName": x["outletName"]},
                                            {"$set": x}, upsert=True)
            report["ratings"]["imported"] += 1

    # ---- Kode Voucher
    if "Kode Voucher" in wb.sheetnames:
        existing = {x["kode"] async for x in db.vouchers.find({}, {"kode": 1})}
        folders = {}
        rows = _rows(wb["Kode Voucher"], "Kode Voucher")
        base = len(existing)
        for i, r in enumerate(rows):
            kode = _s(_get(r, 0))
            if r and len(r) > 16 and _s(_get(r, 10)) in S.VOUCHER_JENIS and _s(_get(r, 16)):
                folders[_s(_get(r, 10))] = _s(_get(r, 16))
            if not kode or not _s(_get(r, 1)):
                continue
            if kode in existing:
                report["vouchers"]["skipped"] += 1
                continue
            td, _ = parse_sheet_time(_get(r, 4))
            tp, _ = parse_sheet_time(_get(r, 5))
            x = {"kode": kode, "jenis": _s(_get(r, 1)), "status": _s(_get(r, 2)) or "Tersedia",
                 "caseId": _s(_get(r, 3)), "tanggalDiterbitkan": td, "tanggalDipakai": tp,
                 "outletPemakaian": _s(_get(r, 6)), "catatan": _s(_get(r, 7)), "order": base + i}
            if not dry_run:
                await db.vouchers.insert_one(x)
            report["vouchers"]["imported"] += 1
        if folders and not dry_run:
            await db.config.update_one({"_id": "voucherFolders"}, {"$set": {"value": folders}}, upsert=True)

    if not dry_run and user:
        await audit(user, "import sheet", None, {k: report[k] for k in ("cases", "csat", "reviews", "ratings", "vouchers")})
    return report
