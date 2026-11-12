import io
import json
import os
import random
import time
from collections import defaultdict
from datetime import timedelta, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Form, Request, Query
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

from . import standards as S
from .auth import (current_user, require, LEAD, WRITERS, ROLES, hash_pin, login, public_user, check_slot, email_ok,
                   ROLE_SLOTS, ROLE_LABEL, MEETING_EDITORS)
from .core import get_db, now, clean, parse_iso, Config, wib_date, wib, WIB, mask_phone, log
from .logic import load_ctx
from .services import (new_id, recompute_all, audit, match_outlet, save_case, next_case_id, add_event,
                       survey_token, get_case_or_404)
from .routes_cases import build_dashboard

router = APIRouter(prefix="/api")


# ------------------------------------------------------------------ auth

class LoginIn(BaseModel):
    name: str
    pin: str


@router.post("/auth/login")
async def do_login(body: LoginIn):
    token, u = await login(body.name, body.pin)
    return {"token": token, "user": public_user(u)}


@router.get("/auth/me")
async def me(u=Depends(current_user)):
    return public_user(u)


@router.post("/auth/logout")
async def logout(authorization: str = Header(default="")):
    await get_db().sessions.delete_one({"token": authorization.replace("Bearer ", "")})
    return {"ok": True}


# ------------------------------------------------------------------ masters

@router.get("/masters")
async def masters(u=Depends(current_user)):
    db = get_db()
    ctx = await load_ctx()
    return {
        "subJenis": sorted([clean(x) for x in ctx["subJenis"].values()], key=lambda x: x.get("order", 0)),
        "channels": sorted([clean(x) for x in ctx["channels"].values()], key=lambda x: x.get("order", 0)),
        "kompensasi": sorted([clean(x) for x in ctx["kompensasi"].values()], key=lambda x: x.get("order", 0)),
        "targets": ctx["targets"], "settings": ctx["settings"], "penanggungJawab": ctx["pj"],
        "resolutionTarget": ctx["resTarget"], "criticalFrt": ctx["criticalFrt"],
        "outlets": sorted([clean(x) for x in ctx["outlets"].values()], key=lambda x: x["name"]),
        "picDept": S.PIC_DEPT, "tipe": S.TIPE, "reviewPlatforms": S.REVIEW_PLATFORMS, "couriers": S.COURIERS, "frozenProducts": S.FROZEN_PRODUCTS, "needsBatch": sorted(S.NEEDS_BATCH), "standardDoc": S.STANDARD_DOC, "areas": S.AREAS, "voucherJenis": S.VOUCHER_JENIS,
        "brands": sorted({o.get("brand") or "Cimol Bojot AA" for o in ctx["outlets"].values()}),
        "agents": sorted({u2["name"] async for u2 in db.users.find({"active": True})}),
    }


@router.put("/masters/{kind}")
async def put_master(kind: str, body: dict, u=Depends(require(*LEAD))):
    db = get_db()
    val = body.get("value")
    if kind in ("subJenis", "channels", "kompensasi"):
        coll = {"subJenis": "sub_jenis", "channels": "channels", "kompensasi": "kompensasi"}[kind]
        if not isinstance(val, list) or not val:
            raise HTTPException(400, "Data harus berupa daftar dan tidak boleh kosong.")
        keyf = "key" if kind == "kompensasi" else "name"
        names = [v.get(keyf) for v in val]
        if any(not n for n in names) or len(set(names)) != len(names):
            raise HTTPException(400, f"Setiap baris wajib punya '{keyf}' yang unik.")
        before = [clean(x) async for x in db[coll].find({})]
        await db[coll].delete_many({})
        await db[coll].insert_many([dict({k: v for k, v in x.items() if k != "_id"}, order=i) for i, x in enumerate(val)])
    elif kind in ("targets", "settings", "penanggungJawab"):
        before = (await db.config.find_one({"_id": kind}) or {}).get("value")
        await db.config.update_one({"_id": kind}, {"$set": {"value": val}}, upsert=True)
    elif kind == "resolutionTarget":
        before = (await db.config.find_one({"_id": kind}) or {}).get("value")
        await db.config.update_one({"_id": kind}, {"$set": {"value": val, "criticalFrt": body.get("criticalFrt", 30)}},
                                   upsert=True)
    else:
        raise HTTPException(404, "Jenis master tidak dikenal.")
    await audit(u, f"master {kind}", before, val, body.get("reason"))
    n = await recompute_all()
    return {"ok": True, "recomputed": n}


# ------------------------------------------------------------------ outlets

class OutletIn(BaseModel):
    name: str
    type: str = "gerobak"
    area: str = "Belum diatur"
    brand: str = "Cimol Bojot AA"
    aliases: list[str] = []
    active: bool = True


@router.post("/outlets")
async def add_outlet(body: OutletIn, u=Depends(require(*LEAD))):
    db = get_db()
    if await db.outlets.find_one({"name": body.name}):
        raise HTTPException(400, "Nama outlet sudah ada.")
    o = {"id": new_id(), **body.model_dump()}
    await db.outlets.insert_one(o)
    return clean(o)


@router.patch("/outlets/{oid}")
async def patch_outlet(oid: str, body: dict, u=Depends(require(*LEAD))):
    allowed = {k: v for k, v in body.items() if k in ("name", "type", "area", "brand", "aliases", "active")}
    await get_db().outlets.update_one({"id": oid}, {"$set": allowed})
    await recompute_all()
    return clean(await get_db().outlets.find_one({"id": oid}))


# ------------------------------------------------------------------ users

class UserIn(BaseModel):
    name: str
    role: str
    pin: str
    email: Optional[str] = None
    areas: list[str] = []


@router.get("/roles")
async def roles(u=Depends(current_user)):
    db = get_db()
    out = []
    for r in ROLES:
        used = await db.users.count_documents({"role": r, "active": True})
        out.append({"role": r, "label": ROLE_LABEL.get(r, r), "slots": ROLE_SLOTS.get(r), "used": used})
    return {"roles": out, "domain": Config.ALLOWED_EMAIL_DOMAIN}


@router.get("/users")
async def users(u=Depends(require(*LEAD))):
    from .core import as_utc
    return [dict(public_user(x), locked=bool(x.get("lockedUntil") and as_utc(x["lockedUntil"]) > now()))
            async for x in get_db().users.find({}).sort("name", 1)]


@router.post("/users")
async def add_user(body: UserIn, u=Depends(require(*LEAD))):
    db = get_db()
    if body.role not in ROLES:
        raise HTTPException(400, "Peran tidak dikenal.")
    if body.role == "Admin" and u["role"] != "Admin":
        raise HTTPException(403, "Hanya Admin yang bisa membuat Admin.")
    if len(body.pin) != 6 or not body.pin.isdigit():
        raise HTTPException(400, "PIN harus 6 digit angka.")
    if await db.users.find_one({"name": body.name}):
        raise HTTPException(400, "Nama sudah dipakai.")
    email = None
    if body.email:
        email = email_ok(body.email)
        if not email:
            raise HTTPException(400, f"Email harus memakai domain @{Config.ALLOWED_EMAIL_DOMAIN}.")
        if await db.users.find_one({"email": email}):
            raise HTTPException(400, "Email sudah dipakai user lain.")
    await check_slot(body.role)
    x = {"id": new_id(), "name": body.name, "email": email, "role": body.role, "areas": body.areas,
         "pinHash": hash_pin(body.pin), "active": True, "created": now()}
    await db.users.insert_one(x)
    await audit(u, f"add user {body.name}", None, body.role)
    return public_user(x)


@router.patch("/users/{uid}")
async def patch_user(uid: str, body: dict, u=Depends(require(*LEAD))):
    db = get_db()
    upd = {k: v for k, v in body.items() if k in ("role", "areas", "active", "name")}
    target = await db.users.find_one({"id": uid})
    if not target:
        raise HTTPException(404, "User tidak ditemukan.")
    if upd.get("role") == "Admin" and u["role"] != "Admin":
        raise HTTPException(403, "Hanya Admin yang bisa memberi peran Admin.")
    if target["role"] == "Admin" and u["role"] != "Admin":
        raise HTTPException(403, "Hanya Admin yang bisa mengubah user Admin.")
    if upd.get("role") and upd["role"] not in ROLES:
        raise HTTPException(400, "Peran tidak dikenal.")
    new_role = upd.get("role", target["role"])
    becomes_active = upd.get("active", target.get("active", True))
    if becomes_active and (new_role != target["role"] or not target.get("active", True)):
        await check_slot(new_role, exclude_id=uid)
    if "email" in body:
        if body["email"]:
            e = email_ok(body["email"])
            if not e:
                raise HTTPException(400, f"Email harus memakai domain @{Config.ALLOWED_EMAIL_DOMAIN}.")
            if await db.users.find_one({"email": e, "id": {"$ne": uid}}):
                raise HTTPException(400, "Email sudah dipakai user lain.")
            upd["email"] = e
        else:
            upd["email"] = None
    if body.get("pin"):
        if len(body["pin"]) != 6 or not body["pin"].isdigit():
            raise HTTPException(400, "PIN harus 6 digit angka.")
        upd["pinHash"] = hash_pin(body["pin"])
    if body.get("unlock") or body.get("pin"):
        upd.update(lockedUntil=None, failedPins=0)
    await db.users.update_one({"id": uid}, {"$set": upd})
    if upd.get("active") is False:
        await db.sessions.delete_many({"userId": uid})
    await audit(u, f"edit user {uid}", None, {k: v for k, v in upd.items() if k != "pinHash"})
    return {"ok": True}


# ------------------------------------------------------------------ monthly transaksi

@router.get("/monthly")
async def monthly(u=Depends(current_user)):
    return [clean(x) async for x in get_db().monthly.find({}).sort("month", -1)]


@router.put("/monthly/{month}")
async def put_monthly(month: str, body: dict, u=Depends(require(*LEAD))):
    await get_db().monthly.update_one({"month": month}, {"$set": {
        "month": month, "totalTransaksi": int(body.get("totalTransaksi") or 0), "notes": body.get("notes")}},
        upsert=True)
    return {"ok": True}


# ------------------------------------------------------------------ CSAT (form publik pengganti Google Form)

_rate_bucket = defaultdict(list)


def _rate_limit(key, limit, window):
    t = time.time()
    b = [x for x in _rate_bucket[key] if x > t - window]
    if len(b) >= limit:
        raise HTTPException(429, "Terlalu banyak kiriman. Coba lagi nanti ya.")
    b.append(t)
    _rate_bucket[key] = b


def csat_needs_triage(r):
    return (isinstance(r.get("ratingKeseluruhan"), int) and r["ratingKeseluruhan"] <= 2) or \
           (isinstance(r.get("puasPelayanan"), int) and r["puasPelayanan"] <= 2) or r.get("beliLagi") == "Tidak"


class CsatIn(BaseModel):
    outlet: str
    outletId: Optional[str] = None
    phone: Optional[str] = None
    puasPelayanan: int
    rasa: int
    kebersihan: int
    beliLagi: str
    kritikSaran: Optional[str] = ""
    ratingKeseluruhan: int
    lamaTunggu: Optional[str] = None


@router.get("/public/outlets")
async def public_outlets():
    return [{"id": o["id"], "name": o["name"]} async for o in
            get_db().outlets.find({"active": True, "type": {"$ne": "online_frozen"}}).sort("name", 1)]


@router.post("/public/csat")
async def public_csat(body: CsatIn, request: Request):
    _rate_limit("csat:" + (request.client.host if request.client else "x"), 10, 3600)
    for f in ("puasPelayanan", "rasa", "kebersihan", "ratingKeseluruhan"):
        if not 1 <= getattr(body, f) <= 5:
            raise HTTPException(400, "Nilai rating harus 1–5.")
    if body.beliLagi not in ("Ya", "Tidak"):
        raise HTTPException(400, "Pilih Ya atau Tidak.")
    db = get_db()
    o = await db.outlets.find_one({"id": body.outletId}) if body.outletId else await match_outlet(body.outlet)
    r = {"id": new_id(), "timestamp": now(), "tanggal": wib_date(now()).isoformat(), "outletText": body.outlet,
         "outletId": o["id"] if o else None, "outletName": o["name"] if o else None,
         **body.model_dump(exclude={"outlet", "outletId"}), "triage": "belum", "linkedCaseId": None}
    r["needsTriage"] = csat_needs_triage(r)
    if not r["needsTriage"]:
        r["triage"] = "tidak_perlu"
    await db.csat.insert_one(r)
    return {"ok": True}


@router.get("/csat")
async def csat_list(u=Depends(current_user), frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None,
                    outletId: Optional[str] = None, unmatched: bool = False):
    q = {}
    if frm or to:
        q["tanggal"] = {"$gte": frm or "0000", "$lte": to or "9999"}
    if outletId:
        q["outletId"] = outletId
    if unmatched:
        q["outletId"] = None
    rows = [clean(r) async for r in get_db().csat.find(q).sort("timestamp", -1)]
    if u["role"] not in ("Admin", "CS Lead", "CS Agent"):
        for r in rows:
            r["phone"] = mask_phone(r.get("phone"))
    return rows


@router.post("/csat/{cid}/match")
async def csat_match(cid: str, body: dict, u=Depends(require(*WRITERS))):
    db = get_db()
    o = await db.outlets.find_one({"id": body.get("outletId")})
    if not o:
        raise HTTPException(400, "Outlet tidak dikenal.")
    r = await db.csat.find_one({"id": cid})
    await db.csat.update_one({"id": cid}, {"$set": {"outletId": o["id"], "outletName": o["name"]}})
    if body.get("addAlias") and r and r.get("outletText"):
        await db.outlets.update_one({"id": o["id"]}, {"$addToSet": {"aliases": r["outletText"]}})
    return {"ok": True}


@router.post("/csat/{cid}/triage")
async def csat_triage(cid: str, body: dict, u=Depends(require(*WRITERS))):
    db = get_db()
    r = await db.csat.find_one({"id": cid})
    if not r:
        raise HTTPException(404, "Respons CSAT tidak ditemukan.")
    if body.get("action") == "tidak_perlu":
        await db.csat.update_one({"id": cid}, {"$set": {"triage": "tidak_perlu"}})
        return {"ok": True}
    if not r.get("outletId"):
        raise HTTPException(400, "Cocokkan outlet dulu sebelum dijadikan case.")
    sub = body.get("subJenis") or "Hospitality"
    ctx = await load_ctx()
    outlet = ctx["outlets"][r["outletId"]]
    case_id = await next_case_id(outlet["type"])
    c = {"caseId": case_id, "brand": outlet.get("brand"), "outletId": outlet["id"], "outletType": outlet["type"],
         "channel": "CSAT Form", "tipe": "Komplain", "subJenis": sub, "valid": "Y",
         "ringkasan": (r.get("kritikSaran") or "").strip() or f"CSAT rating {r.get('ratingKeseluruhan')}",
         "customerPhone": r.get("phone"), "waktuMasuk": r["timestamp"], "hasTime": True, "status": "Open",
         "reopenCount": 0, "csAgent": u["name"], "csAgentId": u["id"], "source": "csat_form", "sourceRefId": cid,
         "createdBy": u["name"], "createdAt": now(), "surveyToken": survey_token(), "photos": [],
         "picDept": ctx["subJenis"][sub]["picOutlet"]}
    await save_case(c, ctx)
    await add_event(case_id, "created", u, {"from": "CSAT"})
    await db.csat.update_one({"id": cid}, {"$set": {"triage": "jadi_case", "linkedCaseId": case_id}})
    return {"caseId": case_id}


# ------------------------------------------------------------------ survey 1-tap per case

@router.get("/public/survey/{token}")
async def survey_get(token: str):
    c = await get_db().cases.find_one({"surveyToken": token})
    if not c:
        raise HTTPException(404, "Link survei tidak valid.")
    return {"caseId": c["caseId"], "outlet": c.get("outletName"), "brand": c.get("brand"), "done": c.get("csat") is not None}


@router.post("/public/survey/{token}")
async def survey_post(token: str, body: dict):
    db = get_db()
    c = await db.cases.find_one({"surveyToken": token})
    if not c:
        raise HTTPException(404, "Link survei tidak valid.")
    v = int(body.get("rating") or 0)
    if not 1 <= v <= 5:
        raise HTTPException(400, "Rating 1–5.")
    c["csat"] = v
    c["csatComment"] = (body.get("comment") or "")[:300]
    await save_case(c)
    await add_event(c["caseId"], "csat", None, {"rating": v})
    return {"ok": True}


# ------------------------------------------------------------------ reviews & ratings online

REVIEW_STATUS = ["Belum diproses", "Sudah dibalas", "Diteruskan ke Outlet", "Selesai"]


async def prep_review(r, ctx):
    sj = ctx["subJenis"].get(r.get("subJenis") or "")
    r["jenis"] = sj["jenis"] if sj else None
    r["level"] = sj["level"] if sj else None
    t = r.get("tanggal")
    r["tanggalDate"] = wib_date(t).isoformat() if t else None
    r["needsTriage"] = (r.get("level") == "Critical") or (isinstance(r.get("rating"), (int, float)) and r["rating"] <= 2)
    r.setdefault("statusTindakLanjut", "Belum diproses")
    r.setdefault("linkedCaseId", None)
    return r


@router.get("/reviews")
async def reviews(u=Depends(current_user), frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None,
                  status: Optional[str] = None, level: Optional[str] = None, platform: Optional[str] = None):
    q = {}
    if frm or to:
        q["tanggalDate"] = {"$gte": frm or "0000", "$lte": to or "9999"}
    for k, v in (("statusTindakLanjut", status), ("level", level), ("platform", platform)):
        if v:
            q[k] = v
    return [clean(r) async for r in get_db().reviews.find(q).sort("tanggal", -1).limit(1000)]


class ReviewIn(BaseModel):
    platform: str
    tanggal: str
    outletId: str
    rating: int
    review: str
    subJenis: str
    orderNo: Optional[str] = None
    tag: Optional[str] = None


@router.post("/reviews")
async def add_review(body: ReviewIn, u=Depends(require(*WRITERS))):
    db = get_db()
    ctx = await load_ctx()
    o = ctx["outlets"].get(body.outletId)
    n = await db.reviews.count_documents({"platform": body.platform})
    if body.platform not in S.REVIEW_PLATFORMS:
        raise HTTPException(400, "Platform tidak dikenal.")
    prefix = {"GoFood": "GF", "GrabFood": "GR", "ShopeeFood": "SF"}[body.platform]
    r = {"id": f"{prefix}-{n + 1:03d}-{new_id()[:4]}", **body.model_dump(), "tanggal": parse_iso(body.tanggal),
         "outletName": o["name"] if o else None, "klasifikasiSumber": "Input manual"}
    await prep_review(r, ctx)
    await db.reviews.insert_one(r)
    return clean(r)


@router.patch("/reviews/{rid}")
async def patch_review(rid: str, body: dict, u=Depends(require(*WRITERS))):
    db = get_db()
    upd = {k: v for k, v in body.items() if k in ("statusTindakLanjut", "subJenis", "triage")}
    if upd.get("statusTindakLanjut") and upd["statusTindakLanjut"] not in REVIEW_STATUS:
        raise HTTPException(400, "Status tidak dikenal.")
    r = await db.reviews.find_one({"id": rid})
    if not r:
        raise HTTPException(404, "Review tidak ditemukan.")
    r.update(upd)
    await prep_review(r, await load_ctx())
    await db.reviews.replace_one({"id": rid}, r)
    return clean(r)


@router.post("/reviews/{rid}/to-case")
async def review_to_case(rid: str, u=Depends(require(*WRITERS))):
    db = get_db()
    r = await db.reviews.find_one({"id": rid})
    if not r:
        raise HTTPException(404, "Review tidak ditemukan.")
    if r.get("linkedCaseId"):
        return {"caseId": r["linkedCaseId"]}
    ctx = await load_ctx()
    outlet = next((o for o in ctx["outlets"].values() if o["name"] == r.get("outletName")), None)
    if not outlet:
        outlet = await match_outlet(r.get("outletName"))
    if not outlet:
        raise HTTPException(400, f"Outlet '{r.get('outletName')}' belum ada di master outlet. Tambahkan dulu di Pengaturan.")
    sub = r.get("subJenis") if r.get("subJenis") in ctx["subJenis"] else "Lainnya: Rasa / Porsi"
    case_id = await next_case_id(outlet["type"])
    c = {"caseId": case_id, "brand": outlet.get("brand"), "outletId": outlet["id"], "outletType": outlet["type"],
         "channel": "Review Online", "tipe": "Komplain", "subJenis": sub, "valid": "Y",
         "ringkasan": f"[{r.get('platform')} ★{r.get('rating')}] {r.get('review')}", "orderNo": r.get("orderNo"),
         "waktuMasuk": r["tanggal"], "hasTime": True, "status": "Open", "reopenCount": 0, "csAgent": u["name"],
         "csAgentId": u["id"], "source": "review_online", "sourceRefId": rid, "createdBy": u["name"],
         "createdAt": now(), "surveyToken": survey_token(), "photos": [],
         "picDept": ctx["subJenis"][sub]["picOutlet"]}
    await save_case(c, ctx)
    await add_event(case_id, "created", u, {"from": "Review Online"})
    await db.reviews.update_one({"id": rid}, {"$set": {"linkedCaseId": case_id, "statusTindakLanjut": "Diteruskan ke Outlet"}})
    return {"caseId": case_id}


@router.get("/ratings")
async def ratings(u=Depends(current_user)):
    return [clean(r) async for r in get_db().ratings.find({}).sort([("bulan", -1), ("outletName", 1)])]


@router.post("/ratings")
async def add_rating(body: dict, u=Depends(require(*WRITERS))):
    r = {k: body.get(k) for k in ("platform", "bulan", "outletName", "jumlahRating", "totalSkor", "ratingLe3",
                                  "transaksi", "grossSales", "netSales")}
    r["avgRating"] = round(float(r["totalSkor"]) / float(r["jumlahRating"]), 2) if r.get("jumlahRating") else None
    await get_db().ratings.update_one({"platform": r["platform"], "bulan": r["bulan"], "outletName": r["outletName"]},
                                      {"$set": r}, upsert=True)
    return r


# ------------------------------------------------------------------ vouchers

@router.get("/vouchers")
async def vouchers(u=Depends(current_user), status: Optional[str] = None, jenis: Optional[str] = None):
    db = get_db()
    q = {}
    if status:
        q["status"] = status
    if jenis:
        q["jenis"] = jenis
    rows = [clean(v) async for v in db.vouchers.find(q).sort("order", 1).limit(2000)]
    stock = []
    folders = (await db.config.find_one({"_id": "voucherFolders"}) or {}).get("value", {})
    for j in S.VOUCHER_JENIS:
        cnt = {s: await db.vouchers.count_documents({"jenis": j, "status": s})
               for s in ("Tersedia", "Diterbitkan", "Terpakai", "Hangus")}
        stock.append({"jenis": j, "total": sum(cnt.values()), **cnt, "folder": folders.get(j)})
    return {"rows": rows, "stock": stock}


@router.post("/vouchers/import")
async def import_vouchers(body: dict, u=Depends(require(*LEAD))):
    db = get_db()
    jenis = body.get("jenis")
    if jenis not in S.VOUCHER_JENIS:
        raise HTTPException(400, "Jenis voucher tidak dikenal.")
    codes = [c.strip() for c in (body.get("codes") or "").replace(",", "\n").splitlines() if c.strip()]
    base = await db.vouchers.count_documents({})
    added = 0
    for i, k in enumerate(codes):
        if await db.vouchers.find_one({"kode": k}):
            continue
        await db.vouchers.insert_one({"kode": k, "jenis": jenis, "status": "Tersedia", "order": base + i})
        added += 1
    if body.get("folder"):
        await db.config.update_one({"_id": "voucherFolders"}, {"$set": {f"value.{jenis}": body["folder"]}}, upsert=True)
    return {"added": added, "skipped": len(codes) - added}


@router.get("/vouchers/lookup/{kode}")
async def voucher_lookup(kode: str, u=Depends(require(*WRITERS, "Manager Area", "Ops/QC"))):
    """Cek kode complimentary saat customer datang ke outlet / saat refund diproses."""
    db = get_db()
    v = await db.vouchers.find_one({"kode": kode.strip().upper()})
    if not v:
        raise HTTPException(404, "Kode tidak ditemukan. Periksa lagi hurufnya.")
    c = await db.cases.find_one({"caseId": v.get("caseId")}) if v.get("caseId") else None
    st = (await db.config.find_one({"_id": "settings"}) or {}).get("value", {})
    exp = None
    if v.get("tanggalDiterbitkan") and not v.get("noExpiry"):
        exp = (wib_date(v["tanggalDiterbitkan"]) + timedelta(days=st.get("voucherExpiryDays", 30))).isoformat()
    return {**clean(v), "kadaluarsa": exp,
            "case": {k: c.get(k) for k in ("caseId", "outletName", "subJenis", "level", "kompensasiLabel", "customerName", "status")} if c else None}


@router.post("/vouchers/{kode}/status")
async def voucher_status(kode: str, body: dict, u=Depends(require(*WRITERS, "Manager Area", "Ops/QC"))):
    st = body.get("status")
    if u["role"] in ("Manager Area", "Ops/QC") and st != "Terpakai":
        raise HTTPException(403, "Peran Anda hanya bisa menandai kode terpakai / diterima.")
    v0 = await get_db().vouchers.find_one({"kode": kode})
    if not v0:
        raise HTTPException(404, "Kode tidak ditemukan.")
    if st == "Terpakai" and v0.get("status") in ("Terpakai", "Hangus") and u["role"] not in ("Admin", "CS Lead"):
        raise HTTPException(400, f"Kode ini sudah {v0['status'].lower()}.")
    if st not in ("Tersedia", "Diterbitkan", "Terpakai", "Hangus"):
        raise HTTPException(400, "Status tidak dikenal.")
    upd = {"status": st}
    if st == "Terpakai":
        upd.update(tanggalDipakai=parse_iso(body["tanggal"]) if body.get("tanggal") else now(),
                   outletPemakaian=body.get("outlet"), dipakaiOleh=u["name"])
    if body.get("catatan") is not None:
        upd["catatan"] = body["catatan"]
    await get_db().vouchers.update_one({"kode": kode}, {"$set": upd})
    return {"ok": True}


# ------------------------------------------------------------------ uploads

@router.post("/uploads")
async def upload(file: UploadFile = File(...), u=Depends(require(*WRITERS))):
    data = await file.read()
    if len(data) > 1_500_000:
        raise HTTPException(400, "Foto terlalu besar (maks 1,5 MB setelah kompresi).")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(400, "Hanya gambar.")
    d = os.path.join(Config.DATA_DIR, "uploads")
    os.makedirs(d, exist_ok=True)
    name = new_id() + ".jpg"
    with open(os.path.join(d, name), "wb") as f:
        f.write(data)
    return {"url": f"/api/uploads/{name}"}


@router.get("/uploads/{name}")
async def get_upload(name: str):
    p = os.path.join(Config.DATA_DIR, "uploads", os.path.basename(name))
    if not os.path.exists(p):
        raise HTTPException(404, "File tidak ada.")
    return FileResponse(p)


# ------------------------------------------------------------------ export xlsx (urutan kolom Case Log lama)

EXPORT_COLS = [
    ("Case ID", "caseId"), ("Waktu Masuk", "waktuMasuk"), ("Waktu First Response", "waktuFirstResponse"),
    ("Waktu Resolved", "waktuResolved"), ("Waktu Closed", "waktuClosed"), ("Channel", "channel"), ("Brand", "brand"),
    ("Outlet", "outletName"), ("Tipe", "tipe"), ("Level Komplain", "level"), ("Sub Jenis Komplain", "subJenis"),
    ("Komplain Valid (Y/N)", "valid"), ("Ringkasan Masalah", "ringkasan"), ("Root Cause", "rootCause"),
    ("PIC Dept", "picDept"), ("Bentuk Complimentary", "kompensasiLabel"), ("Nilai Complimentary (Rp)", "nilaiKompensasi"),
    ("Penanggung Jawab", "penanggungJawab"), ("Status", "status"), ("Customer Follow-up Ulang (Y/N)", "followUpUlang"),
    ("Reopen (Y/N)", "reopenCount"), ("CSAT (1–5)", "csat"), ("CS Agent", "csAgent"), ("Catatan", "notes"),
    ("FRT (menit)", "frtMin"), ("Target FRT (menit)", "targetFrtMin"), ("SLA Response OK", "slaResponseOk"),
    ("Resolution Time (menit)", "resolutionMin"), ("Target Resolution (menit)", "targetResolutionMin"),
    ("Resolution SLA OK", "resolutionSlaOk"), ("Same Day", "sameDay"), ("FCR", "fcr"), ("Puas (CSAT ≥4)", "puas"),
    ("Jenis Komplain", "jenis"), ("Level Standard", "levelStandard"), ("Cost Center", "costCenter"),
    ("Cost Center Final", "costCenterFinal"), ("Kompensasi di luar standard", "kompensasiOutsideStandard"),
    ("Kode Voucher", "voucherCode"), ("No. Pesanan", "orderNo"), ("Produk", "produk"), ("Kode Produksi", "kodeProduksi"),
    ("Ekspedisi", "ekspedisi"), ("No. Resi", "noResi"), ("Qty Dipesan", "qtyPesan"), ("Qty Diterima", "qtyDiterima"), ("Area", "area"), ("Cek Data", "dataIssues"),
]


@router.get("/export/cases.xlsx")
async def export_cases(u=Depends(require("Admin", "CS Lead", "CS Agent", "Marketing TL", "Viewer", "Ops/QC", "Manager Area")),
                       frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    q = {}
    if frm or to:
        q["tanggalMasuk"] = {"$gte": frm or "0000", "$lte": to or "9999"}
    if u["role"] == "Manager Area":
        q["area"] = {"$in": u.get("areas") or ["-"]}
    wb = Workbook()
    ws = wb.active
    ws.title = "Case Log"
    ws.append([h for h, _ in EXPORT_COLS])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="B42F27")
    async for c in get_db().cases.find(q).sort("waktuMasuk", 1):
        row = []
        for _, k in EXPORT_COLS:
            v = c.get(k)
            if k.startswith("waktu") and v:
                d = wib(v)
                v = d.strftime("%d/%m/%Y %H:%M") if c.get("hasTime", True) or k != "waktuMasuk" else d.strftime("%d/%m/%Y")
            elif k == "reopenCount":
                v = "Y" if (v or 0) > 0 else ("N" if c.get("status") == "Closed" else "")
            elif k == "dataIssues":
                v = "; ".join(v or []) or "OK"
            elif isinstance(v, bool):
                v = 1 if v else 0
            elif k == "customerPhone" and u["role"] not in ("Admin", "CS Lead", "CS Agent"):
                v = mask_phone(v)
            row.append(v)
        ws.append(row)
    ws.freeze_panes = "B2"
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=case-log.xlsx"})


# ------------------------------------------------------------------ public metrics (integrasi dashboard CRK lain)

@router.get("/public-metrics/service")
async def public_metrics(frm: str = Query(..., alias="from"), to: str = Query(...), x_api_key: str = Header(default="")):
    if x_api_key != Config.METRICS_API_KEY:
        raise HTTPException(401, "API key salah.")
    d = await build_dashboard(frm, to)
    return {"period": d["period"], "metrics": d["metrics"], "volume": d["volume"],
            "levels": [{"name": r["name"], "count": r["count"]} for r in d["levels"]],
            "topSubJenis": [{"name": r["name"], "count": r["count"]} for r in d["subJenis"][:5]]}


# ------------------------------------------------------------------ notifications

@router.get("/notifications")
async def notifications(u=Depends(current_user)):
    q = {"$or": [{"roles": {"$exists": False}}, {"roles": u["role"]}]}
    rows = [clean(n) async for n in get_db().notifications.find(q).sort("at", -1).limit(30)]
    return rows


@router.post("/notifications/read")
async def notif_read(u=Depends(current_user)):
    await get_db().notifications.update_many({"$or": [{"roles": {"$exists": False}}, {"roles": u["role"]}]},
                                             {"$addToSet": {"readBy": u["id"]}})
    return {"ok": True}


# ------------------------------------------------------------------ admin

@router.post("/admin/recompute")
async def admin_recompute(u=Depends(require(*LEAD))):
    return {"recomputed": await recompute_all()}


@router.post("/admin/backup")
async def admin_backup(u=Depends(require(*LEAD))):
    from .jobs import backup
    path = await backup()
    return {"ok": True, "file": os.path.basename(path)}


@router.get("/admin/backups")
async def list_backups(u=Depends(require(*LEAD))):
    d = os.path.join(Config.DATA_DIR, "backups")
    return sorted(os.listdir(d), reverse=True) if os.path.isdir(d) else []


@router.get("/admin/backups/{name}")
async def get_backup(name: str, u=Depends(require(*LEAD))):
    p = os.path.join(Config.DATA_DIR, "backups", os.path.basename(name))
    if not os.path.exists(p):
        raise HTTPException(404, "Backup tidak ada.")
    return FileResponse(p, filename=name)


@router.get("/admin/audit")
async def audit_log(u=Depends(require(*LEAD))):
    return [clean(a) async for a in get_db().audit.find({}).sort("when", -1).limit(300)]


@router.post("/admin/seed-demo")
async def seed_demo(u=Depends(require("Admin"))):
    db = get_db()
    if await db.cases.count_documents({}) > 0:
        raise HTTPException(400, "Data contoh hanya bisa diisi saat database case masih kosong.")
    ctx = await load_ctx()
    outlets = list(ctx["outlets"].values())
    subs = [s for s in ctx["subJenis"].values() if s["name"] != "Lainnya: Rasa / Porsi"]
    chans = ["WhatsApp", "WhatsApp", "IG DM", "Marketplace Chat", "TikTok DM", "Live Chat"]
    rnd = random.Random(7)
    komp_by_level = defaultdict(list)
    for k in ctx["kompensasi"].values():
        komp_by_level[k["level"]].append(k)
    n = 0
    for d in range(45, 0, -1):
        for _ in range(rnd.randint(0, 4)):
            o = rnd.choice(outlets)
            sj = rnd.choice(subs)
            day = (now() - timedelta(days=d)).astimezone(WIB)
            masuk = day.replace(hour=rnd.choice([9, 11, 13, 15, 17, 19, 20, 21, 22]), minute=rnd.randint(0, 59))
            cid = await next_case_id(o["type"])
            c = {"caseId": cid, "brand": "Cimol Bojot AA", "outletId": o["id"], "outletType": o["type"],
                 "channel": "Marketplace Chat" if o["type"] == "online_frozen" else rnd.choice(chans),
                 "tipe": "Komplain" if rnd.random() > 0.15 else "Inquiry", "subJenis": sj["name"], "valid": "Y",
                 "ringkasan": f"[Contoh] {sj['contoh'][:80]}", "waktuMasuk": masuk, "hasTime": True,
                 "status": "Open", "reopenCount": 0, "csAgent": "Admin", "source": "demo",
                 "picDept": sj["picFrozen"] if o["type"] == "online_frozen" else sj["picOutlet"],
                 "createdBy": "demo", "createdAt": now(), "surveyToken": survey_token(), "photos": []}
            frt = rnd.choice([1, 2, 3, 4, 6, 9, 15, 45, 180, 600]) if masuk.hour >= 19 else rnd.choice([1, 2, 3, 4, 5, 8])
            c["waktuFirstResponse"] = masuk + timedelta(minutes=frt)
            c["status"] = "Responded"
            if d > 1 or rnd.random() > 0.5:
                c["waktuResolved"] = c["waktuFirstResponse"] + timedelta(minutes=rnd.choice([10, 30, 90, 240, 900, 2000]))
                lvl = sj["level"] if sj["level"] in komp_by_level else "Semua"
                k = rnd.choice(komp_by_level[lvl] + komp_by_level["Semua"][:1])
                c.update(kompensasiKey=k["key"], nilaiKompensasi=k.get("nilai") or rnd.choice([0, 12000, 20000, 26000]),
                         rootCause=rnd.choice(sj.get("rootCauses") or ["Lainnya"]), status="Resolved")
                if rnd.random() > 0.3:
                    c.update(waktuClosed=c["waktuResolved"] + timedelta(minutes=rnd.randint(5, 600)),
                             status="Closed", followUpUlang=rnd.choice(["N", "N", "N", "Y"]),
                             costCenterFinal="Operasional", csat=rnd.choice([3, 4, 5, 5, 5]))
            await save_case(c, ctx)
            n += 1
    return {"created": n}


# ------------------------------------------------------------------ import dari Google Sheet lama

@router.post("/import/sheet")
async def import_sheet(file: UploadFile = File(...), dryRun: bool = Form(True), u=Depends(require(*LEAD))):
    from .importer import import_workbook
    data = await file.read()
    return await import_workbook(data, dry_run=dryRun, user=u)
