"""
🏢 MARKAZIY REGISTR — AIMARKETNM_BOT SaaS yadrosi
==================================================

Bu modul barcha bizneslar (tenant) haqidagi ma'lumotni saqlaydi va
ikkita bot uni birgalikda ishlatadi:

  • admin_bot.py — yozadi (biznes ochish, modul yoqish, to'lov qayd etish)
  • bot.py       — o'qiydi (bu foydalanuvchi qaysi biznesniki? qaysi modul
                   yoqilgan? litsenziya amal qiladimi?)

Tenantning ISH ma'lumotlari (xodimlar, vazifalar, savdo...) bu yerda EMAS —
ular har bir biznes uchun alohida SQLite faylda: tenants/<slug>.db

Bito API kaliti shifrlangan holda saqlanadi (MASTER_KEY muhit o'zgaruvchisi).
"""

import os
import re
import sqlite3
import string
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

UZT = timezone(timedelta(hours=5))

# ─────────────────────────── Yo'llar ───────────────────────────

_BASE = "/data" if os.path.isdir("/data") else os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))

CENTRAL_DB = os.getenv("CENTRAL_DB_PATH") or os.path.join(_BASE, "central.db")
TENANTS_DIR = os.getenv("TENANTS_DIR") or os.path.join(_BASE, "tenants")

os.makedirs(TENANTS_DIR, exist_ok=True)


def now_dt():
    return datetime.now(UZT)


def now_str():
    return now_dt().strftime("%Y-%m-%d %H:%M:%S")


def today_str():
    return now_dt().strftime("%Y-%m-%d")


# ───────────────────── Shifrlash (Bito kaliti) ─────────────────────

def _fernet():
    """MASTER_KEY dan Fernet yaratadi.

    MASTER_KEY berilmagan bo'lsa — DB yonidagi .master_key faylidan o'qiydi,
    u ham bo'lmasa yaratadi. Railway'da MASTER_KEY ni Variables'ga qo'ying,
    aks holda volume yo'qolsa barcha Bito kalitlari o'qib bo'lmas holga keladi.
    """
    from cryptography.fernet import Fernet
    key = os.getenv("MASTER_KEY", "").strip()
    if not key:
        keyfile = os.path.join(_BASE, ".master_key")
        if os.path.exists(keyfile):
            key = open(keyfile).read().strip()
        else:
            key = Fernet.generate_key().decode()
            with open(keyfile, "w") as f:
                f.write(key)
            os.chmod(keyfile, 0o600)
            print(f"⚠️  MASTER_KEY yaratildi va {keyfile} ga yozildi. "
                  f"Uni Railway Variables'ga ko'chiring!", flush=True)
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(text):
    if not text:
        return ""
    return _fernet().encrypt(text.encode()).decode()


def decrypt(token):
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except Exception as e:
        print(f"❌ CENTRAL: kalitni ochib bo'lmadi ({str(e)[:60]}). "
              f"MASTER_KEY o'zgarganmi?", flush=True)
        return ""


# ─────────────────────────── Ulanish ───────────────────────────

_conn = None
_lock = threading.RLock()


def _db():
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(CENTRAL_DB, check_same_thread=False)
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        _conn.row_factory = sqlite3.Row
    return _conn


def q(sql, params=()):
    with _lock:
        try:
            cur = _db().execute(sql, params)
            _db().commit()
            return cur
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                print("CENTRAL DB ERR:", str(e)[:160], "| SQL:", sql[:80], flush=True)
            return None


def qone(sql, params=()):
    with _lock:
        c = q(sql, params)
        return c.fetchone() if c else None


def qall(sql, params=()):
    with _lock:
        c = q(sql, params)
        return c.fetchall() if c else []


# ─────────────────────────── Sxema ───────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    slug          TEXT UNIQUE NOT NULL,
    name          TEXT NOT NULL,
    owner_phone   TEXT NOT NULL,
    owner_name    TEXT DEFAULT '',
    owner_tg_id   INTEGER,
    status        TEXT DEFAULT 'trial',
    db_file       TEXT,
    timezone      TEXT DEFAULT 'Asia/Tashkent',
    shop_lat      REAL, shop_lon REAL,
    review_secret TEXT,
    contact_phone TEXT DEFAULT '', work_hours TEXT DEFAULT '',
    plan          TEXT DEFAULT '',
    created_at    TEXT, created_by INTEGER, notes TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS tenant_bito (
    tenant_id      INTEGER PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    api_key_enc    TEXT DEFAULT '',
    org_id         TEXT DEFAULT '', warehouse_id TEXT DEFAULT '',
    currency_id    TEXT DEFAULT '', sale_price_id TEXT DEFAULT '',
    plu_field_id   TEXT DEFAULT '', kg_measure_id TEXT DEFAULT '',
    default_uom_id TEXT DEFAULT '', box_type_id TEXT DEFAULT '',
    wo_reason_id   TEXT DEFAULT '',
    verified_at    TEXT, last_error TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS modules (
    code        TEXT PRIMARY KEY,
    name        TEXT, description TEXT,
    price       INTEGER DEFAULT 0,
    is_core     INTEGER DEFAULT 0,
    needs_bito  INTEGER DEFAULT 0,
    ai_cost     INTEGER DEFAULT 0,
    sort_order  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tenant_modules (
    tenant_id   INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
    module_code TEXT,
    enabled     INTEGER DEFAULT 1,
    price       INTEGER,
    enabled_at  TEXT, disabled_at TEXT,
    PRIMARY KEY (tenant_id, module_code)
);

CREATE TABLE IF NOT EXISTS licenses (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id  INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
    starts_at  TEXT, ends_at TEXT,
    period     TEXT, amount INTEGER DEFAULT 0,
    status     TEXT DEFAULT 'active',
    created_at TEXT, created_by INTEGER
);

CREATE TABLE IF NOT EXISTS payments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id    INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
    amount       INTEGER, paid_at TEXT,
    method       TEXT DEFAULT '', period_label TEXT DEFAULT '',
    note         TEXT DEFAULT '', recorded_by INTEGER
);

CREATE TABLE IF NOT EXISTS tenant_users (
    tg_id     INTEGER PRIMARY KEY,
    tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
    role_hint TEXT DEFAULT 'employee',
    joined_at TEXT
);

CREATE TABLE IF NOT EXISTS invites (
    token      TEXT PRIMARY KEY,
    tenant_id  INTEGER REFERENCES tenants(id) ON DELETE CASCADE,
    role       TEXT DEFAULT 'employee',
    max_uses   INTEGER DEFAULT 0,
    used_count INTEGER DEFAULT 0,
    expires_at TEXT, created_at TEXT, created_by INTEGER
);

CREATE TABLE IF NOT EXISTS ai_usage (
    tenant_id INTEGER, day TEXT, provider TEXT DEFAULT '',
    calls INTEGER DEFAULT 0, tokens INTEGER DEFAULT 0,
    PRIMARY KEY (tenant_id, day, provider)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT, actor_tg_id INTEGER, tenant_id INTEGER,
    action TEXT, detail TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_tu_tenant   ON tenant_users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_lic_tenant  ON licenses(tenant_id, ends_at);
CREATE INDEX IF NOT EXISTS idx_pay_tenant  ON payments(tenant_id, paid_at);
CREATE INDEX IF NOT EXISTS idx_inv_tenant  ON invites(tenant_id);
"""

# Modul katalogi — arxitektura hujjatining 5-bo'limi bilan bir xil.
# (kod, nom, tavsif, narx, majburiymi, bito kerakmi, ai xarajati, tartib)
DEFAULT_MODULES = [
    ("core", "⚙️ Yadro",
     "Ro'yxatdan o'tish, rollar, tasdiqlash, sozlamalar, menyu sozlash, "
     "Excel eksport, veb-ilova (PWA) va dashboard",
     200_000, 1, 0, 0, 0),
    ("jamoa", "👥 Jamoa",
     "GPS kelish/ketish, davomat, haftalik jadval, ish haqi (soat/savdo/ball), "
     "vazifa berish, foto hisobot, ball va jarima, reyting, kunlik testlar",
     300_000, 0, 0, 0, 1),
    ("mijozlar", "⭐ Mijozlar",
     "QR orqali baholash, takliflar va shikoyatlar, guruh chat, "
     "mijozlar ABC-XYZ segmentatsiyasi va avtomatik vazifa qoidalari",
     250_000, 0, 0, 0, 2),
    ("moliya", "💵 Savdo va moliya",
     "Savdo hisobotlari, oylik reja, pul taqvimi, firmalar va qarzlar, "
     "doimiy xarajatlar, zakaz limiti",
     400_000, 0, 1, 0, 3),
    ("ombor", "📦 Ombor",
     "Qoldiq nazorati va ogohlantirish, inventarizatsiya, "
     "zarur mahsulotlar ro'yxati, PLU (tarozi) kodlari",
     350_000, 0, 1, 0, 4),
    ("taminot", "📥 Ta'minot",
     "Nakladnoyni AI bilan o'qish, mahsulot moslashtirish, Bito'ga kirim, "
     "zakaz tavsiyasi, ta'minotchi jadvali",
     500_000, 0, 1, 1, 5),
    ("ai", "🤖 AI yordamchi",
     "AI maslahat chati, ovozli buyruq, kunlik AI tavsiya, AI agent, "
     "maqsadlar va bosqichlar, ishga qabul + AI intervyu",
     450_000, 0, 0, 1, 6),
    ("marketing", "📣 Marketing",
     "Aksiya va oddiy postlar, AI matn va poster, Telegram kanal va Instagram, "
     "post jadvali, marketing tahlili",
     350_000, 0, 1, 1, 7),
]

PACKAGES = {
    "boshlangich": ("Boshlang'ich", ["core", "jamoa", "mijozlar"], 650_000),
    "biznes": ("Biznes", ["core", "jamoa", "mijozlar", "moliya", "ombor"], 1_300_000),
    "premium": ("Premium", [m[0] for m in DEFAULT_MODULES], 2_200_000),
}

TRIAL_DAYS = int(os.getenv("TRIAL_DAYS", "14"))
GRACE_DAYS = int(os.getenv("GRACE_DAYS", "3"))


def init_central():
    """Sxemani yaratadi va modul katalogini to'ldiradi (mavjudini buzmaydi)."""
    with _lock:
        _db().executescript(SCHEMA)
        _db().commit()
    for code, name, desc, price, core, bito, ai, order_ in DEFAULT_MODULES:
        if not qone("SELECT code FROM modules WHERE code=?", (code,)):
            q("""INSERT INTO modules
                 (code,name,description,price,is_core,needs_bito,ai_cost,sort_order)
                 VALUES (?,?,?,?,?,?,?,?)""",
              (code, name, desc, price, core, bito, ai, order_))
        else:
            # narxdan boshqasini yangilab turamiz (narx qo'lda o'zgartirilgan bo'lishi mumkin)
            q("""UPDATE modules SET name=?,description=?,is_core=?,needs_bito=?,
                 ai_cost=?,sort_order=? WHERE code=?""",
              (name, desc, core, bito, ai, order_, code))
    return True


# ─────────────────────────── Slug ───────────────────────────

_TRANSLIT = {"ʻ": "", "'": "", "‘": "", "’": "", "`": "", "ў": "u", "қ": "q",
             "ғ": "g", "ҳ": "h", "ш": "sh", "ч": "ch", "я": "ya", "ю": "yu"}

RESERVED_SLUGS = {"admin", "start", "help", "bot", "api", "app", "webapp",
                  "dashboard", "system", "root", "test"}


def make_slug(name):
    """'Apelsin Market' → 'apelsinmarket'. Telegram start-payload uchun xavfsiz."""
    s = (name or "").strip().lower()
    for a, b in _TRANSLIT.items():
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s[:32]


def slug_available(slug):
    if not slug or len(slug) < 3 or len(slug) > 32:
        return False, "Slug 3-32 belgidan iborat bo'lishi kerak"
    if not re.fullmatch(r"[a-z0-9]+", slug):
        return False, "Faqat kichik lotin harflari va raqamlar"
    if slug in RESERVED_SLUGS:
        return False, "Bu nom band (tizim uchun ajratilgan)"
    if qone("SELECT id FROM tenants WHERE slug=?", (slug,)):
        return False, "Bu slug allaqachon ishlatilgan"
    return True, ""


def _token(n=6):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(n))


def norm_phone(p):
    """'+998 90 123-45-67' → '998901234567'"""
    d = re.sub(r"\D", "", p or "")
    if len(d) == 9:
        d = "998" + d
    return d


# ─────────────────────── Tenant CRUD ───────────────────────

def create_tenant(name, slug, owner_phone, owner_name="", modules=None,
                  trial_days=None, plan="", created_by=0):
    ok, err = slug_available(slug)
    if not ok:
        raise ValueError(err)

    db_file = f"{slug}.db"
    q("""INSERT INTO tenants
         (slug,name,owner_phone,owner_name,status,db_file,review_secret,
          plan,created_at,created_by)
         VALUES (?,?,?,?,'trial',?,?,?,?,?)""",
      (slug, name, norm_phone(owner_phone), owner_name, db_file,
       f"R{_token(10)}", plan, now_str(), created_by))
    row = qone("SELECT id FROM tenants WHERE slug=?", (slug,))
    tid = row["id"]

    q("INSERT OR IGNORE INTO tenant_bito (tenant_id) VALUES (?)", (tid,))

    for code in (modules or ["core"]):
        set_module(tid, code, True)
    set_module(tid, "core", True)  # yadro har doim yoqilgan

    days = TRIAL_DAYS if trial_days is None else trial_days
    start_license(tid, days=days, period="trial", amount=0, created_by=created_by)
    log(created_by, tid, "tenant_created", f"{name} ({slug})")
    return tid


def get_tenant(tid):
    return qone("SELECT * FROM tenants WHERE id=?", (tid,))


def get_tenant_by_slug(slug):
    return qone("SELECT * FROM tenants WHERE slug=?", (slug,))


def get_tenant_by_phone(phone):
    return qone("SELECT * FROM tenants WHERE owner_phone=?", (norm_phone(phone),))


def list_tenants(status=None):
    if status:
        return qall("SELECT * FROM tenants WHERE status=? ORDER BY name", (status,))
    return qall("SELECT * FROM tenants ORDER BY name")


def update_tenant(tid, **fields):
    allowed = {"name", "owner_phone", "owner_name", "owner_tg_id", "status",
               "shop_lat", "shop_lon", "contact_phone", "work_hours",
               "plan", "notes", "timezone"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(norm_phone(v) if k == "owner_phone" else v)
    if not sets:
        return False
    vals.append(tid)
    q(f"UPDATE tenants SET {', '.join(sets)} WHERE id=?", tuple(vals))
    _bust_cache()
    return True


def tenant_db_path(slug):
    return os.path.join(TENANTS_DIR, f"{slug}.db")


# ─────────────────────── Foydalanuvchi ↔ tenant ───────────────────────

_cache = {"users": {}, "modules": {}, "lic": {}, "at": 0.0}
CACHE_TTL = 30.0


def _bust_cache():
    _cache["users"].clear()
    _cache["modules"].clear()
    _cache["lic"].clear()
    _cache["at"] = 0.0


def _cache_ok():
    if time.time() - _cache["at"] > CACHE_TTL:
        _cache["users"].clear()
        _cache["modules"].clear()
        _cache["lic"].clear()
        _cache["at"] = time.time()


def bind_user(tg_id, tenant_id, role_hint="employee"):
    q("""INSERT INTO tenant_users (tg_id,tenant_id,role_hint,joined_at)
         VALUES (?,?,?,?)
         ON CONFLICT(tg_id) DO UPDATE SET tenant_id=excluded.tenant_id,
                                          role_hint=excluded.role_hint""",
      (tg_id, tenant_id, role_hint, now_str()))
    _bust_cache()


def unbind_user(tg_id):
    q("DELETE FROM tenant_users WHERE tg_id=?", (tg_id,))
    _bust_cache()


def tenant_of_user(tg_id):
    """tg_id → tenant qatori (yoki None). Keshlanadi."""
    _cache_ok()
    if tg_id in _cache["users"]:
        return _cache["users"][tg_id]
    row = qone("""SELECT t.* FROM tenants t
                  JOIN tenant_users u ON u.tenant_id = t.id
                  WHERE u.tg_id=?""", (tg_id,))
    _cache["users"][tg_id] = row
    return row


def slug_of_user(tg_id):
    t = tenant_of_user(tg_id)
    return t["slug"] if t else None


def tenant_user_count(tid):
    r = qone("SELECT COUNT(*) c FROM tenant_users WHERE tenant_id=?", (tid,))
    return r["c"] if r else 0


# ─────────────────────── Modullar ───────────────────────

def all_modules():
    return qall("SELECT * FROM modules ORDER BY sort_order")


def module_info(code):
    return qone("SELECT * FROM modules WHERE code=?", (code,))


def set_module(tid, code, enabled, price=None):
    m = module_info(code)
    if not m:
        return False
    if m["is_core"] and not enabled:
        return False  # yadroni o'chirib bo'lmaydi
    q("""INSERT INTO tenant_modules (tenant_id,module_code,enabled,price,enabled_at)
         VALUES (?,?,?,?,?)
         ON CONFLICT(tenant_id,module_code) DO UPDATE SET
             enabled=excluded.enabled,
             price=COALESCE(excluded.price, tenant_modules.price),
             enabled_at=CASE WHEN excluded.enabled=1 THEN ? ELSE tenant_modules.enabled_at END,
             disabled_at=CASE WHEN excluded.enabled=0 THEN ? ELSE NULL END""",
      (tid, code, 1 if enabled else 0,
       price if price is not None else m["price"], now_str(),
       now_str(), now_str()))
    _bust_cache()
    return True


def enabled_modules(tid):
    """Yoqilgan modul kodlari to'plami. Keshlanadi."""
    _cache_ok()
    if tid in _cache["modules"]:
        return _cache["modules"][tid]
    rows = qall("""SELECT module_code FROM tenant_modules
                   WHERE tenant_id=? AND enabled=1""", (tid,))
    s = {r["module_code"] for r in rows}
    s.add("core")
    _cache["modules"][tid] = s
    return s


def has_module(tid, code):
    if not code:
        return True
    return code in enabled_modules(tid)


def apply_package(tid, package_key):
    """Paketni qo'llaydi: paketdagilar yoqiladi, qolganlari o'chiriladi."""
    pkg = PACKAGES.get(package_key)
    if not pkg:
        return False
    _, codes, _price = pkg
    for m in all_modules():
        set_module(tid, m["code"], m["code"] in codes)
    update_tenant(tid, plan=package_key)
    return True


def monthly_price(tid):
    """Shu tenantning oylik hisobi. Paket bo'lsa — paket narxi."""
    t = get_tenant(tid)
    if t and t["plan"] in PACKAGES:
        pkg_name, codes, price = PACKAGES[t["plan"]]
        extra = sum(
            (r["price"] if r["price"] is not None else 0)
            for r in qall("""SELECT price, module_code FROM tenant_modules
                             WHERE tenant_id=? AND enabled=1""", (tid,))
            if r["module_code"] not in codes)
        return price + extra
    rows = qall("""SELECT COALESCE(tm.price, m.price) p
                   FROM tenant_modules tm JOIN modules m ON m.code=tm.module_code
                   WHERE tm.tenant_id=? AND tm.enabled=1""", (tid,))
    return sum(r["p"] or 0 for r in rows)


# ─────────────────────── Litsenziya ───────────────────────

def start_license(tid, days=None, months=0, period="monthly", amount=0,
                  created_by=0):
    """Yangi litsenziya davri. Mavjud muddat tugamagan bo'lsa — ustiga qo'shiladi."""
    cur = current_license(tid)
    base = now_dt()
    if cur:
        try:
            end = datetime.strptime(cur["ends_at"], "%Y-%m-%d").replace(tzinfo=UZT)
            if end > base:
                base = end
        except Exception:
            pass
    if months:
        # oy ≈ 30 kun (kalendar oy kerak bo'lsa dateutil qo'shiladi)
        days = months * 30
    ends = (base + timedelta(days=days or 30)).strftime("%Y-%m-%d")
    q("""INSERT INTO licenses
         (tenant_id,starts_at,ends_at,period,amount,status,created_at,created_by)
         VALUES (?,?,?,?,?,'active',?,?)""",
      (tid, today_str(), ends, period, amount, now_str(), created_by))
    q("UPDATE licenses SET status='expired' WHERE tenant_id=? AND ends_at<? AND status='active'",
      (tid, today_str()))
    update_tenant(tid, status="trial" if period == "trial" else "active")
    _bust_cache()
    log(created_by, tid, "license_extended", f"{period} → {ends}")
    return ends


def current_license(tid):
    return qone("""SELECT * FROM licenses WHERE tenant_id=?
                   ORDER BY ends_at DESC LIMIT 1""", (tid,))


def license_state(tid):
    """('trial'|'active'|'grace'|'locked'|'suspended', qolgan_kun, tugash_sanasi)"""
    _cache_ok()
    if tid in _cache["lic"]:
        return _cache["lic"][tid]

    t = get_tenant(tid)
    if not t:
        res = ("locked", 0, "")
        _cache["lic"][tid] = res
        return res
    if t["status"] == "suspended":
        res = ("suspended", 0, "")
        _cache["lic"][tid] = res
        return res

    lic = current_license(tid)
    if not lic:
        res = ("locked", 0, "")
        _cache["lic"][tid] = res
        return res

    try:
        end = datetime.strptime(lic["ends_at"], "%Y-%m-%d").replace(tzinfo=UZT)
    except Exception:
        res = ("locked", 0, lic["ends_at"])
        _cache["lic"][tid] = res
        return res

    left = (end - now_dt()).days
    if left >= 0:
        state = "trial" if lic["period"] == "trial" else "active"
    elif left >= -GRACE_DAYS:
        state = "grace"
    else:
        state = "locked"
    res = (state, left, lic["ends_at"])
    _cache["lic"][tid] = res
    return res


def is_readonly(tid):
    """True bo'lsa — yozish/AI/Bito amallari taqiqlanadi ('faqat ko'rish')."""
    state, _, _ = license_state(tid)
    return state in ("locked", "suspended")


def license_text(tid):
    state, left, ends = license_state(tid)
    if state == "suspended":
        return "⛔️ Vaqtincha to'xtatilgan"
    if state == "trial":
        return f"🧪 Sinov muddati — {left} kun qoldi ({ends})"
    if state == "active":
        icon = "🟡" if left <= 5 else "🟢"
        return f"{icon} Faol, {ends} gacha ({left} kun qoldi)"
    if state == "grace":
        return f"🟠 Muddat tugagan ({ends}) — {GRACE_DAYS + left + 1} kun imtiyoz qoldi"
    return f"🔴 Muddati tugagan ({ends}) — faqat ko'rish rejimi"


def suspend(tid, on=True, actor=0):
    update_tenant(tid, status="suspended" if on else "active")
    log(actor, tid, "suspended" if on else "resumed", "")
    _bust_cache()


def expiring_soon(days=7):
    """Muddati yaqinlashgan/tugagan tenantlar — eslatma yuborish uchun."""
    out = []
    for t in list_tenants():
        if t["status"] == "suspended":
            continue
        state, left, ends = license_state(t["id"])
        if left <= days:
            out.append((t, state, left, ends))
    return out


# ─────────────────────── To'lovlar ───────────────────────

def record_payment(tid, amount, method="naqd", period_label="", note="",
                   recorded_by=0):
    q("""INSERT INTO payments
         (tenant_id,amount,paid_at,method,period_label,note,recorded_by)
         VALUES (?,?,?,?,?,?,?)""",
      (tid, amount, now_str(), method,
       period_label or now_dt().strftime("%Y-%m"), note, recorded_by))
    log(recorded_by, tid, "payment", f"{amount:,} so'm")


def payments_of(tid, limit=20):
    return qall("""SELECT * FROM payments WHERE tenant_id=?
                   ORDER BY paid_at DESC LIMIT ?""", (tid, limit))


def revenue_summary(month=None):
    """(oylik_tushum, jami_tushum, faol_tenant, kutilayotgan_oylik)"""
    m = month or now_dt().strftime("%Y-%m")
    r1 = qone("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE period_label=?", (m,))
    r2 = qone("SELECT COALESCE(SUM(amount),0) s FROM payments")
    active = [t for t in list_tenants()
              if license_state(t["id"])[0] in ("active", "trial", "grace")]
    mrr = sum(monthly_price(t["id"]) for t in active)
    return (r1["s"] if r1 else 0, r2["s"] if r2 else 0, len(active), mrr)


# ─────────────────────── Takliflar (invite) ───────────────────────

def create_invite(tid, role="employee", days=0, max_uses=0, created_by=0):
    tok = _token(6)
    exp = ((now_dt() + timedelta(days=days)).strftime("%Y-%m-%d")
           if days else "")
    q("""INSERT INTO invites
         (token,tenant_id,role,max_uses,expires_at,created_at,created_by)
         VALUES (?,?,?,?,?,?,?)""",
      (tok, tid, role, max_uses, exp, now_str(), created_by))
    return tok


def use_invite(token):
    """Yaroqli bo'lsa (tenant_row, role) qaytaradi, aks holda (None, sabab)."""
    inv = qone("SELECT * FROM invites WHERE token=?", (token,))
    if not inv:
        return None, "Havola topilmadi"
    if inv["expires_at"] and inv["expires_at"] < today_str():
        return None, "Havola muddati tugagan"
    if inv["max_uses"] and inv["used_count"] >= inv["max_uses"]:
        return None, "Havoladan foydalanish limiti tugagan"
    q("UPDATE invites SET used_count=used_count+1 WHERE token=?", (token,))
    return get_tenant(inv["tenant_id"]), inv["role"]


def revoke_invite(token):
    q("DELETE FROM invites WHERE token=?", (token,))


def invites_of(tid):
    return qall("SELECT * FROM invites WHERE tenant_id=? ORDER BY created_at DESC",
                (tid,))


# ─────────────────────── Bito sozlamalari ───────────────────────

BITO_FIELDS = ["org_id", "warehouse_id", "currency_id", "sale_price_id",
               "plu_field_id", "kg_measure_id", "default_uom_id",
               "box_type_id", "wo_reason_id"]


def set_bito_key(tid, api_key):
    q("INSERT OR IGNORE INTO tenant_bito (tenant_id) VALUES (?)", (tid,))
    q("UPDATE tenant_bito SET api_key_enc=?, last_error='' WHERE tenant_id=?",
      (encrypt(api_key.strip()), tid))
    _bust_cache()


def get_bito(tid):
    """Ochilgan (deshifrlangan) Bito sozlamalari dict ko'rinishida."""
    r = qone("SELECT * FROM tenant_bito WHERE tenant_id=?", (tid,))
    if not r:
        return {}
    d = {f: r[f] for f in BITO_FIELDS}
    d["api_key"] = decrypt(r["api_key_enc"])
    d["verified_at"] = r["verified_at"]
    d["last_error"] = r["last_error"]
    return d


def set_bito_config(tid, **fields):
    sets, vals = [], []
    for k, v in fields.items():
        if k in BITO_FIELDS:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return False
    vals.append(tid)
    q("INSERT OR IGNORE INTO tenant_bito (tenant_id) VALUES (?)", (tid,))
    q(f"UPDATE tenant_bito SET {', '.join(sets)} WHERE tenant_id=?", tuple(vals))
    q("UPDATE tenant_bito SET verified_at=? WHERE tenant_id=?", (now_str(), tid))
    _bust_cache()
    return True


def bito_ready(tid):
    b = get_bito(tid)
    return bool(b.get("api_key") and b.get("org_id"))


# ─────────────────────── AI hisoblagich ───────────────────────

AI_DAILY_LIMIT = int(os.getenv("AI_DAILY_LIMIT", "300"))


def ai_bump(tid, provider="anthropic", tokens=0):
    q("""INSERT INTO ai_usage (tenant_id,day,provider,calls,tokens)
         VALUES (?,?,?,1,?)
         ON CONFLICT(tenant_id,day,provider) DO UPDATE SET
             calls=calls+1, tokens=tokens+excluded.tokens""",
      (tid, today_str(), provider, tokens))


def ai_calls_today(tid):
    r = qone("SELECT COALESCE(SUM(calls),0) c FROM ai_usage WHERE tenant_id=? AND day=?",
             (tid, today_str()))
    return r["c"] if r else 0


def ai_allowed(tid):
    return ai_calls_today(tid) < AI_DAILY_LIMIT


# ─────────────────────── Audit ───────────────────────

def log(actor_tg_id, tenant_id, action, detail=""):
    q("""INSERT INTO audit_log (at,actor_tg_id,tenant_id,action,detail)
         VALUES (?,?,?,?,?)""",
      (now_str(), actor_tg_id or 0, tenant_id or 0, action, str(detail)[:500]))


def recent_log(tid=None, limit=20):
    if tid:
        return qall("""SELECT * FROM audit_log WHERE tenant_id=?
                       ORDER BY id DESC LIMIT ?""", (tid, limit))
    return qall("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))


# ─────────────────────── Havolalar ───────────────────────

MAIN_BOT_USERNAME = os.getenv("MAIN_BOT_USERNAME", "AIMARKETNM_BOT")
# Litsenziya boti — begona odam asosiy botga kirmoqchi bo'lsa shu yerga
# yo'naltiriladi (biznes ochish faqat shu bot orqali).
ADMIN_BOT_USERNAME = os.getenv("ADMIN_BOT_USERNAME", "BMPAINM_BOT")


def owner_link(slug):
    return f"https://t.me/{MAIN_BOT_USERNAME}?start={slug}"


def employee_link(slug, token):
    return f"https://t.me/{MAIN_BOT_USERNAME}?start=e-{slug}-{token}"


def review_link(slug):
    return f"https://t.me/{MAIN_BOT_USERNAME}?start=r-{slug}"


def job_link(slug, job_id):
    return f"https://t.me/{MAIN_BOT_USERNAME}?start=j-{slug}-{job_id}"


def parse_start_payload(payload):
    """start parametrini tahlil qiladi.

    Qaytaradi: (turi, slug, qo'shimcha)
      'owner'    → ('owner', 'apelsinmarket', None)
      'e-x-TOK'  → ('employee', 'apelsinmarket', 'TOK')
      'r-x'      → ('review', 'apelsinmarket', None)
      'j-x-14'   → ('job', 'apelsinmarket', '14')
      noma'lum   → (None, None, None)
    """
    p = (payload or "").strip()
    if not p:
        return (None, None, None)
    parts = p.split("-")
    if len(parts) >= 3 and parts[0] == "e":
        return ("employee", parts[1], "-".join(parts[2:]))
    if len(parts) >= 3 and parts[0] == "j":
        return ("job", parts[1], parts[2])
    if len(parts) == 2 and parts[0] == "r":
        return ("review", parts[1], None)
    if re.fullmatch(r"[a-z0-9]+", p):
        return ("owner", p, None)
    return (None, None, None)


if __name__ == "__main__":
    init_central()
    print(f"✅ Markaziy baza tayyor: {CENTRAL_DB}")
    print(f"   Tenant papkasi:      {TENANTS_DIR}")
    print(f"   Modullar:            {len(all_modules())} ta")
    for m in all_modules():
        print(f"     {m['code']:<10} {m['name']:<22} {m['price']:>9,} so'm"
              f"{'  (majburiy)' if m['is_core'] else ''}")
