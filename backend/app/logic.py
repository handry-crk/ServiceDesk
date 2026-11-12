"""Aturan CRM.STD.001 dan cara hitung metric (sama dengan tab Panduan di sheet lama)."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, date
from statistics import mean

from .core import as_utc, wib, wib_date, now, WIB, get_db
from .standards import NEEDS_BATCH

# CRM.STD.001 5.1: benda asing, potensi keracunan, tidak matang → Factory/Operasional sesuai root cause
CRITICAL_COST_RC = {"Kontaminasi", "Keracunan", "Undercooked"}
CC_ROOT = "Factory/Operasional (cek root cause)"


def needs_cost_final(c):
    return c.get("level") == "Critical" and c.get("costCenter") == CC_ROOT


async def load_ctx():
    db = get_db()
    sj = {d["name"]: d async for d in db.sub_jenis.find({})}
    ch = {d["name"]: d async for d in db.channels.find({})}
    komp = {d["key"]: d async for d in db.kompensasi.find({})}
    tg = await db.config.find_one({"_id": "targets"}) or {}
    st = await db.config.find_one({"_id": "settings"}) or {}
    pj = await db.config.find_one({"_id": "penanggungJawab"}) or {}
    rt = await db.config.find_one({"_id": "resolutionTarget"}) or {}
    outlets = {d["id"]: d async for d in db.outlets.find({})}
    return {
        "subJenis": sj, "channels": ch, "kompensasi": komp,
        "targets": tg.get("value", {}), "settings": st.get("value", {}),
        "pj": pj.get("value", {}), "resTarget": rt.get("value", {}),
        "criticalFrt": rt.get("criticalFrt", 30), "outlets": outlets,
    }


def _minutes(a, b):
    a, b = as_utc(a), as_utc(b)
    if not a or not b:
        return None
    return round((b - a).total_seconds() / 60, 1)


def _hm(s):
    h, m = s.split(":")
    return int(h), int(m)


def work_minutes(start, end, op_start="08:00", op_end="22:00"):
    """Menit di antara start dan end yang jatuh di jam operasional CS (WIB)."""
    s, e = wib(start), wib(end)
    if not s or not e or e <= s:
        return 0.0 if s and e else None
    sh, sm = _hm(op_start)
    eh, em = _hm(op_end)
    total = 0.0
    day = s.date()
    while day <= e.date():
        ws = datetime(day.year, day.month, day.day, sh, sm, tzinfo=WIB)
        we = datetime(day.year, day.month, day.day, eh, em, tzinfo=WIB)
        a, b = max(ws, s), min(we, e)
        if b > a:
            total += (b - a).total_seconds() / 60
        day += timedelta(days=1)
    return round(total, 1)


def compute_case(c: dict, ctx: dict) -> dict:
    """Isi semua kolom otomatis. Mengubah dan mengembalikan dict case."""
    sj = ctx["subJenis"].get(c.get("subJenis") or "")
    outlet = ctx["outlets"].get(c.get("outletId")) or {}
    otype = c.get("outletType") or outlet.get("type") or "gerobak"
    c["outletType"] = otype
    c["outletName"] = outlet.get("name") or c.get("outletName")
    c["area"] = outlet.get("area") or c.get("area") or "Belum diatur"
    c["jenis"] = sj["jenis"] if sj else None
    c["levelStandard"] = sj["level"] if sj else None
    if not c.get("level"):
        c["level"] = c["levelStandard"] if c["levelStandard"] in ("Minor", "Major", "Critical") else None
    lvl = c.get("level")
    lvl_key = lvl or "Belum Diatur"
    pj_auto = ctx["pj"].get(lvl_key, "CS Lead")
    if not c.get("penanggungJawab") or not c.get("pjImported"):
        c["penanggungJawab"] = pj_auto

    # cost center
    sname = c.get("subJenis")
    frozen = otype == "online_frozen"
    if lvl == "Minor":
        cc = "Factory" if (frozen and sname == "Kesalahan Kemasan") else "Operasional"
    elif lvl == "Major":
        cc = "Team Frozen" if frozen else "Operasional"
    elif lvl == "Critical":
        # spoiled product frozen ikut dicek ke Factory (sama dengan sheet lama)
        spoiled_frozen = frozen and sname == "Penurunan Mutu (tidak dapat dikonsumsi)"
        cc = CC_ROOT if (sname in CRITICAL_COST_RC or spoiled_frozen) else "Operasional"
    else:
        cc = "Belum Diatur"
    c["costCenter"] = cc

    # kompensasi
    k = ctx["kompensasi"].get(c.get("kompensasiKey") or "")
    if k:
        c["kompensasiJenis"] = k["jenis"]
        c["kompensasiLabel"] = k["label"]
        c["kompensasiOutsideStandard"] = (not k.get("standard")) or (k["level"] not in ("Semua", lvl))
    elif c.get("kompensasiJenis"):
        c["kompensasiLabel"] = c.get("kompensasiLabel") or c["kompensasiJenis"]
        c["kompensasiOutsideStandard"] = c["kompensasiJenis"] in ("Refund", "Tidak Ada") or \
            bool(c.get("kompensasiForceOutside"))
    else:
        c["kompensasiOutsideStandard"] = False

    # target & SLA
    ch = ctx["channels"].get(c.get("channel") or "") or {}
    tfrt = ch.get("targetFrt", 5)
    if lvl == "Critical":
        tfrt = min(tfrt, ctx.get("criticalFrt", 30))
    c["targetFrtMin"] = tfrt
    c["countInSla"] = ch.get("countInSla", True)
    has_time = c.get("hasTime", True)
    st = ctx["settings"]
    if has_time and c.get("waktuFirstResponse"):
        c["frtMin"] = _minutes(c["waktuMasuk"], c["waktuFirstResponse"])
        c["frtWorkMin"] = work_minutes(c["waktuMasuk"], c["waktuFirstResponse"],
                                       st.get("opStart", "08:00"), st.get("opEnd", "22:00"))
        c["slaResponseOk"] = (c["frtMin"] is not None and c["frtMin"] <= tfrt) if c["countInSla"] else None
    else:
        c["frtMin"] = c["frtWorkMin"] = None
        c["slaResponseOk"] = None
    tres = ctx["resTarget"].get(lvl) if lvl else None
    c["targetResolutionMin"] = tres
    if has_time and c.get("waktuResolved"):
        c["resolutionMin"] = _minutes(c["waktuMasuk"], c["waktuResolved"])
        c["resolutionSlaOk"] = (c["resolutionMin"] <= tres) if (tres and c["resolutionMin"] is not None) else None
    else:
        c["resolutionMin"] = None
        c["resolutionSlaOk"] = None
    dm = wib_date(c.get("waktuMasuk"))
    if c.get("waktuResolved"):
        c["sameDay"] = wib_date(c["waktuResolved"]) == dm
    elif dm and wib_date(now()) > dm:
        c["sameDay"] = False
    else:
        c["sameDay"] = None
    fu = c.get("followUpUlang")
    c["fcr"] = (fu == "N") if (fu in ("Y", "N") and c.get("waktuResolved")) else None
    cs = c.get("csat")
    c["puas"] = (cs >= 4) if isinstance(cs, (int, float)) else None
    c["jamMasuk"] = wib(c["waktuMasuk"]).hour if (c.get("waktuMasuk") and has_time) else None
    c["tanggalMasuk"] = dm.isoformat() if dm else None
    c["dataIssues"] = data_issues(c, pj_auto)
    c["dataOk"] = not any(i for i in c["dataIssues"] if not i.startswith("Info:"))
    return c


def data_issues(c, pj_auto):
    iss = []
    if c.get("levelStandard") in ("Minor", "Major", "Critical") and c.get("level") and \
            c["level"] != c["levelStandard"] and not c.get("levelChangeReason"):
        iss.append("Level berbeda dari standard tanpa alasan")
    if c.get("penanggungJawab") and c["penanggungJawab"] != pj_auto and c.get("level"):
        iss.append("Penanggung jawab tidak sesuai level")
    if c.get("waktuClosed") and (not c.get("waktuResolved") or as_utc(c["waktuClosed"]) < as_utc(c["waktuResolved"])):
        iss.append("Closed sebelum Resolved")
    for f in ("waktuFirstResponse", "waktuResolved", "waktuClosed"):
        if c.get(f) and c.get("waktuMasuk") and as_utc(c[f]) < as_utc(c["waktuMasuk"]) - timedelta(minutes=1):
            iss.append("Waktu lebih awal dari Waktu Masuk")
            break
    if not c.get("hasTime", True):
        iss.append("Waktu tanpa jam")
    if c.get("waktuResolved") and not c.get("rootCause"):
        iss.append("Resolved tanpa root cause")
    if c.get("waktuClosed") and c.get("followUpUlang") not in ("Y", "N"):
        iss.append("Closed tanpa Follow-up Y/N")
    if needs_cost_final(c) and c.get("waktuClosed") and not c.get("costCenterFinal") and c.get("source") != "import":
        iss.append("Critical tanpa cost center final")
    if c.get("outletType") == "online_frozen" and c.get("subJenis") in NEEDS_BATCH and not c.get("kodeProduksi") \
            and c.get("source") != "import":
        iss.append("Kode produksi belum diisi")
    if c.get("possibleDuplicateOf"):
        iss.append("Mungkin duplikat " + c["possibleDuplicateOf"])
    if c.get("kompensasiOutsideStandard"):
        iss.append("Info: Kompensasi di luar standard")
    return iss


# ---------------- metrics ----------------

def _rate(num, den):
    return round(num / den, 4) if den else None


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(mean(xs), 1) if xs else None


def status_of(key, actual, targets):
    t = targets.get(key)
    if actual is None or not t:
        return "-"
    ok = actual <= t["target"] if t["dir"] == "max" else actual >= t["target"]
    if key == "reopen":
        ok = actual < t["target"]
    return "On Track" if ok else "Below Target"


def compute_metrics(cases, targets, total_trx=None):
    contact = cases
    komplain = [c for c in cases if c.get("tipe", "Komplain") == "Komplain"]
    valid = [c for c in komplain if c.get("valid", "Y") == "Y"]
    responded = [c for c in contact if c.get("frtMin") is not None]
    sla_base = [c for c in responded if c.get("countInSla", True)]
    resolved = [c for c in komplain if c.get("resolutionMin") is not None]
    res_sla_base = [c for c in resolved if c.get("resolutionSlaOk") is not None]
    sameday_base = [c for c in komplain if c.get("sameDay") is not None]
    fcr_base = [c for c in komplain if c.get("fcr") is not None]
    closed = [c for c in komplain if c.get("status") == "Closed"]
    rated = [c for c in contact if c.get("puas") is not None]
    m = {
        "frt": _avg([c["frtMin"] for c in responded]),
        "frtWork": _avg([c.get("frtWorkMin") for c in responded]),
        "slaResponse": _rate(sum(1 for c in sla_base if c.get("slaResponseOk")), len(sla_base)),
        "avgResolution": _avg([c["resolutionMin"] for c in resolved]),
        "resolutionSla": _rate(sum(1 for c in res_sla_base if c["resolutionSlaOk"]), len(res_sla_base)),
        "sameDay": _rate(sum(1 for c in sameday_base if c["sameDay"]), len(sameday_base)),
        "fcr": _rate(sum(1 for c in fcr_base if c["fcr"]), len(fcr_base)),
        "compSuccess": _rate(sum(1 for c in valid if c.get("kompensasiJenis") and c["kompensasiJenis"] != "Tidak Ada"),
                             len(valid)),
        "reopen": _rate(sum(1 for c in closed if (c.get("reopenCount") or 0) > 0), len(closed)) if closed else None,
        "csat": _rate(sum(1 for c in rated if c["puas"]), len(rated)),
        "csatN": len(rated),
        "csatSent": sum(1 for c in contact if c.get("surveySentAt")),
        "csatResponse": _rate(sum(1 for c in contact if c.get("surveySentAt") and c.get("puas") is not None),
                              sum(1 for c in contact if c.get("surveySentAt"))),
    }
    biaya = sum(c.get("nilaiKompensasi") or 0 for c in komplain)
    biaya_out = sum(c.get("nilaiKompensasi") or 0 for c in komplain if c.get("kompensasiOutsideStandard"))
    vol = {
        "contact": len(contact),
        "inquiry": sum(1 for c in contact if c.get("tipe") == "Inquiry"),
        "komplain": len(komplain),
        "komplainValid": len(valid),
        "open": sum(1 for c in komplain if c.get("status") not in ("Resolved", "Closed")),
        "per1000": round(len(komplain) / total_trx * 1000, 2) if total_trx else None,
        "biaya": biaya,
        "biayaLuarStandard": biaya_out,
        "countLuarStandard": sum(1 for c in komplain if c.get("kompensasiOutsideStandard")),
        "critical": sum(1 for c in komplain if c.get("level") == "Critical"),
        "dataIssues": sum(1 for c in contact if not c.get("dataOk", True)),
    }
    metrics_table = []
    groups = [("Response", "frt"), ("Response", "slaResponse"), ("Resolution", "avgResolution"),
              ("Resolution", "resolutionSla"), ("Resolution", "sameDay"), ("Resolution", "fcr"),
              ("Quality", "compSuccess"), ("Quality", "reopen"), ("Quality", "csat")]
    for g, k in groups:
        t = targets.get(k, {})
        metrics_table.append({"group": g, "key": k, "label": t.get("label", k), "actual": m[k],
                              "target": t.get("target"), "dir": t.get("dir"), "status": status_of(k, m[k], targets)})
    return m, vol, metrics_table


def breakdown(cases, key, extra=None):
    groups = defaultdict(list)
    for c in cases:
        groups[c.get(key) or "Belum Terklasifikasi"].append(c)
    total = len(cases) or 1
    rows = []
    for name, cs in groups.items():
        sd = [c for c in cs if c.get("sameDay") is not None]
        rows.append({
            "name": name, "count": len(cs), "pct": round(len(cs) / total, 4),
            "open": sum(1 for c in cs if c.get("status") not in ("Resolved", "Closed")),
            "sameDay": _rate(sum(1 for c in sd if c["sameDay"]), len(sd)),
            "avgResolution": _avg([c.get("resolutionMin") for c in cs]),
            "avgFrt": _avg([c.get("frtMin") for c in cs]),
            "slaResponse": _rate(sum(1 for c in cs if c.get("slaResponseOk")),
                                 sum(1 for c in cs if c.get("slaResponseOk") is not None)),
            "biaya": sum(c.get("nilaiKompensasi") or 0 for c in cs),
            "critical": sum(1 for c in cs if c.get("level") == "Critical"),
        })
        if extra:
            rows[-1].update(extra(name, cs))
    rows.sort(key=lambda r: -r["count"])
    return rows


def weekly(cases, start: date, end: date, targets):
    """Minggu = blok 7 hari mulai dari Periode Mulai (sama dengan tab Tren Mingguan)."""
    out = []
    i = 0
    s = start
    while s <= end and i < 12:
        e = min(s + timedelta(days=6), end)
        cs = [c for c in cases if c.get("tanggalMasuk") and s.isoformat() <= c["tanggalMasuk"] <= e.isoformat()]
        m, vol, _ = compute_metrics(cs, targets)
        out.append({"week": f"W{i + 1}", "start": s.isoformat(), "end": e.isoformat(), "contact": vol["contact"],
                    "komplain": vol["komplain"], "frt": m["frt"], "slaResponse": m["slaResponse"],
                    "sameDay": m["sameDay"], "csat": m["csat"], "critical": vol["critical"]})
        s = e + timedelta(days=1)
        i += 1
    return out


def by_hour(cases):
    rows = []
    for h in range(24):
        cs = [c for c in cases if c.get("jamMasuk") == h]
        rows.append({"hour": h, "count": len(cs), "avgFrt": _avg([c.get("frtMin") for c in cs]),
                     "late": sum(1 for c in cs if c.get("slaResponseOk") is False)})
    return rows


def rp(x):
    return f"{int(x or 0):,}".replace(",", ".")


def pct(x):
    return "-" if x is None else f"{round(x * 100)}%"


def insights(cases, m, vol, hours, subj, channels):
    out = {}
    late = [c for c in cases if c.get("slaResponseOk") is False]
    if late:
        eve = sum(1 for c in late if c.get("jamMasuk") is not None and (c["jamMasuk"] >= 19 or c["jamMasuk"] < 8))
        out["hour"] = (f"{round(eve / len(late) * 100)}% respons yang melewati target terjadi pada chat yang masuk "
                       f"≥ 19.00 atau < 08.00 ({eve} dari {len(late)} case).")
    else:
        out["hour"] = "Tidak ada respons yang melewati target pada periode ini."
    if subj:
        top = subj[:2]
        out["subJenis"] = " dan ".join(f"{r['name']} ({r['count']} case, {pct(r['pct'])})" for r in top) + \
                          " menjadi penyumbang komplain terbesar."
    if channels:
        worst = max((r for r in channels if r["avgFrt"] is not None and r["name"] not in ("CSAT Form", "Review Online")),
                    key=lambda r: r["avgFrt"], default=None)
        if worst:
            out["channel"] = f"FRT rata-rata tertinggi ada di {worst['name']} ({worst['avgFrt']:.0f} menit, {worst['count']} case)."
    if vol["countLuarStandard"]:
        out["kompensasi"] = (f"{vol['countLuarStandard']} case memakai kompensasi di luar CRM.STD.001 "
                             f"(Refund/Tidak Ada/di luar level), senilai Rp{rp(vol['biayaLuarStandard'])}.")
    return out


def suggest_insights(cases, m, vol, subj, levels, reviews_summary=None):
    rows = []
    lv = {r["name"]: r for r in levels}
    if levels:
        top = max(levels, key=lambda r: r["count"])
        top_sj = [r for r in subj if r["count"]][:3]
        rows.append({
            "whatHappened": f"{top['count']} dari {vol['komplain']} komplain ({pct(top['pct'])}) berlevel {top['name']}: "
                            + ", ".join(f"{r['name']} {r['count']}" for r in top_sj),
            "why": "Isi dari root cause terbanyak di Case Log",
            "businessImpact": f"Biaya kompensasi level {top['name']} Rp{rp(top['biaya'])}",
            "action": "", "pic": ""})
    crit = [c for c in cases if c.get("level") == "Critical"]
    if crit:
        cnt = Counter(c.get("subJenis") for c in crit)
        outlets = len({c.get("outletName") for c in crit})
        rows.append({
            "whatHappened": f"{len(crit)} komplain Critical: " + ", ".join(f"{k} {v}" for k, v in cnt.most_common(3))
                            + f" di {outlets} outlet",
            "why": "", "businessImpact": "Risiko keamanan pangan dan reputasi", "action": "", "pic": ""})
    if m.get("slaResponse") is not None and m["slaResponse"] < 0.9:
        rows.append({
            "whatHappened": f"SLA Response {pct(m['slaResponse'])} (target 90%), FRT rata-rata {m['frt']} menit",
            "why": "Lihat grafik FRT per jam masuk", "businessImpact": "Customer menunggu jawaban terlalu lama",
            "action": "", "pic": "CRM / CS"})
    if vol["countLuarStandard"]:
        rows.append({
            "whatHappened": f"{vol['countLuarStandard']} case memakai Refund/Tidak Ada (di luar CRM.STD.001)",
            "why": "Bentuk kompensasi belum diatur di standard",
            "businessImpact": f"Rp{rp(vol['biayaLuarStandard'])} di luar standard",
            "action": "Keputusan status Refund", "pic": "Direksi"})
    outside = [r for r in subj if r["name"] in ("Delivery / Ekspedisi", "Driver / Online Platform")]
    if outside:
        n = sum(r["count"] for r in outside)
        rows.append({"whatHappened": f"{n} komplain belum punya klasifikasi di CRM.STD.001 (ekspedisi/driver)",
                     "why": "Standard belum mengatur pengiriman dan platform",
                     "businessImpact": "Level, PJ, dan kompensasi belum baku",
                     "action": "Tambahkan kategori Delivery di revisi CRM.STD.001", "pic": "CRM / CS"})
    return rows[:5]
