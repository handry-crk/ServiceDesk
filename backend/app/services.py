import difflib
import re
import secrets
import uuid
from datetime import timedelta

from fastapi import HTTPException

from . import standards as S
from .auth import hash_pin, verify_pin
from .core import get_db, now, as_utc, Config, log
from .logic import load_ctx, compute_case


def new_id():
    return uuid.uuid4().hex[:12]


async def seed_if_empty():
    db = get_db()
    if await db.sub_jenis.count_documents({}) == 0:
        await db.sub_jenis.insert_many([dict(x) for x in S.SUB_JENIS])
    if await db.channels.count_documents({}) == 0:
        await db.channels.insert_many([dict(x, order=i) for i, x in enumerate(S.CHANNELS)])
    if await db.kompensasi.count_documents({}) == 0:
        await db.kompensasi.insert_many([dict(x, order=i) for i, x in enumerate(S.KOMPENSASI)])
    for key, val, extra in (("targets", S.TARGETS, {}), ("settings", S.SETTINGS, {}),
                            ("penanggungJawab", S.PENANGGUNG_JAWAB, {}),
                            ("resolutionTarget", S.RESOLUTION_TARGET, {"criticalFrt": S.CRITICAL_FRT})):
        if not await db.config.find_one({"_id": key}):
            await db.config.insert_one({"_id": key, "value": val, **extra})
    if await db.outlets.count_documents({}) == 0:
        await db.outlets.insert_many([
            {"id": new_id(), "name": n, "type": S.outlet_type(n), "area": S.guess_area(n),
             "brand": "Cimol Bojot AA", "aliases": [], "active": True} for n in S.OUTLETS])
    if await db.users.count_documents({}) == 0:
        await db.users.insert_one({"id": new_id(), "name": "Admin", "role": "Admin", "areas": [],
                                   "pinHash": hash_pin(Config.DEFAULT_ADMIN_PIN), "active": True, "created": now()})
        log.info("User 'Admin' dibuat dengan DEFAULT_ADMIN_PIN.")
    else:
        # Admin yang belum pernah berhasil login → PIN disamakan dengan DEFAULT_ADMIN_PIN saat ini.
        # Mengatasi Admin yang terbentuk saat deploy awal sebelum variable final diisi.
        adm = await db.users.find_one({"name": "Admin", "role": "Admin"})
        if adm and not adm.get("lastLogin") and not verify_pin(Config.DEFAULT_ADMIN_PIN, adm.get("pinHash", "")):
            await db.users.update_one({"id": adm["id"]}, {"$set": {
                "pinHash": hash_pin(Config.DEFAULT_ADMIN_PIN), "failedPins": 0, "lockedUntil": None}})
            log.info("PIN 'Admin' (belum pernah login) disamakan dengan DEFAULT_ADMIN_PIN.")
    if Config.RESET_ADMIN_PIN:
        await db.users.update_one({"name": "Admin"}, {"$set": {
            "pinHash": hash_pin(Config.DEFAULT_ADMIN_PIN), "failedPins": 0, "lockedUntil": None, "active": True,
            "role": "Admin"}})
        log.warning("RESET_ADMIN_PIN=true: PIN 'Admin' direset ke DEFAULT_ADMIN_PIN. Hapus variable ini setelah login.")
    # migrasi: review hasil impor versi awal jangan membanjiri Inbox
    await db.reviews.update_many({"klasifikasiSumber": {"$ne": "Input manual"}, "triage": {"$exists": False}},
                                 {"$set": {"triage": "tidak_perlu"}})
    for coll, keys in (("cases", ["caseId", "tanggalMasuk", "status", "outletId", "subJenis", "surveyToken"]),
                       ("sessions", ["token"]), ("vouchers", ["kode", "status"]), ("csat", ["id", "timestamp"]),
                       ("reviews", ["id"]), ("events", ["caseId"])):
        for k in keys:
            try:
                await db[coll].create_index(k)
            except Exception:
                pass


# ---------- outlet fuzzy match ----------

_STOP = r"\b(cimol|bojot|aa|cabang|outlet|kios|gerobak|jl|jalan|dekat|raya)\b"


def _norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(_STOP, " ", s)
    return re.sub(r"\s+", " ", s).strip()


async def match_outlet(text):
    """Cocokkan teks bebas (CSAT/review) ke outlet. Return outlet atau None."""
    if not text:
        return None
    db = get_db()
    outlets = [o async for o in db.outlets.find({"active": True})]
    t = _norm(text)
    if not t:
        return None
    best, score = None, 0.0
    for o in outlets:
        for cand in [o["name"]] + (o.get("aliases") or []):
            c = _norm(cand)
            if not c:
                continue
            if c == t:
                return o
            if set(re.findall(r"\d+", c)) != set(re.findall(r"\d+", t)):
                continue  # 'Tiktok 1' bukan 'Tiktok 2'

            if c in t or t in c:
                sc = 0.9 + min(len(c), len(t)) / 1000
            else:
                sc = difflib.SequenceMatcher(None, c, t).ratio()
            if sc > score:
                best, score = o, sc
    return best if score >= 0.78 else None


# ---------- cases ----------

async def next_case_id(outlet_type):
    db = get_db()
    prefix = "FRZ-" if outlet_type == "online_frozen" else "OTL-"
    mx = 0
    async for c in db.cases.find({"caseId": {"$regex": "^" + prefix}}, {"caseId": 1}):
        try:
            mx = max(mx, int(c["caseId"].split("-")[1]))
        except (ValueError, IndexError):
            pass
    return f"{prefix}{mx + 1:02d}"


async def save_case(c, ctx=None):
    ctx = ctx or await load_ctx()
    compute_case(c, ctx)
    c["updatedAt"] = now()
    await get_db().cases.replace_one({"caseId": c["caseId"]}, c, upsert=True)
    return c


async def recompute_all():
    db = get_db()
    ctx = await load_ctx()
    n = 0
    async for c in db.cases.find({}):
        compute_case(c, ctx)
        await db.cases.replace_one({"_id": c["_id"]}, c)
        n += 1
    return n


async def add_event(case_id, typ, user=None, payload=None):
    await get_db().events.insert_one({"id": new_id(), "caseId": case_id, "type": typ,
                                      "by": user["name"] if user else "Sistem", "at": now(),
                                      "payload": payload or {}})


async def audit(user, what, before=None, after=None, reason=None):
    await get_db().audit.insert_one({"who": user["name"] if user else "Sistem", "what": what, "when": now(),
                                     "before": before, "after": after, "reason": reason})


async def find_duplicates(outlet_id, sub_jenis, waktu, order_no=None, exclude=None):
    db = get_db()
    out = []
    if outlet_id and sub_jenis and waktu:
        w = as_utc(waktu)
        q = {"outletId": outlet_id, "subJenis": sub_jenis,
             "waktuMasuk": {"$gte": w - timedelta(minutes=30), "$lte": w + timedelta(minutes=30)}}
        async for c in db.cases.find(q):
            if c["caseId"] != exclude:
                out.append(c["caseId"])
    if order_no:
        async for c in db.cases.find({"orderNo": order_no}):
            if c["caseId"] != exclude and c["caseId"] not in out:
                out.append(c["caseId"])
    return out


async def get_case_or_404(case_id):
    c = await get_db().cases.find_one({"caseId": case_id})
    if not c:
        raise HTTPException(404, f"Case {case_id} tidak ditemukan.")
    return c


def survey_token():
    return secrets.token_urlsafe(10)


async def issue_voucher(jenis, case_id):
    db = get_db()
    v = await db.vouchers.find_one({"jenis": jenis, "status": "Tersedia"}, sort=[("order", 1)])
    if not v:
        return None
    await db.vouchers.update_one({"kode": v["kode"]}, {"$set": {
        "status": "Diterbitkan", "caseId": case_id, "tanggalDiterbitkan": now()}})
    v.update(status="Diterbitkan", caseId=case_id)
    return v
