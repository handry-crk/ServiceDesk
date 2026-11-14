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
    else:
        # migrasi teks contoh & kata kunci sesuai dokumen MASTER CRM.STD.001 (hanya bila belum diubah manual)
        new = {x["name"]: x for x in S.SUB_JENIS}
        for name, (old_c, old_k) in S.SUB_JENIS_OLD_TEXT.items():
            cur = await db.sub_jenis.find_one({"name": name})
            if not cur:
                continue
            upd = {}
            if cur.get("contoh") == old_c:
                upd["contoh"] = new[name]["contoh"]
            if cur.get("keywords") == old_k:
                upd["keywords"] = new[name]["keywords"]
            if upd:
                await db.sub_jenis.update_one({"name": name}, {"$set": upd})
    if await db.channels.count_documents({}) == 0:
        await db.channels.insert_many([dict(x, order=i) for i, x in enumerate(S.CHANNELS)])
    else:
        # migrasi: tambah channel baru (mis. GoFood/GrabFood/ShopeeFood) & isi group/orderRequired
        # tanpa mengubah target yang sudah diatur CS Lead
        for i, ch in enumerate(S.CHANNELS):
            cur = await db.channels.find_one({"name": ch["name"]})
            if not cur:
                await db.channels.insert_one(dict(ch, order=i))
            else:
                fill = {k: ch[k] for k in ("group", "orderRequired") if k in ch and k not in cur}
                if cur.get("group") == "Sistem":
                    fill["group"] = ch["group"]
                fill["order"] = i
                await db.channels.update_one({"name": ch["name"]}, {"$set": fill})
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
    # migrasi: desk CS per channel (Online / Offline), lalu hitung ulang case lama agar punya desk
    async for ch in db.channels.find({"desk": {"$exists": False}}):
        await db.channels.update_one({"_id": ch["_id"]}, {"$set": {"desk": S.default_desk(ch["name"])}})
    if await db.cases.count_documents({"desk": {"$exists": False}}):
        await recompute_all()
    for n, area in S.NEW_OUTLETS.items():
        if not await db.outlets.find_one({"name": n}):
            await db.outlets.insert_one({"id": new_id(), "name": n, "type": S.outlet_type(n), "area": area,
                                         "brand": "Cimol Bojot AA", "aliases": [], "active": True})
            log.info("Outlet baru ditambahkan: %s", n)
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
    # migrasi: case frozen hasil impor lama → ambil ekspedisi / produk / no. pesanan dari catatan
    from .importer import parse_frozen_notes
    async for c in db.cases.find({"outletType": "online_frozen", "source": "import", "frozenParsed": {"$exists": False}}):
        fz = parse_frozen_notes(c.get("notes"))
        on = fz.pop("orderNoFromNotes", None)
        upd = {k: v for k, v in fz.items() if not c.get(k)}
        if on and not c.get("orderNo"):
            upd["orderNo"] = on
        upd["frozenParsed"] = True
        await db.cases.update_one({"_id": c["_id"]}, {"$set": upd})
    for coll, keys in (("cases", ["caseId", "tanggalMasuk", "status", "outletId", "subJenis", "surveyToken"]),
                       ("sessions", ["token"]), ("vouchers", ["kode", "status"]), ("csat", ["id", "timestamp"]),
                       ("reviews", ["id"]), ("events", ["caseId"]), ("users", ["email"]),
                       ("registrations", ["id", "email", "status"])):
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


CODE_PREFIX = {"Voucher": "VC", "Replacement": "RP", "Complimentary": "KT", "Refund": "RF", "Cover Pengobatan": "MD"}
NO_CODE = ("Apologize", "Tidak Ada")
NO_EXPIRY = ("Refund", "Cover Pengobatan")


async def make_tracking_code(kategori):
    """Kode unik complimentary: CMP-<jenis>-<YYMM>-<nomor>, mis. CMP-RP-2611-0007."""
    from .core import wib
    db = get_db()
    ym = wib(now()).strftime("%y%m")
    pre = f"CMP-{CODE_PREFIX.get(kategori, 'CM')}-{ym}-"
    n = await db.vouchers.count_documents({"kode": {"$regex": "^" + pre}})
    while True:
        n += 1
        kode = f"{pre}{n:04d}"
        if not await db.vouchers.find_one({"kode": kode}):
            return kode


async def issue_complimentary(k, c):
    """Setiap complimentary (selain Apologize / Tidak Ada) mendapat kode untuk dilacak sampai dipakai/diterima.
    Voucher diskon memakai stok kode; bila stok habis atau bukan voucher → kode CMP otomatis."""
    if k["jenis"] in NO_CODE:
        return None, False
    db = get_db()
    if k.get("voucherJenis"):
        v = await issue_voucher(k["voucherJenis"], c["caseId"])
        if v:
            await db.vouchers.update_one({"kode": v["kode"]}, {"$set": {"kategori": "Voucher", "label": k["label"],
                                                                       "nilai": c.get("nilaiKompensasi") or k.get("nilai", 0)}})
            return v, False
    v = {"kode": await make_tracking_code(k["jenis"]), "jenis": k.get("voucherJenis") or k["label"], "label": k["label"],
         "kategori": k["jenis"], "status": "Diterbitkan", "caseId": c["caseId"], "tanggalDiterbitkan": now(),
         "nilai": c.get("nilaiKompensasi") or k.get("nilai", 0), "auto": True, "noExpiry": k["jenis"] in NO_EXPIRY,
         "outletCase": c.get("outletName"), "order": 10 ** 7 + await db.vouchers.count_documents({})}
    await db.vouchers.insert_one(dict(v))
    return v, bool(k.get("voucherJenis"))


async def issue_voucher(jenis, case_id):
    db = get_db()
    v = await db.vouchers.find_one({"jenis": jenis, "status": "Tersedia"}, sort=[("order", 1)])
    if not v:
        return None
    await db.vouchers.update_one({"kode": v["kode"]}, {"$set": {
        "status": "Diterbitkan", "caseId": case_id, "tanggalDiterbitkan": now()}})
    v.update(status="Diterbitkan", caseId=case_id)
    return v
