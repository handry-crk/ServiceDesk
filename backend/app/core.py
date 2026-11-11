"""Config, database, waktu (WIB), dan helper umum."""
import logging
import os
import re
from datetime import datetime, timedelta, timezone, date

log = logging.getLogger("servicedesk")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

WIB = timezone(timedelta(hours=7))


class Config:
    MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    DB_NAME = os.getenv("DB_NAME", "service_desk")
    USE_MOCK_DB = os.getenv("USE_MOCK_DB", "false").lower() in ("1", "true", "yes")
    SECRET_KEY = os.getenv("SECRET_KEY", "ganti-secret-ini")
    DEFAULT_ADMIN_PIN = os.getenv("DEFAULT_ADMIN_PIN", "123456")
    METRICS_API_KEY = os.getenv("METRICS_API_KEY", "ganti-api-key-ini")
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
    DATA_DIR = os.getenv("DATA_DIR", "/data")
    RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
    MAIL_FROM = os.getenv("MAIL_FROM", "Service Desk <noreply@example.com>")
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASS = os.getenv("SMTP_PASS", "")
    DISABLE_JOBS = os.getenv("DISABLE_JOBS", "false").lower() in ("1", "true", "yes")


_client = None
db = None


def init_db():
    global _client, db
    if Config.USE_MOCK_DB:
        from mongomock_motor import AsyncMongoMockClient
        _client = AsyncMongoMockClient()
        log.warning("USE_MOCK_DB=true: data hanya di memori dan hilang saat restart.")
    else:
        from motor.motor_asyncio import AsyncIOMotorClient
        _client = AsyncIOMotorClient(Config.MONGO_URL, tz_aware=True)
    db = _client[Config.DB_NAME]
    for name, val in (("SECRET_KEY", "ganti-secret-ini"), ("DEFAULT_ADMIN_PIN", "123456"),
                      ("METRICS_API_KEY", "ganti-api-key-ini")):
        if getattr(Config, name) == val:
            log.warning("%s masih memakai nilai bawaan. Ganti di environment variable sebelum produksi.", name)
    return db


def get_db():
    return db


# ---------- waktu ----------

def now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = parse_iso(dt)
    if dt.tzinfo is None:  # mongomock / pymongo naive = UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def wib(dt):
    dt = as_utc(dt)
    return dt.astimezone(WIB) if dt else None


def wib_date(dt) -> date | None:
    d = wib(dt)
    return d.date() if d else None


def parse_iso(s):
    if not s:
        return None
    if isinstance(s, datetime):
        return as_utc(s)
    s = str(s).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=WIB)  # tanpa zona = WIB
    return dt.astimezone(timezone.utc)


_DMY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})(?:[ T]+(\d{1,2})[:.](\d{2})(?::(\d{2}))?)?$")


def parse_sheet_time(v):
    """Parse waktu dari sheet lama. Return (datetime UTC, hasTime) atau (None, False).
    Selalu dibaca hari/bulan/tahun (tidak pernah bulan/hari)."""
    if v is None or v == "":
        return None, False
    if isinstance(v, datetime):
        dt = v if v.tzinfo else v.replace(tzinfo=WIB)
        has_time = not (dt.hour == 0 and dt.minute == 0 and dt.second == 0)
        return dt.astimezone(timezone.utc), has_time
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day, tzinfo=WIB).astimezone(timezone.utc), False
    s = str(v).strip()
    m = _DMY.match(s)
    if not m:
        try:
            return parse_iso(s), True
        except Exception:
            return None, False
    d, mo, y, hh, mm, ss = m.groups()
    if hh is None:
        return datetime(int(y), int(mo), int(d), tzinfo=WIB).astimezone(timezone.utc), False
    dt = datetime(int(y), int(mo), int(d), int(hh), int(mm), int(ss or 0), tzinfo=WIB)
    has_time = not (int(hh) == 0 and int(mm) == 0)
    return dt.astimezone(timezone.utc), has_time


def parse_rupiah(v):
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = re.sub(r"[^\d]", "", str(v))
    return int(s) if s else None


def iso(dt):
    dt = as_utc(dt)
    return dt.isoformat() if dt else None


def clean(doc):
    """Mongo doc → JSON (hapus _id, datetime → ISO)."""
    if doc is None:
        return None
    if isinstance(doc, list):
        return [clean(d) for d in doc]
    out = {}
    for k, v in doc.items():
        if k == "_id":
            continue
        if isinstance(v, datetime):
            out[k] = iso(v)
        elif isinstance(v, dict):
            out[k] = clean(v)
        elif isinstance(v, list):
            out[k] = [clean(x) if isinstance(x, dict) else (iso(x) if isinstance(x, datetime) else x) for x in v]
        else:
            out[k] = v
    return out


def mask_phone(p):
    if not p:
        return p
    digits = re.sub(r"\D", "", str(p))
    if len(digits) < 7:
        return "****"
    return digits[:4] + "****" + digits[-3:]
