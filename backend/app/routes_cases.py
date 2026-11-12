from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .auth import current_user, require, LEAD, WRITERS, MEETING_EDITORS
from .core import get_db, now, parse_iso, as_utc, clean, mask_phone, wib_date, Config
from . import standards as S
from .logic import compute_case, load_ctx, compute_metrics, breakdown, weekly, by_hour, insights, suggest_insights, by_member, level_breakdown
from .services import (next_case_id, save_case, add_event, audit, find_duplicates, get_case_or_404,
                       survey_token, issue_voucher, issue_complimentary, new_id)

router = APIRouter(prefix="/api")


# ------------------------------------------------------------------ helpers

def can_see_phone(u):
    return u["role"] in ("Admin", "CS Lead", "CS Agent")


def out_case(c, u):
    d = clean(c)
    if not can_see_phone(u):
        d["customerPhone"] = mask_phone(d.get("customerPhone"))
    return d


def check_area(u, c):
    if u["role"] == "Manager Area" and c.get("area") not in (u.get("areas") or []):
        raise HTTPException(403, "Case ini di luar area Anda.")


def area_filter(u, q):
    if u["role"] == "Manager Area":
        q["area"] = {"$in": u.get("areas") or ["-"]}
    return q


async def cases_in_period(frm: str, to: str, u=None, brand=None, area=None, ctx=None, line=None):
    """Kolom otomatis dihitung ulang saat dibaca, supaya Same-Day case yang masih open
    dan perubahan target/standard selalu ikut terbaru."""
    from .logic import compute_case
    ctx = ctx or await load_ctx()
    q = {"tanggalMasuk": {"$gte": frm, "$lte": to}}
    if brand:
        q["brand"] = brand
    if area:
        q["area"] = area
    if line == "frozen":
        q["outletType"] = "online_frozen"
    elif line == "outlet":
        q["outletType"] = {"$ne": "online_frozen"}
    if u:
        area_filter(u, q)
    return [compute_case(c, ctx) async for c in get_db().cases.find(q)]


# ------------------------------------------------------------------ create

class CaseIn(BaseModel):
    channel: str
    outletId: str
    subJenis: str
    ringkasan: str
    waktuMasuk: Optional[str] = None
    brand: Optional[str] = None
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
    source: Optional[str] = "manual"
    sourceRefId: Optional[str] = None
    waktuMasukReason: Optional[str] = None
    force: bool = False


@router.get("/cases/check-duplicate")
async def check_dup(outletId: str, subJenis: str, waktuMasuk: Optional[str] = None, orderNo: Optional[str] = None,
                    u=Depends(current_user)):
    w = parse_iso(waktuMasuk) if waktuMasuk else now()
    return {"duplicates": await find_duplicates(outletId, subJenis, w, orderNo)}


@router.post("/cases")
async def create_case(body: CaseIn, u=Depends(require(*WRITERS))):
    db = get_db()
    ctx = await load_ctx()
    outlet = ctx["outlets"].get(body.outletId)
    if not outlet:
        raise HTTPException(400, "Outlet tidak dikenal. Pilih dari daftar.")
    if body.subJenis not in ctx["subJenis"]:
        raise HTTPException(400, "Sub Jenis Komplain tidak dikenal.")
    if body.channel not in ctx["channels"]:
        raise HTTPException(400, "Channel tidak dikenal.")
    if not body.ringkasan.strip():
        raise HTTPException(400, "Ringkasan masalah wajib diisi.")
    w = parse_iso(body.waktuMasuk) if body.waktuMasuk else now()
    if w > now() + timedelta(minutes=2):
        raise HTTPException(400, "Waktu Masuk tidak boleh di masa depan.")
    lag = (now() - as_utc(w)).total_seconds() / 60
    lag_max = ctx["settings"]["masukLagReasonMin"]
    if lag > lag_max and u["role"] not in LEAD and not (body.waktuMasukReason or "").strip():
        raise HTTPException(400, f"Waktu masuk lebih dari {lag_max} menit yang lalu: tulis alasan kenapa baru dicatat.")
    dups = await find_duplicates(body.outletId, body.subJenis, w, body.orderNo)
    if dups and not body.force:
        raise HTTPException(409, {"message": f"Mungkin sama dengan {', '.join(dups)}. Tetap simpan?",
                                  "duplicates": dups})
    case_id = await next_case_id(outlet["type"])
    c = {
        "caseId": case_id, "brand": body.brand or outlet.get("brand") or "Cimol Bojot AA",
        "outletId": body.outletId, "outletType": outlet["type"], "channel": body.channel,
        "tipe": body.tipe or "Komplain", "subJenis": body.subJenis, "valid": "Y",
        "ringkasan": body.ringkasan.strip(), "orderNo": body.orderNo, "customerName": body.customerName,
        "customerPhone": body.customerPhone, "photos": body.photos[:3], "waktuMasuk": w, "hasTime": True,
        "status": "Open", "reopenCount": 0, "csAgent": u["name"], "csAgentId": u["id"],
        "source": body.source or "manual", "sourceRefId": body.sourceRefId,
        "possibleDuplicateOf": dups[0] if dups else None,
        **{k: (v.strip() if isinstance(v, str) else v) for k, v in
           (("produk", body.produk), ("kodeProduksi", body.kodeProduksi), ("ekspedisi", body.ekspedisi),
            ("noResi", body.noResi), ("qtyPesan", body.qtyPesan), ("qtyDiterima", body.qtyDiterima))
           if v not in (None, "")},
        "createdBy": u["name"], "createdAt": now(), "surveyToken": survey_token(),
        "waktuMasukReason": (body.waktuMasukReason or "").strip() or None,
    }
    sj = ctx["subJenis"][body.subJenis]
    c["picDept"] = sj["picFrozen"] if outlet["type"] == "online_frozen" else sj["picOutlet"]
    await save_case(c, ctx)
    await add_event(case_id, "created", u, {"channel": body.channel})
    return out_case(c, u)


# ------------------------------------------------------------------ read

@router.get("/cases")
async def list_cases(u=Depends(current_user), frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None,
                     status: Optional[str] = None, level: Optional[str] = None, jenis: Optional[str] = None,
                     subJenis: Optional[str] = None, channel: Optional[str] = None, outletId: Optional[str] = None,
                     area: Optional[str] = None, picDept: Optional[str] = None, kompensasi: Optional[str] = None,
                     luarStandard: bool = False, dataIssue: bool = False, agent: Optional[str] = None,
                     q: Optional[str] = None, limit: int = 3000):
    qq = {}
    if frm or to:
        qq["tanggalMasuk"] = {"$gte": frm or "0000", "$lte": to or "9999"}
    for k, v in (("status", status), ("level", level), ("jenis", jenis), ("subJenis", subJenis),
                 ("channel", channel), ("outletId", outletId), ("area", area), ("picDept", picDept),
                 ("kompensasiJenis", kompensasi), ("csAgent", agent)):
        if v:
            qq[k] = {"$in": v.split("|")} if "|" in v else v
    if luarStandard:
        qq["kompensasiOutsideStandard"] = True
    if dataIssue:
        qq["dataOk"] = False
    area_filter(u, qq)
    rows = [c async for c in get_db().cases.find(qq).sort("waktuMasuk", -1).limit(limit)]
    if q:
        ql = q.lower()
        rows = [c for c in rows if ql in " ".join(str(c.get(k) or "") for k in
                                                   ("caseId", "ringkasan", "outletName", "orderNo", "customerName",
                                                    "subJenis", "notes")).lower()]
    return [out_case(c, u) for c in rows]


@router.get("/cases/{case_id}")
async def get_case(case_id: str, u=Depends(current_user)):
    c = await get_case_or_404(case_id)
    check_area(u, c)
    ev = [clean(e) async for e in get_db().events.find({"caseId": case_id}).sort("at", 1)]
    d = out_case(c, u)
    d["events"] = ev
    d["surveyUrl"] = f"{Config.PUBLIC_BASE_URL}/survei/{c.get('surveyToken')}" if c.get("surveyToken") else None
    if c.get("voucherCode"):
        d["voucher"] = clean(await get_db().vouchers.find_one({"kode": c["voucherCode"]}))
    return d


# ------------------------------------------------------------------ actions

class PatchIn(BaseModel):
    ringkasan: Optional[str] = None
    orderNo: Optional[str] = None
    customerName: Optional[str] = None
    customerPhone: Optional[str] = None
    notes: Optional[str] = None
    valid: Optional[str] = None
    tipe: Optional[str] = None
    rootCause: Optional[str] = None
    picDept: Optional[str] = None
    brand: Optional[str] = None
    subJenis: Optional[str] = None
    outletId: Optional[str] = None
    channel: Optional[str] = None
    costCenterFinal: Optional[str] = None
    photos: Optional[list[str]] = None
    nilaiKompensasi: Optional[int] = None
    produk: Optional[str] = None
    kodeProduksi: Optional[str] = None
    ekspedisi: Optional[str] = None
    noResi: Optional[str] = None
    qtyPesan: Optional[int] = None
    qtyDiterima: Optional[int] = None


@router.patch("/cases/{case_id}")
async def patch_case(case_id: str, body: PatchIn, u=Depends(current_user)):
    c = await get_case_or_404(case_id)
    check_area(u, c)
    data = body.model_dump(exclude_none=True)
    limited = {"rootCause", "notes", "costCenterFinal", "kodeProduksi"}
    if u["role"] in ("Manager Area", "Ops/QC"):
        if set(data) - limited:
            raise HTTPException(403, "Peran Anda hanya bisa mengisi root cause, catatan, cost center final, dan kode produksi.")
    elif u["role"] == "Viewer":
        raise HTTPException(403, "Viewer hanya bisa melihat.")
    if "subJenis" in data and u["role"] not in LEAD and data["subJenis"] != c.get("subJenis"):
        if c["status"] not in ("Open", "Responded"):
            raise HTTPException(403, "Sub jenis case yang sudah Resolved hanya bisa diubah CS Lead.")
    before = {k: c.get(k) for k in data}
    c.update(data)
    if "subJenis" in data and before.get("subJenis") != data["subJenis"]:
        c["level"] = None
        c["levelChangeReason"] = None
    if "outletId" in data:
        c["outletType"] = None
    c.pop("possibleDuplicateOf", None) if data.get("valid") else None
    await save_case(c)
    await add_event(case_id, "edited", u, {"fields": list(data)})
    return out_case(c, u)


def _check_fr_time(c, at):
    if as_utc(at) > now() + timedelta(minutes=2):
        raise HTTPException(400, "Waktu dibalas tidak boleh di masa depan.")
    if as_utc(at) < as_utc(c["waktuMasuk"]):
        raise HTTPException(400, "Waktu dibalas tidak boleh sebelum waktu masuk.")
    if c.get("waktuResolved") and as_utc(at) > as_utc(c["waktuResolved"]):
        raise HTTPException(400, "Waktu dibalas tidak boleh setelah waktu Resolved.")


def _mins(a, b):
    return round((as_utc(b) - as_utc(a)).total_seconds() / 60)


async def check_period_lock(c, u):
    """Periode yang sudah dikunci di meeting tidak bisa diubah waktunya (kecuali Admin)."""
    if u["role"] == "Admin":
        return
    d = c.get("tanggalMasuk") or wib_date(c["waktuMasuk"]).isoformat()
    m = await get_db().meetings.find_one({"locked": True, "periodStart": {"$lte": d}, "periodEnd": {"$gte": d}})
    if m:
        raise HTTPException(403, f"Periode {m['periodStart']} s/d {m['periodEnd']} sudah dikunci di meeting. "
                                 f"Waktu case ini hanya bisa diubah Admin.")


async def _open_request(c, u, value, reason, photo, kind):
    """Koreksi yang membuat FRT lebih cepat → menunggu persetujuan CRM Supervisor."""
    from .jobs import notify
    if not (reason or "").strip():
        raise HTTPException(400, "Tulis alasan koreksi.")
    if not photo:
        raise HTTPException(400, "Lampirkan screenshot chat yang menunjukkan jam pesan customer dan jam balasan Anda.")
    cur = c.get("waktuFirstResponse")
    before = _mins(c["waktuMasuk"], cur) if cur else None
    after = _mins(c["waktuMasuk"], value)
    tfrt = c.get("targetFrtMin") or 5
    req = {"id": new_id(), "kind": kind, "field": "waktuFirstResponse", "value": value, "current": cur,
           "reason": reason.strip(), "photo": photo, "by": u["name"], "byId": u["id"], "at": now(),
           "frtBefore": before, "frtAfter": after,
           "flipsSla": bool(before is not None and before > tfrt >= after)}
    c["timeRequest"] = req
    await add_event(c["caseId"], "time_requested", u, {"before": str(cur), "after": str(value), "reason": req["reason"],
                                                     "frtBefore": before, "frtAfter": after})
    await notify("time_request",
                 f"{u['name']} mengajukan jam dibalas {c['caseId']} dimajukan: FRT {before} → {after} mnt"
                 f"{' (SLA jadi lolos)' if req['flipsSla'] else ''}. Cek screenshot lalu setujui / tolak.",
                 c["caseId"], roles=LEAD, link="/integritas")
    return req


class RespondIn(BaseModel):
    at: Optional[str] = None
    reason: Optional[str] = None
    photo: Optional[str] = None


@router.post("/cases/{case_id}/respond")
async def respond(case_id: str, body: RespondIn | None = None, u=Depends(require(*WRITERS))):
    """Tandai sudah dibalas. `at` = jam balasan sebenarnya bila dicatat belakangan.
    CS: mundur ≤ frGraceMin langsung diterima; sampai frMaxBackMin perlu persetujuan + screenshot;
    lebih dari itu ditolak (lewat CRM Supervisor)."""
    c = await get_case_or_404(case_id)
    if c.get("waktuFirstResponse"):
        raise HTTPException(400, "Case ini sudah ditandai dibalas. Pakai 'Ubah waktu dibalas' untuk mengoreksi.")
    st = (await load_ctx())["settings"]
    rec = now()
    at = parse_iso(body.at) if body and body.at else rec
    _check_fr_time(c, at)
    back = (rec - as_utc(at)).total_seconds() / 60
    reason = ((body.reason if body else None) or "").strip()
    lead = u["role"] in LEAD
    if back > 2:
        await check_period_lock(c, u)
    if not lead and back > st["frMaxBackMin"]:
        raise HTTPException(400, f"Lebih dari {st['frMaxBackMin']} menit ke belakang. Tekan 'Sudah dibalas' sekarang, "
                                 f"lalu minta CRM Supervisor mengoreksi jamnya.")
    if back > 60 and not reason:
        raise HTTPException(400, "Waktu dibalas lebih dari 60 menit yang lalu: tulis alasannya.")
    c["frRecordedAt"] = rec
    c["frBy"] = u["name"]
    pending = (not lead) and back > st["frGraceMin"]
    if pending:
        c["waktuFirstResponse"] = rec      # sementara: jam pencatatan, sampai disetujui
        await _open_request(c, u, at, reason, body.photo if body else None, "respond")
    else:
        c["waktuFirstResponse"] = at
        if back > 2:
            c["frtManual"] = True
    if c["status"] == "Open":
        c["status"] = "Responded"
    await save_case(c)
    await add_event(case_id, "responded", u, {"backdatedMin": round(back) if back > 2 and not pending else 0,
                                               "reason": reason or None, "pending": pending})
    if back > 2 and not pending:
        await audit(u, f"respond-backdated {case_id}", None, str(at), reason or f"dicatat {round(back)} menit setelah membalas")
    return out_case(c, u)


class DecideIn(BaseModel):
    note: Optional[str] = None


@router.get("/time-requests")
async def time_requests(u=Depends(require(*LEAD))):
    ctx = await load_ctx()
    rows = [out_case(compute_case(c, ctx), u) async for c in
            get_db().cases.find({"timeRequest": {"$ne": None}, "timeRequest.id": {"$exists": True}})]
    return sorted(rows, key=lambda c: str(c["timeRequest"]["at"]))


@router.post("/cases/{case_id}/time-request/{decision}")
async def decide_time_request(case_id: str, decision: str, body: DecideIn | None = None, u=Depends(require(*LEAD))):
    if decision not in ("approve", "reject"):
        raise HTTPException(404, "Aksi tidak dikenal.")
    c = await get_case_or_404(case_id)
    r = c.get("timeRequest")
    if not r:
        raise HTTPException(404, "Tidak ada pengajuan yang menunggu.")
    if r["byId"] == u["id"]:
        raise HTTPException(403, "Pengajuan sendiri harus disetujui CRM Supervisor / Admin lain.")
    note = ((body.note if body else None) or "").strip()
    if decision == "reject" and not note:
        raise HTTPException(400, "Tulis alasan penolakan.")
    if decision == "approve":
        await check_period_lock(c, u)
        _check_fr_time(c, parse_iso(r["value"]))
        before = c.get("waktuFirstResponse")
        c["waktuFirstResponse"] = parse_iso(r["value"])
        c["frtManual"] = True
        await audit(u, f"approve-time {case_id}", str(before), str(r["value"]), f"{r['by']}: {r['reason']}")
    log = c.get("timeRequestLog") or []
    log.append({**r, "status": "approved" if decision == "approve" else "rejected", "decidedBy": u["name"],
                "decidedAt": now(), "note": note or None})
    c["timeRequestLog"] = log
    c["timeRequest"] = None
    await save_case(c)
    await add_event(case_id, "time_approved" if decision == "approve" else "time_rejected", u,
                    {"after": str(r["value"]), "reason": note or None, "by": r["by"]})
    return out_case(c, u)


class ResolveIn(BaseModel):
    rootCause: str
    picDept: Optional[str] = None
    kompensasiKey: str
    nilaiKompensasi: Optional[int] = None


@router.post("/cases/{case_id}/resolve")
async def resolve(case_id: str, body: ResolveIn, u=Depends(require(*WRITERS))):
    db = get_db()
    c = await get_case_or_404(case_id)
    ctx = await load_ctx()
    k = ctx["kompensasi"].get(body.kompensasiKey)
    if not k:
        raise HTTPException(400, "Bentuk kompensasi tidak dikenal.")
    if not body.rootCause.strip():
        raise HTTPException(400, "Root cause wajib diisi sebelum Resolved.")
    if not c.get("waktuFirstResponse"):
        c["waktuFirstResponse"] = c["frRecordedAt"] = now()
        c["frBy"] = u["name"]
    c.update(rootCause=body.rootCause.strip(), kompensasiKey=k["key"], kompensasiJenis=k["jenis"],
             kompensasiLabel=k["label"], waktuResolved=now(), status="Resolved",
             nilaiKompensasi=body.nilaiKompensasi if body.nilaiKompensasi is not None else k.get("nilai", 0))
    if body.picDept:
        c["picDept"] = body.picDept
    voucher, stock_empty = None, False
    if not c.get("voucherCode"):
        voucher, stock_empty = await issue_complimentary(k, c)
        if voucher:
            c["voucherCode"] = voucher["kode"]
            await add_event(case_id, "voucher_issued", u, {"kode": voucher["kode"]})
    await save_case(c, ctx)
    await add_event(case_id, "resolved", u, {"kompensasi": k["label"], "nilai": c["nilaiKompensasi"]})
    d = out_case(c, u)
    d["voucher"] = clean(voucher)
    d["voucherWarning"] = (f"Stok {k['voucherJenis']} habis: dipakai kode otomatis {voucher['kode']}. "
                           f"Tambah stok di menu Voucher.") if stock_empty else None
    return d


class CloseIn(BaseModel):
    followUpUlang: str
    costCenterFinal: Optional[str] = None


@router.post("/cases/{case_id}/close")
async def close(case_id: str, body: CloseIn, u=Depends(require(*WRITERS))):
    c = await get_case_or_404(case_id)
    if not c.get("waktuResolved"):
        raise HTTPException(400, "Selesaikan case dulu (Resolved) sebelum Closed.")
    if body.followUpUlang not in ("Y", "N"):
        raise HTTPException(400, "Pilih Y atau N untuk 'Customer follow-up ulang?'.")
    if body.costCenterFinal:
        c["costCenterFinal"] = body.costCenterFinal
    from .logic import needs_cost_final
    if needs_cost_final(c) and not c.get("costCenterFinal"):
        raise HTTPException(400, "Case Critical ini butuh cost center final (Factory atau Operasional) sebelum Closed.")
    c.update(followUpUlang=body.followUpUlang, waktuClosed=now(), status="Closed")
    await save_case(c)
    await add_event(case_id, "closed", u, {"followUpUlang": body.followUpUlang})
    return out_case(c, u)


@router.post("/cases/{case_id}/survey-sent")
async def survey_sent(case_id: str, body: dict | None = None, u=Depends(require(*WRITERS))):
    """Dicatat saat CS mengirim link survei CSAT (WhatsApp / salin), untuk menghitung tingkat respons survei."""
    c = await get_case_or_404(case_id)
    via = (body or {}).get("via") or "copy"
    c["surveySentAt"] = now()
    c["surveySentVia"] = via
    c["surveySentCount"] = (c.get("surveySentCount") or 0) + 1
    await save_case(c)
    await add_event(case_id, "survey_sent", u, {"via": via})
    return out_case(c, u)


@router.post("/cases/{case_id}/reopen")
async def reopen(case_id: str, body: dict, u=Depends(require(*WRITERS))):
    c = await get_case_or_404(case_id)
    if c["status"] not in ("Resolved", "Closed"):
        raise HTTPException(400, "Hanya case Resolved/Closed yang bisa dibuka ulang.")
    c["reopenCount"] = (c.get("reopenCount") or 0) + 1
    c["status"] = "Responded"
    c["waktuClosed"] = None
    c["waktuResolved"] = None
    await save_case(c)
    await add_event(case_id, "reopened", u, {"reason": body.get("reason")})
    return out_case(c, u)


@router.post("/cases/{case_id}/note")
async def note(case_id: str, body: dict, u=Depends(require("Admin", "CS Lead", "CS Agent", "Manager Area", "Ops/QC"))):
    check_area(u, await get_case_or_404(case_id))
    t = (body.get("text") or "").strip()
    if not t:
        raise HTTPException(400, "Catatan kosong.")
    await add_event(case_id, "note", u, {"text": t})
    return {"ok": True}


class CorrectIn(BaseModel):
    field: str
    value: Optional[str] = None
    reason: str
    photo: Optional[str] = None


@router.post("/cases/{case_id}/correct-time")
async def correct_time(case_id: str, body: CorrectIn, u=Depends(require(*WRITERS))):
    if body.field not in ("waktuMasuk", "waktuFirstResponse", "waktuResolved", "waktuClosed"):
        raise HTTPException(400, "Kolom waktu tidak dikenal.")
    lead = u["role"] in LEAD
    if body.field != "waktuFirstResponse" and not lead:
        raise HTTPException(403, "CS hanya bisa mengubah waktu dibalas. Waktu lain dikoreksi CRM Supervisor.")
    if not body.reason.strip():
        raise HTTPException(400, "Alasan koreksi wajib diisi.")
    c = await get_case_or_404(case_id)
    await check_period_lock(c, u)
    val = parse_iso(body.value) if body.value else None
    if val and val > now() + timedelta(minutes=2):
        raise HTTPException(400, "Waktu tidak boleh di masa depan.")
    trial = dict(c)
    trial[body.field] = val
    if body.field == "waktuMasuk" and not val:
        raise HTTPException(400, "Waktu Masuk tidak boleh kosong.")
    wm = as_utc(trial["waktuMasuk"])
    for f in ("waktuFirstResponse", "waktuResolved", "waktuClosed"):
        if trial.get(f) and as_utc(trial[f]) < wm:
            raise HTTPException(400, "Waktu tidak boleh lebih awal dari Waktu Masuk.")
    if trial.get("waktuClosed") and (not trial.get("waktuResolved") or as_utc(trial["waktuClosed"]) < as_utc(trial["waktuResolved"])):
        raise HTTPException(400, "Waktu Closed tidak boleh sebelum Waktu Resolved.")
    if body.field == "waktuFirstResponse":
        if val and trial.get("waktuResolved") and as_utc(val) > as_utc(trial["waktuResolved"]):
            raise HTTPException(400, "Waktu dibalas tidak boleh setelah waktu Resolved.")
        if not lead:
            st = (await load_ctx())["settings"]
            if not val:
                raise HTTPException(400, "Isi jam dibalas yang benar.")
            if not c.get("waktuFirstResponse"):
                raise HTTPException(400, "Case belum ditandai dibalas. Pakai tombol 'Dibalas jam lain…'.")
            if c["status"] in ("Resolved", "Closed"):
                raise HTTPException(403, "Case sudah Resolved: koreksi jam dibalas lewat CRM Supervisor.")
            if c.get("timeRequest"):
                raise HTTPException(400, "Masih ada pengajuan jam dibalas yang menunggu persetujuan.")
            if (c.get("frEditCount") or 0) >= 1:
                raise HTTPException(403, "Jam dibalas case ini sudah pernah diubah. Koreksi berikutnya lewat CRM Supervisor.")
            base = c.get("frRecordedAt") or c["waktuFirstResponse"]
            if now() - as_utc(base) > timedelta(hours=st["frEditHours"]):
                raise HTTPException(403, f"Lewat {st['frEditHours']} jam sejak dibalas: koreksi lewat CRM Supervisor.")
            c["frEditCount"] = (c.get("frEditCount") or 0) + 1
            if as_utc(val) < as_utc(c["waktuFirstResponse"]):
                # FRT jadi lebih cepat → perlu persetujuan + bukti
                if (as_utc(base) - as_utc(val)).total_seconds() / 60 > st["frMaxBackMin"]:
                    raise HTTPException(400, f"Lebih dari {st['frMaxBackMin']} menit sebelum jam pencatatan: minta CRM Supervisor.")
                await _open_request(c, u, val, body.reason, body.photo, "edit")
                await save_case(c)
                return out_case(c, u)
        c["frtManual"] = bool(val)
    before = c.get(body.field)
    c[body.field] = val
    if body.field == "waktuMasuk":
        c["hasTime"] = True
    st_ = "Open"
    if c.get("waktuFirstResponse"):
        st_ = "Responded"
    if c.get("waktuResolved"):
        st_ = "Resolved"
    if c.get("waktuClosed"):
        st_ = "Closed"
    c["status"] = st_
    await save_case(c)
    await audit(u, f"correct-time {case_id}.{body.field}", str(before), str(val), body.reason)
    await add_event(case_id, "time_corrected", u, {"field": body.field, "before": str(before), "after": str(val),
                                                  "reason": body.reason})
    return out_case(c, u)


class LevelIn(BaseModel):
    level: str
    reason: str


@router.post("/cases/{case_id}/change-level")
async def change_level(case_id: str, body: LevelIn, u=Depends(require(*WRITERS))):
    if body.level not in ("Minor", "Major", "Critical"):
        raise HTTPException(400, "Level tidak dikenal.")
    if not body.reason.strip():
        raise HTTPException(400, "Alasan perubahan level wajib diisi.")
    c = await get_case_or_404(case_id)
    before = c.get("level")
    c["level"] = body.level
    c["levelChangeReason"] = body.reason.strip() if body.level != c.get("levelStandard") else None
    await save_case(c)
    await audit(u, f"change-level {case_id}", before, body.level, body.reason)
    await add_event(case_id, "level_changed", u, {"from": before, "to": body.level, "reason": body.reason})
    return out_case(c, u)


@router.delete("/cases/{case_id}")
async def delete_case(case_id: str, u=Depends(require("Admin"))):
    c = await get_case_or_404(case_id)
    await get_db().cases.delete_one({"caseId": case_id})
    await audit(u, f"delete {case_id}", clean(c), None, "hapus case")
    return {"ok": True}


# ------------------------------------------------------------------ inbox

@router.get("/inbox")
async def inbox(u=Depends(current_user)):
    db = get_db()
    q = area_filter(u, {"status": {"$in": ["Open", "Responded", "Resolved"]}})
    rows = [c async for c in db.cases.find(q)]
    t = now()

    def urgency(c):
        crit = 0 if c.get("level") == "Critical" else 1
        if c["status"] == "Open":
            left = c.get("targetFrtMin", 5) - (t - as_utc(c["waktuMasuk"])).total_seconds() / 60
        else:
            tr = c.get("targetResolutionMin") or 4320
            left = tr - (t - as_utc(c["waktuMasuk"])).total_seconds() / 60
        return crit, left

    rows.sort(key=urgency)
    sec = {"open": [], "responded": [], "resolved": []}
    resolved_older = 0
    for c in rows:
        if c["status"] == "Resolved" and c.get("waktuResolved") and \
                (t - as_utc(c["waktuResolved"])).days > 14:
            resolved_older += 1  # menunggu konfirmasi > 14 hari: tidak ditampilkan di Inbox
            continue
        d = out_case(c, u)
        d["ageMin"] = round((t - as_utc(c["waktuMasuk"])).total_seconds() / 60)
        sec[c["status"].lower()].append(d)
    sec["resolvedOlder"] = resolved_older
    csat = [clean(x) async for x in db.csat.find({"triage": "belum", "needsTriage": True}).sort("timestamp", -1).limit(50)]
    reviews = [clean(x) async for x in db.reviews.find({"needsTriage": True, "linkedCaseId": None,
                                                        "triage": {"$ne": "tidak_perlu"}}).sort("tanggal", -1).limit(50)]
    if not can_see_phone(u):
        for x in csat:
            x["phone"] = mask_phone(x.get("phone"))
    pend = await db.cases.count_documents({"timeRequest.id": {"$exists": True}}) if u["role"] in LEAD else 0
    return {**sec, "csatDrafts": csat, "reviewDrafts": reviews, "timeRequests": pend}


# ------------------------------------------------------------------ dashboard

async def total_trx(frm: date, to: date):
    """Total transaksi periode dari input bulanan, prorata per hari."""
    db = get_db()
    total, have = 0.0, False
    d = frm
    cache = {}
    while d <= to:
        key = d.strftime("%Y-%m")
        if key not in cache:
            cache[key] = await db.monthly.find_one({"month": key})
        mi = cache[key]
        if mi and mi.get("totalTransaksi"):
            nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
            days = (nxt - d.replace(day=1)).days
            total += mi["totalTransaksi"] / days
            have = True
        d += timedelta(days=1)
    return round(total) if have else None


async def build_dashboard(frm: str, to: str, u=None, brand=None, area=None, line=None):
    ctx = await load_ctx()
    targets = ctx["targets"]
    cases = await cases_in_period(frm, to, u, brand, area, ctx, line)
    f, t = date.fromisoformat(frm), date.fromisoformat(to)
    trx = await total_trx(f, t)
    m, vol, table = compute_metrics(cases, targets, trx)
    scope = [] if line == "frozen" else outlet_scope(ctx, u, brand, area)
    co = await csat_summary(frm, to, scope)
    m["csatOutlet"], m["csatOutletN"] = co["puas"], co["rated"]
    span = (t - f).days + 1
    pf, pt = f - timedelta(days=span), f - timedelta(days=1)
    prev_cases = await cases_in_period(pf.isoformat(), pt.isoformat(), u, brand, area, ctx, line)
    pm, pvol, _ = compute_metrics(prev_cases, targets)
    pco = await csat_summary(pf.isoformat(), pt.isoformat(), scope)
    pm["csatOutlet"], pm["csatOutletN"] = pco["puas"], pco["rated"]
    komplain = [c for c in cases if c.get("tipe", "Komplain") == "Komplain"]
    levels = breakdown(komplain, "level")
    order = {"Minor": 0, "Major": 1, "Critical": 2}
    levels.sort(key=lambda r: order.get(r["name"], 3))
    for r in levels:
        r["pj"] = ctx["pj"].get(r["name"], "-")
    jenis = breakdown(komplain, "jenis")
    subj = breakdown(komplain, "subJenis", lambda n, cs: {
        "jenis": (ctx["subJenis"].get(n) or {}).get("jenis"), "levelStandard": (ctx["subJenis"].get(n) or {}).get("level")})
    channels = breakdown(cases, "channel")
    grp = {n: (c.get("group") or "Lainnya") for n, c in ctx["channels"].items()}
    for c in cases:
        c["_srcGroup"] = grp.get(c.get("channel"), "Lainnya")
    sourceGroups = breakdown(cases, "_srcGroup")
    for r in channels:
        r["group"] = grp.get(r["name"], "Lainnya")
    pic = breakdown(komplain, "picDept")
    outlets = breakdown(komplain, "outletName", lambda n, cs: {
        "topSub": max(((s, sum(1 for c in cs if c.get("subJenis") == s)) for s in {c.get("subJenis") for c in cs}),
                      key=lambda x: x[1])[0] if cs else None})[:10]
    komp = breakdown([c for c in komplain if c.get("kompensasiJenis")], "kompensasiJenis", lambda n, cs: {
        "luarStandard": any(c.get("kompensasiOutsideStandard") for c in cs)})
    hours = by_hour(cases)
    weeks = weekly(cases, f, t, targets)
    return {
        "period": {"from": frm, "to": to, "prevFrom": pf.isoformat(), "prevTo": pt.isoformat(), "totalTrx": trx},
        "metrics": m, "prev": pm, "volume": vol, "prevVolume": pvol, "table": table, "targets": targets,
        "levels": levels, "jenis": jenis, "subJenis": subj, "channels": channels, "sourceGroups": sourceGroups, "picDept": pic,
        "outlets": outlets, "kompensasi": komp, "hours": hours, "weeks": weeks,
        "members": by_member(cases, targets), "levelDetail": level_breakdown(komplain, f, t),
        "insights": insights(cases, m, vol, hours, subj, channels),
    }


@router.get("/dashboard")
async def dashboard(u=Depends(current_user), frm: str = Query(..., alias="from"), to: str = Query(...),
                    brand: Optional[str] = None, area: Optional[str] = None, line: Optional[str] = None):
    return await build_dashboard(frm, to, u, brand, area, line)


@router.get("/dashboard/frozen")
async def dashboard_frozen(u=Depends(current_user), frm: str = Query(..., alias="from"), to: str = Query(...)):
    """Komplain frozen food (toko Online Frozen di Shopee / TikTok)."""
    from collections import Counter, defaultdict
    ctx = await load_ctx()
    cases = await cases_in_period(frm, to, u, None, None, ctx, "frozen")
    f, t = date.fromisoformat(frm), date.fromisoformat(to)
    span = (t - f).days + 1
    pf, pt = f - timedelta(days=span), f - timedelta(days=1)
    prev = await cases_in_period(pf.isoformat(), pt.isoformat(), u, None, None, ctx, "frozen")
    targets = ctx["targets"]
    m, vol, table = compute_metrics(cases, targets)
    pm, pvol, _ = compute_metrics(prev, targets)
    komplain = [c for c in cases if c.get("tipe", "Komplain") == "Komplain"]
    need = [c for c in komplain if c.get("subJenis") in S.NEEDS_BATCH]
    with_batch = [c for c in need if c.get("kodeProduksi")]
    batches = defaultdict(list)
    for c in komplain:
        if c.get("kodeProduksi"):
            batches[c["kodeProduksi"].strip().upper()].append(c)
    repeat = sorted(([{"kode": k, "count": len(v), "cases": [x["caseId"] for x in v],
                       "subJenis": Counter(x.get("subJenis") for x in v).most_common(1)[0][0],
                       "produk": Counter(x.get("produk") for x in v if x.get("produk")).most_common(1)[0][0]
                       if any(x.get("produk") for x in v) else None}
                      for k, v in batches.items() if len(v) >= 2]), key=lambda r: -r["count"])
    short = [c for c in komplain if isinstance(c.get("qtyPesan"), int) and isinstance(c.get("qtyDiterima"), int)]
    pcs_kurang = sum(max(0, c["qtyPesan"] - c["qtyDiterima"]) for c in short)
    for c in komplain:
        c["_produk"] = c.get("produk") or "Belum diisi"
        c["_ekspedisi"] = c.get("ekspedisi") or "Belum diisi"
        c["_rc"] = c.get("rootCause") or "Belum diisi"
        c["_cc"] = c.get("costCenterFinal") or c.get("costCenter") or "-"
    open_rows = sorted([out_case(c, u) for c in komplain if c.get("status") not in ("Resolved", "Closed")],
                       key=lambda c: c.get("waktuMasuk") or "")
    sub = breakdown(komplain, "subJenis")
    stores = breakdown(komplain, "outletName")
    couriers = breakdown(komplain, "_ekspedisi")
    ins = {}
    if komplain:
        top = sub[0]
        ins["sub"] = f"{top['name']} menyumbang {top['count']} dari {len(komplain)} komplain frozen ({round(top['pct'] * 100)}%)."
        known = [r for r in couriers if r["name"] != "Belum diisi"]
        if known:
            ins["courier"] = f"Ekspedisi terbanyak dikomplain: {known[0]['name']} ({known[0]['count']} case)."
        if need:
            ins["batch"] = (f"Kode produksi terisi di {len(with_batch)} dari {len(need)} komplain produk "
                            f"({round(len(with_batch) / len(need) * 100)}%). Tanpa kode produksi, batch bermasalah tidak bisa ditelusuri.")
    return {
        "period": {"from": frm, "to": to, "prevFrom": pf.isoformat(), "prevTo": pt.isoformat()},
        "metrics": m, "prev": pm, "volume": vol, "prevVolume": pvol, "table": table, "targets": targets,
        "stores": stores, "subJenis": sub, "couriers": couriers, "products": breakdown(komplain, "_produk")[:10],
        "rootCauses": breakdown(komplain, "_rc")[:10], "picDept": breakdown(komplain, "picDept"),
        "costCenters": breakdown(komplain, "_cc"), "levels": breakdown(komplain, "level"),
        "batch": {"needed": len(need), "filled": len(with_batch),
                  "rate": round(len(with_batch) / len(need), 4) if need else None, "repeat": repeat},
        "qty": {"cases": len(short), "pcsKurang": pcs_kurang},
        "weeks": weekly(cases, f, t, targets), "open": open_rows, "insights": ins,
    }


BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def outlet_scope(ctx, u=None, brand=None, area=None):
    """Outlet yang ikut dihitung untuk CSAT outlet sesuai filter brand/area/peran. None = semua."""
    areas = None
    if u and u.get("role") == "Manager Area":
        areas = set(u.get("areas") or [])
    if area:
        areas = {area} if areas is None else (areas & {area})
    if areas is None and not brand:
        return None
    return [o["id"] for o in ctx["outlets"].values()
            if (areas is None or o.get("area") in areas) and (not brand or (o.get("brand") or "Cimol Bojot AA") == brand)]


def compare_periods(mode: str, n: int, end: date):
    """Periode kalender: minggu Senin–Minggu atau bulan penuh. Periode terakhir berisi `end`
    (berjalan / belum penuh). Urut lama → baru."""
    out = []
    if mode == "week":
        start = end - timedelta(days=end.weekday())
        for i in range(n - 1, -1, -1):
            s = start - timedelta(weeks=i)
            e = s + timedelta(days=6)
            iso = s.isocalendar()
            out.append({"key": f"{iso[0]}-W{iso[1]:02d}", "label": f"W{iso[1]} · {s.day} {BULAN[s.month - 1]}",
                        "from": s, "to": e})
    else:
        y, m = end.year, end.month
        for i in range(n - 1, -1, -1):
            yy, mm = y, m - i
            while mm <= 0:
                mm += 12
                yy -= 1
            s = date(yy, mm, 1)
            e = (date(yy + (mm == 12), mm % 12 + 1, 1) - timedelta(days=1))
            out.append({"key": f"{yy}-{mm:02d}", "label": f"{BULAN[mm - 1]} {yy}", "from": s, "to": e})
    for p in out:
        p["partial"] = p["to"] > end
        p["toData"] = min(p["to"], end)
    return out


@router.get("/dashboard/compare")
async def dashboard_compare(u=Depends(current_user), mode: str = "week", n: int = 8, end: Optional[str] = None,
                            brand: Optional[str] = None, area: Optional[str] = None, line: Optional[str] = None):
    return await build_compare(mode, n, end, u, brand, area, line)


async def build_compare(mode="week", n=8, end=None, u=None, brand=None, area=None, line=None):
    if mode not in ("week", "month"):
        raise HTTPException(400, "mode harus week atau month.")
    n = max(2, min(n, 26 if mode == "week" else 24))
    end_d = date.fromisoformat(end) if end else wib_date(now())
    periods = compare_periods(mode, n, end_d)
    ctx = await load_ctx()
    targets = ctx["targets"]
    allc = await cases_in_period(periods[0]["from"].isoformat(), end_d.isoformat(), u, brand, area, ctx, line)
    scope = [] if line == "frozen" else outlet_scope(ctx, u, brand, area)
    rows = []
    sub_counts = {}
    src_counts = {}
    grp = {name: (ch.get("group") or "Lainnya") for name, ch in ctx["channels"].items()}
    for p in periods:
        f, t = p["from"].isoformat(), p["toData"].isoformat()
        cs = [c for c in allc if c.get("tanggalMasuk") and f <= c["tanggalMasuk"] <= t]
        trx = await total_trx(p["from"], p["toData"])
        m, vol, _ = compute_metrics(cs, targets, trx)
        co = await csat_summary(f, t, scope)
        m["csatOutlet"], m["csatOutletN"] = co["puas"], co["rated"]
        komplain = [c for c in cs if c.get("tipe", "Komplain") == "Komplain"]
        for c in komplain:
            k = c.get("subJenis") or "Belum Terklasifikasi"
            sub_counts.setdefault(k, {})[p["key"]] = sub_counts.get(k, {}).get(p["key"], 0) + 1
            for sk in (grp.get(c.get("channel"), "Lainnya"), c.get("channel") or "-"):
                src_counts.setdefault(sk, {})[p["key"]] = src_counts.get(sk, {}).get(p["key"], 0) + 1
        lv = {lvl: sum(1 for c in komplain if c.get("level") == lvl) for lvl in ("Minor", "Major", "Critical")}
        rows.append({"key": p["key"], "label": p["label"], "from": f, "to": p["to"].isoformat(), "partial": p["partial"],
                     "days": (p["toData"] - p["from"]).days + 1, "metrics": m, "volume": vol, "levels": lv,
                     "totalTrx": trx})
    subs = sorted(sub_counts.items(), key=lambda kv: -sum(kv[1].values()))[:12]
    groups_order = list(dict.fromkeys(grp.values()))
    sources = []
    for g in groups_order:
        if g not in src_counts:
            continue
        sources.append({"name": g, "isGroup": True, "counts": [src_counts[g].get(r["key"], 0) for r in rows],
                        "total": sum(src_counts[g].values())})
        for chn, cg in grp.items():
            if cg == g and chn in src_counts:
                sources.append({"name": chn, "isGroup": False, "group": g,
                                "counts": [src_counts[chn].get(r["key"], 0) for r in rows],
                                "total": sum(src_counts[chn].values())})
    return {"mode": mode, "periods": rows, "targets": targets, "sources": sources,
            "subJenis": [{"name": k, "counts": [v.get(r["key"], 0) for r in rows], "total": sum(v.values())}
                         for k, v in subs]}


# ------------------------------------------------------------------ meeting

class MeetingIn(BaseModel):
    date: str
    periodStart: str
    periodEnd: str
    title: Optional[str] = None
    attendees: Optional[str] = None


@router.get("/meetings")
async def meetings(u=Depends(current_user)):
    return [clean(m) async for m in get_db().meetings.find({}, {"snapshot": 0}).sort("date", -1)]


@router.post("/meetings")
async def create_meeting(body: MeetingIn, u=Depends(require(*MEETING_EDITORS))):
    m = {"id": new_id(), **body.model_dump(), "insights": [], "decisions": [], "locked": False,
         "createdBy": u["name"], "createdAt": now()}
    m["title"] = m["title"] or f"Meeting Service Excellence {body.date}"
    await get_db().meetings.insert_one(m)
    return clean(m)


async def _top5(dash):
    db = get_db()
    rows = [r for r in dash["subJenis"] if r["count"]][:5]
    out = []
    for i, r in enumerate(rows):
        a = await db.voc_actions.find_one({"subJenis": r["name"], "status": {"$nin": ["Dropped"]}},
                                          sort=[("createdAt", -1)])
        out.append({"rank": i + 1, **r, "action": clean(a)})
    return out


@router.get("/meetings/{mid}")
async def get_meeting(mid: str, u=Depends(current_user)):
    db = get_db()
    m = await db.meetings.find_one({"id": mid})
    if not m:
        raise HTTPException(404, "Meeting tidak ditemukan.")
    if m.get("locked") and m.get("snapshot"):
        dash = m["snapshot"]
    else:
        dash = await build_dashboard(m["periodStart"], m["periodEnd"])
    if "integrity" not in dash:
        from .routes_integrity import build_integrity
        dash["integrity"] = await build_integrity(m["periodStart"], m["periodEnd"])
    if "komp" not in dash:
        from .routes_komp import build_komp
        dash["komp"] = await build_komp(m["periodStart"], m["periodEnd"])
    prev = await db.meetings.find_one({"date": {"$lt": m["date"]}, "locked": True}, sort=[("date", -1)])
    open_actions = [clean(a) async for a in db.voc_actions.find({"status": {"$in": ["Open", "On Progress"]}}).sort("deadline", 1)]
    reviews = await review_summary(m["periodStart"], m["periodEnd"])
    csat = await csat_summary(m["periodStart"], m["periodEnd"])
    return {"meeting": clean({k: v for k, v in m.items() if k != "snapshot"}), "dashboard": dash,
            "top5": await _top5(dash), "openActions": open_actions, "reviews": reviews, "csat": csat,
            "prevMetrics": (prev or {}).get("snapshot", {}).get("metrics") if prev else None,
            "prevMeetingDate": prev["date"] if prev else None}


@router.patch("/meetings/{mid}")
async def patch_meeting(mid: str, body: dict, u=Depends(require(*MEETING_EDITORS))):
    db = get_db()
    m = await db.meetings.find_one({"id": mid})
    if not m:
        raise HTTPException(404, "Meeting tidak ditemukan.")
    if m.get("locked"):
        raise HTTPException(400, "Meeting sudah dikunci.")
    allowed = {k: v for k, v in body.items() if k in ("insights", "decisions", "attendees", "title")}
    await db.meetings.update_one({"id": mid}, {"$set": allowed})
    return {"ok": True}


@router.post("/meetings/{mid}/suggest")
async def suggest(mid: str, u=Depends(current_user)):
    m = await get_db().meetings.find_one({"id": mid})
    if not m:
        raise HTTPException(404, "Meeting tidak ditemukan.")
    cases = await cases_in_period(m["periodStart"], m["periodEnd"])
    dash = await build_dashboard(m["periodStart"], m["periodEnd"])
    komplain = [c for c in cases if c.get("tipe", "Komplain") == "Komplain"]
    rows = suggest_insights(komplain, dash["metrics"], dash["volume"], dash["subJenis"], dash["levels"])
    agg = [r for r in dash["channels"] if r.get("group") == "Online Food Aggregator" and r["count"]]
    if agg:
        n = sum(r["count"] for r in agg)
        aggc = {r["name"] for r in agg}
        from collections import Counter
        top = Counter(c.get("subJenis") for c in komplain if c.get("channel") in aggc).most_common(2)
        rows.insert(min(2, len(rows)), {
            "whatHappened": f"{n} komplain dari Online Food Aggregator (" + ", ".join(f"{r['name']} {r['count']}" for r in agg)
                            + "); terbanyak " + ", ".join(f"{k} {v}" for k, v in top if k),
            "why": "", "businessImpact": "Rating outlet di platform dan peluang order online",
            "action": "", "pic": "Ops / Outlet + CRM / CS"})
    return rows[:5]


@router.post("/meetings/{mid}/lock")
async def lock(mid: str, u=Depends(require(*LEAD))):
    db = get_db()
    m = await db.meetings.find_one({"id": mid})
    if not m:
        raise HTTPException(404, "Meeting tidak ditemukan.")
    dash = await build_dashboard(m["periodStart"], m["periodEnd"])
    dash["compare"] = {"week": await build_compare("week", 6, m["periodEnd"]),
                       "month": await build_compare("month", 6, m["periodEnd"])}
    from .routes_integrity import build_integrity
    dash["integrity"] = await build_integrity(m["periodStart"], m["periodEnd"])
    from .routes_komp import build_komp
    dash["komp"] = await build_komp(m["periodStart"], m["periodEnd"])
    await db.meetings.update_one({"id": mid}, {"$set": {"locked": True, "snapshot": dash, "lockedAt": now(),
                                                        "lockedBy": u["name"]}})
    return {"ok": True}


@router.delete("/meetings/{mid}")
async def del_meeting(mid: str, u=Depends(require(*LEAD))):
    await get_db().meetings.delete_one({"id": mid})
    return {"ok": True}


class ActionIn(BaseModel):
    subJenis: Optional[str] = None
    topic: Optional[str] = None
    rootCause: Optional[str] = ""
    action: str
    picDept: Optional[str] = ""
    picName: Optional[str] = ""
    status: str = "Open"
    deadline: Optional[str] = None
    meetingId: Optional[str] = None


@router.get("/voc-actions")
async def actions(u=Depends(current_user), status: Optional[str] = None):
    q = {"status": {"$in": status.split("|")}} if status else {}
    return [clean(a) async for a in get_db().voc_actions.find(q).sort("createdAt", -1)]


@router.post("/voc-actions")
async def add_action(body: ActionIn, u=Depends(require(*MEETING_EDITORS, "Manager Area", "Ops/QC"))):
    a = {"id": new_id(), **body.model_dump(), "updates": [], "createdAt": now(), "createdBy": u["name"]}
    await get_db().voc_actions.insert_one(a)
    return clean(a)


@router.patch("/voc-actions/{aid}")
async def patch_action(aid: str, body: dict, u=Depends(require(*MEETING_EDITORS, "Manager Area", "Ops/QC"))):
    db = get_db()
    a = await db.voc_actions.find_one({"id": aid})
    if not a:
        raise HTTPException(404, "Action tidak ditemukan.")
    upd = {k: v for k, v in body.items() if k in ("rootCause", "action", "picDept", "picName", "status", "deadline",
                                                  "subJenis", "topic")}
    push = {}
    if body.get("update"):
        push = {"$push": {"updates": {"date": now(), "text": body["update"], "by": u["name"]}}}
    if upd.get("status") and upd["status"] != a.get("status"):
        push.setdefault("$push", {"updates": {"date": now(), "text": f"Status → {upd['status']}", "by": u["name"]}})
    await db.voc_actions.update_one({"id": aid}, {"$set": upd, **push})
    return clean(await db.voc_actions.find_one({"id": aid}))


# ------------------------------------------------------------------ summaries for meeting

async def review_summary(frm, to):
    rows = [r async for r in get_db().reviews.find({"tanggalDate": {"$gte": frm, "$lte": to}})]
    from collections import Counter
    return {"count": len(rows),
            "byPlatform": dict(Counter(r.get("platform") for r in rows)),
            "bySubJenis": Counter(r.get("subJenis") for r in rows).most_common(6),
            "byLevel": dict(Counter(r.get("level") or "Belum Diatur" for r in rows)),
            "belumDiproses": sum(1 for r in rows if (r.get("statusTindakLanjut") or "Belum diproses") == "Belum diproses"),
            "critical": sum(1 for r in rows if r.get("level") == "Critical")}


async def csat_summary(frm, to, outlet_ids=None):
    q = {"tanggal": {"$gte": frm, "$lte": to}}
    if outlet_ids is not None:
        q["outletId"] = {"$in": list(outlet_ids)}
    rows = [r async for r in get_db().csat.find(q)]
    rated = [r for r in rows if isinstance(r.get("ratingKeseluruhan"), int)]
    return {"count": len(rows), "rated": len(rated),
            "puas": round(sum(1 for r in rated if r["ratingKeseluruhan"] >= 4) / len(rated), 4) if rated else None,
            "beliLagi": round(sum(1 for r in rows if r.get("beliLagi") == "Ya") / len(rows), 4) if rows else None,
            "avg": round(sum(r["ratingKeseluruhan"] for r in rated) / len(rated), 2) if rated else None}
