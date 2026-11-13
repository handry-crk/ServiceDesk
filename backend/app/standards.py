"""Seed data dari sheet 'Service Excellence Reporting CRK Okt 2026' dan CRM.STD.001 Revisi 00
(efektif 20 Oktober 2026). Semua nilai ini disimpan ke database saat pertama kali jalan dan
bisa diubah CS Lead di menu Pengaturan; kode tidak membaca konstanta ini setelah seed."""

LEVELS = ["Minor", "Major", "Critical"]

PENANGGUNG_JAWAB = {
    "Minor": "Customer Service",
    "Major": "Manager Area",
    "Critical": "Manager / Direksi",
    "Belum Diatur": "CS Lead",
}

# group: dipakai untuk mengelompokkan pilihan di Catat Komplain & ringkasan per sumber di dashboard.
# orderRequired: channel yang hampir selalu punya nomor pesanan → kolom No. Pesanan tampil di form utama.
CHANNELS = [
    {"name": "WhatsApp", "targetFrt": 5, "excellent": 2, "countInSla": True, "group": "Chat & Sosmed"},
    {"name": "Live Chat", "targetFrt": 5, "excellent": 2, "countInSla": True, "group": "Chat & Sosmed"},
    {"name": "IG DM", "targetFrt": 10, "excellent": 5, "countInSla": True, "group": "Chat & Sosmed"},
    {"name": "TikTok DM", "targetFrt": 10, "excellent": 5, "countInSla": True, "group": "Chat & Sosmed"},
    {"name": "Social Comment", "targetFrt": 15, "excellent": 10, "countInSla": True, "group": "Chat & Sosmed"},
    {"name": "Email", "targetFrt": 240, "excellent": 60, "countInSla": True, "group": "Chat & Sosmed"},
    {"name": "Marketplace Chat", "targetFrt": 5, "excellent": 2, "countInSla": True, "group": "Marketplace (Frozen)",
     "orderRequired": True},
    # Online Food Aggregator — target awal 15 menit (asumsi; sesuaikan di Pengaturan → Target & SLA)
    {"name": "GoFood", "targetFrt": 15, "excellent": 10, "countInSla": True, "group": "Online Food Aggregator",
     "orderRequired": True},
    {"name": "GrabFood", "targetFrt": 15, "excellent": 10, "countInSla": True, "group": "Online Food Aggregator",
     "orderRequired": True},
    {"name": "ShopeeFood", "targetFrt": 15, "excellent": 10, "countInSla": True, "group": "Online Food Aggregator",
     "orderRequired": True},
    {"name": "CSAT Form", "targetFrt": 1440, "excellent": None, "countInSla": False, "group": "Survei & Review"},
    {"name": "Review Online", "targetFrt": 1440, "excellent": None, "countInSla": False, "group": "Survei & Review"},
]

STANDARD_DOC = {"code": "CRM.STD.001", "title": "Standar Penanganan Komplain dan Complimentary", "revision": "00",
                "effective": "2026-10-20", "reference": "CRK.QA.P.003 Keluhan Pelanggan; CRK.MMS.003 Manual Sistem Jaminan Produk Halal",
                "considerations": ["Tingkat keluhan/komplain", "Dampak yang dialami pelanggan", "Jumlah produk yang terdampak", "Jarak customer"]}

# Frozen food (Online Frozen Shopee / TikTok)
COURIERS = ["J&T Express", "SPX Standard", "SPX Instan", "Gojek / GoSend Instan", "Grab Instan", "JNE", "SiCepat",
            "AnterAja", "POS Indonesia", "Kurir toko", "Lainnya"]
FROZEN_PRODUCTS = [
    "Paket Jajan Hemat Nikmat 3 Cimol AA isi Mozzarella", "Paket Jajan Hemat Nikmat 3 Cimol AA isi Ayam",
    "Paket AA Mukbang 5 Cimol Isi Mozzarella Daun Jeruk", "Mix 3 pcs Mozza", "Mix 5 pcs Mozza",
    "Mozza AP", "Mozza AB", "Mozza BQ", "Mozza BDO", "Mozza JB", "Ayam AP", "Ayam BQ", "Ayam JB",
    "Cimol Bojot AA Mozzarella Frozen Food",
]
# sub jenis yang perlu kode produksi untuk telusur batch (produk / isi paket)
NEEDS_BATCH = {"Cacat Produksi", "Penurunan Mutu (masih dapat dikonsumsi)", "Penurunan Mutu (tidak dapat dikonsumsi)",
               "Kontaminasi", "Undercooked", "Overcooked", "Keracunan", "Missing Item", "Wrong Item", "Kesalahan Kemasan"}


def normalize_courier(text):
    t = (text or "").lower()
    if not t:
        return None
    if "j&t" in t or "jnt" in t or "j & t" in t:
        return "J&T Express"
    if "spx" in t:
        return "SPX Instan" if "instan" in t else "SPX Standard"
    if "gojek" in t or "gosend" in t or "goto" in t:
        return "Gojek / GoSend Instan"
    if "grab" in t:
        return "Grab Instan"
    if t.strip() in ("pos", "pos indonesia") or "pos indo" in t:
        return "POS Indonesia"
    for c in ("JNE", "SiCepat", "AnterAja"):
        if c.lower() in t:
            return c
    return "Lainnya"


REVIEW_PLATFORMS = ["GoFood", "GrabFood", "ShopeeFood"]

TIPE = ["Komplain", "Inquiry", "Advice and Suggestion"]

PIC_DEPT = [
    "Ops / Outlet", "Kitchen / QC", "Gudang / Packing Frozen", "Logistics / Delivery",
    "Marketing", "Tech / Online Platform", "CRM / CS",
]

# name, jenis, level, contoh, keywords, pic (outlet), pic (frozen), root cause chips
_SJ = [
    ("Penurunan Mutu (masih dapat dikonsumsi)", "Product Quality", "Minor",
     "Produk masam, berubah warna, berjamur, bumbu menggumpal, tetapi masih dapat dikonsumsi",
     "masam asem basi warna jamur menggumpal bau", "Kitchen / QC", "Gudang / Packing Frozen",
     ["Penyimpanan", "Expired", "Bahan baku"]),
    ("Penurunan Mutu (tidak dapat dikonsumsi)", "Product Quality", "Critical",
     "Sudah tidak dapat dikonsumsi, seperti berubah warna dan rasa masam",
     "basi busuk masam asem tidak bisa dimakan spoiled", "Kitchen / QC", "Gudang / Packing Frozen",
     ["Penyimpanan", "Expired", "Rantai dingin", "Bahan baku"]),
    ("Kontaminasi", "Product Quality", "Critical",
     "Kontaminasi bahan haram/najis sehingga produk tidak halal; benda asing (rambut, kertas, kawat, pest, logam, kaca, benda tajam)",
     "rambut benda asing plastik kawat kertas kecoa serangga halal haram najis logam kaca beling tajam paku", "Kitchen / QC", "Gudang / Packing Frozen",
     ["Personal hygiene", "Area produksi", "Kemasan"]),
    ("Cacat Produksi", "Product Quality", "Major",
     "Quantity kurang/lebih, varian dalam satu pack tidak sesuai dengan label kemasan",
     "pcs kurang isi kurang varian label pack", "Kitchen / QC", "Gudang / Packing Frozen",
     ["Produk Kurang", "Varian Salah", "Packing tidak dicek"]),
    ("Overcooked", "Product Quality", "Major", "Produk gosong atau keras",
     "gosong keras alot hangus", "Kitchen / QC", "Kitchen / QC", ["SOP penggorengan", "Minyak", "Suhu"]),
    ("Undercooked", "Product Quality", "Critical", "Raw/finished product belum matang",
     "mentah belum matang lembek dalam keras dalam", "Kitchen / QC", "Kitchen / QC",
     ["SOP penggorengan", "Suhu minyak", "Waktu goreng", "Antrean ramai"]),
    ("Kesalahan Kemasan", "Product Quality", "Minor", "Kesalahan kemasan",
     "kemasan bocor robek kertas mangkok cup segel", "Ops / Outlet", "Gudang / Packing Frozen",
     ["Kemasan rusak", "Jenis kemasan"]),
    ("Hospitality", "Service", "Minor", "Keramahan, etika mitra outlet kepada customer",
     "jutek kasar tidak ramah judes sopan etika", "Ops / Outlet", "CRM / CS", ["Sikap crew", "Training crew"]),
    ("Missing Item", "Service", "Major",
     "Jumlah pesanan kurang saat diterima customer dibanding yang tertera di struk",
     "kurang tidak ada ketinggalan hilang pcs kurang bumbu tidak ada", "Ops / Outlet", "Gudang / Packing Frozen",
     ["Ketelitian Crew", "Produk Kurang", "Packing tidak dicek"]),
    ("Wrong Item", "Service", "Major", "Produk pesanan customer tidak sama dengan yang ada di struk",
     "salah beda tertukar bukan pesanan varian salah", "Ops / Outlet", "Gudang / Packing Frozen",
     ["Ketelitian Crew", "Varian Salah", "Salah input"]),
    ("Payment Issue", "Service", "Major",
     "Uang kembalian tidak sesuai/tidak diberi, double payment (saldo terpotong dua kali), kesalahan hitung pada tagihan, payment cashless tidak masuk",
     "kembalian bayar dua kali double payment saldo terpotong tagihan salah hitung qris transfer", "Ops / Outlet", "Tech / Online Platform",
     ["Kembalian", "QRIS", "Double payment"]),
    ("Jam Operasional", "Service", "Minor", "Jam buka outlet tidak sesuai dengan jadwal jam operasional",
     "tutup belum buka jam buka", "Ops / Outlet", "Ops / Outlet", ["Crew telat", "Stok habis"]),
    ("Queueing System", "Service", "Minor", "Pemasakan dan pemberian pesanan tidak sesuai urutan struk",
     "nyerobot urutan antrean tidak urut", "Ops / Outlet", "Ops / Outlet", ["Pesanan tidak dicatat"]),
    ("Speed of Service", "Service", "Minor", "Customer mengantri terlalu lama",
     "lama nunggu antri lama lambat sejam", "Ops / Outlet", "Ops / Outlet", ["Kurang crew", "Antrean ramai", "Gas habis"]),
    ("Kebersihan Area", "Cleanliness", "Minor",
     "Area outlet kotor, kumuh, tidak ada tempat sampah (area tidak kontak langsung dengan produk)",
     "kotor kumuh sampah gelap lampu", "Ops / Outlet", "Ops / Outlet", ["Kebersihan harian"]),
    ("Kebersihan Area (ada pest)", "Cleanliness", "Critical",
     "Ada pest berkeliaran (lalat, nyamuk, kecoa, tikus, kucing, anjing, dan lain-lain)",
     "lalat tikus kecoa kucing anjing semut", "Ops / Outlet", "Ops / Outlet", ["Pest control"]),
    ("Kebersihan Equipment", "Cleanliness", "Major", "Peralatan yang digunakan terlihat kotor, berkarat, berdebu",
     "alat kotor karat debu wajan minyak hitam", "Ops / Outlet", "Ops / Outlet", ["Kebersihan alat"]),
    ("Personal Hygiene", "Cleanliness", "Minor",
     "Mitra tidak memakai apron, topi, sepatu tertutup, celana panjang (tidak sobek), masker mulut & sarung tangan saat bekerja; aksesoris berlebihan; pakaian provokatif",
     "apron topi masker sarung tangan merokok aksesoris pakaian provokatif grooming", "Ops / Outlet", "Ops / Outlet", ["Grooming"]),
    ("Potential Fraud", "Potential Fraud", "Minor",
     "Menjual produk selain Cimol Bojot AA, menjual produk mentah ke customer, menjual supply Cimol Bojot AA ke pedagang lain, mengatakan hanya menjual porsi tertentu padahal produk & packaging tersedia",
     "porsi kecil tidak ada tidak dikasih bill struk jual lain mentah supply", "Ops / Outlet", "Ops / Outlet", ["Mitra"]),
    ("Social Media Complaint", "Social Media Complaint", "Critical",
     "Komentar publik, story mention, atau viral complain",
     "viral story komentar mention tiktok instagram", "Marketing", "Marketing", ["Viral"]),
    ("Keracunan", "Product Quality", "Critical", "Dugaan keracunan pangan; berpotensi gangguan kesehatan atau cedera (4.3 b & d)",
     "keracunan sakit perut muntah diare mual pusing alergi cedera", "Kitchen / QC", "Kitchen / QC", ["Bahan baku", "Penyimpanan"]),
    ("Perkelahian / Adu Argumen", "Service", "Critical",
     "Terjadi perkelahian atau adu argumen dengan customer, termasuk kejadian yang berpotensi viral",
     "berantem ribut adu argumen marah bentak", "Ops / Outlet", "Ops / Outlet", ["Sikap crew"]),
    ("Delivery / Ekspedisi", "Di Luar Standard", "Belum Diatur",
     "Paket stuck, rusak di perjalanan, atau diretur. Belum diatur di CRM.STD.001",
     "ekspedisi kurir paket stuck retur jnt spx jne", "Logistics / Delivery", "Logistics / Delivery",
     ["Tidak ada update ekspedisi", "Paket rusak", "Retur"]),
    ("Driver / Online Platform", "Di Luar Standard", "Belum Diatur",
     "Driver salah antar atau double order. Belum diatur di CRM.STD.001",
     "driver ojol gojek grab salah antar double order", "Tech / Online Platform", "Tech / Online Platform",
     ["Driver", "Aplikasi"]),
    ("Lainnya: Rasa / Porsi", "Di Luar Standard", "Belum Diatur",
     "Keluhan rasa/porsi/harga yang belum ada di CRM.STD.001 (dipakai untuk Review Online)",
     "rasa hambar bumbu sedikit porsi kecil mahal", "Ops / Outlet", "Ops / Outlet", ["Bumbu", "Porsi"]),
]

# Teks lama (versi awal) — dipakai migrasi: hanya diganti bila belum diubah CS Lead
SUB_JENIS_OLD_TEXT = {'Kontaminasi': ('Kontaminasi bahan haram/najis; benda asing (rambut, kertas, kawat, pest)', 'rambut benda asing plastik kawat kertas kecoa serangga halal najis'), 'Payment Issue': ('Uang kembalian tidak sesuai/tidak diberi, double payment, payment cashless tidak masuk', 'kembalian bayar dua kali double payment qris transfer'), 'Personal Hygiene': ('Mitra tidak memakai apron, topi, sepatu tertutup, celana panjang, masker, sarung tangan; aksesoris berlebihan', 'apron topi masker sarung tangan merokok'), 'Potential Fraud': ('Menjual produk selain Cimol Bojot AA, menjual produk mentah, menjual supply ke pedagang lain, membatasi porsi padahal tersedia', 'porsi kecil tidak ada tidak dikasih bill struk jual lain'), 'Keracunan': ('Dugaan keracunan pangan (4.3 d)', 'keracunan sakit perut muntah diare mual')}

SUB_JENIS = [
    {"name": n, "jenis": j, "level": l, "contoh": c, "keywords": k,
     "picOutlet": po, "picFrozen": pf, "rootCauses": rc, "active": True, "order": i}
    for i, (n, j, l, c, k, po, pf, rc) in enumerate(_SJ)
]

# Bentuk kompensasi (CRM.STD.001 5.1). jenis = bentuk dasar untuk statistik.
KOMPENSASI = [
    {"key": "min-apologize", "level": "Minor", "label": "Apologize", "jenis": "Apologize", "nilai": 0, "standard": True},
    {"key": "min-v5", "level": "Minor", "label": "Voucher Diskon 5K", "jenis": "Voucher", "nilai": 5000, "standard": True, "voucherJenis": "Voucher Diskon 5K"},
    {"key": "maj-apologize", "level": "Major", "label": "Apologize", "jenis": "Apologize", "nilai": 0, "standard": True},
    {"key": "maj-v10", "level": "Major", "label": "Voucher Diskon 10K", "jenis": "Voucher", "nilai": 10000, "standard": True, "voucherJenis": "Voucher Diskon 10K"},
    {"key": "maj-v5", "level": "Major", "label": "Voucher Diskon 5K (salah level pedas/topping)", "jenis": "Voucher", "nilai": 5000, "standard": True, "voucherJenis": "Voucher Diskon 5K"},
    {"key": "maj-replacement", "level": "Major", "label": "Replacement (porsi baru)", "jenis": "Replacement", "nilai": 0, "standard": True},
    {"key": "maj-comp", "level": "Major", "label": "Complimentary 1 menu setara (salah produk)", "jenis": "Complimentary", "nilai": 0, "standard": True},
    {"key": "cri-apologize", "level": "Critical", "label": "Apologize", "jenis": "Apologize", "nilai": 0, "standard": True},
    {"key": "cri-kit1", "level": "Critical", "label": "Replacement + Complimentary Kit 1 (spoiled/benda asing)", "jenis": "Complimentary", "nilai": 0, "standard": True},
    {"key": "cri-kit2", "level": "Critical", "label": "Complimentary Kit 2 (perkelahian/berpotensi viral)", "jenis": "Complimentary", "nilai": 0, "standard": True},
    {"key": "cri-kit3", "level": "Critical", "label": "Complimentary Kit 3 (health/safety incident)", "jenis": "Complimentary", "nilai": 0, "standard": True},
    {"key": "cri-medis", "level": "Critical", "label": "Cover Pengobatan", "jenis": "Cover Pengobatan", "nilai": 0, "standard": True},
    {"key": "all-refund", "level": "Semua", "label": "Refund", "jenis": "Refund", "nilai": 0, "standard": False},
    {"key": "all-none", "level": "Semua", "label": "Tidak Ada", "jenis": "Tidak Ada", "nilai": 0, "standard": False},
]

TARGETS = {
    "frt": {"label": "FRT rata-rata (menit)", "target": 5, "dir": "max"},
    "slaResponse": {"label": "% SLA Response", "target": 0.90, "dir": "min"},
    "avgResolution": {"label": "Avg Resolution Time (menit)", "target": 120, "dir": "max"},
    "resolutionSla": {"label": "% Resolution sesuai SLA", "target": 0.90, "dir": "min"},
    "sameDay": {"label": "% Same-Day Resolution", "target": 0.90, "dir": "min"},
    "fcr": {"label": "First Contact Resolution", "target": 0.80, "dir": "min"},
    "compSuccess": {"label": "Complimentary Success Rate", "target": 0.95, "dir": "min"},
    "reopen": {"label": "Reopen Rate", "target": 0.05, "dir": "max"},
    "csat": {"label": "CSAT (% puas)", "target": 0.90, "dir": "min"},
}

RESOLUTION_TARGET = {"Minor": 1440, "Major": 2880, "Critical": 4320}
CRITICAL_FRT = 30

SETTINGS = {
    "opStart": "08:00",          # jam operasional CS — konfirmasi CS Lead
    "opEnd": "22:00",
    "workDays": [0, 1, 2, 3, 4, 5],   # hari kerja CS (0 = Senin … 6 = Minggu); Minggu libur
    "holidays": [],                   # tanggal libur CS, format YYYY-MM-DD
    "voucherExpiryDays": 30,
    "alertCriticalAfterMin": 20,
    "emailRecipients": [],
    "appName": "CRK Service Desk",
    # integritas waktu (anti mundur-jam)
    "frGraceMin": 15,           # mundur ≤ N menit langsung diterima (tetap bertanda manual)
    "frMaxBackMin": 120,        # CS maksimal mundurkan jam dibalas N menit; lebih → CRM Supervisor
    "frEditHours": 24,          # CS hanya bisa ubah jam dibalas dalam N jam, sekali per case
    "masukLagReasonMin": 30,    # waktu masuk > N menit sebelum dicatat → wajib alasan
    "manualAlertPct": 0.15,     # notifikasi bila % jam manual seorang CS di atas ini (7 hari)
    "auditSamplePerCs": 5,      # audit acak mingguan per CS
}

VOUCHER_JENIS = ["Voucher Diskon 5K", "Voucher Diskon 10K", "Free Produk Porsi Besar", "Free Produk Porsi Kecil"]

# Daftar outlet dari sheet Master Data (kolom Outlet)
OUTLETS = [
    "Kios Serpong Cisauk", "Kios Ceger Raya Tangsel", "Kios Grand Galaxy Park", "Bhayangkara 1",
    "Central Kitchen Tanjung Duren", "Perumnas 3 Bekasi", "Kios Jombang Raya", "Pondok Petir", "Kios Benda Raya",
    "Kios Tole Iskandar", "Gunung Batu", "Online Frozen (Tiktok 2)", "Online Frozen (Shopee)", "Pasar Slipi",
    "Pengadegan Selatan", "Kencana Bogor", "Bangka Raya 2", "Zamrud Bekasi", "Raya Sukahati Bogor", "Kosambi",
    "Saparua", "Duri Kosambi", "Puri CNI", "Kios Margonda", "Kios Karang Asih", "Cimahpar", "Panyileukan",
    "Raya Tonjong", "Jatinangor", "Bendungan Walahar", "Stasiun Tanjung Barat", "RSUD Cengkareng", "Lokasari",
    "Pondok Rangon", "Naga Jatiwaringin", "Peta Barat", "Kerkof Cimahi", "Metland Cileungsi", "Pasar Cijeruk",
    "Irigasi Pekayon", "Kemang Raya Bekasi", "Kios Suryakencana", "Jagakarsa", "Sumatra (Tangsel)", "Cingised",
    "UPI 2", "Ujung Berung", "Menceng Raya", "Kartini Raya", "Pahlawan 2", "Puri Jaya Tangerang",
    "Kios Permata Cimahi", "Villa Kencana Sukatani", "Kalibaru Cilincing",
    "Kemang Raya 4 Gacoan", "Kurdi", "Central Kitchen Meruya", "Mekarsari Depok",
]

# Outlet baru: ditambahkan otomatis ke database yang sudah berjalan (bila namanya belum ada)
NEW_OUTLETS = {"Kemang Raya 4 Gacoan": "Belum diatur", "Kurdi": "Bandung",
               "Central Kitchen Meruya": "Jakarta", "Mekarsari Depok": "Depok"}

AREAS = ["Jakarta", "Bandung", "Bekasi", "Depok", "Bogor", "Tangsel", "Tangerang", "Cimahi", "Online", "Belum diatur"]

_AREA_HINTS = [
    ("mekarsari", "Depok"), ("meruya", "Jakarta"), ("kurdi", "Bandung"),
    ("online", "Online"), ("bekasi", "Bekasi"), ("pekayon", "Bekasi"), ("jatiwaringin", "Bekasi"),
    ("karang asih", "Bekasi"), ("sukatani", "Bekasi"), ("cileungsi", "Bogor"), ("bogor", "Bogor"),
    ("cimahpar", "Bogor"), ("suryakencana", "Bogor"), ("cijeruk", "Bogor"), ("pahlawan", "Bogor"),
    ("tangsel", "Tangsel"), ("serpong", "Tangsel"), ("pondok petir", "Depok"), ("margonda", "Depok"),
    ("tangerang", "Tangerang"), ("cimahi", "Cimahi"), ("panyileukan", "Bandung"), ("jatinangor", "Bandung"),
    ("ujung berung", "Bandung"), ("upi", "Bandung"), ("saparua", "Bandung"), ("cingised", "Bandung"),
    ("tanjung duren", "Jakarta"), ("slipi", "Jakarta"), ("pengadegan", "Jakarta"), ("cengkareng", "Jakarta"),
    ("lokasari", "Jakarta"), ("jagakarsa", "Jakarta"), ("tanjung barat", "Jakarta"), ("cilincing", "Jakarta"),
    ("kosambi", "Jakarta"), ("pondok rangon", "Jakarta"), ("bangka", "Jakarta"), ("gunung batu", "Bogor"),
]


def outlet_type(name: str) -> str:
    n = name.lower()
    if n.startswith("online frozen"):
        return "online_frozen"
    if n.startswith("central kitchen"):
        return "central_kitchen"
    if n.startswith("kios"):
        return "kios"
    return "gerobak"


def guess_area(name: str) -> str:
    n = name.lower()
    for hint, area in _AREA_HINTS:
        if hint in n:
            return area
    return "Belum diatur"
