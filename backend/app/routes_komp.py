"""Tracker complimentary / kompensasi: apa yang diberikan, berapa biayanya, dan apakah voucher dipakai."""
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query

from .auth import current_user
from .core import get_db, now, as_utc, wib_date
from .logic import load_ctx, _rate, _avg

router = APIRouter(prefix="/api")


def _group(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[r.get(key) or "-"].append(r)
    out = [{"name": n, "count": len(x), "biaya": sum(r["nilai"] for r in x),
            "voucher": sum(1 for r in x if r["kode"]), "terpakai": sum(1 for r in x if r["status"] == "Terpakai"),
            "luarStandard": sum(1 for r in x if r["luarStandard"])} for n, x in g.items()]
    return sorted(out, key=lambda r: (-r["count"], -r["biaya"]))


async def build_komp(frm, to, u=None, brand=None, area=None, line=None):
    from .routes_cases import cases_in_period
    ctx = await load_ctx()
    exp_days = ctx["settings"].get("voucherExpiryDays", 30)
    cases = await cases_in_period(frm, to, u, brand, area, ctx, line)
    given = [c for c in cases if c.get("kompensasiJenis") and c["kompensasiJenis"] != "Tidak Ada"]
    ids = [c["caseId"] for c in given]
    vouchers = {v["caseId"]: v async for v in get_db().vouchers.find({"caseId": {"$in": ids}})}
    today = wib_date(now())
    rows = []
    for c in given:
        v = vouchers.get(c["caseId"]) or {}
        issued = v.get("tanggalDiterbitkan")
        exp = (wib_date(issued) + timedelta(days=exp_days)) if (issued and not v.get("noExpiry")) else None
        used = v.get("tanggalDipakai")
        st = v.get("status") if v else ("Tanpa kode" if not c.get("voucherCode") else "Tidak ditemukan")
        rows.append({
            "caseId": c["caseId"], "tanggal": c.get("tanggalMasuk"), "outlet": c.get("outletName"), "area": c.get("area"),
            "brand": c.get("brand"), "subJenis": c.get("subJenis"), "level": c.get("level") or "Belum Diatur",
            "jenis": c["kompensasiJenis"], "label": c.get("kompensasiLabel") or c["kompensasiJenis"],
            "nilai": c.get("nilaiKompensasi") or 0, "luarStandard": bool(c.get("kompensasiOutsideStandard")),
            "costCenter": c.get("costCenterFinal") or c.get("costCenter"), "status": st, "kode": v.get("kode") or c.get("voucherCode"),
            "voucherJenis": v.get("jenis"), "diterbitkan": issued, "kadaluarsa": exp.isoformat() if exp else None,
            "dipakai": used, "outletPemakaian": v.get("outletPemakaian"), "dipakaiOleh": v.get("dipakaiOleh"),
            "auto": bool(v.get("auto")), "noExpiry": bool(v.get("noExpiry")),
            "hariSampaiDipakai": (wib_date(used) - wib_date(issued)).days if (used and issued) else None,
            "sisaHari": (exp - today).days if (exp and st == "Diterbitkan") else None,
            "caseStatus": c.get("status"),
        })
    rows.sort(key=lambda r: (r["tanggal"] or "", r["caseId"]), reverse=True)
    vr = [r for r in rows if r["kode"]]
    aktif = [r for r in vr if r["status"] == "Diterbitkan"]
    selesai = [r for r in vr if r["status"] in ("Terpakai", "Hangus")]
    f, t = date.fromisoformat(frm), date.fromisoformat(to)
    weeks, s, i = [], f, 0
    while s <= t and i < 12:
        e = min(s + timedelta(days=6), t)
        wk = [r for r in rows if r["tanggal"] and s.isoformat() <= r["tanggal"] <= e.isoformat()]
        weeks.append({"week": f"W{i + 1}", "start": s.isoformat(), "end": e.isoformat(), "count": len(wk),
                      "biaya": sum(r["nilai"] for r in wk)})
        s, i = e + timedelta(days=1), i + 1
    summary = {
        "cases": len(rows), "biaya": sum(r["nilai"] for r in rows),
        "luarStandard": sum(1 for r in rows if r["luarStandard"]),
        "biayaLuarStandard": sum(r["nilai"] for r in rows if r["luarStandard"]),
        "voucher": len(vr), "aktif": len(aktif), "terpakai": sum(1 for r in vr if r["status"] == "Terpakai"),
        "hangus": sum(1 for r in vr if r["status"] == "Hangus"),
        "redemption": _rate(sum(1 for r in selesai if r["status"] == "Terpakai"), len(selesai)),
        "redemptionAll": _rate(sum(1 for r in vr if r["status"] == "Terpakai"), len(vr)),
        "avgHariDipakai": _avg([r["hariSampaiDipakai"] for r in vr]),
        "nilaiAktif": sum(r["nilai"] for r in aktif),
        "segeraHangus": sum(1 for r in aktif if r["sisaHari"] is not None and r["sisaHari"] <= 7),
        "tanpaKode": sum(1 for r in rows if not r["kode"] and r["jenis"] != "Apologize"),
        "komplainTotal": sum(1 for c in cases if c.get("tipe", "Komplain") == "Komplain"),
    }
    summary["komplainDiberi"] = sum(1 for c in given if c.get("tipe", "Komplain") == "Komplain")
    summary["pctDiberi"] = _rate(summary["komplainDiberi"], summary["komplainTotal"])
    return {"period": {"from": frm, "to": to}, "summary": summary, "rows": rows,
            "byJenis": _group(rows, "label"), "byLevel": _group(rows, "level"), "byOutlet": _group(rows, "outlet")[:10],
            "byCostCenter": _group(rows, "costCenter"), "byStatus": _group(vr, "status"), "weeks": weeks,
            "expiryDays": exp_days}


@router.get("/kompensasi-tracker")
async def komp_tracker(u=Depends(current_user), frm: str = Query(..., alias="from"), to: str = Query(...),
                       brand: Optional[str] = None, area: Optional[str] = None, line: Optional[str] = None):
    return await build_komp(frm, to, u, brand, area, line)
