import json
import os
import smtplib
from datetime import timedelta, date
from email.mime.text import MIMEText

from .core import get_db, now, Config, as_utc, clean, log, wib, wib_date


async def recipients():
    st = (await get_db().config.find_one({"_id": "settings"}) or {}).get("value", {})
    return [e for e in st.get("emailRecipients", []) if "@" in e]


def send_email(to, subject, html):
    if not to:
        return False
    try:
        if Config.RESEND_API_KEY:
            import httpx
            httpx.post("https://api.resend.com/emails", timeout=15,
                       headers={"Authorization": f"Bearer {Config.RESEND_API_KEY}"},
                       json={"from": Config.MAIL_FROM, "to": to, "subject": subject, "html": html})
            return True
        if Config.SMTP_HOST:
            msg = MIMEText(html, "html", "utf-8")
            msg["Subject"], msg["From"], msg["To"] = subject, Config.MAIL_FROM, ", ".join(to)
            with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=15) as s:
                s.starttls()
                if Config.SMTP_USER:
                    s.login(Config.SMTP_USER, Config.SMTP_PASS)
                s.sendmail(Config.MAIL_FROM, to, msg.as_string())
            return True
    except Exception as e:  # jangan sampai job berhenti karena email
        log.error("Gagal kirim email: %s", e)
    return False


async def notify(kind, text, case_id=None, email_subject=None):
    db = get_db()
    await db.notifications.insert_one({"kind": kind, "text": text, "caseId": case_id, "at": now(), "readBy": []})
    if email_subject:
        send_email(await recipients(), email_subject, f"<p>{text}</p><p>{Config.PUBLIC_BASE_URL}/case/{case_id or ''}</p>")


async def critical_alert():
    """Case Critical tanpa first response setelah N menit → alert sekali."""
    db = get_db()
    st = (await db.config.find_one({"_id": "settings"}) or {}).get("value", {})
    after = st.get("alertCriticalAfterMin", 20)
    cutoff = now() - timedelta(minutes=after)
    async for c in db.cases.find({"level": "Critical", "status": "Open", "criticalAlerted": {"$ne": True}}):
        if as_utc(c["waktuMasuk"]) <= cutoff:
            await notify("critical", f"{c['caseId']} Critical ({c.get('subJenis')}, {c.get('outletName')}) belum dibalas "
                                     f"{after}+ menit. Target < 30 menit.", c["caseId"],
                         f"[CRITICAL] {c['caseId']} belum dibalas")
            await db.cases.update_one({"caseId": c["caseId"]}, {"$set": {"criticalAlerted": True}})


async def morning():
    db = get_db()
    open_ = await db.cases.count_documents({"status": {"$in": ["Open", "Responded"]}})
    crit = await db.cases.count_documents({"status": {"$in": ["Open", "Responded"]}, "level": "Critical"})
    today = wib_date(now()).isoformat()
    overdue = await db.voc_actions.count_documents({"status": {"$in": ["Open", "On Progress"]}, "deadline": {"$lt": today}})
    drafts = await db.csat.count_documents({"triage": "belum", "needsTriage": True})
    text = (f"Pagi ini: {open_} case belum selesai ({crit} Critical), {overdue} action meeting lewat deadline, "
            f"{drafts} draft CSAT menunggu.")
    await notify("morning", text, None, "Service Desk — ringkasan pagi")


async def weekly_recap():
    from .routes_cases import build_dashboard
    t = wib_date(now())
    frm, to = t - timedelta(days=7), t - timedelta(days=1)
    d = await build_dashboard(frm.isoformat(), to.isoformat())
    m, v = d["metrics"], d["volume"]
    p = lambda x: "-" if x is None else f"{round(x * 100)}%"
    rows = "".join(f"<li>{r['name']}: {r['count']}</li>" for r in d["subJenis"][:5])
    html = (f"<h3>Rekap mingguan {frm:%d/%m}–{to:%d/%m}</h3><p>Komplain {v['komplain']} (Critical {v['critical']}), "
            f"FRT {m['frt']} mnt, SLA Response {p(m['slaResponse'])}, Same-Day {p(m['sameDay'])}, CSAT {p(m['csat'])}.</p>"
            f"<p>Top 5 sub jenis:</p><ul>{rows}</ul>")
    send_email(await recipients(), "Service Desk — rekap mingguan", html)


async def voucher_expiry():
    db = get_db()
    st = (await db.config.find_one({"_id": "settings"}) or {}).get("value", {})
    days = st.get("voucherExpiryDays", 30)
    cutoff = now() - timedelta(days=days)
    async for v in db.vouchers.find({"status": "Diterbitkan"}):
        if v.get("tanggalDiterbitkan") and as_utc(v["tanggalDiterbitkan"]) < cutoff:
            await db.vouchers.update_one({"kode": v["kode"]}, {"$set": {"status": "Hangus"}})
    stock = {}
    async for v in db.vouchers.find({"status": "Tersedia"}):
        stock[v["jenis"]] = stock.get(v["jenis"], 0) + 1
    for j, n in stock.items():
        if n < 10:
            await notify("voucher", f"Stok {j} tinggal {n} kode.")


async def backup():
    db = get_db()
    d = os.path.join(Config.DATA_DIR, "backups")
    os.makedirs(d, exist_ok=True)
    out = {}
    for coll in ("cases", "events", "csat", "reviews", "ratings", "vouchers", "voc_actions", "meetings", "outlets",
                 "users", "sub_jenis", "channels", "kompensasi", "config", "monthly", "audit"):
        rows = []
        async for x in db[coll].find({}):
            x = dict(x)
            if coll == "config":
                x["id_"] = x.get("_id")
            rows.append(clean(x))
        out[coll] = rows
    path = os.path.join(d, f"backup-{wib(now()):%Y%m%d-%H%M}.json")
    with open(path, "w") as f:
        json.dump(out, f, ensure_ascii=False, default=str)
    files = sorted(x for x in os.listdir(d) if x.startswith("backup-"))
    for old in files[:-8]:
        os.remove(os.path.join(d, old))
    return path


async def nightly_recompute():
    """Simpan ulang kolom otomatis (Same-Day case open, Cek Data) agar list & export ikut terbaru."""
    from .services import recompute_all
    await recompute_all()


def start_scheduler():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    s = AsyncIOScheduler(timezone="Asia/Jakarta")
    s.add_job(critical_alert, "interval", minutes=5, id="critical")
    s.add_job(morning, "cron", hour=8, minute=0, id="morning")
    s.add_job(weekly_recap, "cron", day_of_week="mon", hour=8, minute=30, id="weekly")
    s.add_job(voucher_expiry, "cron", hour=0, minute=10, id="voucher")
    s.add_job(backup, "cron", day_of_week="sun", hour=2, minute=0, id="backup")
    s.add_job(nightly_recompute, "cron", hour=0, minute=20, id="recompute")
    s.start()
    return s
