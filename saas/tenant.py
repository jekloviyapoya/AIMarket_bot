"""
🧭 TENANT YADROSI — bot.py ni ko'p-ijarachi qiladigan qatlam
============================================================

G'oya: `bot.py` ichidagi 384 ta SQL chaqiruvi va yuzlab lug'at murojaatini
BIRMA-BIR o'zgartirmaymiz. Ularning hammasi 3 ta markaziy nuqtadan o'tadi:

  1. q()/qone()/qall()  → joriy tenantning SQLite fayliga yo'naltiramiz
  2. W_*/CACHE lug'atlari → TDict/TSet bilan avtomatik namespace qilamiz
  3. BITO_API_KEY, SUPER_ADMIN_ID kabi globallar → CFG obyektidan olamiz

"Joriy tenant" — contextvar. Har bir Telegram update qayta ishlanishidan
oldin o'rnatiladi; fon oqimlari esa tenantlar bo'ylab aylanib, har biri uchun
alohida o'rnatadi.

SXEMA: bot.py ishga tushayotganda 34 ta CREATE TABLE va 14 ta ALTER TABLE
modul darajasida bajariladi. Biz ularni YOZIB OLAMIZ (_SCHEMA) va yangi
tenant bazasi birinchi marta ochilganda qaytadan o'ynatamiz. Shu sababli
bot.py dagi DDL qatorlariga umuman tegilmaydi.
"""

import contextvars
import copy
import os
import sqlite3
import sys
import threading
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import central as C  # noqa: E402

# ─────────────────────────── Kontekst ───────────────────────────

CURRENT = contextvars.ContextVar("tenant_slug", default=None)

# Kontekst o'rnatilmagan bo'lsa ishlatiladigan tenant (migratsiya davri uchun).
# Ishlab chiqarishda buni bo'sh qoldirib, kontekstsiz chaqiruvlarni xatoga
# chiqarish mumkin — hozircha mos ravishda ishlashi muhimroq.
DEFAULT_TENANT = os.getenv("DEFAULT_TENANT", "bonnu")


class tenant_ctx:
    """with tenant_ctx('apelsinmarket'): ...  — shu blok ichidagi barcha
    DB va kesh murojaatlari shu biznesga tegishli bo'ladi."""

    def __init__(self, slug):
        self.slug = slug
        self._tok = None

    def __enter__(self):
        self._tok = CURRENT.set(self.slug)
        return self

    def __exit__(self, *a):
        if self._tok is not None:
            CURRENT.reset(self._tok)
        return False


def current():
    return CURRENT.get() or DEFAULT_TENANT


def current_tenant_row():
    return C.get_tenant_by_slug(current())


def run_in(slug, fn, *a, **kw):
    """Funksiyani berilgan tenant kontekstida bajaradi (threadlar uchun)."""
    with tenant_ctx(slug):
        return fn(*a, **kw)


def in_ctx(slug, fn):
    """threading.Thread(target=in_ctx('x', f)) uchun o'ram."""
    def _w(*a, **kw):
        with tenant_ctx(slug):
            return fn(*a, **kw)
    _w.__name__ = getattr(fn, "__name__", "wrapped")
    return _w


# ─────────────────────── DB ulanish registri ───────────────────────

_CONNS = {}
_LOCKS = {}
_REG_LOCK = threading.RLock()

_SCHEMA = []          # (sql, params) — import vaqtida yig'iladi
RECORDING = True      # bot.py yuklanayotganda True, oxirida False bo'ladi

_WARNED = set()


def _tenant_file(slug):
    return os.path.join(C.TENANTS_DIR, f"{slug}.db")


def _open(slug):
    path = _tenant_file(slug)
    fresh = not os.path.exists(path)
    os.makedirs(C.TENANTS_DIR, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    if fresh and _SCHEMA:
        # Yangi biznes — yig'ilgan sxemani o'ynatamiz.
        # Ikki bosqichda: avval CREATE, keyin ALTER/INDEX. Sababi: bot.py da
        # ba'zi ALTER TABLE o'z jadvalidan OLDIN turadi (masalan promo_posts) —
        # bitta o'tishda ular "no such table" bilan yiqilardi.
        n = 0
        creates = [s for s in _SCHEMA if s[0].lstrip()[:12].lower() == "create table"]
        rest = [s for s in _SCHEMA if s not in creates]
        for sql, params in creates + rest:
            try:
                con.execute(sql, params)
                n += 1
            except Exception as e:
                if "duplicate column name" not in str(e).lower():
                    print(f"SCHEMA ERR ({slug}):", str(e)[:90], flush=True)
        con.commit()
        print(f"🆕 TENANT: '{slug}' bazasi yaratildi ({n} ta jadval/ustun)",
              flush=True)
    return con


def conn_for(slug):
    with _REG_LOCK:
        if slug not in _CONNS:
            _CONNS[slug] = _open(slug)
            _LOCKS[slug] = threading.RLock()
        return _CONNS[slug], _LOCKS[slug]


def close_all():
    with _REG_LOCK:
        for c in _CONNS.values():
            try:
                c.close()
            except Exception:
                pass
        _CONNS.clear()
        _LOCKS.clear()


def ensure_tenant_db(slug):
    """Yangi biznes ochilganda chaqiriladi — bo'sh baza + to'liq sxema."""
    conn_for(slug)
    return _tenant_file(slug)


def schema_size():
    return len(_SCHEMA)


def stop_recording():
    """bot.py to'liq yuklangach chaqiriladi."""
    global RECORDING
    RECORDING = False
    print(f"📐 SXEMA: {len(_SCHEMA)} ta DDL yozib olindi "
          f"(yangi tenantlar shundan yaratiladi)", flush=True)


_DDL = ("create table", "alter table", "create index", "create unique",
        "create trigger", "create view")


def _is_ddl(sql):
    return sql.lstrip()[:20].lower().startswith(_DDL)


def _warn_no_ctx():
    """Kontekstsiz DB chaqiruvini bir marta loglaydi (migratsiya yordamchisi)."""
    if os.getenv("TENANT_STRICT") != "1":
        return
    st = traceback.extract_stack(limit=6)[-4]
    key = f"{st.filename}:{st.lineno}"
    if key in _WARNED:
        return
    _WARNED.add(key)
    print(f"⚠️  TENANT: kontekstsiz DB murojaati → {key} ({st.name})", flush=True)


# ─────────────────────── q / qone / qall ───────────────────────

def q(sql, params=()):
    """bot.py dagi q() ning o'rnini bosadi — imzo bir xil."""
    if RECORDING and _is_ddl(sql):
        _SCHEMA.append((sql, params))

    slug = CURRENT.get()
    if slug is None:
        _warn_no_ctx()
        slug = DEFAULT_TENANT

    db, lock = conn_for(slug)
    with lock:
        try:
            cur = db.execute(sql, params)
            db.commit()
            return cur
        except Exception as e:
            msg = str(e)
            if "duplicate column name" not in msg.lower():
                print(f"DB ERR [{slug}]:", msg[:100], "SQL:", sql[:60], flush=True)
            return None


def qone(sql, params=()):
    slug = CURRENT.get() or DEFAULT_TENANT
    _, lock = conn_for(slug)
    with lock:
        r = q(sql, params)
        return r.fetchone() if r else None


def qall(sql, params=()):
    slug = CURRENT.get() or DEFAULT_TENANT
    _, lock = conn_for(slug)
    with lock:
        r = q(sql, params)
        return r.fetchall() if r else []


def db_path():
    """Joriy tenantning fayl yo'li (PROMO_POSTER_DIR kabilar uchun)."""
    return _tenant_file(current())


# ─────────────────── Tenant bo'yicha ajraladigan xotira ───────────────────

class TDict:
    """Kaliti avtomatik joriy tenant bilan namespace qilinadigan lug'at.

    bot.py da faqat E'LON qatori o'zgaradi:  W_TASK = {}  →  W_TASK = TDict()
    Chaqiruv joylari (W_TASK[uid], uid in W_TASK, .pop, .get ...) tegilmaydi.
    """

    __slots__ = ("_d", "_lock", "_tpl")

    def __init__(self, initial=None, template=None):
        """template — yo'q kalit so'ralganda qaytariladigan standart qiymatlar.
        Keshlar uchun kerak: har bir yangi tenant uchun {"ts": 0, ...} o'zidan
        paydo bo'ladi, KeyError chiqmaydi."""
        self._d = {}
        self._tpl = dict(template) if template else None
        self._lock = threading.RLock()
        if initial:
            for k, v in dict(initial).items():
                self[k] = v

    def _k(self, k):
        return (CURRENT.get() or DEFAULT_TENANT, k)

    # --- asosiy protokol ---
    def __getitem__(self, k):
        with self._lock:
            key = self._k(k)
            if key not in self._d and self._tpl is not None and k in self._tpl:
                self._d[key] = copy.deepcopy(self._tpl[k])
            return self._d[key]

    def __setitem__(self, k, v):
        with self._lock:
            self._d[self._k(k)] = v

    def __delitem__(self, k):
        with self._lock:
            del self._d[self._k(k)]

    def __contains__(self, k):
        with self._lock:
            if self._k(k) in self._d:
                return True
            return self._tpl is not None and k in self._tpl

    def __len__(self):
        return len(self.keys())

    def __iter__(self):
        return iter(self.keys())

    def __bool__(self):
        return len(self.keys()) > 0

    def __repr__(self):
        return f"TDict({dict(self.items())!r})"

    # --- dict API ---
    def get(self, k, default=None):
        with self._lock:
            key = self._k(k)
            if key in self._d:
                return self._d[key]
        if self._tpl is not None and k in self._tpl:
            return self[k]
        return default

    def pop(self, k, *default):
        with self._lock:
            return self._d.pop(self._k(k), *default)

    def setdefault(self, k, default=None):
        with self._lock:
            return self._d.setdefault(self._k(k), default)

    def update(self, other=None, **kw):
        for k, v in dict(other or {}, **kw).items():
            self[k] = v

    def keys(self):
        t = CURRENT.get() or DEFAULT_TENANT
        with self._lock:
            ks = [k for (ten, k) in list(self._d) if ten == t]
        if self._tpl:
            ks += [k for k in self._tpl if k not in ks]
        return ks

    def values(self):
        return [self[k] for k in self.keys()]

    def items(self):
        return [(k, self[k]) for k in self.keys()]

    def clear(self):
        t = CURRENT.get() or DEFAULT_TENANT
        with self._lock:
            for key in [key for key in list(self._d) if key[0] == t]:
                self._d.pop(key, None)

    def clear_tenant(self, slug):
        with self._lock:
            for key in [key for key in list(self._d) if key[0] == slug]:
                self._d.pop(key, None)

    def all_items(self):
        """Barcha tenantlar bo'ylab — faqat diagnostika uchun."""
        with self._lock:
            return dict(self._d)


class TSet:
    """TDict ning to'plam varianti (W_AI_CHAT, W_PROMO_TIME kabilar uchun)."""

    __slots__ = ("_s", "_lock")

    def __init__(self, initial=None):
        self._s = set()
        self._lock = threading.RLock()
        for v in (initial or ()):
            self.add(v)

    def _k(self, v):
        return (CURRENT.get() or DEFAULT_TENANT, v)

    def add(self, v):
        with self._lock:
            self._s.add(self._k(v))

    def discard(self, v):
        with self._lock:
            self._s.discard(self._k(v))

    def remove(self, v):
        with self._lock:
            self._s.remove(self._k(v))

    def __contains__(self, v):
        with self._lock:
            return self._k(v) in self._s

    def __iter__(self):
        t = CURRENT.get() or DEFAULT_TENANT
        with self._lock:
            return iter([v for (ten, v) in list(self._s) if ten == t])

    def __len__(self):
        return len(list(iter(self)))

    def __bool__(self):
        return len(self) > 0

    def __repr__(self):
        return f"TSet({set(iter(self))!r})"

    def clear(self):
        t = CURRENT.get() or DEFAULT_TENANT
        with self._lock:
            for key in [k for k in list(self._s) if k[0] == t]:
                self._s.discard(key)

    def pop(self, *a):
        it = list(iter(self))
        if not it:
            if a:
                return a[0]
            raise KeyError("pop from empty TSet")
        self.discard(it[0])
        return it[0]


# ─────────────────────── Konfiguratsiya proksisi ───────────────────────

class _Cfg:
    """Tenantga bog'liq sozlamalar. bot.py da SUPER_ADMIN_ID → CFG.SUPER_ADMIN_ID.

    Qiymatlar markaziy bazadan olinadi va 30 soniya keshlanadi.
    Muhit o'zgaruvchisi berilgan bo'lsa — u ustun (bir tenantli eski rejim).
    """

    _ENV_OVERRIDE = {
        "BITO_API_KEY": "BITO_API_KEY",
        "BITO_ORG_ID": "BITO_ORG_ID",
        "PLU_FIELD_ID": "BITO_PLU_FIELD_ID",
        "KG_MEASURE_ID": "BITO_KG_MEASURE_ID",
        "NAK_DEFAULT_UOM_ID": "BITO_DEFAULT_UOM_ID",
    }

    def _row(self):
        return C.get_tenant_by_slug(current())

    def _bito(self, field, default=""):
        t = self._row()
        if not t:
            return default
        return C.get_bito(t["id"]).get(field) or default

    # --- egasi / do'kon ---
    @property
    def SUPER_ADMIN_ID(self):
        """Shu biznesning egasi. Muhit o'zgaruvchisi faqat tenant topilmasa
        ishlatiladi (migratsiyagacha bo'lgan bir tenantli rejim)."""
        t = self._row()
        if t and t["owner_tg_id"]:
            return int(t["owner_tg_id"])
        return int(os.getenv("SUPER_ADMIN_ID", "0") or "0")

    @property
    def TENANT_ID(self):
        t = self._row()
        return t["id"] if t else 0

    @property
    def SHOP_NAME(self):
        t = self._row()
        return t["name"] if t else "Market"

    APP_NAME = SHOP_NAME

    @property
    def SHOP_LAT(self):
        t = self._row()
        return float(t["shop_lat"] or 0) if t and t["shop_lat"] else 0.0

    @property
    def SHOP_LON(self):
        t = self._row()
        return float(t["shop_lon"] or 0) if t and t["shop_lon"] else 0.0

    @property
    def REVIEW_SECRET(self):
        t = self._row()
        return (t["review_secret"] if t and t["review_secret"]
                else os.getenv("REVIEW_SECRET", "BONUSMARKET_REVIEW"))

    @property
    def PROMO_PHONE(self):
        t = self._row()
        return (t["contact_phone"] if t and t["contact_phone"]
                else os.getenv("PROMO_PHONE", ""))

    @property
    def PROMO_HOURS(self):
        t = self._row()
        return (t["work_hours"] if t and t["work_hours"]
                else os.getenv("PROMO_HOURS", ""))

    # --- Bito ---
    @property
    def BITO_API_KEY(self):
        return os.getenv("BITO_API_KEY") or self._bito("api_key")

    @property
    def BITO_ORG_ID(self):
        return os.getenv("BITO_ORG_ID") or self._bito("org_id")

    @property
    def BITO_WAREHOUSE_ID(self):
        return self._bito("warehouse_id")

    @property
    def BITO_SALE_PRICE_ID(self):
        return self._bito("sale_price_id")

    @property
    def PLU_FIELD_ID(self):
        return os.getenv("BITO_PLU_FIELD_ID") or self._bito("plu_field_id")

    @property
    def KG_MEASURE_ID(self):
        return os.getenv("BITO_KG_MEASURE_ID") or self._bito("kg_measure_id")

    @property
    def NAK_DEFAULT_UOM_ID(self):
        return os.getenv("BITO_DEFAULT_UOM_ID") or self._bito("default_uom_id")

    @property
    def NAK_DEFAULT_BOX_TYPE_ID(self):
        return self._bito("box_type_id")

    @property
    def INV_WO_REASON_ID(self):
        return self._bito("wo_reason_id")

    @property
    def BITO_READY(self):
        t = self._row()
        return C.bito_ready(t["id"]) if t else False

    # --- litsenziya / modul ---
    @property
    def READONLY(self):
        t = self._row()
        return C.is_readonly(t["id"]) if t else False

    def has(self, module_code):
        t = self._row()
        return C.has_module(t["id"], module_code) if t else False


CFG = _Cfg()


# ─────────────────────── Foydalanuvchi → tenant ───────────────────────

def resolve_tenant(tg_id):
    """Telegram foydalanuvchisi qaysi biznesga tegishli? (slug yoki None)"""
    return C.slug_of_user(tg_id)


def tenant_for_update(obj):
    """Telegram update (Message yoki CallbackQuery) qaysi biznesga tegishli?"""
    uid = None
    try:
        uid = obj.from_user.id
    except Exception:
        pass
    if uid:
        slug = C.slug_of_user(uid)
        if slug:
            return slug
    # Hali bog'lanmagan foydalanuvchi — /start havolasidan aniqlaymiz
    txt = getattr(obj, "text", None) or ""
    if txt.startswith("/start"):
        parts = txt.split(maxsplit=1)
        if len(parts) > 1:
            _kind, slug, _extra = C.parse_start_payload(parts[1].strip())
            if slug and C.get_tenant_by_slug(slug):
                return slug
    return None


# ─────────────── Modul gating va "faqat ko'rish" siyosati ───────────────

_GATE = {"buttons": {}, "commands": {}, "callbacks": {}}
_RO = {"buttons": set(), "commands": set()}


def set_gates(buttons=None, commands=None, callbacks=None):
    """bot.py o'z xaritalarini shu yerga beradi: matn/buyruq/callback → modul."""
    if buttons:
        _GATE["buttons"] = dict(buttons)
    if commands:
        _GATE["commands"] = dict(commands)
    if callbacks:
        _GATE["callbacks"] = dict(callbacks)


def set_readonly_policy(allowed_buttons=None, allowed_commands=None):
    """Litsenziya tugaganda ISHLASHDA DAVOM ETADIGAN tugma/buyruqlar."""
    _RO["buttons"] = set(allowed_buttons or ())
    _RO["commands"] = set(allowed_commands or ())


def _cmd_of(text):
    if not text or not text.startswith("/"):
        return None
    return text[1:].split()[0].split("@")[0].lower()


def gate_module(obj):
    """Shu update qaysi modulga tegishli? (yo'q bo'lsa None = yadro)"""
    data = getattr(obj, "data", None)
    if data:
        for pref, mod in _GATE["callbacks"].items():
            if data.startswith(pref):
                return mod
        return None
    txt = getattr(obj, "text", None) or ""
    cmd = _cmd_of(txt)
    if cmd:
        return _GATE["commands"].get(cmd)
    return _GATE["buttons"].get(txt)


def _readonly_blocks(obj):
    """Faqat ko'rish rejimida bu update to'silishi kerakmi?"""
    txt = getattr(obj, "text", None) or ""
    cmd = _cmd_of(txt)
    if cmd:
        return cmd not in _RO["commands"]
    if txt:
        return txt not in _RO["buttons"]
    return True          # callback, rasm, lokatsiya, ovoz — hammasi yozuv


def _chat_id_of(obj):
    try:
        return (obj.message.chat.id if hasattr(obj, "message") and obj.message
                else obj.chat.id)
    except Exception:
        return None


def _tell(obj, text):
    cid = _chat_id_of(obj)
    if cid is None or not _DENY_SENDER:
        return
    try:
        _DENY_SENDER(cid, text)
    except Exception:
        pass


def _gate_check(obj):
    """True qaytarsa — handler bajarilmaydi."""
    t = current_tenant_row()
    if not t:
        return False

    # 1) Litsenziya: faqat ko'rish rejimi
    state, _left, ends = C.license_state(t["id"])
    if state in ("locked", "suspended") and _readonly_blocks(obj):
        if state == "suspended":
            _tell(obj, "⛔️ Bot vaqtincha to'xtatilgan. Bot egasi bilan "
                       "bog'laning.")
        else:
            _tell(obj, f"🔒 <b>Obuna muddati tugagan</b> ({ends}).\n\n"
                       f"Hozir faqat hisobotlarni <b>ko'rish</b> mumkin. "
                       f"Yangi yozuv qo'shish, AI va Bito amallari to'xtatilgan.\n\n"
                       f"Davom ettirish uchun to'lovni amalga oshiring.")
        return True

    # 2) Modul yoqilganmi
    mod = gate_module(obj)
    if mod and not C.has_module(t["id"], mod):
        m = C.module_info(mod)
        _tell(obj, f"🔒 <b>{m['name'] if m else mod}</b> bo'limi sizning "
                   f"tarifingizga kirmagan.\n\nQo'shish uchun bot egasiga "
                   f"murojaat qiling.")
        return True
    return False


def _wrap_handler(fn):
    if getattr(fn, "_tenant_wrapped", False):
        return fn

    def w(arg, *a, **kw):
        with tenant_ctx(tenant_for_update(arg) or DEFAULT_TENANT):
            if _gate_check(arg):
                return None
            return fn(arg, *a, **kw)

    w._tenant_wrapped = True
    w.__name__ = getattr(fn, "__name__", "handler")
    w.__doc__ = getattr(fn, "__doc__", None)
    return w


def attach_tenant_routing(bot):
    """Har bir update o'z biznesining kontekstida qayta ishlanishini ta'minlaydi.

    Ikki joyda o'rnatiladi:
      1. filtrlar (func=lambda m: is_boss_or_mgr(...)) — polling oqimida
         baholanadi, ular ham DB o'qiydi;
      2. handler funksiyasining o'zi — u ishchi oqimda (thread pool) ishlaydi,
         u yerga contextvar avtomatik ko'chmaydi.
    """
    # pyTelegramBotAPI 4.x da filtrlar (func=lambda m: ...) handler bilan
    # BIR JOYDA — _run_middlewares_and_handler ichida, ishchi oqimda
    # baholanadi. Shuning uchun kontekstni aynan shu yerda o'rnatamiz;
    # aks holda filtr lambdalari noto'g'ri biznesning bazasini o'qir edi.
    hooked = False
    if hasattr(bot, "_run_middlewares_and_handler"):
        orig_run = bot._run_middlewares_and_handler

        def run(message, *a, **kw):
            with tenant_ctx(tenant_for_update(message) or DEFAULT_TENANT):
                return orig_run(message, *a, **kw)

        bot._run_middlewares_and_handler = run
        hooked = True

    # Eskiroq versiyalar uchun zaxira yo'l
    if not hooked and hasattr(bot, "_notify_command_handlers"):
        orig_notify = bot._notify_command_handlers

        def notify(handlers, new_messages, update_type):
            for msg in new_messages:
                with tenant_ctx(tenant_for_update(msg) or DEFAULT_TENANT):
                    orig_notify(handlers, [msg], update_type)

        bot._notify_command_handlers = notify
        hooked = True

    if not hooked:
        print("⚠️  TENANT: dispatch nuqtasi topilmadi — filtrlar standart "
              "tenantda baholanadi!", flush=True)

    n = 0
    for attr in ("message_handlers", "edited_message_handlers",
                 "channel_post_handlers", "edited_channel_post_handlers",
                 "callback_query_handlers", "inline_handlers",
                 "chosen_inline_handlers", "shipping_query_handlers",
                 "pre_checkout_query_handlers", "poll_handlers",
                 "poll_answer_handlers", "my_chat_member_handlers",
                 "chat_member_handlers", "chat_join_request_handlers"):
        for h in getattr(bot, attr, []) or []:
            if isinstance(h, dict) and "function" in h:
                h["function"] = _wrap_handler(h["function"])
                n += 1
    print(f"🧭 TENANT: {n} ta handler yo'naltirishga ulandi", flush=True)
    return n


def active_slugs(module=None):
    """Fon oqimlari aylanadigan tenantlar: to'xtatilmaganlari.
    module berilsa — shu modul yoqilganlari."""
    out = []
    for t in C.list_tenants():
        if t["status"] == "suspended":
            continue
        if module and not C.has_module(t["id"], module):
            continue
        out.append(t["slug"])
    return out


def for_each_tenant(fn, module=None, label=""):
    """Har bir faol tenant uchun fn() ni o'z kontekstida bajaradi.
    Bitta tenantdagi xato qolganlarini to'xtatmaydi."""
    for slug in active_slugs(module):
        try:
            with tenant_ctx(slug):
                fn()
        except Exception as e:
            print(f"TENANT JOB ERR [{slug}] {label}: {str(e)[:120]}", flush=True)


# ─────────────────────── Modul qo'riqchisi ───────────────────────

class ModuleDisabled(Exception):
    pass


def needs(module_code, silent=False):
    """Handler dekoratori:

        @bot.message_handler(commands=['nakladnoy'])
        @needs("taminot")
        def nakladnoy_cmd(message): ...

    Modul yoqilmagan bo'lsa handler umuman bajarilmaydi.
    """
    def deco(fn):
        def wrapper(arg, *a, **kw):
            t = current_tenant_row()
            if t and not C.has_module(t["id"], module_code):
                if not silent:
                    _deny(arg, module_code)
                return None
            return fn(arg, *a, **kw)
        wrapper.__name__ = getattr(fn, "__name__", "wrapped")
        wrapper.__doc__ = getattr(fn, "__doc__", None)
        return wrapper
    return deco


_DENY_SENDER = None       # bot.py o'z send funksiyasini shu yerga qo'yadi


def set_deny_sender(fn):
    """fn(chat_id, text) — modul yopiq bo'lganda xabar yuborish uchun."""
    global _DENY_SENDER
    _DENY_SENDER = fn


def _deny(arg, module_code):
    if not _DENY_SENDER:
        return
    chat_id = None
    try:
        chat_id = (arg.message.chat.id if hasattr(arg, "message")
                   else arg.chat.id)
    except Exception:
        return
    m = C.module_info(module_code)
    name = m["name"] if m else module_code
    try:
        _DENY_SENDER(chat_id,
                     f"🔒 <b>{name}</b> bo'limi sizning tarifingizga kirmagan.\n\n"
                     f"Qo'shish uchun bot egasiga murojaat qiling.")
    except Exception:
        pass
