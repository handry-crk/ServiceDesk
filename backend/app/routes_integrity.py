"""Integritas waktu: pengawasan per CS, pengajuan koreksi, dan audit acak mingguan."""
import random
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .auth import require, LEAD
from .core import get_db, now, clean, wib_date
from .logic import load_ctx, _avg, _rate
from .services import new_id, add_event, save_case, get_case_or_404

router = APIRouter(prefix="/api")
VIEWERS = ("Admin", "CS Lead", "Marketing TL")


def _resp_by(c):
    return c.get("frBy") or c.get("csAgent") or "Tanpa nama"


async def build_integrity(frm: str, to: str):
    from .routes_cases import cases_in_period
    ctx = await load_ctx()
    st = ctx["settings"]
    cases = [c for c in await cases_in_period(frm, to, None, None, None, ctx) if c.get("source", "manual") != "import"]
    audits = [a async for a in get_db().audits.find({"weekStart": {"$lte": to}, "weekEnd": {"$gte": frm}})]
    audit_by = defaultdict(lambda: {"cocok": 0, "tidak": 0, "belum": 0})
    for a in audits:
        for it in a["items"]:
            audit_by[it["cs"]][it.get("result") or "belum"] += 1
    groups = defaultdict(list)
    for c in cases:
        groups[_resp_by(c)].append(c)
    names = set(groups) | set(audit_by)
    rows = []
    for name in sorted(names):
        cs = groups.get(name, [])
        resp = [c for c in cs if c.get("frRecordedAt")]
        manual = [c for c in resp if c.get("frtManual")]
        log = [r for c in cs for r in (c.get("timeRequestLog") or [])]
        created = [c for c in cs if c.get("csAgent") == name and c.get("masukLagMin") is not None]
        late = [c for c in created if c["masukLagMin"] > st["masukLagReasonMin"]]
        ad = audit_by[name]
        r = {
            "name": name, "responded": len(resp), "manual": len(manual),
            "manualPct": _rate(len(manual), len(resp)),
            "avgBackdate": _avg([c.get("frBackdateMin") for c in manual]),
            "rescued": sum(1 for c in resp if c.get("slaRescued")),
            "frtReported": _avg([c.get("frtMin") for c in resp]), "frtSystem": _avg([c.get("frtSystemMin") for c in resp]),
            "lateEntry": len(late), "avgLag": _avg([c["masukLagMin"] for c in late]),
            "approved": sum(1 for x in log if x["status"] == "approved"),
            "rejected": sum(1 for x in log if x["status"] == "rejected"),
            "pending": sum(1 for c in cs if c.get("timeRequest")),
            "auditOk": ad["cocok"], "auditBad": ad["tidak"], "auditOpen": ad["belum"],
        }
        flags = []
        if r["manualPct"] is not None and r["manualPct"] > st["manualAlertPct"] and len(resp) >= 5:
            flags.append(f"Jam manual {round(r['manualPct'] * 100)}% (batas {round(st['manualAlertPct'] * 100)}%)")
        if r["rejected"]:
            flags.append(f"{r['rejected']} pengajuan ditolak")
        if r["auditBad"]:
            flags.append(f"{r['auditBad']} audit tidak cocok")
        if r["rescued"]:
            flags.append(f"{r['rescued']} case SLA lolos karena jam manual")
        r["flags"] = flags
        rows.append(r)
    rows.sort(key=lambda r: (-len(r["flags"]), -(r["manualPct"] or 0)))
    resp_all = [c for c in cases if c.get("frRecordedAt")]
    total = {
        "responded": len(resp_all), "manual": sum(1 for c in resp_all if c.get("frtManual")),
        "manualPct": _rate(sum(1 for c in resp_all if c.get("frtManual")), len(resp_all)),
        "frtReported": _avg([c.get("frtMin") for c in resp_all]), "frtSystem": _avg([c.get("frtSystemMin") for c in resp_all]),
        "rescued": sum(1 for c in resp_all if c.get("slaRescued")),
        "pending": sum(1 for c in cases if c.get("timeRequest")),
        "auditOk": sum(v["cocok"] for v in audit_by.values()), "auditBad": sum(v["tidak"] for v in audit_by.values()),
        "auditOpen": sum(v["belum"] for v in audit_by.values()),
    }
    return {"period": {"from": frm, "to": to}, "settings": {k: st[k] for k in (
        "frGraceMin", "frMaxBackMin", "frEditHours", "masukLagReasonMin", "manualAlertPct", "auditSamplePerCs")},
        "rows": rows, "total": total}


@router.get("/integrity")
async def integrity(frm: str, to: str, u=Depends(require(*VIEWERS))):
    return await build_integrity(frm, to)


# ------------------------------------------------------------------ audit acak

class AuditIn(BaseModel):
    weekStart: Optional[str] = None   # Senin; default = minggu lalu


def last_week():
    t = wib_date(now())
    mon = t - timedelta(days=t.weekday() + 7)
    return mon, mon + timedelta(days=6)


async def create_audit(week_start: date, by: str):
    from .routes_cases import cases_in_period
    db = get_db()
    ws, we = week_start, week_start + timedelta(days=6)
    ex = await db.audits.find_one({"weekStart": ws.isoformat()})
    if ex:
        return ex, False
    ctx = await load_ctx()
    n = ctx["settings"]["auditSamplePerCs"]
    cases = [c for c in await cases_in_period(ws.isoformat(), we.isoformat(), None, None, None, ctx)
             if c.get("waktuFirstResponse") and c.get("source", "manual") == "manual"]
    by_cs = defaultdict(list)
    for c in cases:
        by_cs[_resp_by(c)].append(c)
    rnd = random.SystemRandom()
    items = []
    for cs, lst in sorted(by_cs.items()):
        manual = [c for c in lst if c.get("frtManual")]
        pick = rnd.sample(manual, min(len(manual), (n + 1) // 2))
        rest = [c for c in lst if c not in pick]
        pick += rnd.sample(rest, min(len(rest), n - len(pick)))
        for c in pick:
            items.append({"caseId": c["caseId"], "cs": cs, "channel": c.get("channel"), "waktuMasuk": c["waktuMasuk"],
                          "waktuFirstResponse": c["waktuFirstResponse"], "frtMin": c.get("frtMin"),
                          "manual": bool(c.get("frtManual")), "result": None, "note": None})
    a = {"id": new_id(), "weekStart": ws.isoformat(), "weekEnd": we.isoformat(), "items": items,
         "createdBy": by, "createdAt": now()}
    await db.audits.insert_one(a)
    return a, True


@router.get("/audits")
async def audits(u=Depends(require(*VIEWERS))):
    return [clean(a) async for a in get_db().audits.find({}).sort("weekStart", -1).limit(12)]


@router.post("/audits")
async def new_audit(body: AuditIn, u=Depends(require(*LEAD))):
    if body.weekStart:
        d = date.fromisoformat(body.weekStart)
        ws = d - timedelta(days=d.weekday())
    else:
        ws, _ = last_week()
    a, created = await create_audit(ws, u["name"])
    return {**clean(a), "created": created}


class AuditItemIn(BaseModel):
    result: str
    note: Optional[str] = None


@router.post("/audits/{aid}/items/{case_id}")
async def audit_item(aid: str, case_id: str, body: AuditItemIn, u=Depends(require(*LEAD))):
    if body.result not in ("cocok", "tidak"):
        raise HTTPException(400, "Hasil harus 'cocok' atau 'tidak'.")
    if body.result == "tidak" and not (body.note or "").strip():
        raise HTTPException(400, "Tulis apa yang tidak cocok (jam sebenarnya di chat).")
    db = get_db()
    a = await db.audits.find_one({"id": aid})
    if not a:
        raise HTTPException(404, "Audit tidak ditemukan.")
    it = next((x for x in a["items"] if x["caseId"] == case_id), None)
    if not it:
        raise HTTPException(404, "Case tidak ada di sampel audit ini.")
    if it["cs"] == u["name"]:
        raise HTTPException(403, "Tidak bisa mengaudit case sendiri.")
    it.update(result=body.result, note=(body.note or "").strip() or None, checkedBy=u["name"], checkedAt=now())
    await db.audits.update_one({"id": aid}, {"$set": {"items": a["items"]}})
    c = await get_case_or_404(case_id)
    c["auditResult"] = body.result
    await save_case(c)
    await add_event(case_id, "audit_checked", u, {"result": body.result, "reason": it["note"]})
    return clean(a)
