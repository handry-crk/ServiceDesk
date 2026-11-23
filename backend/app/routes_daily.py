"""Data harian: jumlah transaksi dan jumlah komplain diterima per hari, per sales channel.

Sales channel: Offline (Outlet / Kios) · Online Aggregator (GrabFood, GoFood, TikTok Go, ShopeeFood) ·
Marketplace (Shopee, TikTok Tokopedia).
- Transaksi harian dipakai untuk 'komplain per 1.000 transaksi' (lebih tepat daripada prorata bulanan).
- Komplain diterima (hitungan manual) dibandingkan dengan yang sudah tercatat di aplikasi.
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .auth import current_user, require, WRITERS
from .core import get_db, now, wib_date
from . import standards as S

router = APIRouter(prefix="/api")
NAMES = [n for n, _ in S.SALES_CHANNELS]


class DailyIn(BaseModel):
    tanggal: str
    trx: Optional[dict] = None        # {sales channel: jumlah transaksi}
    kom: Optional[dict] = None        # {sales channel: jumlah komplain diterima}
    transaksi: Optional[int] = None   # total (cara lama, tanpa rincian channel)
    komplain: Optional[int] = None
    catatan: Optional[str] = None


def _clean(d, label):
    out = {}
    for k, v in (d or {}).items():
        if k not in NAMES:
            raise HTTPException(400, f"Sales channel '{k}' tidak dikenal.")
        if v in (None, ""):
            continue
        try:
            v = int(v)
        except (TypeError, ValueError):
            raise HTTPException(400, f"{label} {k} harus angka.")
        if v < 0 or v > 10_000_000:
            raise HTTPException(400, f"{label} {k} tidak wajar.")
        out[k] = v
    return out


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
    trx, kom = _clean(body.trx, "Transaksi"), _clean(body.kom, "Komplain")
    transaksi = sum(trx.values()) if trx else body.transaksi
    komplain = sum(kom.values()) if kom else body.komplain
    db = get_db()
    if transaksi is None and komplain is None and not (body.catatan or "").strip():
        await db.daily.delete_one({"tanggal": body.tanggal})
        return {"ok": True, "deleted": True}
    await db.daily.update_one({"tanggal": body.tanggal}, {"$set": {
        "tanggal": body.tanggal, "transaksi": transaksi, "komplain": komplain, "trx": trx or None, "kom": kom or None,
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
                                 {"tanggalMasuk": 1, "tipe": 1, "level": 1, "salesChannel": 1}):
        if c.get("tipe", "Komplain") == "Komplain":
            k = c["tanggalMasuk"]
            rec.setdefault(k, {})
            sc = c.get("salesChannel") or "Outlet / Kios"
            rec[k][sc] = rec[k].get(sc, 0) + 1
            if c.get("level") == "Critical":
                crit[k] = crit.get(k, 0) + 1
    rows, d = [], t
    tot = {n: {"transaksi": 0, "komplain": 0, "tercatat": 0, "komDays": 0} for n in NAMES}
    while d >= f:
        k = d.isoformat()
        m = manual.get(k) or {}
        trxc, komc, recc = m.get("trx") or {}, m.get("kom") or {}, rec.get(k, {})
        trx, kom, tercatat = m.get("transaksi"), m.get("komplain"), sum(recc.values())
        base = kom if kom is not None else tercatat
        groups = {}
        for g in S.SALES_GROUPS:
            names = [n for n in NAMES if S.SALES_GROUP[n] == g]
            groups[g] = {"transaksi": sum(trxc.get(n, 0) for n in names) if trxc else None,
                         "komplain": sum(komc.get(n, 0) for n in names) if komc else None,
                         "tercatat": sum(recc.get(n, 0) for n in names)}
        for n in NAMES:
            tot[n]["transaksi"] += trxc.get(n, 0)
            tot[n]["komplain"] += komc.get(n, 0)
            tot[n]["tercatat"] += recc.get(n, 0)
        rows.append({"tanggal": k, "transaksi": trx, "komplain": kom, "tercatat": tercatat, "critical": crit.get(k, 0),
                     "selisih": (kom - tercatat) if kom is not None else None,
                     "per1000": round(base / trx * 1000, 2) if trx else None,
                     "trx": trxc, "kom": komc, "rec": recc, "groups": groups,
                     "catatan": m.get("catatan"), "updatedBy": m.get("updatedBy")})
        d -= timedelta(days=1)
    filled = [r for r in rows if r["transaksi"]]
    tot_trx = sum(r["transaksi"] for r in filled)
    tot_kom = sum((r["komplain"] if r["komplain"] is not None else r["tercatat"]) for r in filled)

    def line(name, kind, names):
        tr = sum(tot[n]["transaksi"] for n in names)
        km = sum(tot[n]["komplain"] for n in names)
        tc = sum(tot[n]["tercatat"] for n in names)
        return {"name": name, "kind": kind, "transaksi": tr or None, "komplain": km, "tercatat": tc,
                "per1000": round(max(km, tc) / tr * 1000, 2) if tr else None}
    channels = []
    for g in S.SALES_GROUPS:
        names = [n for n in NAMES if S.SALES_GROUP[n] == g]
        channels.append(line(g, "group", names))
        if len(names) > 1:
            channels += [line(n, "channel", [n]) for n in names]
    channels.append(line("Total", "total", NAMES))
    return {"rows": rows, "channels": channels, "summary": {
        "hariTerisi": len(filled), "hari": len(rows), "transaksi": tot_trx,
        "komplainManual": sum(r["komplain"] or 0 for r in rows), "tercatat": sum(r["tercatat"] for r in rows),
        "belumDirekap": sum(max(0, r["selisih"]) for r in rows if r["selisih"] is not None),
        "per1000": round(tot_kom / tot_trx * 1000, 2) if tot_trx else None}}


@router.get("/daily")
async def get_daily(u=Depends(current_user), frm: str = Query(..., alias="from"), to: str = Query(...)):
    return await build_daily(frm, to)
