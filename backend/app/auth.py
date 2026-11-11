import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import Depends, Header, HTTPException

from .core import get_db, now, as_utc, Config

ROLES = ["Admin", "CS Lead", "Marketing TL", "CS Agent", "Manager Area", "Ops/QC", "Viewer"]
ROLE_LABEL = {"CS Lead": "CRM Supervisor", "Marketing TL": "Marketing Team Leader", "CS Agent": "Customer Service"}
# Kuota user AKTIF per peran (pendaftaran member baru + pembuatan user oleh admin)
ROLE_SLOTS = {"CS Lead": 1, "Marketing TL": 1, "CS Agent": 5}
MEETING_EDITORS = ("Admin", "CS Lead", "CS Agent", "Marketing TL")
LEAD = ("Admin", "CS Lead")
WRITERS = ("Admin", "CS Lead", "CS Agent")


def hash_pin(pin: str, salt: str | None = None):
    """PBKDF2 + salt per user. Sengaja TIDAK memakai SECRET_KEY, supaya mengganti
    SECRET_KEY di Railway tidak membuat semua PIN tidak bisa dipakai."""
    salt = salt or secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 120_000).hex()
    return f"v2${salt}${h}"


def _legacy_hash(pin, salt, secret):
    return f"{salt}$" + hashlib.pbkdf2_hmac("sha256", (pin + secret).encode(), salt.encode(), 120_000).hex()


def verify_pin(pin: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith("v2$"):
        try:
            _, salt, _ = stored.split("$", 2)
        except ValueError:
            return False
        return hmac.compare_digest(hash_pin(pin, salt), stored)
    try:  # format lama (versi pertama): pin + SECRET_KEY
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(_legacy_hash(pin, salt, Config.SECRET_KEY), stored)


async def current_user(authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        raise HTTPException(401, "Silakan login dulu.")
    db = get_db()
    s = await db.sessions.find_one({"token": token})
    if not s or as_utc(s["expires"]) < now():
        raise HTTPException(401, "Sesi berakhir. Silakan login lagi.")
    u = await db.users.find_one({"id": s["userId"], "active": True})
    if not u:
        raise HTTPException(401, "User tidak aktif.")
    return u


def require(*roles):
    async def dep(u=Depends(current_user)):
        if roles and u["role"] not in roles:
            raise HTTPException(403, "Peran Anda tidak punya akses untuk tindakan ini.")
        return u
    return dep


async def login(name: str, pin: str):
    """`name` = email kantor (user baru) atau nama pengguna (Admin / user lama tanpa email)."""
    db = get_db()
    key = (name or "").strip()
    q = {"email": key.lower()} if "@" in key else {"name": key}
    u = await db.users.find_one({**q, "active": True})
    if not u:
        raise HTTPException(401, "Email/nama atau PIN salah.")
    if u.get("lockedUntil") and as_utc(u["lockedUntil"]) > now():
        mins = int((as_utc(u["lockedUntil"]) - now()).total_seconds() // 60) + 1
        raise HTTPException(423, f"Akun dikunci karena 5 kali PIN salah. Coba lagi {mins} menit lagi atau minta CS Lead membuka kunci.")
    if not verify_pin(pin, u["pinHash"]):
        fails = (u.get("failedPins") or 0) + 1
        upd = {"failedPins": fails}
        if fails >= 5:
            upd = {"failedPins": 0, "lockedUntil": now() + timedelta(minutes=15)}
        await db.users.update_one({"id": u["id"]}, {"$set": upd})
        raise HTTPException(401, "Email/nama atau PIN salah." + (" Akun dikunci 15 menit." if fails >= 5 else ""))
    await db.users.update_one({"id": u["id"]}, {"$set": {"failedPins": 0, "lockedUntil": None, "lastLogin": now()}})
    token = secrets.token_urlsafe(32)
    await db.sessions.insert_one({"token": token, "userId": u["id"], "created": now(),
                                  "expires": now() + timedelta(days=30)})
    return token, u


def public_user(u):
    return {"id": u["id"], "name": u["name"], "email": u.get("email"), "role": u["role"],
            "roleLabel": ROLE_LABEL.get(u["role"], u["role"]), "areas": u.get("areas", []),
            "active": u.get("active", True)}


async def check_slot(role, exclude_id=None):
    """Tolak bila kuota peran sudah penuh (dihitung dari user aktif)."""
    if role not in ROLE_SLOTS:
        return
    q = {"role": role, "active": True}
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    used = await get_db().users.count_documents(q)
    if used >= ROLE_SLOTS[role]:
        raise HTTPException(409, f"Kuota {ROLE_LABEL[role]} sudah penuh ({used}/{ROLE_SLOTS[role]}). "
                                 "Nonaktifkan user lama dulu atau ubah perannya.")


def email_ok(email):
    from .core import Config
    e = (email or "").strip().lower()
    return e if (e.count("@") == 1 and e.endswith("@" + Config.ALLOWED_EMAIL_DOMAIN) and len(e) > len(Config.ALLOWED_EMAIL_DOMAIN) + 1) else None
