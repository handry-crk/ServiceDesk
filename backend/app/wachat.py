"""Baca chat WhatsApp yang disalin (WhatsApp Web/Desktop) atau hasil 'Export chat' (Android / iPhone).

Contoh baris yang dikenali:
  [19.41, 16/11/2026] Budi: halo kak
  [7:41 PM, 11/16/2026] Budi: halo kak
  16/11/26 19.41 - Budi: halo kak
  16/11/2026, 19:41 - Budi: halo kak
  [16/11/26 19.41.22] Budi: halo kak
Tanggal dibaca hari/bulan (format Indonesia) kecuali jelas bulan/hari.
"""
import re
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))
_CLEAN = re.compile(r"[‎‏‪-‮⁦-⁩﻿]")
_SP = re.compile(r"[   ]")
_T = r"(\d{1,2})[.:](\d{2})(?:[.:](\d{2}))?\s*([AaPp]\.?[Mm]\.?)?"
_D = r"(\d{1,2})/(\d{1,2})/(\d{2,4})"
P_WEB = re.compile(r"^\[" + _T + r",\s*" + _D + r"\]\s*([^:]{1,60}?):\s?(.*)$")
P_EXP = re.compile(r"^\[?" + _D + r",?\s+" + _T + r"\]?\s*(?:-\s*)?([^:]{1,60}?):\s?(.*)$")
PHONE = re.compile(r"^\+?\d[\d\s\-()]{7,}$")


def _dt(h, mi, ap, a, b, y):
    h, mi, a, b, y = int(h), int(mi), int(a), int(b), int(y)
    if y < 100:
        y += 2000
    if ap:
        ap = ap.lower().replace(".", "")
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
    day, mon = (a, b) if (a > 12 or b <= 12) else (b, a)
    if mon > 12:
        day, mon = mon, day
    return datetime(y, mon, day, h, mi, tzinfo=WIB)


def parse_chat(text):
    """Kembalikan daftar pesan [{at, sender, text}] berurutan sesuai teks."""
    msgs = []
    for raw in (text or "").splitlines():
        line = _SP.sub(" ", _CLEAN.sub("", raw)).strip()
        if not line:
            continue
        m = P_WEB.match(line)
        try:
            if m:
                h, mi, _s, ap, a, b, y, who, body = m.groups()
                at = _dt(h, mi, ap, a, b, y)
            else:
                m = P_EXP.match(line)
                if not m:
                    if msgs:
                        msgs[-1]["text"] += "\n" + line
                    continue
                a, b, y, h, mi, _s, ap, who, body = m.groups()
                at = _dt(h, mi, ap, a, b, y)
        except ValueError:
            continue
        msgs.append({"at": at, "sender": who.strip(), "text": body.strip()})
    return msgs


_G = re.compile(r"(?:(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})|(\d{1,2})([-/.])(\d{1,2})(?:[-/.](\d{2,4}))?)[ ,T]+(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp][Mm])?")


def parse_generic(text):
    """Platform lain (Douke, seller center, dll.): baris judul berisi nama + tanggal-jam, diikuti isi pesan.
    Contoh: 'Budi 2026-11-18 10:02:11', '2026-11-18 10:02 CS Aliya', atau nama dan tanggal-jam di baris terpisah."""
    msgs, prev = [], None
    year = datetime.now(WIB).year
    for raw in (text or "").splitlines():
        line = _SP.sub(" ", _CLEAN.sub("", raw)).strip()
        if not line:
            continue
        m = _G.search(line)
        head = m and len(line) - (m.end() - m.start()) <= 45
        if not head:
            if msgs:
                msgs[-1]["text"] = (msgs[-1]["text"] + "\n" + line).strip()
            prev = line
            continue
        y, mo, d, a, sep, b, y2, h, mi, ap = m.groups()
        try:
            if y:
                y, mo, d = int(y), int(mo), int(d)
            else:
                a, b = int(a), int(b)
                y = int(y2) if y2 else year
                y = y + 2000 if y < 100 else y
                # 'MM-DD' (gaya aplikasi marketplace) bila tanpa tahun & pakai '-', selain itu DD/MM
                mo, d = (a, b) if (not y2 and sep == "-") else (b, a)
                if mo > 12:
                    mo, d = d, mo
            h, mi = int(h), int(mi)
            if ap:
                ap = ap.lower()
                h = h + 12 if (ap == "pm" and h < 12) else 0 if (ap == "am" and h == 12) else h
            at = datetime(y, mo, d, h, mi, tzinfo=WIB)
        except ValueError:
            continue
        who = (line[:m.start()] + " " + line[m.end():]).strip(" -:|·,[]()")
        if not who and prev and len(prev) <= 45:
            who = prev
            if msgs and msgs[-1]["text"].endswith(prev):   # baris nama terlanjur menempel ke pesan sebelumnya
                msgs[-1]["text"] = msgs[-1]["text"][:-len(prev)].strip()
        msgs.append({"at": at, "sender": who or "Tanpa nama", "text": ""})
        prev = None
    return msgs if len(msgs) >= 2 else []


def analyze(text, customer=None):
    """Waktu masuk = pesan pertama customer; dibalas = pesan pertama pihak lain sesudahnya."""
    msgs = parse_chat(text) or parse_generic(text)
    if not msgs:
        return {"messages": 0}
    senders = []
    for x in msgs:
        if x["sender"] not in senders:
            senders.append(x["sender"])
    cust = customer if customer in senders else senders[0]
    masuk = next((x for x in msgs if x["sender"] == cust), None)
    fr = next((x for x in msgs if masuk and x["sender"] != cust and x["at"] >= masuk["at"]), None)
    first_text = " ".join(x["text"] for x in msgs if x["sender"] == cust)[:300]
    return {
        "messages": len(msgs), "senders": senders, "customer": cust,
        "masuk": masuk["at"] if masuk else None, "dibalas": fr["at"] if fr else None,
        "terakhir": msgs[-1]["at"], "customerText": first_text,
        "customerPhone": cust if PHONE.match(cust or "") else None,
    }
