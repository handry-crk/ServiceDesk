"""Data harian: jumlah transaksi dan jumlah komplain yang diterima per hari (diisi CS / CRM Supervisor).

- Transaksi harian dipakai untuk 'komplain per 1.000 transaksi' (lebih tepat daripada prorata bulanan).
- Jumlah komplain harian (hitungan manual) dibandingkan dengan yang sudah tercatat di aplikasi,
  supaya terlihat bila ada komplain yang belum direkap.
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .auth import current_user, require, WRITERS
from .core import get_db, now, wib_date

router = APIRouter(prefix="/api")


class DailyIn(BaseModel):
    tanggal: str
    transaksi: Optional[int] = None
    komplain: Optional[int] = None
    catatan: Optional[str] = None


@router.put("/daily")
async def put_daily(body: DailyIn, u=Depends(require(*WRITERS))):
    try:
        d = date.fromisoformat(body.tanggal)
    except ValueError:
        raise HTTPException(400, "Tanggal tidak valid.")
    if d > wib_date(now()):
        raise HTTPException(400, "Tanggal tidak boleh di masa depan.")
    for label, v in (("Jumlah transaksi", body.transaksi), ("Jumlah komplain", body.komplain)):
        if v is not None and (v < 0 or v > 10_000_000):
            raise HTTPException(400, f"{label} tidak wajar.")
    db = get_db()
    if body.transaksi is None and body.komplain is None and not (body.catatan or "").strip():
        await db.daily.delete_one({"tanggal": body.tanggal})
        return {"ok": True, "deleted": True}
    await db.daily.update_one({"tanggal": body.tanggal}, {"$set": {
        "tanggal": body.tanggal, "transaksi": body.transaksi, "komplain": body.komplain,
        "catatan": (body.catatan or "").strip() or None, "updatedBy": u["name"], "updatedAt": now()}}, upsert=True)
    return {"ok": True}


async def build_daily(frm: str, to: str):
    db = get_db()
    f, t = date.fromisoformat(frm), min(date.fromisoformat(to), wib_date(now()))
    if (t - f).days > 100:
        f = t - timedelta(days=100)
    manual = {x["tanggal"]: x async for x in db.daily.find({"tanggal": {"$gte": f.isoformat(), "$lte": t.isoformat()}})}
    rec, crit = {}, {}
    async for c in db.cases.find({"tanggalMasuk": {"$gte": f.isoformat(), "$lte": t.isoformat()}},
                                 {"tanggalMasuk": 1, "tipe": 1, "level": 1}):
        if c.get("tipe", "Komplain") == "Komplain":
            rec[c["tanggalMasuk"]] = rec.get(c["tanggalMasuk"], 0) + 1
            if c.get("level") == "Critical":
                crit[c["tanggalMasuk"]] = crit.get(c["tanggalMasuk"], 0) + 1
    rows, d = [], t
    while d >= f:
        k = d.isoformat()
        m = manual.get(k) or {}
        trx, kom, tercatat = m.get("transaksi"), m.get("komplain"), rec.get(k, 0)
        base = kom if kom is not None else tercatat
        rows.append({"tanggal": k, "transaksi": trx, "komplain": kom, "tercatat": tercatat, "critical": crit.get(k, 0),
                     "selisih": (kom - tercatat) if kom is not None else None,
                     "per1000": round(base / trx * 1000, 2) if trx else None,
                     "catatan": m.get("catatan"), "updatedBy": m.get("updatedBy")})
        d -= timedelta(days=1)
    filled = [r for r in rows if r["transaksi"]]
    tot_trx = sum(r["transaksi"] for r in filled)
    tot_kom = sum((r["komplain"] if r["komplain"] is not None else r["tercatat"]) for r in filled)
    return {"rows": rows, "summary": {
        "hariTerisi": len(filled), "hari": len(rows), "transaksi": tot_trx,
        "komplainManual": sum(r["komplain"] or 0 for r in rows), "tercatat": sum(r["tercatat"] for r in rows),
        "belumDirekap": sum(max(0, r["selisih"]) for r in rows if r["selisih"] is not None),
        "per1000": round(tot_kom / tot_trx * 1000, 2) if tot_trx else None}}


@router.get("/daily")
async def get_daily(u=Depends(current_user), frm: str = Query(..., alias="from"), to: str = Query(...)):
    return await build_daily(frm, to)
