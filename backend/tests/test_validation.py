"""Uji validasi data, rumus, peran, dan alur sampingan (jalankan: cd backend && pytest -q)."""
import os
from datetime import datetime, timedelta, timezone

os.environ.update(USE_MOCK_DB="true", DISABLE_JOBS="true", DATA_DIR="/tmp/sd-test-val", DEFAULT_ADMIN_PIN="111111",
                  METRICS_API_KEY="kunci-uji")

import pytest
from fastapi.testclient import TestClient

from app import core
from app.main import app

WIB = timezone(timedelta(hours=7))


def wib_iso(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=WIB).isoformat()


@pytest.fixture(scope="module")
def ctx():
    core.Config.METRICS_API_KEY = "kunci-uji"
    with TestClient(app) as c:
        # database bersih untuk modul ini
        import asyncio
        db = core.get_db()

        async def wipe():
            for coll in ("cases", "events", "csat", "reviews", "vouchers", "meetings", "voc_actions", "monthly"):
                await db[coll].delete_many({})
            await db.users.delete_many({"name": {"$ne": "Admin"}})
            from app.auth import hash_pin
            await db.users.update_one({"name": "Admin"}, {"$set": {"pinHash": hash_pin("111111"), "failedPins": 0,
                                                                    "lockedUntil": None}})
        asyncio.get_event_loop().run_until_complete(wipe()) if False else None
        H = login(c, "Admin", "111111")
        for n, r, a in (("Lead", "CS Lead", []), ("Agen", "CS Agent", []), ("MA Bekasi", "Manager Area", ["Bekasi"]),
                        ("QC", "Ops/QC", []), ("Lihat", "Viewer", [])):
            c.post("/api/users", json={"name": n, "role": r, "pin": "123123", "areas": a}, headers=H)
        m = c.get("/api/masters", headers=H).json()
        o = {x["name"]: x["id"] for x in m["outlets"]}
        yield c, H, o


def login(c, n, p):
    r = c.post("/api/auth/login", json={"name": n, "pin": p})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def mk(c, H, o, **kw):
    body = {"channel": "WhatsApp", "outletId": o["Jagakarsa"], "subJenis": "Hospitality", "ringkasan": "uji", "force": True}
    body.update(kw)
    return c.post("/api/cases", json=body, headers=H)


def test_input_validation(ctx):
    c, H, o = ctx
    assert mk(c, H, o, ringkasan="   ").status_code == 400
    assert mk(c, H, o, outletId="tidak-ada").status_code == 400
    assert mk(c, H, o, subJenis="Ngawur").status_code == 400
    assert mk(c, H, o, channel="Fax").status_code == 400
    fut = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    assert mk(c, H, o, waktuMasuk=fut).status_code == 400
    r = c.post("/api/cases", json={"channel": "WhatsApp"}, headers=H)
    assert r.status_code == 422 and "Data belum lengkap" in r.json()["detail"]
    # duplikat nomor pesanan
    assert mk(c, H, o, orderNo="F-1", force=False, subJenis="Wrong Item").status_code == 200
    r = mk(c, H, o, orderNo="F-1", force=False, subJenis="Payment Issue", outletId=o["Lokasari"])
    assert r.status_code == 409


def test_status_flow_rules(ctx):
    c, H, o = ctx
    k = mk(c, H, o, subJenis="Speed of Service").json()
    cid = k["caseId"]
    assert c.post(f"/api/cases/{cid}/reopen", json={}, headers=H).status_code == 400
    assert c.post(f"/api/cases/{cid}/respond", headers=H).status_code == 200
    assert c.post(f"/api/cases/{cid}/respond", headers=H).status_code == 400
    assert c.post(f"/api/cases/{cid}/resolve", json={"rootCause": "x", "kompensasiKey": "ngawur"}, headers=H).status_code == 400
    assert c.post(f"/api/cases/{cid}/resolve", json={"rootCause": " ", "kompensasiKey": "min-apologize"}, headers=H).status_code == 400
    # stok voucher kosong → tetap resolved + peringatan
    r = c.post(f"/api/cases/{cid}/resolve", json={"rootCause": "Antrean", "kompensasiKey": "min-v5"}, headers=H).json()
    assert r["status"] == "Resolved" and "habis" in (r["voucherWarning"] or "")
    assert c.post(f"/api/cases/{cid}/close", json={"followUpUlang": "X"}, headers=H).status_code == 400
    r = c.post(f"/api/cases/{cid}/close", json={"followUpUlang": "Y"}, headers=H).json()
    assert r["fcr"] is False
    r = c.post(f"/api/cases/{cid}/reopen", json={"reason": "customer komplain lagi"}, headers=H).json()
    assert r["status"] == "Responded" and r["reopenCount"] == 1 and r["waktuResolved"] is None


def test_kompensasi_level_rules(ctx):
    c, H, o = ctx
    # voucher Major dipakai di case Minor → di luar standard
    k = mk(c, H, o, subJenis="Hospitality").json()
    r = c.post(f"/api/cases/{k['caseId']}/resolve", json={"rootCause": "x", "kompensasiKey": "maj-replacement"}, headers=H).json()
    assert r["kompensasiOutsideStandard"] is True
    # level Belum Diatur (Delivery) → pilihan level apa pun ditandai di luar standard, Refund juga
    k = mk(c, H, o, subJenis="Delivery / Ekspedisi", outletId=o["Online Frozen (Shopee)"], channel="Marketplace Chat").json()
    assert k["level"] is None and k["penanggungJawab"] == "CS Lead" and k["targetResolutionMin"] is None
    r = c.post(f"/api/cases/{k['caseId']}/resolve", json={"rootCause": "x", "kompensasiKey": "maj-v10"}, headers=H).json()
    assert r["kompensasiOutsideStandard"] is True and r["resolutionSlaOk"] is None


def test_cost_center_rules(ctx):
    c, H, o = ctx
    fz = o["Online Frozen (Shopee)"]
    cases = {
        ("Kesalahan Kemasan", fz): "Factory", ("Kesalahan Kemasan", o["Jagakarsa"]): "Operasional",
        ("Cacat Produksi", fz): "Team Frozen", ("Wrong Item", o["Jagakarsa"]): "Operasional",
        ("Undercooked", o["Jagakarsa"]): "Factory/Operasional (cek root cause)",
        ("Penurunan Mutu (tidak dapat dikonsumsi)", o["Jagakarsa"]): "Operasional",
        ("Penurunan Mutu (tidak dapat dikonsumsi)", fz): "Factory/Operasional (cek root cause)",
        ("Perkelahian / Adu Argumen", o["Jagakarsa"]): "Operasional",
    }
    for (sj, oid), cc in cases.items():
        r = mk(c, H, o, subJenis=sj, outletId=oid).json()
        assert r["costCenter"] == cc, (sj, r["costCenter"])


def test_time_rules_and_formulas(ctx):
    c, H, o = ctx
    # case masuk 06:30 WIB (= 23:30 UTC hari sebelumnya) → tanggal WIB yang dipakai
    k = mk(c, H, o, subJenis="Jam Operasional", waktuMasuk=wib_iso(2026, 11, 3, 6, 30)).json()
    assert k["tanggalMasuk"] == "2026-11-03"
    cid = k["caseId"]
    # koreksi waktu: Closed sebelum Resolved ditolak, waktu masuk tidak boleh kosong
    assert c.post(f"/api/cases/{cid}/correct-time", json={"field": "waktuMasuk", "value": None, "reason": "x"}, headers=H).status_code == 400
    assert c.post(f"/api/cases/{cid}/correct-time", json={"field": "waktuClosed", "value": wib_iso(2026, 11, 3, 9, 0), "reason": "x"}, headers=H).status_code == 400
    assert c.post(f"/api/cases/{cid}/correct-time", json={"field": "waktuResolved", "value": wib_iso(2026, 11, 3, 9, 0), "reason": ""}, headers=H).status_code == 400
    # FRT jam kerja: masuk 21:50, balas besok 08:10, jam CS 08–22 → 10 + 10 = 20 menit
    k = mk(c, H, o, subJenis="Speed of Service", waktuMasuk=wib_iso(2026, 11, 4, 21, 50)).json()
    r = c.post(f"/api/cases/{k['caseId']}/correct-time", json={"field": "waktuFirstResponse", "value": wib_iso(2026, 11, 5, 8, 10), "reason": "chat malam"}, headers=H).json()
    assert r["frtMin"] == 620 and r["frtWorkMin"] == 20 and r["slaResponseOk"] is False and r["status"] == "Responded"
    # resolved lewat tengah malam → bukan same day
    r = c.post(f"/api/cases/{k['caseId']}/correct-time", json={"field": "waktuResolved", "value": wib_iso(2026, 11, 5, 8, 30), "reason": "x"}, headers=H).json()
    assert r["sameDay"] is False and r["resolutionMin"] == 640 and r["resolutionSlaOk"] is True  # Minor 1440
    # Critical: target FRT = min(channel, 30); Email 240 → 30
    r = mk(c, H, o, subJenis="Kontaminasi", channel="Email").json()
    assert r["targetFrtMin"] == 30 and r["targetResolutionMin"] == 4320


def test_open_case_same_day_not_stale(ctx):
    c, H, o = ctx
    y = datetime.now(WIB) - timedelta(days=1)
    k = mk(c, H, o, subJenis="Hospitality", outletId=o["Kosambi"], waktuMasuk=y.replace(hour=12, minute=0).isoformat()).json()
    d = y.date().isoformat()
    dash = c.get("/api/dashboard", params={"from": d, "to": d}, headers=H).json()
    row = next(x for x in dash["outlets"] if x["name"] == "Kosambi")
    assert row["sameDay"] == 0  # case kemarin yang belum resolved dihitung tidak same-day


def test_level_change_and_subjenis_edit(ctx):
    c, H, o = ctx
    A = login(c, "Agen", "123123")
    k = mk(c, A, o, subJenis="Hospitality").json()
    assert c.post(f"/api/cases/{k['caseId']}/change-level", json={"level": "Major", "reason": ""}, headers=A).status_code == 400
    r = c.post(f"/api/cases/{k['caseId']}/change-level", json={"level": "Major", "reason": "customer marah"}, headers=A).json()
    assert r["level"] == "Major" and r["penanggungJawab"] == "Manager Area"
    assert not any("Level" in i or "Penanggung" in i for i in r["dataIssues"]), r["dataIssues"]
    c.post(f"/api/cases/{k['caseId']}/resolve", json={"rootCause": "x", "kompensasiKey": "maj-apologize"}, headers=A)
    assert c.patch(f"/api/cases/{k['caseId']}", json={"subJenis": "Undercooked"}, headers=A).status_code == 403
    L = login(c, "Lead", "123123")
    r = c.patch(f"/api/cases/{k['caseId']}", json={"subJenis": "Undercooked"}, headers=L).json()
    assert r["level"] == "Critical" and r["levelStandard"] == "Critical" and r["jenis"] == "Product Quality"


def test_roles(ctx):
    c, H, o = ctx
    MA = login(c, "MA Bekasi", "123123")
    QC = login(c, "QC", "123123")
    V = login(c, "Lihat", "123123")
    jkt = mk(c, H, o, subJenis="Hospitality", customerPhone="081234567890").json()["caseId"]
    bks = mk(c, H, o, subJenis="Hospitality", outletId=o["Perumnas 3 Bekasi"]).json()["caseId"]
    assert c.patch(f"/api/cases/{jkt}", json={"rootCause": "x"}, headers=MA).status_code == 403
    assert c.post(f"/api/cases/{jkt}/note", json={"text": "x"}, headers=MA).status_code == 403
    assert c.patch(f"/api/cases/{bks}", json={"rootCause": "Sikap crew"}, headers=MA).status_code == 200
    assert c.patch(f"/api/cases/{bks}", json={"ringkasan": "ubah"}, headers=MA).status_code == 403
    assert all(x["area"] == "Bekasi" for x in c.get("/api/cases", headers=MA).json())
    assert mk(c, QC, o).status_code == 403
    assert c.post(f"/api/cases/{jkt}/respond", headers=V).status_code == 403
    assert c.get(f"/api/cases/{jkt}", headers=V).json()["customerPhone"] == "0812****890"
    assert c.get("/api/masters/x", headers=V).status_code in (404, 405)
    assert c.put("/api/masters/targets", json={"value": {}}, headers=V).status_code == 403
    assert c.post("/api/users", json={"name": "X", "role": "Admin", "pin": "123456"}, headers=login(c, "Lead", "123123")).status_code == 403
    assert c.post("/api/users", json={"name": "X", "role": "CS Agent", "pin": "12ab"}, headers=H).status_code == 400


def test_csat_public_and_survey(ctx):
    c, H, o = ctx
    base = {"outlet": "Cabang Jagakarsa", "puasPelayanan": 5, "rasa": 5, "kebersihan": 5, "beliLagi": "Ya", "ratingKeseluruhan": 5}
    assert c.post("/api/public/csat", json={**base, "rasa": 0}).status_code == 400
    assert c.post("/api/public/csat", json={**base, "beliLagi": "Mungkin"}).status_code == 400
    r = c.post("/api/public/csat", json={**base, "outlet": "warung antah berantah", "ratingKeseluruhan": 1})
    assert r.status_code == 200
    draft = next(x for x in c.get("/api/inbox", headers=H).json()["csatDrafts"] if x["outletText"] == "warung antah berantah")
    assert draft["outletId"] is None
    assert c.post(f"/api/csat/{draft['id']}/triage", json={"action": "jadi_case"}, headers=H).status_code == 400
    c.post(f"/api/csat/{draft['id']}/match", json={"outletId": o["Saparua"], "addAlias": True}, headers=H)
    assert c.post(f"/api/csat/{draft['id']}/triage", json={"action": "jadi_case", "subJenis": "Hospitality"}, headers=H).status_code == 200
    c.post("/api/public/csat", json={**base, "outlet": "warung antah berantah"})
    rows = c.get("/api/csat", headers=H).json()
    assert rows[0]["outletName"] == "Saparua"  # alias dipakai
    for _ in range(10):
        c.post("/api/public/csat", json=base)
    assert c.post("/api/public/csat", json=base).status_code == 429
    # survei per case
    k = mk(c, H, o).json()
    tok = c.get(f"/api/cases/{k['caseId']}", headers=H).json()["surveyUrl"].rsplit("/", 1)[1]
    assert c.get("/api/public/survey/salah").status_code == 404
    assert c.post(f"/api/public/survey/{tok}", json={"rating": 6}).status_code == 400
    assert c.post(f"/api/public/survey/{tok}", json={"rating": 4}).status_code == 200
    assert c.get(f"/api/cases/{k['caseId']}", headers=H).json()["puas"] is True


def test_reviews_vouchers_masters_trx(ctx):
    c, H, o = ctx
    r = c.post("/api/reviews", json={"platform": "GoFood", "tanggal": wib_iso(2026, 11, 10, 12, 0), "outletId": o["Jagakarsa"],
                                     "rating": 1, "review": "mentah", "subJenis": "Undercooked"}, headers=H).json()
    assert r["level"] == "Critical" and r["needsTriage"]
    a = c.post(f"/api/reviews/{r['id']}/to-case", headers=H).json()
    b = c.post(f"/api/reviews/{r['id']}/to-case", headers=H).json()
    assert a["caseId"] == b["caseId"]  # idempoten
    assert c.post("/api/vouchers/import", json={"jenis": "Voucher Diskon 5K", "codes": "A1\nA2\nA1"}, headers=H).json() == {"added": 2, "skipped": 1}
    assert c.post("/api/vouchers/A1/status", json={"status": "Ngawur"}, headers=H).status_code == 400
    assert c.put("/api/masters/subJenis", json={"value": []}, headers=H).status_code == 400
    assert c.put("/api/masters/kompensasi", json={"value": [{"key": "x"}, {"key": "x"}]}, headers=H).status_code == 400
    # Refund dijadikan standard → case refund tidak lagi 'di luar standard'
    k = mk(c, H, o, subJenis="Wrong Item").json()
    c.post(f"/api/cases/{k['caseId']}/resolve", json={"rootCause": "x", "kompensasiKey": "all-refund"}, headers=H)
    komp = c.get("/api/masters", headers=H).json()["kompensasi"]
    for x in komp:
        if x["key"] == "all-refund":
            x["standard"] = True
    c.put("/api/masters/kompensasi", json={"value": komp}, headers=H)
    assert c.get(f"/api/cases/{k['caseId']}", headers=H).json()["kompensasiOutsideStandard"] is False
    # komplain per 1.000 trx diprorata: Nov 30.000 trx → 1–10 Nov = 10.000
    c.put("/api/monthly/2026-11", json={"totalTransaksi": 30000}, headers=H)
    d = c.get("/api/dashboard", params={"from": "2026-11-01", "to": "2026-11-10"}, headers=H).json()
    assert d["period"]["totalTrx"] == 10000
    assert d["volume"]["per1000"] == round(d["volume"]["komplain"] / 10000 * 1000, 2)
    # target diubah → status ikut berubah
    t = c.get("/api/masters", headers=H).json()["targets"]
    t["compSuccess"]["target"] = 0.0
    c.put("/api/masters/targets", json={"value": t}, headers=H)
    d = c.get("/api/dashboard", params={"from": "2026-11-01", "to": "2026-11-10"}, headers=H).json()
    assert next(r for r in d["table"] if r["key"] == "compSuccess")["status"] == "On Track"
    # public metrics
    assert c.get("/api/public-metrics/service", params={"from": "2026-11-01", "to": "2026-11-10"},
                 headers={"X-API-Key": "kunci-uji"}).status_code == 200


def test_meeting_lock(ctx):
    c, H, o = ctx
    m = c.post("/api/meetings", json={"date": "2026-11-11", "periodStart": "2026-11-01", "periodEnd": "2026-11-10"}, headers=H).json()
    s = c.post(f"/api/meetings/{m['id']}/suggest", headers=H).json()
    assert 1 <= len(s) <= 5 and all("whatHappened" in x for x in s)
    assert c.patch(f"/api/meetings/{m['id']}", json={"insights": s}, headers=H).status_code == 200
    c.post(f"/api/meetings/{m['id']}/lock", headers=H)
    assert c.patch(f"/api/meetings/{m['id']}", json={"insights": []}, headers=H).status_code == 400
    g = c.get(f"/api/meetings/{m['id']}", headers=H).json()
    assert g["meeting"]["locked"] and g["dashboard"]["volume"]["komplain"] >= 1
    cmp = g["dashboard"]["compare"]
    assert len(cmp["week"]["periods"]) == 6 and len(cmp["month"]["periods"]) == 6
    assert cmp["week"]["periods"][-1]["from"] <= "2026-11-10" <= cmp["week"]["periods"][-1]["to"]


def test_compare_week_month(ctx):
    c, H, o = ctx
    r = c.get("/api/dashboard/compare", params={"mode": "month", "n": 3, "end": "2026-11-10"}, headers=H).json()
    assert [p["key"] for p in r["periods"]] == ["2026-09", "2026-10", "2026-11"]
    assert r["periods"][-1]["partial"] and r["periods"][-1]["days"] == 10
    nov = c.get("/api/dashboard", params={"from": "2026-11-01", "to": "2026-11-10"}, headers=H).json()
    assert r["periods"][-1]["volume"]["komplain"] == nov["volume"]["komplain"]
    w = c.get("/api/dashboard/compare", params={"mode": "week", "n": 4, "end": "2026-11-11"}, headers=H).json()
    p = w["periods"]
    assert p[-1]["from"] == "2026-11-09" and p[-1]["to"] == "2026-11-15" and p[0]["from"] == "2026-10-19"
    assert all(len(s["counts"]) == 4 for s in w["subJenis"])
    assert c.get("/api/dashboard/compare", params={"mode": "year"}, headers=H).status_code == 400


def test_food_aggregator_channels(ctx):
    c, H, o = ctx
    import asyncio
    from app import services
    db = core.get_db()
    # simulasi database lama: channel GoFood belum ada & target WhatsApp sudah diubah CS Lead
    async def legacy():
        await db.channels.delete_many({"name": {"$in": ["GoFood", "GrabFood", "ShopeeFood"]}})
        await db.channels.update_one({"name": "WhatsApp"}, {"$set": {"targetFrt": 3}, "$unset": {"group": ""}})
        await services.seed_if_empty()
    asyncio.run(legacy())
    ch = {x["name"]: x for x in c.get("/api/masters", headers=H).json()["channels"]}
    assert {"GoFood", "GrabFood", "ShopeeFood"} <= set(ch)
    assert ch["WhatsApp"]["targetFrt"] == 3 and ch["WhatsApp"]["group"] == "Chat & Sosmed"
    assert ch["GoFood"]["orderRequired"] and ch["GoFood"]["group"] == "Online Food Aggregator"
    k = mk(c, H, o, channel="ShopeeFood", subJenis="Missing Item", orderNo="SF-0001").json()
    assert k["channel"] == "ShopeeFood" and k["targetFrtMin"] == 15
    r = c.post("/api/reviews", json={"platform": "ShopeeFood", "tanggal": wib_iso(2026, 11, 10, 12, 0), "outletId": o["Jagakarsa"],
                                     "rating": 2, "review": "kurang", "subJenis": "Missing Item"}, headers=H).json()
    assert r["id"].startswith("SF-")
    assert c.post("/api/reviews", json={"platform": "Tokopedia", "tanggal": wib_iso(2026, 11, 10, 12, 0), "outletId": o["Jagakarsa"],
                                        "rating": 2, "review": "x", "subJenis": "Missing Item"}, headers=H).status_code == 400
    today = datetime.now(WIB).date().isoformat()
    d = c.get("/api/dashboard", params={"from": today, "to": today}, headers=H).json()
    g = {x["name"]: x["count"] for x in d["sourceGroups"]}
    assert g.get("Online Food Aggregator", 0) >= 1
    assert next(x for x in d["channels"] if x["name"] == "ShopeeFood")["group"] == "Online Food Aggregator"
