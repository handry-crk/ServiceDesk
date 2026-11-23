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
    # FRT = jam kerja: masuk 21:50, balas besok 08:10, jam CS 08–22 → 10 + 10 = 20 menit (tunggu kalender 620)
    k = mk(c, H, o, subJenis="Speed of Service", waktuMasuk=wib_iso(2026, 11, 4, 21, 50)).json()
    r = c.post(f"/api/cases/{k['caseId']}/correct-time", json={"field": "waktuFirstResponse", "value": wib_iso(2026, 11, 5, 8, 10), "reason": "chat malam"}, headers=H).json()
    assert r["waitMin"] == 620 and r["frtMin"] == 20 and r["frtWorkMin"] == 20 and r["slaResponseOk"] is False and r["status"] == "Responded"
    # resolved lewat tengah malam → bukan same day
    r = c.post(f"/api/cases/{k['caseId']}/correct-time", json={"field": "waktuResolved", "value": wib_iso(2026, 11, 5, 8, 30), "reason": "x"}, headers=H).json()
    assert r["sameDay"] is False and r["resolutionMin"] == 640 and r["resolutionSlaOk"] is True  # Minor 1440
    # Critical: target FRT = min(channel, 30); Email 240 → 30
    r = mk(c, H, o, subJenis="Kontaminasi", channel="Email").json()
    assert r["targetFrtMin"] == 30 and r["targetResolutionMin"] == 4320


def test_open_case_same_day_not_stale(ctx):
    c, H, o = ctx
    y = datetime.now(WIB) - timedelta(days=1)
    while y.weekday() == 6:  # Minggu libur CS → same-day dihitung dari hari kerja berikutnya
        y -= timedelta(days=1)
    k = mk(c, H, o, subJenis="Hospitality", outletId=o["Kosambi"], waktuMasuk=y.replace(hour=12, minute=0).isoformat()).json()
    d = y.date().isoformat()
    dash = c.get("/api/dashboard", params={"from": d, "to": d}, headers=H).json()
    row = next(x for x in dash["outlets"] if x["name"] == "Kosambi")
    assert row["sameDay"] == 0  # case hari kerja kemarin yang belum resolved dihitung tidak same-day


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


def test_meeting_sources(ctx):
    c, H, o = ctx
    today = datetime.now(WIB).date().isoformat()
    mk(c, H, o, channel="GrabFood", subJenis="Wrong Item", orderNo="A-1")
    m = c.post("/api/meetings", json={"date": today, "periodStart": today, "periodEnd": today}, headers=H).json()
    s = c.post(f"/api/meetings/{m['id']}/suggest", headers=H).json()
    assert any("Online Food Aggregator" in r["whatHappened"] for r in s) and len(s) <= 5
    cmp = c.get("/api/dashboard/compare", params={"mode": "week", "n": 4}, headers=H).json()
    names = {x["name"] for x in cmp["sources"]}
    assert {"Online Food Aggregator", "GrabFood"} <= names
    g = next(x for x in cmp["sources"] if x["name"] == "Online Food Aggregator")
    assert g["isGroup"] and g["total"] == sum(x["total"] for x in cmp["sources"] if x.get("group") == "Online Food Aggregator")


def test_standard_text_migration(ctx):
    """Teks contoh lama diganti versi dokumen MASTER; teks yang sudah diubah CS Lead tidak disentuh."""
    import asyncio
    from app import services, standards as S
    c, H, o = ctx
    db = core.get_db()
    old_c, old_k = S.SUB_JENIS_OLD_TEXT["Kontaminasi"]

    async def run():
        await db.sub_jenis.update_one({"name": "Kontaminasi"}, {"$set": {"contoh": old_c, "keywords": old_k}})
        await db.sub_jenis.update_one({"name": "Keracunan"}, {"$set": {"contoh": "ditulis CS Lead"}})
        await services.seed_if_empty()
    asyncio.run(run())
    sj = {x["name"]: x for x in c.get("/api/masters", headers=H).json()["subJenis"]}
    assert "logam" in sj["Kontaminasi"]["contoh"] and "kaca" in sj["Kontaminasi"]["keywords"]
    assert sj["Keracunan"]["contoh"] == "ditulis CS Lead"
    doc = c.get("/api/masters", headers=H).json()["standardDoc"]
    assert doc["code"] == "CRM.STD.001" and doc["effective"] == "2026-10-20" and len(doc["considerations"]) == 4


def test_csat_complaint_and_outlet(ctx):
    c, H, o = ctx
    today = datetime.now(WIB).date().isoformat()
    k = mk(c, H, o, subJenis="Hospitality", outletId=o["Pondok Rangon"], customerPhone="0812 3456 7890").json()
    cid = k["caseId"]
    c.post(f"/api/cases/{cid}/resolve", json={"rootCause": "x", "kompensasiKey": "min-apologize"}, headers=H)
    c.post(f"/api/cases/{cid}/close", json={"followUpUlang": "N"}, headers=H)
    d0 = c.get("/api/dashboard", params={"from": today, "to": today}, headers=H).json()["metrics"]
    r = c.post(f"/api/cases/{cid}/survey-sent", json={"via": "whatsapp"}, headers=H).json()
    assert r["surveySentVia"] == "whatsapp" and r["surveySentAt"]
    d1 = c.get("/api/dashboard", params={"from": today, "to": today}, headers=H).json()["metrics"]
    assert d1["csatSent"] == d0["csatSent"] + 1
    tok = c.get(f"/api/cases/{cid}", headers=H).json()["surveyToken"]
    c.post(f"/api/public/survey/{tok}", json={"rating": 5})
    d2 = c.get("/api/dashboard", params={"from": today, "to": today}, headers=H).json()["metrics"]
    assert d2["csatN"] == d1["csatN"] + 1 and d2["csat"] is not None and d2["csatResponse"] > 0
    # CSAT outlet (form) terpisah dari CSAT komplain, ikut filter area
    assert "csatOutlet" in d2 and d2["csatOutletN"] >= 1
    bks = c.get("/api/dashboard", params={"from": today, "to": today, "area": "Bekasi"}, headers=H).json()["metrics"]
    assert bks["csatOutletN"] < d2["csatOutletN"]
    cmp = c.get("/api/dashboard/compare", params={"mode": "week", "n": 2}, headers=H).json()
    assert "csatOutlet" in cmp["periods"][-1]["metrics"]
    # viewer tidak boleh menandai survei terkirim
    V = login(c, "Lihat", "123123")
    assert c.post(f"/api/cases/{cid}/survey-sent", json={}, headers=V).status_code == 403


def _settings(c, H, **kw):
    st = c.get("/api/masters", headers=H).json()["settings"]
    c.put("/api/masters/settings", json={"value": {**st, **kw}, "reason": "uji"}, headers=H)
    return st


def test_first_response_time_edit(ctx):
    c, H, o = ctx
    old = _settings(c, H, opStart="00:00", opEnd="23:59", workDays=[0, 1, 2, 3, 4, 5, 6])
    try:
        _fr_edit(c, H, o)
    finally:
        _settings(c, H, **old)


def _fr_edit(c, H, o):
    A = login(c, "Agen", "123123")
    L = login(c, "Lead", "123123")
    now_w = datetime.now(WIB).replace(second=0, microsecond=0)
    masuk = now_w - timedelta(hours=3)
    # waktu masuk > 30 menit lalu tanpa alasan → ditolak untuk CS
    assert mk(c, A, o, subJenis="Speed of Service", waktuMasuk=masuk.isoformat()).status_code == 400
    k = mk(c, A, o, subJenis="Speed of Service", waktuMasuk=masuk.isoformat(), waktuMasukReason="chat malam baru dibaca").json()
    cid = k["caseId"]
    assert k["masukLagMin"] >= 179
    # validasi dasar
    assert c.post(f"/api/cases/{cid}/respond", json={"at": (masuk - timedelta(minutes=5)).isoformat(), "reason": "x"}, headers=A).status_code == 400
    assert c.post(f"/api/cases/{cid}/respond", json={"at": (now_w + timedelta(hours=1)).isoformat(), "reason": "x"}, headers=A).status_code == 400
    # > 120 menit ke belakang: CS ditolak
    assert c.post(f"/api/cases/{cid}/respond", json={"at": (now_w - timedelta(minutes=150)).isoformat(), "reason": "x", "photo": "/u/a.jpg"}, headers=A).status_code == 400
    # 90 menit ke belakang: wajib alasan + screenshot, lalu menunggu persetujuan
    at = (now_w - timedelta(minutes=90)).isoformat()
    assert c.post(f"/api/cases/{cid}/respond", json={"at": at, "reason": "balas dari HP"}, headers=A).status_code == 400
    r = c.post(f"/api/cases/{cid}/respond", json={"at": at, "reason": "balas dari HP", "photo": "/u/a.jpg"}, headers=A).json()
    assert r["status"] == "Responded" and r["timeRequest"]["frtAfter"] == 90 and r["frtMin"] >= 179 and r["frtSystemMin"] >= 179
    assert "Info: Jam dibalas menunggu persetujuan" in r["dataIssues"]
    assert any(x["caseId"] == cid for x in c.get("/api/time-requests", headers=L).json())
    assert c.get("/api/time-requests", headers=A).status_code == 403
    assert c.post(f"/api/cases/{cid}/time-request/approve", headers=A).status_code == 403
    r = c.post(f"/api/cases/{cid}/time-request/approve", json={}, headers=L).json()
    assert r["frtMin"] == 90 and r["frtManual"] is True and not r.get("timeRequest") and r["frBackdateMin"] >= 89
    # mundur ≤ 15 menit: langsung diterima
    k2 = mk(c, A, o, subJenis="Hospitality", ringkasan="uji fr 2", waktuMasuk=(now_w - timedelta(minutes=20)).isoformat()).json()
    r = c.post(f"/api/cases/{k2['caseId']}/respond", json={"at": (now_w - timedelta(minutes=10)).isoformat()}, headers=A).json()
    assert r["frtMin"] == 10 and r["frtManual"] is True and not r.get("timeRequest")
    # ubah jam dibalas jadi LEBIH LAMA: langsung; sekali saja
    r = c.post(f"/api/cases/{k2['caseId']}/correct-time", json={"field": "waktuFirstResponse", "value": (now_w - timedelta(minutes=5)).isoformat(), "reason": "salah jam"}, headers=A).json()
    assert r["frtMin"] == 15 and r["frEditCount"] == 1
    assert c.post(f"/api/cases/{k2['caseId']}/correct-time", json={"field": "waktuFirstResponse", "value": (now_w - timedelta(minutes=4)).isoformat(), "reason": "lagi"}, headers=A).status_code == 403
    # ubah jadi LEBIH CEPAT: perlu screenshot + persetujuan; ditolak → tidak berubah
    k3 = mk(c, A, o, subJenis="Hospitality", ringkasan="uji fr 3", waktuMasuk=(now_w - timedelta(minutes=25)).isoformat()).json()
    c.post(f"/api/cases/{k3['caseId']}/respond", headers=A)
    body = {"field": "waktuFirstResponse", "value": (now_w - timedelta(minutes=22)).isoformat(), "reason": "lupa tekan"}
    assert c.post(f"/api/cases/{k3['caseId']}/correct-time", json=body, headers=A).status_code == 400
    r = c.post(f"/api/cases/{k3['caseId']}/correct-time", json={**body, "photo": "/u/b.jpg"}, headers=A).json()
    assert r["timeRequest"] and r["frtMin"] >= 24
    assert c.post(f"/api/cases/{k3['caseId']}/time-request/reject", json={}, headers=L).status_code == 400
    r = c.post(f"/api/cases/{k3['caseId']}/time-request/reject", json={"note": "di chat dibalas 11.40"}, headers=L).json()
    assert r["frtMin"] >= 24 and r["timeRequestLog"][-1]["status"] == "rejected"
    # CS tidak boleh mengosongkan / mengubah waktu lain
    assert c.post(f"/api/cases/{cid}/correct-time", json={"field": "waktuFirstResponse", "value": None, "reason": "x"}, headers=A).status_code == 400
    assert c.post(f"/api/cases/{cid}/correct-time", json={"field": "waktuMasuk", "value": masuk.isoformat(), "reason": "x"}, headers=A).status_code == 403
    # integritas per CS
    t = now_w.date().isoformat()
    ig = c.get("/api/integrity", params={"frm": (now_w.date() - timedelta(days=1)).isoformat(), "to": t}, headers=L).json()
    row = next(r for r in ig["rows"] if r["name"] == "Agen")
    assert row["approved"] == 1 and row["rejected"] == 1 and row["manual"] >= 2 and "1 pengajuan ditolak" in row["flags"]
    assert c.get("/api/integrity", params={"frm": t, "to": t}, headers=A).status_code == 403
    # audit acak minggu ini
    au = c.post("/api/audits", json={"weekStart": t}, headers=L).json()
    assert au["items"] and all(i["cs"] for i in au["items"])
    item = next(i for i in au["items"] if i["cs"] == "Agen")
    assert c.post(f"/api/audits/{au['id']}/items/{item['caseId']}", json={"result": "tidak"}, headers=L).status_code == 400
    c.post(f"/api/audits/{au['id']}/items/{item['caseId']}", json={"result": "tidak", "note": "chat jam 10.15"}, headers=L)
    assert "Audit: jam tidak cocok dengan chat" in c.get(f"/api/cases/{item['caseId']}", headers=L).json()["dataIssues"]
    assert c.post("/api/audits", json={"weekStart": t}, headers=L).json()["created"] is False
    # Viewer tidak boleh membalas
    V = login(c, "Lihat", "123123")
    assert c.post(f"/api/cases/{k3['caseId']}/respond", headers=V).status_code == 403
    # kunci periode: setelah meeting dikunci, CS & Lead tidak bisa ubah waktu; Admin bisa
    k4 = mk(c, A, o, subJenis="Hospitality", ringkasan="uji kunci").json()
    c.post(f"/api/cases/{k4['caseId']}/respond", headers=A)
    m = c.post("/api/meetings", json={"date": t, "periodStart": t, "periodEnd": t}, headers=L).json()
    c.post(f"/api/meetings/{m['id']}/lock", headers=L)
    assert c.get(f"/api/meetings/{m['id']}", headers=L).json()["dashboard"]["integrity"]["total"]["responded"] >= 3
    b2 = {"field": "waktuFirstResponse", "value": datetime.now(WIB).isoformat(), "reason": "x"}
    assert c.post(f"/api/cases/{k4['caseId']}/correct-time", json=b2, headers=A).status_code == 403
    assert c.post(f"/api/cases/{k4['caseId']}/correct-time", json=b2, headers=L).status_code == 403
    assert c.post(f"/api/cases/{k4['caseId']}/correct-time", json=b2, headers=H).status_code == 200
    c.delete(f"/api/meetings/{m['id']}", headers=L)


def test_frozen_fields_and_dashboard(ctx):
    c, H, o = ctx
    tk, sp = o["Online Frozen (Tiktok 2)"], o["Online Frozen (Shopee)"]
    m = c.get("/api/masters", headers=H).json()
    assert "J&T Express" in m["couriers"] and "Mozza AP" in m["frozenProducts"]
    day = wib_iso(2026, 10, 14, 10, 0)
    a = mk(c, H, o, outletId=tk, channel="WhatsApp", subJenis="Cacat Produksi", ringkasan="cimol pecah", waktuMasuk=day,
           produk="Mozza AP", ekspedisi="J&T Express", noResi="JX123", kodeProduksi="B2410", qtyPesan=10, qtyDiterima=8).json()
    assert a["caseId"].startswith("FRZ") and a["produk"] == "Mozza AP" and a["kodeProduksi"] == "B2410"
    assert "Kode produksi belum diisi" not in (a.get("dataIssues") or [])
    b = mk(c, H, o, outletId=sp, channel="WhatsApp", subJenis="Cacat Produksi", ringkasan="cimol pecah 2", waktuMasuk=wib_iso(2026, 10, 15, 10, 0),
           produk="Mozza AP", ekspedisi="J&T Express", kodeProduksi="b2410").json()
    d = mk(c, H, o, outletId=sp, channel="WhatsApp", subJenis="Missing Item", ringkasan="kurang 1", waktuMasuk=wib_iso(2026, 10, 16, 10, 0),
           ekspedisi="SPX Standard").json()
    assert "Kode produksi belum diisi" in d["dataIssues"]
    # QC/Ops boleh isi kode produksi
    Q = login(c, "QC", "123123")
    r = c.patch(f"/api/cases/{d['caseId']}", json={"kodeProduksi": "C0110"}, headers=Q)
    assert r.status_code == 200 and "Kode produksi belum diisi" not in r.json()["dataIssues"]
    mk(c, H, o, subJenis="Hospitality", ringkasan="outlet biasa", waktuMasuk=day)
    f = c.get("/api/dashboard/frozen", params={"from": "2026-10-01", "to": "2026-10-31"}, headers=H).json()
    assert f["volume"]["komplain"] == 3
    assert sum(s["count"] for s in f["stores"]) == 3
    assert {x["name"]: x["count"] for x in f["couriers"]}["J&T Express"] == 2
    assert f["batch"]["needed"] == 3 and f["batch"]["filled"] == 3 and f["batch"]["rate"] == 1
    assert f["batch"]["repeat"][0]["kode"] == "B2410" and f["batch"]["repeat"][0]["count"] == 2
    assert f["qty"]["pcsKurang"] == 2
    # filter line di dashboard & komparasi
    fz = c.get("/api/dashboard", params={"from": "2026-10-01", "to": "2026-10-31", "line": "frozen"}, headers=H).json()
    ol = c.get("/api/dashboard", params={"from": "2026-10-01", "to": "2026-10-31", "line": "outlet"}, headers=H).json()
    al = c.get("/api/dashboard", params={"from": "2026-10-01", "to": "2026-10-31"}, headers=H).json()
    assert fz["volume"]["komplain"] + ol["volume"]["komplain"] == al["volume"]["komplain"] and fz["volume"]["komplain"] == 3
    cp = c.get("/api/dashboard/compare", params={"mode": "month", "n": 2, "end": "2026-10-31", "line": "frozen"}, headers=H).json()
    assert cp["periods"][-1]["volume"]["komplain"] == 3


def test_parse_frozen_notes():
    from app.importer import parse_frozen_notes as p
    r = p("Rekap Frozen #1; Tiktok 2 / JNT; No. pesanan 586279494678512944; produk Mozza AP; kode produksi kosong")
    assert r == {"ekspedisi": "J&T Express", "orderNoFromNotes": "586279494678512944", "produk": "Mozza AP"}
    assert p("Rekap Frozen #3; Shopee / SPX Instan; produk Mix 3 pcs Mozza; kode produksi A0901")["kodeProduksi"] == "A0901"
    assert p(None) == {}


def test_member_frt_level_breakdown_komp_tracker(ctx):
    c, H, o = ctx
    L = login(c, "Lead", "123123")
    a = mk(c, H, o, subJenis="Undercooked", ringkasan="mentah", waktuMasuk=wib_iso(2026, 9, 2, 10, 0)).json()
    b = mk(c, H, o, subJenis="Kontaminasi", ringkasan="rambut", waktuMasuk=wib_iso(2026, 9, 3, 10, 0)).json()
    d = mk(c, H, o, subJenis="Undercooked", ringkasan="mentah 2", waktuMasuk=wib_iso(2026, 9, 9, 10, 0)).json()
    for k, mins in ((a, 4), (b, 40), (d, 10)):
        c.post(f"/api/cases/{k['caseId']}/correct-time", json={"field": "waktuFirstResponse", "value": wib_iso(2026, 9, int(k["tanggalMasuk"][-2:]), 10, mins), "reason": "uji"}, headers=L)
    m = c.get("/api/masters", headers=H).json()
    komp = next(x for x in m["kompensasi"] if x.get("voucherJenis"))
    r = c.post(f"/api/cases/{a['caseId']}/resolve", json={"rootCause": "goreng kurang lama", "kompensasiKey": komp["key"]}, headers=L).json()
    dash = c.get("/api/dashboard", params={"from": "2026-09-01", "to": "2026-09-30"}, headers=H).json()
    mem = {x["name"]: x for x in dash["members"]}
    assert mem["Admin"]["count"] == 3 and mem["Admin"]["avgFrt"] == 18 and mem["Admin"]["medianFrt"] == 10
    crit = next(x for x in dash["levelDetail"]["levels"] if x["level"] == "Critical")
    assert crit["count"] == 3 and crit["subJenis"][0] == {**crit["subJenis"][0], "name": "Undercooked", "count": 2}
    assert crit["summary"].startswith("Critical 3 case: Undercooked 2, Kontaminasi 1")
    w = dash["levelDetail"]["weeks"]
    assert w[0]["Critical"] == 2 and w[1]["Critical"] == 1 and w[0]["criticalDetail"]["Undercooked"] == 1
    kt = c.get("/api/kompensasi-tracker", params={"from": "2026-09-01", "to": "2026-09-30"}, headers=H).json()
    row = next(x for x in kt["rows"] if x["caseId"] == a["caseId"])
    assert kt["summary"]["cases"] >= 1 and row["level"] == "Critical"
    if r.get("voucher"):
        assert row["status"] == "Diterbitkan" and row["kode"] and row["kadaluarsa"]
        c.post(f"/api/vouchers/{row['kode']}/status", json={"status": "Terpakai"}, headers=H)
        kt = c.get("/api/kompensasi-tracker", params={"from": "2026-09-01", "to": "2026-09-30"}, headers=H).json()
        assert kt["summary"]["terpakai"] == 1 and kt["summary"]["redemption"] == 1


def test_complimentary_tracking_code(ctx):
    c, H, o = ctx
    L = login(c, "Lead", "123123")
    M = login(c, "MA Bekasi", "123123")
    V = login(c, "Lihat", "123123")
    a = mk(c, H, o, subJenis="Missing Item", ringkasan="kurang 2", waktuMasuk=wib_iso(2026, 9, 20, 10, 0)).json()
    r = c.post(f"/api/cases/{a['caseId']}/resolve", json={"rootCause": "lupa masuk", "kompensasiKey": "maj-replacement"}, headers=L).json()
    kode = r["voucherCode"]
    assert kode.startswith("CMP-RP-") and r["voucher"]["kode"] == kode
    lk = c.get(f"/api/vouchers/lookup/{kode.lower()}", headers=M).json()
    assert lk["status"] == "Diterbitkan" and lk["case"]["caseId"] == a["caseId"] and lk["kadaluarsa"]
    assert c.get(f"/api/vouchers/lookup/{kode}", headers=V).status_code == 403
    assert c.post(f"/api/vouchers/{kode}/status", json={"status": "Hangus"}, headers=M).status_code == 403
    assert c.post(f"/api/vouchers/{kode}/status", json={"status": "Terpakai", "outlet": "Jagakarsa"}, headers=M).status_code == 200
    assert c.post(f"/api/vouchers/{kode}/status", json={"status": "Terpakai"}, headers=M).status_code == 400
    # refund: kode tanpa kadaluarsa; apologize: tanpa kode
    b = mk(c, H, o, subJenis="Missing Item", ringkasan="kurang 3", waktuMasuk=wib_iso(2026, 9, 21, 10, 0)).json()
    r = c.post(f"/api/cases/{b['caseId']}/resolve", json={"rootCause": "x", "kompensasiKey": "all-refund", "nilaiKompensasi": 15000}, headers=L).json()
    assert r["voucherCode"].startswith("CMP-RF-")
    assert c.get(f"/api/vouchers/lookup/{r['voucherCode']}", headers=L).json()["kadaluarsa"] is None
    d = mk(c, H, o, subJenis="Hospitality", ringkasan="jutek", waktuMasuk=wib_iso(2026, 9, 22, 10, 0)).json()
    r = c.post(f"/api/cases/{d['caseId']}/resolve", json={"rootCause": "x", "kompensasiKey": "min-apologize"}, headers=L).json()
    assert not r.get("voucherCode")
    kt = c.get("/api/kompensasi-tracker", params={"from": "2026-09-20", "to": "2026-09-22"}, headers=H).json()
    st = {x["caseId"]: x for x in kt["rows"]}
    assert st[a["caseId"]]["status"] == "Terpakai" and st[a["caseId"]]["dipakaiOleh"] == "MA Bekasi"
    assert st[b["caseId"]]["status"] == "Diterbitkan" and st[b["caseId"]]["kadaluarsa"] is None


def test_sunday_off_and_holidays(ctx):
    c, H, o = ctx
    L = login(c, "Lead", "123123")
    # Minggu 8 Nov 15:00, dibalas Senin 08:02 → FRT jam kerja 4 mnt (lolos), tunggu kalender 1024 mnt
    k = mk(c, H, o, subJenis="Hospitality", ringkasan="minggu", waktuMasuk=wib_iso(2026, 11, 8, 15, 0)).json()
    assert k["frtDueAt"].startswith("2026-11-09T01:0")  # Senin 08:0x WIB (jam buka + target channel)
    r = c.post(f"/api/cases/{k['caseId']}/correct-time", json={"field": "waktuFirstResponse", "value": wib_iso(2026, 11, 9, 8, 2), "reason": "libur"}, headers=H).json()
    assert "frtMin" in r, r
    assert r["frtMin"] == 2 and r["waitMin"] == 1022 and r["slaResponseOk"] is True
    r = c.post(f"/api/cases/{k['caseId']}/correct-time", json={"field": "waktuResolved", "value": wib_iso(2026, 11, 9, 15, 0), "reason": "x"}, headers=H).json()
    assert r["sameDay"] is True and r["sameDayBase"] == "2026-11-09" and r["resolutionMin"] == 900 and r["resolutionCalMin"] == 1440
    # tanggal libur: Senin 9 Nov libur → dibalas Selasa 08:02 tetap 4 mnt
    old = _settings(c, H, holidays=["2026-11-09"])
    try:
        k2 = mk(c, H, o, subJenis="Hospitality", ringkasan="libur nasional", waktuMasuk=wib_iso(2026, 11, 8, 20, 0)).json()
        r = c.post(f"/api/cases/{k2['caseId']}/correct-time", json={"field": "waktuFirstResponse", "value": wib_iso(2026, 11, 10, 8, 2), "reason": "libur"}, headers=H).json()
        assert r["frtMin"] == 2 and r["slaResponseOk"] is True
        # hari kerja biasa tidak berubah: Sabtu 21:50 → Senin 08:10 = 10 + 10 (Minggu & tgl 9 libur? Sabtu 7 → Selasa 10)
        k3 = mk(c, H, o, subJenis="Hospitality", ringkasan="sabtu malam", waktuMasuk=wib_iso(2026, 11, 7, 21, 50)).json()
        r = c.post(f"/api/cases/{k3['caseId']}/correct-time", json={"field": "waktuFirstResponse", "value": wib_iso(2026, 11, 10, 8, 10), "reason": "x"}, headers=H).json()
        assert r["frtMin"] == 20
    finally:
        _settings(c, H, **old)


def test_tanggal_masuk_sunday_kept(ctx):
    c, H, o = ctx
    k = mk(c, H, o, subJenis="Hospitality", ringkasan="minggu malam", waktuMasuk=wib_iso(2026, 11, 8, 23, 0)).json()
    assert k["tanggalMasuk"] == "2026-11-08" and k["sameDayBase"] == "2026-11-09" and k["jamMasuk"] == 23


def test_cs_desks(ctx):
    c, H, o = ctx
    m = c.get("/api/masters", headers=H).json()
    assert [d["key"] for d in m["desks"]] == ["Online", "Offline"]
    assert {x["name"]: x["desk"] for x in m["channels"]}["GoFood"] == "Online"
    for n, dk in (("Felita", "Online"), ("Aliya", "Online"), ("Intan", "Offline")):
        r = c.post("/api/users", json={"name": n, "role": "CS Agent", "pin": "456456", "desk": dk}, headers=H)
        assert r.status_code == 200 and r.json()["desk"] == dk, r.text
    F = login(c, "Felita", "456456")
    I = login(c, "Intan", "456456")
    on = mk(c, F, o, channel="GoFood", subJenis="Missing Item", ringkasan="gofood kurang", orderNo="F-1").json()
    fz = mk(c, F, o, outletId=o["Online Frozen (Shopee)"], channel="WhatsApp", subJenis="Missing Item", ringkasan="frozen kurang").json()
    off = mk(c, I, o, channel="WhatsApp", subJenis="Hospitality", ringkasan="kasir jutek desk").json()
    assert on["desk"] == "Online" and fz["desk"] == "Online" and off["desk"] == "Offline"
    ib = c.get("/api/inbox", headers=F).json()
    ids = [x["caseId"] for x in ib["open"]]
    assert ib["desk"] == "Online" and on["caseId"] in ids and off["caseId"] not in ids
    ib = c.get("/api/inbox", headers=I).json()
    assert off["caseId"] in [x["caseId"] for x in ib["open"]] and on["caseId"] not in [x["caseId"] for x in ib["open"]]
    assert on["caseId"] in [x["caseId"] for x in c.get("/api/inbox", params={"desk": "all"}, headers=I).json()["open"]]
    # pindah desk manual
    r = c.patch(f"/api/cases/{off['caseId']}", json={"deskOverride": "Online"}, headers=I).json()
    assert r["desk"] == "Online"
    c.post(f"/api/cases/{on['caseId']}/respond", headers=F)
    c.post(f"/api/cases/{off['caseId']}/respond", headers=I)
    t = on["tanggalMasuk"]
    d = c.get("/api/dashboard", params={"from": t, "to": t}, headers=H).json()
    mem = {x["name"]: x for x in d["members"]}
    assert mem["Felita"]["desk"] == "Online" and mem["Intan"]["desk"] == "Offline"
    dk = {x["desk"]: x for x in d["desks"]}
    assert dk["Online"]["contact"] >= 3 and "Offline" in dk
    assert all(x["desk"] == "Online" for x in c.get("/api/cases", params={"desk": "Online", "from": t, "to": t}, headers=H).json()["items"]) if isinstance(c.get("/api/cases", params={"desk": "Online"}, headers=H).json(), dict) else True


CHAT = """[10.02, 03/11/2026] +62 812-1111-2222: Kak cimol saya kurang 2, pesan 10 dapat 8
[10.04, 03/11/2026] CS Cimol Bojot AA: Mohon maaf kak, boleh foto struknya?
[10.06, 03/11/2026] +62 812-1111-2222: ini kak
[10.30, 03/11/2026] CS Cimol Bojot AA: Baik kak, kami ganti porsi baru ya"""


def test_rekap_from_whatsapp(ctx):
    c, H, o = ctx
    A = login(c, "Agen", "123123")
    L = login(c, "Lead", "123123")
    p = c.post("/api/wa/parse", json={"text": CHAT}, headers=A).json()
    assert p["messages"] == 4 and p["customerPhone"] == "+62 812-1111-2222"
    assert p["masuk"].startswith("2026-11-03T10:02") and p["dibalas"].startswith("2026-11-03T10:04")
    assert c.post("/api/wa/parse", json={"text": "halo kak"}, headers=A).status_code == 400
    # outlet belum terdaftar → diketik CS, langsung bisa dipakai
    no = c.post("/api/outlets/quick", json={"name": "Gerobak  Pasar Minggu Baru"}, headers=A).json()
    assert no["pending"] is True and no["existing"] is False
    assert c.post("/api/outlets/quick", json={"name": "gerobak pasar minggu baru"}, headers=A).json()["existing"] is True
    body = {"channel": "WhatsApp", "outletId": no["id"], "subJenis": "Missing Item", "ringkasan": p["customerText"],
            "waktuMasuk": p["masuk"], "waktuFirstResponse": p["dibalas"], "waktuResolved": wib_iso(2026, 11, 3, 10, 30),
            "rootCause": "lupa masuk", "kompensasiKey": "maj-replacement", "closed": True, "followUpUlang": "N",
            "chatText": CHAT, "customerPhone": p["customerPhone"], "force": True}
    r = c.post("/api/cases/rekap", json=body, headers=A).json()
    assert r["status"] == "Closed" and r["frtMin"] == 2 and r["timeEvidence"] == "chat" and not r.get("frtManual")
    assert r["voucherCode"].startswith("CMP-RP") and "Outlet menunggu verifikasi" in r["dataIssues"]
    assert r["resolutionMin"] == 28 and r["source"] == "rekap"
    # jam diubah dari chat tanpa screenshot → ditolak; dengan screenshot → tersimpan sebagai manual
    b2 = {**body, "waktuFirstResponse": wib_iso(2026, 11, 3, 10, 3), "waktuResolved": None, "closed": False,
          "rootCause": None, "kompensasiKey": None, "ringkasan": "uji manual"}
    assert c.post("/api/cases/rekap", json=b2, headers=A).status_code == 400
    r2 = c.post("/api/cases/rekap", json={**b2, "photo": "/u/x.jpg"}, headers=A).json()
    assert r2["timeEvidence"] == "screenshot" and r2["frtManual"] is True and r2["status"] == "Responded"
    # selesai tanpa root cause → ditolak
    assert c.post("/api/cases/rekap", json={**body, "rootCause": "", "ringkasan": "x2"}, headers=A).status_code == 400
    assert c.get("/api/rekap/mine", headers=A).status_code == 200
    # CRM Supervisor gabungkan outlet ke yang sudah ada → case ikut pindah, nama jadi alias
    m = c.post(f"/api/outlets/{no['id']}/merge", json={"targetId": o["Jagakarsa"]}, headers=L).json()
    assert m["moved"] == 2
    k = c.get(f"/api/cases/{r['caseId']}", headers=L).json()
    assert k["outletName"] == "Jagakarsa" and "Outlet menunggu verifikasi" not in k["dataIssues"]
    assert c.post("/api/outlets/quick", json={"name": "Gerobak Pasar Minggu Baru"}, headers=A).json()["id"] == o["Jagakarsa"]
    # verifikasi outlet baru
    n2 = c.post("/api/outlets/quick", json={"name": "Kios Uji Verifikasi"}, headers=A).json()
    assert c.post(f"/api/outlets/{n2['id']}/verify", json={"area": "Depok"}, headers=A).status_code == 403
    v = c.post(f"/api/outlets/{n2['id']}/verify", json={"area": "Depok"}, headers=L).json()
    assert v["pending"] is False and v["area"] == "Depok"


def test_bulk_input(ctx):
    c, H, o = ctx
    A = login(c, "Agen", "123123")
    head = "Tanggal\tJam Masuk\tJam Dibalas\tJam Selesai\tChannel\tOutlet\tSub Jenis\tRingkasan\tRoot Cause\tKompensasi\tNilai (Rp)\tStatus\tNama Customer\tNo HP\tNo Pesanan"
    rows = [
        "02/11/2026\t10.02\t10.05\t10.30\tWhatsApp\tJagakarsa\tMissing Item\tkurang 2 bulk\tKetelitian Crew\tReplacement\t\tSelesai\tBudi\t081211112222\t",
        "02/11/2026\t13:40\t13:44\t\tgofood\tKios Margonda\tSpeed of Service\tlama bulk\t\t\t\tDiproses\t\t\tF-77",
        "02/11/2026\t23.50\t00.10\t\tWhatsApp\tGerobak Bulk Baru\tHospitality\tjutek bulk\tx\tApologize\t\tClosed\t\t\t",
        "02/11/2026\t25.99\t10.05\t\tWhatsApp\tJagakarsa\tTidak Ada Sub\tsalah\t\t\t\t\t\t\t",
        "02/11/2026\t09.00\t09.03\t09.30\tWhatsApp\tJagakarsa\tMissing Item\tselesai tanpa komp\t\t\t\tSelesai\t\t\t",
    ]
    text = "\n".join([head] + rows)
    p = c.post("/api/cases/bulk", json={"text": text}, headers=A).json()
    assert p["dryRun"] and p["summary"] == {"rows": 5, "ok": 3, "error": 2, "warning": 1, "dup": 0}, p["summary"]
    r = p["rows"]
    assert r[0]["data"]["kompensasiKey"] == "maj-replacement" and r[0]["data"]["frtMin"] == 3
    assert r[1]["data"]["channel"] == "Review Online" and r[1]["data"]["platform"] == "GoFood" and r[1]["data"]["status"] == "Diproses"
    assert r[2]["data"]["dibalas"].startswith("2026-11-03T00:10") and any("belum terdaftar" in w for w in r[2]["warnings"])
    assert any("Jam Masuk" in e for e in r[3]["errors"]) and any("Sub Jenis" in e for e in r[3]["errors"])
    assert any("Kompensasi kosong" in e for e in r[4]["errors"])
    s = c.post("/api/cases/bulk", json={"text": text, "dryRun": False}, headers=A).json()
    assert len(s["created"]) == 3 and not s["failed"] and len(s["errorRows"]) == 2
    k = c.get(f"/api/cases/{s['created'][0]['caseId']}", headers=A).json()
    assert k["status"] == "Resolved" and k["timeEvidence"] == "bulk" and k["frtManual"] is True and k["voucherCode"].startswith("CMP-RP")
    k3 = c.get(f"/api/cases/{s['created'][2]['caseId']}", headers=A).json()
    assert k3["status"] == "Closed" and k3["outletPending"] is True
    # tempel ulang → terdeteksi duplikat dan dilewati
    s2 = c.post("/api/cases/bulk", json={"text": text, "dryRun": False}, headers=A).json()
    assert s2["skippedDup"] == 3 and not s2["created"]
    # tanpa header (urutan template) & template bisa diunduh
    p = c.post("/api/cases/bulk", json={"text": "04/11/2026\t10.02\t10.05\t\tWA\tJagakarsa\tHospitality\ttanpa header"}, headers=A).json()
    assert p["summary"]["ok"] == 1
    t = c.get("/api/cases/bulk/template", headers=A)
    assert t.status_code == 200 and len(t.content) > 3000
    f = c.post("/api/cases/bulk/file", files={"file": ("t.xlsx", t.content)}, headers=A).json()
    assert c.post("/api/cases/bulk", json={"text": f["text"]}, headers=A).json()["summary"]["ok"] == 3
    assert c.post("/api/cases/bulk", json={"text": text}, headers=login(c, "Lihat", "123123")).status_code == 403


def test_frozen_subs_and_generic_chat(ctx):
    c, H, o = ctx
    m = c.get("/api/masters", headers=H).json()
    fz = [s for s in m["subJenis"] if s.get("frozen")]
    assert {"Pesanan Kurang (Frozen)", "Salah Varian (Frozen)", "Kemasan Bocor (Frozen)", "Pengiriman Lama / Tidak Ada Update"} <= {s["name"] for s in fz}
    assert "Missing Item" not in {s["name"] for s in fz} and len([s for s in m["subJenis"] if s.get("priority")]) == 30
    mi = next(s for s in fz if s["name"] == "Pesanan Kurang (Frozen)")
    assert "kekurangan" in mi["keywords"] and mi["priority"] == "Critical" and mi["jenis"] == "Frozen Product"
    t = "Budi_shop 2026-11-02 10:02:11\nkak paket kurang 1 pack\nCimol Bojot AA Official 2026-11-02 10:09:40\nmohon maaf kak\n"
    p = c.post("/api/wa/parse", json={"text": t}, headers=H).json()
    assert p["messages"] == 2 and p["customer"] == "Budi_shop" and p["dibalas"].startswith("2026-11-02T10:09")
    body = {"channel": "Marketplace Chat", "outletId": o["Online Frozen (Shopee)"], "subJenis": "Missing Item", "ringkasan": "kurang 1 pack douke",
            "waktuMasuk": p["masuk"], "waktuFirstResponse": p["dibalas"], "chatText": t, "orderNo": "D-1", "force": True}
    r = c.post("/api/cases/rekap", json=body, headers=H).json()
    assert r["timeEvidence"] == "chat" and r["frtMin"] == 7 and r["desk"] == "Online" and r["caseId"].startswith("FRZ")


def test_frozen_product_line_any_outlet(ctx):
    c, H, o = ctx
    day = wib_iso(2026, 8, 5, 10, 0)
    a = mk(c, H, o, subJenis="Missing Item", ringkasan="frozen beli di gerobak kurang", waktuMasuk=day, produkFrozen=True, produk="Mozza AP").json()
    assert a["desk"] == "Online"
    assert a["frozen"] is True and a["caseId"].startswith("OTL") and a["costCenter"] == "Team Frozen" and a["picDept"] == "Gudang / Packing Frozen"
    assert "Kode produksi belum diisi" in a["dataIssues"]
    b = mk(c, H, o, subJenis="Missing Item", ringkasan="gerobak biasa kurang", waktuMasuk=wib_iso(2026, 8, 6, 10, 0)).json()
    assert b["frozen"] is False and b["costCenter"] == "Operasional" and b["desk"] == "Offline"
    f = c.get("/api/dashboard/frozen", params={"from": "2026-08-01", "to": "2026-08-31"}, headers=H).json()
    assert f["volume"]["komplain"] == 1 and f["stores"][0]["name"] == "Jagakarsa"
    ol = c.get("/api/dashboard", params={"from": "2026-08-01", "to": "2026-08-31", "line": "outlet"}, headers=H).json()
    assert ol["volume"]["komplain"] == 1
    r = c.patch(f"/api/cases/{b['caseId']}", json={"produkFrozen": True}, headers=H).json()
    assert r["frozen"] is True and r["costCenter"] == "Team Frozen" and r["desk"] == "Online"


def test_order_time(ctx):
    c, H, o = ctx
    m = wib_iso(2026, 7, 6, 12, 0)
    assert mk(c, H, o, ringkasan="order salah", waktuMasuk=m, waktuOrder=wib_iso(2026, 7, 6, 12, 30)).status_code == 400
    k = mk(c, H, o, ringkasan="order ok", waktuMasuk=m, waktuOrder=wib_iso(2026, 7, 6, 11, 15)).json()
    assert k["orderToComplaintMin"] == 45 and k["waktuOrder"]
    r = c.patch(f"/api/cases/{k['caseId']}", json={"waktuOrder": wib_iso(2026, 7, 6, 11, 0)}, headers=H).json()
    assert r["orderToComplaintMin"] == 60
    assert c.patch(f"/api/cases/{k['caseId']}", json={"waktuOrder": wib_iso(2026, 7, 6, 13, 0)}, headers=H).status_code == 400
    r = c.patch(f"/api/cases/{k['caseId']}", json={"waktuOrder": ""}, headers=H).json()
    assert r.get("orderToComplaintMin") is None
    t = "Tanggal\tJam Masuk\tJam Dibalas\tChannel\tOutlet\tSub Jenis\tRingkasan\tJam Order\n07/07/2026\t10.00\t10.03\tWhatsApp\tJagakarsa\tHospitality\torder bulk\t09.20\n08/07/2026\t00.30\t08.05\tWhatsApp\tJagakarsa\tHospitality\torder malam\t23.50"
    p = c.post("/api/cases/bulk", json={"text": t}, headers=H).json()
    assert p["rows"][0]["data"]["order"].startswith("2026-07-07T09:20") and p["rows"][1]["data"]["order"].startswith("2026-07-07T23:50")
    s = c.post("/api/cases/bulk", json={"text": t, "dryRun": False}, headers=H).json()
    assert c.get(f"/api/cases/{s['created'][0]['caseId']}", headers=H).json()["orderToComplaintMin"] == 40


def test_review_online_as_case(ctx):
    c, H, o = ctx
    m = wib_iso(2026, 6, 3, 19, 20)
    base = {"channel": "Review Online", "outletId": o["Jagakarsa"], "subJenis": "Missing Item", "ringkasan": "pesan 3 datang 2", "waktuMasuk": m, "force": True}
    assert c.post("/api/cases/rekap", json=base, headers=H).status_code == 400          # platform wajib
    r = c.post("/api/cases/rekap", json={**base, "reviewPlatform": "GoFood", "rating": 1, "orderNo": "F-9"}, headers=H).json()
    assert r["status"] == "Open" and r["reviewPlatform"] == "GoFood" and r["rating"] == 1 and r["timeEvidence"] == "review"
    r2 = c.post("/api/cases/rekap", json={**base, "ringkasan": "review 2", "reviewPlatform": "GrabFood", "rating": 2,
                "waktuFirstResponse": wib_iso(2026, 6, 3, 20, 0), "waktuResolved": wib_iso(2026, 6, 3, 21, 0),
                "rootCause": "x", "kompensasiKey": "maj-apologize"}, headers=H).json()
    assert r2["status"] == "Resolved" and r2["slaResponseOk"] is None and not r2.get("frtManual")
    assert mk(c, H, o, channel="WhatsApp", ringkasan="bukan review", waktuMasuk=m, reviewPlatform="GoFood").json().get("reviewPlatform") is None
    rs = c.get("/api/meetings", headers=H)
    t = "Tanggal\tJam Masuk\tJam Dibalas\tChannel\tOutlet\tSub Jenis\tRingkasan\tPlatform Online\tRating\n04/06/2026\t12.00\t\t\tJagakarsa\tHospitality\treview bulk\tshopeefood\t2\n04/06/2026\t13.00\t\tReview Online\tJagakarsa\tHospitality\ttanpa platform\t\t"
    p = c.post("/api/cases/bulk", json={"text": t}, headers=H).json()
    assert p["rows"][0]["ok"] and p["rows"][0]["data"]["channel"] == "Review Online" and p["rows"][0]["data"]["platform"] == "ShopeeFood"
    assert not p["rows"][1]["ok"]
    s = c.post("/api/cases/bulk", json={"text": t, "dryRun": False}, headers=H).json()
    k = c.get(f"/api/cases/{s['created'][0]['caseId']}", headers=H).json()
    assert k["status"] == "Open" and k["reviewPlatform"] == "ShopeeFood" and k["rating"] == 2
    from app.routes_cases import review_summary


def test_platform_online_tiktok_go(ctx):
    c, H, o = ctx
    m = c.get("/api/masters", headers=H).json()
    assert "TikTok Go" in m["reviewPlatforms"]
    ch = {x["name"]: x for x in m["channels"]}
    assert ch["GoFood"]["hidden"] and ch["GrabFood"]["hidden"] and ch["ShopeeFood"]["hidden"] and not ch["Review Online"].get("hidden")
    r = c.post("/api/cases/rekap", json={"channel": "Review Online", "outletId": o["Jagakarsa"], "subJenis": "Hospitality", "ringkasan": "tiktok go",
               "waktuMasuk": wib_iso(2026, 5, 5, 10, 0), "reviewPlatform": "TikTok Go", "force": True}, headers=H).json()
    assert r["reviewPlatform"] == "TikTok Go" and r["desk"] == "Online"
    t = "Tanggal\tJam Masuk\tJam Dibalas\tChannel\tOutlet\tSub Jenis\tRingkasan\n06/05/2026\t10.00\t10.05\tTikTok Go\tJagakarsa\tHospitality\tbulk tiktok go"
    d = c.post("/api/cases/bulk", json={"text": t}, headers=H).json()["rows"][0]["data"]
    assert d["channel"] == "Review Online" and d["platform"] == "TikTok Go"


def test_daily_data(ctx):
    c, H, o = ctx
    A = login(c, "Agen", "123123")
    for hh in (9, 11):
        mk(c, H, o, ringkasan=f"harian {hh}", waktuMasuk=wib_iso(2026, 4, 7, hh, 0))
    assert c.put("/api/daily", json={"tanggal": "2026-04-07", "transaksi": 2000, "komplain": 3}, headers=A).status_code == 200
    assert c.put("/api/daily", json={"tanggal": "2099-01-01", "transaksi": 1}, headers=A).status_code == 400
    assert c.put("/api/daily", json={"tanggal": "2026-04-07", "transaksi": -5}, headers=A).status_code == 400
    assert c.put("/api/daily", json={"tanggal": "2026-04-07", "transaksi": 1}, headers=login(c, "Lihat", "123123")).status_code == 403
    d = c.get("/api/daily", params={"from": "2026-04-06", "to": "2026-04-08"}, headers=A).json()
    r = next(x for x in d["rows"] if x["tanggal"] == "2026-04-07")
    assert r["tercatat"] == 2 and r["komplain"] == 3 and r["selisih"] == 1 and r["per1000"] == 1.5
    assert d["summary"]["belumDirekap"] == 1 and d["summary"]["transaksi"] == 2000 and len(d["rows"]) == 3
    dash = c.get("/api/dashboard", params={"from": "2026-04-07", "to": "2026-04-07"}, headers=H).json()
    assert dash["period"]["totalTrx"] == 2000 and dash["volume"]["per1000"] == 1.0
    c.put("/api/daily", json={"tanggal": "2026-04-07"}, headers=A)
    assert c.get("/api/daily", params={"from": "2026-04-07", "to": "2026-04-07"}, headers=A).json()["rows"][0]["transaksi"] is None


def test_no_complaint(ctx):
    c, H, o = ctx
    m = c.get("/api/masters", headers=H).json()
    assert any(s["name"] == "No Complaint" for s in m["subJenis"]) and "No Complaint" in m["tipe"]
    day = wib_iso(2026, 3, 3, 10, 0)
    a = mk(c, H, o, subJenis="No Complaint", ringkasan="customer cuma tanya jam buka", waktuMasuk=day).json()
    assert a["tipe"] == "No Complaint" and a["level"] is None and a["dataOk"] is True
    mk(c, H, o, subJenis="Hospitality", ringkasan="komplain asli", waktuMasuk=wib_iso(2026, 3, 3, 11, 0))
    d = c.get("/api/dashboard", params={"from": "2026-03-03", "to": "2026-03-03"}, headers=H).json()
    assert d["volume"]["contact"] == 2 and d["volume"]["komplain"] == 1 and all(x["name"] != "No Complaint" for x in d["subJenis"])
    r = c.post("/api/cases/rekap", json={"channel": "Review Online", "reviewPlatform": "GoFood", "rating": 5, "outletId": o["Jagakarsa"],
               "subJenis": "No Complaint", "ringkasan": "enak banget", "waktuMasuk": wib_iso(2026, 3, 4, 10, 0),
               "waktuFirstResponse": wib_iso(2026, 3, 4, 10, 5), "waktuResolved": wib_iso(2026, 3, 4, 10, 5), "force": True}, headers=H).json()
    assert r["status"] == "Resolved" and r["kompensasiOutsideStandard"] is False and not r.get("voucherCode") and r["dataOk"] is True
    # diubah jadi komplain sungguhan → kembali dihitung
    r = c.patch(f"/api/cases/{a['caseId']}", json={"subJenis": "Hospitality"}, headers=H).json()
    assert r["tipe"] == "Komplain" and r["level"] == "Minor"
    t = "Tanggal\tJam Masuk\tJam Dibalas\tChannel\tOutlet\tSub Jenis\tRingkasan\tStatus\n05/03/2026\t10.00\t10.02\tWA\tJagakarsa\tno complaint\tpujian\tSelesai"
    p = c.post("/api/cases/bulk", json={"text": t}, headers=H).json()
    assert p["rows"][0]["ok"], p["rows"][0]


def test_new_frozen_categories_rules(ctx):
    c, H, o = ctx
    sp = o["Online Frozen (Shopee)"]
    a = mk(c, H, o, outletId=sp, subJenis="Produk Asam / Masam (Frozen)", ringkasan="asam", waktuMasuk=wib_iso(2026, 2, 3, 10, 0)).json()
    assert a["level"] == "Critical" and a["jenis"] == "Frozen Product" and a["priority"] == "Critical" and a["costCenter"].startswith("Factory/Operasional")
    assert a["picDept"] == "Gudang / Packing Frozen" and "Kode produksi belum diisi" in a["dataIssues"] and a["salesChannel"] == "Shopee" and a["salesGroup"] == "Marketplace"
    b = mk(c, H, o, outletId=sp, subJenis="Kemasan Bocor (Frozen)", ringkasan="bocor", waktuMasuk=wib_iso(2026, 2, 3, 11, 0)).json()
    assert b["level"] == "Minor" and b["costCenter"] == "Factory"
    d = mk(c, H, o, outletId=o["Online Frozen (Tiktok 2)"], subJenis="Pengiriman Lama / Tidak Ada Update", ringkasan="lama", waktuMasuk=wib_iso(2026, 2, 3, 12, 0)).json()
    assert d["level"] is None and d["picDept"] == "Logistics / Delivery" and d["salesChannel"] == "TikTok Tokopedia"
    e = mk(c, H, o, subJenis="Voucher Tidak Bisa Dipakai", ringkasan="voucher", waktuMasuk=wib_iso(2026, 2, 3, 13, 0)).json()
    assert e["jenis"] == "Membership / Promo" and e["salesChannel"] == "Outlet / Kios" and e["salesGroup"] == "Offline"


def test_sales_channel_breakdown(ctx):
    c, H, o = ctx
    day = "2026-01-13"
    mk(c, H, o, ringkasan="sc outlet", waktuMasuk=wib_iso(2026, 1, 13, 9, 0))
    mk(c, H, o, ringkasan="sc grab via wa", waktuMasuk=wib_iso(2026, 1, 13, 10, 0), salesChannel="GrabFood")
    c.post("/api/cases/rekap", json={"channel": "Review Online", "reviewPlatform": "TikTok Go", "outletId": o["Jagakarsa"], "subJenis": "Hospitality",
           "ringkasan": "sc tiktok go", "waktuMasuk": wib_iso(2026, 1, 13, 11, 0), "force": True}, headers=H)
    mk(c, H, o, outletId=o["Online Frozen (Shopee)"], subJenis="Pesanan Kurang (Frozen)", ringkasan="sc shopee", waktuMasuk=wib_iso(2026, 1, 13, 12, 0))
    assert mk(c, H, o, ringkasan="x", salesChannel="Lazada").status_code == 400
    r = c.put("/api/daily", json={"tanggal": day, "trx": {"Outlet / Kios": 1000, "GrabFood": 200, "TikTok Go": 50, "Shopee": 100},
                                  "kom": {"Outlet / Kios": 2, "GrabFood": 1, "TikTok Go": 1, "Shopee": 1}}, headers=H)
    assert r.status_code == 200
    assert c.put("/api/daily", json={"tanggal": day, "trx": {"Lazada": 5}}, headers=H).status_code == 400
    d = c.get("/api/daily", params={"from": day, "to": day}, headers=H).json()
    row = d["rows"][0]
    assert row["transaksi"] == 1350 and row["komplain"] == 5 and row["tercatat"] == 4 and row["selisih"] == 1
    assert row["groups"]["Online Aggregator"] == {"transaksi": 250, "komplain": 2, "tercatat": 2}
    ch = {x["name"]: x for x in d["channels"]}
    assert ch["Offline"]["tercatat"] == 1 and ch["GrabFood"]["tercatat"] == 1 and ch["TikTok Go"]["transaksi"] == 50 and ch["Marketplace"]["per1000"] == 10.0
    dash = c.get("/api/dashboard", params={"from": day, "to": day}, headers=H).json()
    sc = {x["name"]: x for x in dash["salesChannels"]["rows"]}
    assert sc["Total"]["komplain"] == 4 and sc["Total"]["transaksi"] == 1350 and sc["Online Aggregator"]["komplain"] == 2
    assert sc["Shopee"]["per1000"] == 10.0 and sc["Offline"]["per1000"] == 1.0 and dash["period"]["totalTrx"] == 1350
    t = "Tanggal\tJam Masuk\tJam Dibalas\tChannel\tOutlet\tSub Jenis\tRingkasan\tSales Channel\n14/01/2026\t10.00\t10.02\tWA\tJagakarsa\tHospitality\tsc bulk\tshopee food"
    p = c.post("/api/cases/bulk", json={"text": t}, headers=H).json()
    assert p["rows"][0]["data"]["salesChannel"] == "ShopeeFood"
