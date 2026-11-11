"""Pendaftaran member baru: hanya email @<ALLOWED_EMAIL_DOMAIN>, kuota per peran, wajib disetujui Admin.

Alur: daftar → (bila email server aktif) verifikasi kode 6 digit ke email → menunggu persetujuan Admin
→ disetujui = user aktif, login dengan email kantor + PIN yang dibuat saat daftar."""
import hashlib
import secrets
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .auth import require, hash_pin, check_slot, email_ok, ROLE_SLOTS, ROLE_LABEL, public_user
from .core import get_db, now, clean, Config, as_utc, log
from .services import new_id, audit

router = APIRouter(prefix="/api")

REG_ROLES = ["CS Lead", "Marketing TL", "CS Agent"]  # peran yang boleh didaftarkan sendiri
CODE_TTL_MIN = 30
RATE_LIMIT = 5  # pendaftaran per IP per jam


def _code_hash(code: str, rid: str) -> str:
    return hashlib.sha256(f"{rid}:{code}".encode()).hexdigest()


def _mail_ready() -> bool:
    return bool(Config.RESEND_API_KEY or Config.SMTP_HOST)


async def _slots():
    db = get_db()
    out = []
    for r in REG_ROLES:
        used = await db.users.count_documents({"role": r, "active": True})
        pending = await db.registrations.count_documents({"role": r, "status": "pending"})
        out.append({"role": r, "label": ROLE_LABEL[r], "slots": ROLE_SLOTS[r], "used": used,
                    "available": max(0, ROLE_SLOTS[r] - used), "pending": pending})
    return out


async def _notify_admins(text):
    from .jobs import notify
    await notify("registration", text, None, "Service Desk — pendaftaran member baru", roles=["Admin"],
                 link="/pengaturan?tab=user")


@router.get("/public/register/info")
async def register_info():
    return {"domain": Config.ALLOWED_EMAIL_DOMAIN, "roles": await _slots(), "emailVerification": _mail_ready()}


class RegisterIn(BaseModel):
    name: str
    email: str
    role: str
    pin: str
    phone: Optional[str] = None


_bucket = {}


def _rate(ip):
    import time
    t = time.time()
    b = [x for x in _bucket.get(ip, []) if x > t - 3600]
    if len(b) >= RATE_LIMIT:
        raise HTTPException(429, "Terlalu banyak percobaan pendaftaran. Coba lagi 1 jam lagi.")
    b.append(t)
    _bucket[ip] = b


@router.post("/public/register")
async def register(body: RegisterIn, request: Request):
    _rate(request.client.host if request.client else "x")
    db = get_db()
    name = " ".join(body.name.split())
    if len(name) < 3:
        raise HTTPException(400, "Nama lengkap minimal 3 huruf.")
    email = email_ok(body.email)
    if not email:
        raise HTTPException(400, f"Pendaftaran hanya untuk email kantor @{Config.ALLOWED_EMAIL_DOMAIN}.")
    if body.role not in REG_ROLES:
        raise HTTPException(400, "Peran tidak tersedia untuk pendaftaran.")
    if len(body.pin) != 6 or not body.pin.isdigit():
        raise HTTPException(400, "PIN harus 6 digit angka.")
    if body.pin in ("123456", "000000", "111111", "654321") or len(set(body.pin)) == 1:
        raise HTTPException(400, "PIN terlalu mudah ditebak. Pilih kombinasi lain.")
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "Email ini sudah terdaftar sebagai user. Silakan login.")
    used = await db.users.count_documents({"role": body.role, "active": True})
    if used >= ROLE_SLOTS[body.role]:
        raise HTTPException(409, f"Kuota {ROLE_LABEL[body.role]} sudah penuh ({used}/{ROLE_SLOTS[body.role]}). "
                                 "Hubungi Admin.")
    # satu permintaan aktif per email: yang lama digantikan
    await db.registrations.update_many({"email": email, "status": {"$in": ["verify", "pending"]}},
                                       {"$set": {"status": "replaced", "decidedAt": now()}})
    rid = new_id()
    r = {"id": rid, "name": name, "email": email, "role": body.role, "phone": (body.phone or "").strip() or None,
         "pinHash": hash_pin(body.pin), "createdAt": now(), "ip": request.client.host if request.client else None}
    if _mail_ready():
        from .jobs import send_email
        code = f"{secrets.randbelow(10 ** 6):06d}"
        r.update(status="verify", codeHash=_code_hash(code, rid), codeExpires=now() + timedelta(minutes=CODE_TTL_MIN),
                 codeTries=0)
        await db.registrations.insert_one(r)
        sent = send_email([email], "Kode verifikasi CRK Service Desk",
                          f"<p>Halo {name},</p><p>Kode verifikasi pendaftaran Anda: <b style='font-size:20px'>{code}</b></p>"
                          f"<p>Berlaku {CODE_TTL_MIN} menit. Abaikan email ini bila Anda tidak mendaftar.</p>")
        if sent:
            return {"id": rid, "status": "verify", "email": email}
        # email gagal terkirim → lanjut ke persetujuan Admin saja
        await db.registrations.update_one({"id": rid}, {"$set": {"status": "pending", "emailVerified": False}})
    else:
        r.update(status="pending", emailVerified=False)
        await db.registrations.insert_one(r)
    await _notify_admins(f"Pendaftaran baru: {name} ({email}) sebagai {ROLE_LABEL[body.role]}. Menunggu persetujuan Admin.")
    return {"id": rid, "status": "pending", "email": email}


@router.post("/public/register/{rid}/verify")
async def verify(rid: str, body: dict):
    db = get_db()
    r = await db.registrations.find_one({"id": rid, "status": "verify"})
    if not r:
        raise HTTPException(404, "Permintaan tidak ditemukan atau sudah diverifikasi.")
    if as_utc(r["codeExpires"]) < now():
        raise HTTPException(400, "Kode sudah kedaluwarsa. Silakan daftar ulang.")
    if (r.get("codeTries") or 0) >= 5:
        raise HTTPException(429, "Terlalu banyak kode salah. Silakan daftar ulang.")
    code = str(body.get("code") or "").strip()
    if _code_hash(code, rid) != r["codeHash"]:
        await db.registrations.update_one({"id": rid}, {"$inc": {"codeTries": 1}})
        raise HTTPException(400, "Kode salah.")
    await db.registrations.update_one({"id": rid}, {"$set": {"status": "pending", "emailVerified": True,
                                                             "verifiedAt": now()}, "$unset": {"codeHash": ""}})
    await _notify_admins(f"Pendaftaran baru (email terverifikasi): {r['name']} ({r['email']}) sebagai "
                         f"{ROLE_LABEL[r['role']]}. Menunggu persetujuan Admin.")
    return {"status": "pending"}


@router.get("/public/register/{rid}")
async def register_status(rid: str):
    r = await get_db().registrations.find_one({"id": rid})
    if not r:
        raise HTTPException(404, "Permintaan tidak ditemukan.")
    return {"status": r["status"], "email": r["email"], "role": ROLE_LABEL.get(r["role"], r["role"]),
            "reason": r.get("reason")}


# ------------------------------------------------------------------ Admin

def _out(r):
    d = clean(r)
    for k in ("pinHash", "codeHash", "ip"):
        d.pop(k, None)
    d["roleLabel"] = ROLE_LABEL.get(r["role"], r["role"])
    return d


@router.get("/registrations")
async def registrations(u=Depends(require("Admin", "CS Lead")), status: Optional[str] = None):
    q = {"status": status} if status else {"status": {"$in": ["pending", "verify", "approved", "rejected"]}}
    rows = [_out(r) async for r in get_db().registrations.find(q).sort("createdAt", -1).limit(200)]
    return {"rows": rows, "slots": await _slots(), "canApprove": u["role"] == "Admin"}


@router.post("/registrations/{rid}/approve")
async def approve(rid: str, body: dict | None = None, u=Depends(require("Admin"))):
    db = get_db()
    r = await db.registrations.find_one({"id": rid})
    if not r or r["status"] != "pending":
        raise HTTPException(400, "Hanya permintaan berstatus menunggu yang bisa disetujui.")
    role = (body or {}).get("role") or r["role"]
    if role not in REG_ROLES:
        raise HTTPException(400, "Peran tidak tersedia.")
    if await db.users.find_one({"email": r["email"]}):
        raise HTTPException(409, "Email ini sudah menjadi user.")
    await check_slot(role)
    name = r["name"]
    if await db.users.find_one({"name": name}):
        name = f"{name} ({r['email'].split('@')[0]})"
    x = {"id": new_id(), "name": name, "email": r["email"], "phone": r.get("phone"), "role": role, "areas": [],
         "pinHash": r["pinHash"], "active": True, "created": now(), "registrationId": rid}
    await db.users.insert_one(x)
    await db.registrations.update_one({"id": rid}, {"$set": {"status": "approved", "role": role, "decidedAt": now(),
                                                             "decidedBy": u["name"], "userId": x["id"]}})
    await audit(u, f"approve registration {r['email']}", None, role)
    if Config.RESEND_API_KEY or Config.SMTP_HOST:
        from .jobs import send_email
        send_email([r["email"]], "Akun CRK Service Desk Anda sudah aktif",
                   f"<p>Halo {r['name']},</p><p>Pendaftaran Anda sebagai <b>{ROLE_LABEL[role]}</b> sudah disetujui. "
                   f"Login di {Config.PUBLIC_BASE_URL} dengan email kantor dan PIN yang Anda buat saat mendaftar.</p>")
    return public_user(x)


@router.post("/registrations/{rid}/reject")
async def reject(rid: str, body: dict | None = None, u=Depends(require("Admin"))):
    db = get_db()
    r = await db.registrations.find_one({"id": rid})
    if not r or r["status"] not in ("pending", "verify"):
        raise HTTPException(400, "Permintaan ini sudah diputuskan.")
    reason = ((body or {}).get("reason") or "").strip() or None
    await db.registrations.update_one({"id": rid}, {"$set": {"status": "rejected", "reason": reason,
                                                             "decidedAt": now(), "decidedBy": u["name"]}})
    await audit(u, f"reject registration {r['email']}", None, None, reason)
    return {"ok": True}
