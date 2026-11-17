"""Rekap dari WhatsApp: CS menyelesaikan komplain di WhatsApp dulu, lalu merekap satu case utuh sekaligus.

Jam masuk & jam dibalas diambil dari chat yang ditempel (bukti otomatis). Bila jam diketik manual,
wajib screenshot; case tetap langsung tersimpan dan diprioritaskan di audit acak.
Outlet yang belum terdaftar bisa diketik langsung → outlet 'menunggu verifikasi' (dikonfirmasi CRM Supervisor).
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import require, LEAD, WRITERS
from .core import get_db, now, parse_iso, as_utc, clean
from .services import new_id, save_case, add_event, audit, get_case_or_404, recompute_all
from .logic import load_ctx
from .wachat import analyze
from . import standards as S

router = APIRouter(prefix="/api")
MAX_CHAT = 30000


# ------------------------------------------------------------------ chat WhatsApp

class ParseIn(BaseModel):
    text: str
    customer: Optional[str] = None


@router.post("/wa/parse")
async def wa_parse(body: ParseIn, u=Depends(require(*WRITERS))):
    r = analyze(body.text[:MAX_CHAT], body.customer)
    if not r.get("messages"):
        raise HTTPException(400, "Format chat tidak dikenali. Salin dari WhatsApp Web/Desktop (blok pesan → salin) "
                                 "atau tempel isi file 'Export chat'.")
    return r


# ------------------------------------------------------------------ outlet baru dari CS

def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


class QuickOutletIn(BaseModel):
    name: str
    area: Optional[str] = None
    type: Optional[str] = None


@router.post("/outlets/quick")
async def quick_outlet(body: QuickOutletIn, u=Depends(require(*WRITERS))):
    """CS mengetik outlet yang belum ada → langsung bisa dipakai, status menunggu verifikasi CRM Supervisor."""
    from .jobs import notify
    name = " ".join(body.name.split())
    if len(name) < 3:
        raise HTTPException(400, "Nama outlet minimal 3 huruf.")
    db = get_db()
    key = _norm(name)
    async for o in db.outlets.find({}):
        if _norm(o["name"]) == key or key in [_norm(a) for a in o.get("aliases", [])]:
            return {**clean(o), "existing": True}
    area = body.area if body.area in S.AREAS else S.guess_area(name)
    o = {"id": new_id(), "name": name, "type": body.type if body.type in ("gerobak", "kios", "central_kitchen", "online_frozen")
         else S.outlet_type(name), "area": area, "brand": "Cimol Bojot AA", "aliases": [], "active": True,
         "pending": True, "requestedBy": u["name"], "requestedAt": now()}
    await db.outlets.insert_one(dict(o))
    await notify("outlet_pending", f"{u['name']} menambahkan outlet baru '{name}' saat rekap. Konfirmasi atau gabungkan "
                                   f"di Pengaturan → Outlet.", None, roles=LEAD, link="/pengaturan?tab=outlet")
    return {**clean(o), "existing": False}


@router.post("/outlets/{oid}/verify")
async def verify_outlet(oid: str, body: dict | None = None, u=Depends(require(*LEAD))):
    db = get_db()
    o = await db.outlets.find_one({"id": oid})
    if not o:
        raise HTTPException(404, "Outlet tidak ditemukan.")
    upd = {"pending": False, "verifiedBy": u["name"], "verifiedAt": now()}
    for k in ("name", "area", "type", "brand"):
        if (body or {}).get(k):
            upd[k] = body[k]
    await db.outlets.update_one({"id": oid}, {"$set": upd})
    await recompute_all()
    await audit(u, f"verify outlet {o['name']}", None, upd.get("name", o["name"]))
    return clean(await db.outlets.find_one({"id": oid}))


@router.post("/outlets/{oid}/merge")
async def merge_outlet(oid: str, body: dict, u=Depends(require(*LEAD))):
    """Gabungkan outlet (biasanya yang diketik CS) ke outlet yang sudah ada: semua case dipindah, nama jadi alias."""
    db = get_db()
    src = await db.outlets.find_one({"id": oid})
    dst = await db.outlets.find_one({"id": body.get("targetId")})
    if not src or not dst or src["id"] == dst["id"]:
        raise HTTPException(400, "Pilih outlet tujuan yang berbeda.")
    n = await db.cases.count_documents({"outletId": oid})
    await db.cases.update_many({"outletId": oid}, {"$set": {"outletId": dst["id"], "outletType": dst["type"]}})
    for coll in ("csat", "reviews"):
        await db[coll].update_many({"outletId": oid}, {"$set": {"outletId": dst["id"]}})
    await db.outlets.update_one({"id": dst["id"]}, {"$addToSet": {"aliases": src["name"]}})
    await db.outlets.delete_one({"id": oid})
    await recompute_all()
    await audit(u, f"merge outlet {src['name']} → {dst['name']}", None, f"{n} case")
    return {"ok": True, "moved": n, "target": clean(dst)}


# ------------------------------------------------------------------ rekap satu case utuh

class RekapIn(BaseModel):
    channel: str
    outletId: str
    subJenis: str
    ringkasan: str
    waktuMasuk: str
    waktuFirstResponse: str
    waktuResolved: Optional[str] = None
    rootCause: Optional[str] = None
    picDept: Optional[str] = None
    kompensasiKey: Optional[str] = None
    nilaiKompensasi: Optional[int] = None
    closed: bool = False
    followUpUlang: Optional[str] = None
    chatText: Optional[str] = None
    chatCustomer: Optional[str] = None
    photo: Optional[str] = None
    tipe: Optional[str] = "Komplain"
    orderNo: Optional[str] = None
    customerName: Optional[str] = None
    customerPhone: Optional[str] = None
    photos: list[str] = []
    produk: Optional[str] = None
    kodeProduksi: Optional[str] = None
    ekspedisi: Optional[str] = None
    noResi: Optional[str] = None
    qtyPesan: Optional[int] = None
    qtyDiterima: Optional[int] = None
    force: bool = False


def _same_min(a, b):
    return a is not None and b is not None and abs((as_utc(a) - as_utc(b)).total_seconds()) < 60


@router.post("/cases/rekap")
async def rekap(body: RekapIn, u=Depends(require(*WRITERS))):
    return await do_rekap(body, u)


async def do_rekap(body: RekapIn, u, evidence_override=None):
    from .routes_cases import CaseIn, create_case, ResolveIn, resolve, out_case
    masuk, fr = parse_iso(body.waktuMasuk), parse_iso(body.waktuFirstResponse)
    res = parse_iso(body.waktuResolved) if body.waktuResolved else None
    t = now()
    for label, x in (("Waktu masuk", masuk), ("Waktu dibalas", fr), ("Waktu selesai", res)):
        if x and as_utc(x) > t:
            raise HTTPException(400, f"{label} tidak boleh di masa depan.")
    if as_utc(fr) < as_utc(masuk):
        raise HTTPException(400, "Waktu dibalas tidak boleh sebelum waktu masuk.")
    if res and as_utc(res) < as_utc(fr):
        raise HTTPException(400, "Waktu selesai tidak boleh sebelum waktu dibalas.")
    if (res or body.closed) and not (body.kompensasiKey and (body.rootCause or "").strip()):
        raise HTTPException(400, "Case yang sudah selesai wajib diisi root cause dan bentuk kompensasi.")
    if body.closed and body.followUpUlang not in ("Y", "N"):
        raise HTTPException(400, "Pilih apakah customer follow-up ulang (Y/N).")

    # bukti jam: chat yang ditempel → otomatis; selain itu wajib screenshot
    evidence, chat = None, None
    if body.chatText and body.chatText.strip():
        chat = body.chatText.strip()[:MAX_CHAT]
        a = analyze(chat, body.chatCustomer)
        if _same_min(a.get("masuk"), masuk) and _same_min(a.get("dibalas"), fr):
            evidence = "chat"
    if not evidence and evidence_override:
        evidence = evidence_override
    if not evidence:
        if not body.photo:
            raise HTTPException(400, "Jam masuk/dibalas berbeda dengan chat (atau chat tidak ditempel): "
                                     "lampirkan screenshot chat sebagai bukti.")
        evidence = "screenshot"

    ci = CaseIn(channel=body.channel, outletId=body.outletId, subJenis=body.subJenis, ringkasan=body.ringkasan,
                waktuMasuk=body.waktuMasuk, tipe=body.tipe, orderNo=body.orderNo, customerName=body.customerName,
                customerPhone=body.customerPhone, photos=(body.photos or [])[:3], produk=body.produk,
                kodeProduksi=body.kodeProduksi, ekspedisi=body.ekspedisi, noResi=body.noResi, qtyPesan=body.qtyPesan,
                qtyDiterima=body.qtyDiterima, source="rekap",
                waktuMasukReason="Bulk input" if evidence == "bulk" else "Rekap dari WhatsApp", force=body.force)
    created = await create_case(ci, u)
    cid = created["caseId"]
    c = await get_case_or_404(cid)
    c.update(waktuFirstResponse=fr, status="Responded", frBy=u["name"], recordMode="rekap", timeEvidence=evidence,
             frtManual=evidence != "chat", rekapAt=t)
    if chat:
        c["chatText"], c["chatCustomer"] = chat, body.chatCustomer
    if body.photo:
        c["evidencePhoto"] = body.photo
    await save_case(c)
    await add_event(cid, "rekap", u, {"evidence": evidence})
    out = None
    if res or body.closed:
        out = await resolve(cid, ResolveIn(rootCause=body.rootCause, picDept=body.picDept, kompensasiKey=body.kompensasiKey,
                                           nilaiKompensasi=body.nilaiKompensasi), u)
        c = await get_case_or_404(cid)
        c["waktuResolved"] = res or t
        if body.closed:
            c.update(followUpUlang=body.followUpUlang, waktuClosed=t, status="Closed")
        await save_case(c)
    c = await get_case_or_404(cid)
    d = out_case(c, u)
    if out:
        d["voucher"], d["voucherWarning"] = out.get("voucher"), out.get("voucherWarning")
    return d


@router.get("/rekap/mine")
async def my_rekap(u=Depends(require(*WRITERS))):
    """Rekap yang dibuat user ini hari ini (untuk daftar di bawah form)."""
    from .routes_cases import out_case
    from .core import wib_date
    today = wib_date(now())
    rows = [c async for c in get_db().cases.find({"recordMode": "rekap", "createdBy": u["name"]}).sort("createdAt", -1).limit(60)]
    return [out_case(c, u) for c in rows if wib_date(c["createdAt"]) == today]
