"""Acceptance test utama (jalankan: cd backend && pytest -q). Memakai database memori."""
import os
from datetime import timedelta, datetime, timezone

os.environ.update(USE_MOCK_DB="true", DISABLE_JOBS="true", DATA_DIR="/tmp/sd-test", DEFAULT_ADMIN_PIN="111111")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        yield client


def auth(c, name="Admin", pin="111111"):
    r = c.post("/api/auth/login", json={"name": name, "pin": pin})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def outlet(c, H, name):
    return next(o for o in c.get("/api/masters", headers=H).json()["outlets"] if o["name"] == name)


def test_full_flow(c):
    H = auth(c)
    # users
    assert c.post("/api/users", json={"name": "Sari", "role": "CS Agent", "pin": "222222"}, headers=H).status_code == 200
    assert c.post("/api/users", json={"name": "Budi", "role": "Manager Area", "pin": "333333", "areas": ["Bekasi"]},
                  headers=H).status_code == 200
    assert c.post("/api/users", json={"name": "Vina", "role": "Viewer", "pin": "444444"}, headers=H).status_code == 200
    A = auth(c, "Sari", "222222")
    c.post("/api/vouchers/import", json={"jenis": "Voucher Diskon 10K", "codes": "CRK-D10-AAA\nCRK-D10-BBB"}, headers=H)

    jg = outlet(c, A, "Jagakarsa")
    r = c.post("/api/cases", json={"channel": "WhatsApp", "outletId": jg["id"], "subJenis": "Missing Item",
                                   "ringkasan": "pesan 16 pcs dibuat 8 pcs", "customerPhone": "081281806894"},
               headers=A)
    assert r.status_code == 200, r.text
    k = r.json()
    assert k["caseId"] == "OTL-01" and k["level"] == "Major" and k["penanggungJawab"] == "Manager Area"
    assert k["costCenter"] == "Operasional" and k["targetFrtMin"] == 5 and k["targetResolutionMin"] == 2880
    cid = k["caseId"]

    # duplikat
    r = c.post("/api/cases", json={"channel": "WhatsApp", "outletId": jg["id"], "subJenis": "Missing Item",
                                   "ringkasan": "sama"}, headers=A)
    assert r.status_code == 409 and "OTL-01" in r.json()["detail"]["duplicates"]

    # frozen
    fz = outlet(c, A, "Online Frozen (Shopee)")
    r = c.post("/api/cases", json={"channel": "Marketplace Chat", "outletId": fz["id"], "subJenis": "Missing Item",
                                   "ringkasan": "pcs kurang"}, headers=A).json()
    assert r["caseId"] == "FRZ-01" and r["costCenter"] == "Team Frozen" and r["picDept"] == "Gudang / Packing Frozen"

    # critical IG DM → target min(10, 30) = 10
    r = c.post("/api/cases", json={"channel": "IG DM", "outletId": jg["id"], "subJenis": "Undercooked",
                                   "ringkasan": "mentah"}, headers=A).json()
    assert r["level"] == "Critical" and r["targetFrtMin"] == 10
    crit = r["caseId"]

    # close sebelum resolve diblok
    assert c.post(f"/api/cases/{cid}/close", json={"followUpUlang": "N"}, headers=A).status_code == 400
    assert c.post(f"/api/cases/{cid}/respond", headers=A).json()["slaResponseOk"] is True
    r = c.post(f"/api/cases/{cid}/resolve", json={"rootCause": "Ketelitian Crew", "kompensasiKey": "maj-v10"},
               headers=A).json()
    assert r["voucherCode"] == "CRK-D10-AAA" and r["nilaiKompensasi"] == 10000
    r = c.post(f"/api/cases/{cid}/close", json={"followUpUlang": "N"}, headers=A).json()
    assert r["status"] == "Closed" and r["fcr"] is True and r["dataOk"]

    # refund = di luar standard
    c.post(f"/api/cases/FRZ-01/respond", headers=A)
    r = c.post(f"/api/cases/FRZ-01/resolve", json={"rootCause": "Produk Kurang", "kompensasiKey": "all-refund",
                                                   "nilaiKompensasi": 26000}, headers=A).json()
    assert r["kompensasiOutsideStandard"] is True

    # critical undercooked butuh cost center final
    c.post(f"/api/cases/{crit}/resolve", json={"rootCause": "Suhu minyak", "kompensasiKey": "cri-kit1"}, headers=A)
    assert c.post(f"/api/cases/{crit}/close", json={"followUpUlang": "N"}, headers=A).status_code == 400
    assert c.post(f"/api/cases/{crit}/close", json={"followUpUlang": "N", "costCenterFinal": "Operasional"},
                  headers=A).status_code == 200

    # koreksi waktu: hanya CS Lead/Admin, tidak boleh sebelum masuk / masa depan
    assert c.post(f"/api/cases/{cid}/correct-time", json={"field": "waktuResolved", "value": "2020-01-01T10:00:00",
                                                         "reason": "x"}, headers=A).status_code == 403
    assert c.post(f"/api/cases/{cid}/correct-time", json={"field": "waktuResolved", "value": "2020-01-01T10:00:00",
                                                         "reason": "salah"}, headers=H).status_code == 400
    fut = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert c.post(f"/api/cases/{cid}/correct-time", json={"field": "waktuClosed", "value": fut, "reason": "x"},
                  headers=H).status_code == 400
    assert len(c.get("/api/admin/audit", headers=H).json()) >= 1

    # ubah level wajib alasan
    assert c.post(f"/api/cases/{cid}/change-level", json={"level": "Critical", "reason": ""}, headers=A).status_code == 400

    # CSAT publik → draft → case
    r = c.post("/api/public/csat", json={"outlet": "Cimol bojot AA lokasari", "phone": "0895", "puasPelayanan": 1,
                                         "rasa": 1, "kebersihan": 1, "beliLagi": "Tidak", "kritikSaran": "tidak dikasih bill",
                                         "ratingKeseluruhan": 1})
    assert r.status_code == 200
    inbox = c.get("/api/inbox", headers=A).json()
    d = inbox["csatDrafts"][0]
    assert d["outletName"] == "Lokasari"
    r = c.post(f"/api/csat/{d['id']}/triage", json={"action": "jadi_case", "subJenis": "Potential Fraud"}, headers=A).json()
    assert r["caseId"].startswith("OTL-")
    assert c.get(f"/api/cases/{r['caseId']}", headers=A).json()["channel"] == "CSAT Form"

    # peran
    B = auth(c, "Budi", "333333")
    assert c.get(f"/api/cases/{cid}", headers=B).status_code == 403  # Jagakarsa = Jakarta
    V = auth(c, "Vina", "444444")
    assert "****" in c.get(f"/api/cases/{cid}", headers=V).json()["customerPhone"]
    assert c.post("/api/cases", json={"channel": "WhatsApp", "outletId": jg["id"], "subJenis": "Hospitality",
                                      "ringkasan": "x"}, headers=V).status_code == 403

    # dashboard + meeting
    today = datetime.now(timezone(timedelta(hours=7))).date().isoformat()
    dsh = c.get("/api/dashboard", params={"from": today, "to": today}, headers=A).json()
    assert dsh["volume"]["komplain"] == 4 and dsh["volume"]["countLuarStandard"] == 1
    m = c.post("/api/meetings", json={"date": today, "periodStart": today, "periodEnd": today}, headers=H).json()
    mm = c.get(f"/api/meetings/{m['id']}", headers=H).json()
    assert mm["top5"][0]["name"] == "Missing Item"
    a = c.post("/api/voc-actions", json={"subJenis": "Missing Item", "action": "Checklist struk", "picDept": "Ops / Outlet"},
               headers=H).json()
    mm = c.get(f"/api/meetings/{m['id']}", headers=H).json()
    assert mm["top5"][0]["action"]["id"] == a["id"]
    assert c.post(f"/api/meetings/{m['id']}/lock", headers=H).status_code == 200

    # export & public metrics
    assert c.get("/api/export/cases.xlsx", headers=H).status_code == 200
    assert c.get("/api/public-metrics/service", params={"from": today, "to": today}).status_code == 401


def test_pin_lock(c):
    for _ in range(5):
        c.post("/api/auth/login", json={"name": "Admin", "pin": "000000"})
    r = c.post("/api/auth/login", json={"name": "Admin", "pin": "111111"})
    assert r.status_code == 423


def test_admin_pin_resync_and_legacy_hash():
    """Admin yang dibuat dengan PIN/SECRET_KEY lama dan belum pernah login ikut DEFAULT_ADMIN_PIN baru."""
    import asyncio
    from app import core, services
    from app.auth import _legacy_hash, verify_pin, hash_pin

    assert verify_pin("123456", _legacy_hash("123456", "abcd", core.Config.SECRET_KEY)) is True
    assert verify_pin("123456", hash_pin("123456")) and not verify_pin("654321", hash_pin("123456"))

    async def run():
        core.Config.USE_MOCK_DB = True
        db = core.init_db()
        await db.users.delete_many({})
        await db.users.insert_one({"id": "a1", "name": "Admin", "role": "Admin", "active": True,
                                   "pinHash": _legacy_hash("999999", "s1", "secret-lama")})
        await services.seed_if_empty()
        u = await db.users.find_one({"name": "Admin"})
        assert verify_pin(core.Config.DEFAULT_ADMIN_PIN, u["pinHash"])
        # setelah pernah login, PIN tidak disentuh lagi
        await db.users.update_one({"id": "a1"}, {"$set": {"lastLogin": core.now(), "pinHash": hash_pin("222333")}})
        await services.seed_if_empty()
        u = await db.users.find_one({"name": "Admin"})
        assert verify_pin("222333", u["pinHash"])
    asyncio.run(run())
