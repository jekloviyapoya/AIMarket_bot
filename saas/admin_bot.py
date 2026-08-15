"""
🏢 LITSENZIYA BOTI — AIMARKETNM_BOT platformasi
================================================

Faqat platforma egasi (siz) foydalanadi. Vazifasi:

  • yangi biznes ochish va unga havola berish
  • modullarni yoqish/o'chirish
  • litsenziya muddatini uzaytirish, to'lovni qayd etish
  • bizneslar holati va daromad hisoboti
  • muddati yaqinlashganda ogohlantirish

Ishga tushirish:
    ADMIN_BOT_TOKEN=...  SAAS_OWNER_ID=...  python3 saas/admin_bot.py

Asosiy bot (bot.py) bilan bitta jarayonda ishlatish uchun:
    from saas.admin_bot import start_admin_bot
    start_admin_bot()          # o'z threadida polling qiladi
"""

import os
import sys
import html
import threading
import time

import telebot
from telebot import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import central as C  # noqa: E402

ADMIN_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("SAAS_OWNER_ID", "0") or "0")

bot = telebot.TeleBot(ADMIN_TOKEN) if ADMIN_TOKEN else None
if bot:
    telebot.apihelper.RETRY_ON_ERROR = True
    telebot.apihelper.MAX_RETRIES = 3

W = {}          # tg_id -> {"step": ..., "data": {...}}  sehrgar holati

# Asosiy menyu tugmalari — sehrgar bularni yutib yubormasligi kerak
MENU_TEXTS = {"➕ Yangi biznes", "📋 Bizneslar", "💳 To'lovlar", "📊 Hisobot",
              "⏰ Muddati yaqinlar", "🧩 Modul narxlari", "❌ Bekor qilish"}

NEW_TENANT_STEPS = {"name", "slug", "phone", "owner", "package"}


# ─────────────────────────── Yordamchilar ───────────────────────────

def h(s):
    return html.escape(str(s or ""))


def money(n):
    return f"{int(n or 0):,}".replace(",", " ")


def is_owner(tg_id):
    return OWNER_ID and tg_id == OWNER_ID


def guard(m):
    """Faqat platforma egasi. Boshqalarga javob bermaymiz.

    Asosiy menyu tugmasi bosilganda yarim qolgan sehrgar holati tozalanadi —
    aks holda keyingi xabar eski bosqichga tushib ketardi.
    """
    if not is_owner(m.from_user.id):
        return False
    W.pop(m.from_user.id, None)
    return True


def main_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("➕ Yangi biznes", "📋 Bizneslar")
    kb.add("💳 To'lovlar", "📊 Hisobot")
    kb.add("⏰ Muddati yaqinlar", "🧩 Modul narxlari")
    return kb


def cancel_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("❌ Bekor qilish")
    return kb


def send(chat_id, text, **kw):
    kw.setdefault("parse_mode", "HTML")
    kw.setdefault("disable_web_page_preview", True)
    try:
        return bot.send_message(chat_id, text, **kw)
    except Exception as e:
        print("ADMIN SEND ERR:", str(e)[:120], flush=True)


def ack(call, text=""):
    try:
        bot.answer_callback_query(call.id, text[:200])
    except Exception:
        pass


# ─────────────────────────── /start ───────────────────────────

if bot:
    @bot.message_handler(commands=["start", "menu"])
    def cmd_start(m):
        if not is_owner(m.from_user.id):
            send(m.chat.id,
                 "🔒 Bu bot platforma egasiga tegishli.\n\n"
                 "Agar siz biznes egasi bo'lsangiz — sizga berilgan havola "
                 "orqali asosiy botga kiring.")
            return
        W.pop(m.from_user.id, None)
        n = len(C.list_tenants())
        send(m.chat.id,
             f"🏢 <b>AIMARKET — Litsenziya boshqaruvi</b>\n\n"
             f"Bizneslar: <b>{n}</b> ta\n"
             f"Quyidagi menyudan tanlang:",
             reply_markup=main_kb())

    @bot.message_handler(func=lambda m: m.text == "❌ Bekor qilish")
    def cmd_cancel(m):
        if not guard(m):
            return
        W.pop(m.from_user.id, None)
        send(m.chat.id, "Bekor qilindi.", reply_markup=main_kb())


# ─────────────────── Yangi biznes ochish (sehrgar) ───────────────────

def wiz(uid):
    return W.get(uid, {}).get("data", {})


if bot:
    @bot.message_handler(func=lambda m: m.text == "➕ Yangi biznes")
    def new_tenant(m):
        if not guard(m):
            return
        W[m.from_user.id] = {"step": "name", "data": {}}
        send(m.chat.id,
             "🏪 <b>Yangi biznes</b>\n\n1/5 — Biznes nomini yozing:\n"
             "<i>masalan: Apelsin Market</i>",
             reply_markup=cancel_kb())

    @bot.message_handler(func=lambda m: is_owner(m.from_user.id)
                         and (m.text or "") not in MENU_TEXTS
                         and W.get(m.from_user.id, {}).get("step") in NEW_TENANT_STEPS)
    def wizard_step(m):
        uid = m.from_user.id
        st = W[uid]["step"]
        d = W[uid]["data"]
        txt = (m.text or "").strip()

        if st == "name":
            if len(txt) < 2:
                send(m.chat.id, "⚠️ Nom juda qisqa. Qaytadan yozing:")
                return
            d["name"] = txt
            d["slug"] = C.make_slug(txt)
            ok, err = C.slug_available(d["slug"])
            W[uid]["step"] = "slug"
            suffix = "" if ok else f"\n\n⚠️ <b>{h(err)}</b> — boshqa slug yozing."
            send(m.chat.id,
                 f"2/5 — Havola nomi (slug):\n\n"
                 f"Taklif: <code>{h(d['slug'])}</code>\n"
                 f"Havola: <code>{h(C.owner_link(d['slug']))}</code>\n\n"
                 f"Rozimisiz? <b>ha</b> deb yozing yoki boshqa slug kiriting."
                 f"{suffix}")
            return

        if st == "slug":
            if txt.lower() not in ("ha", "ok", "+", "yes"):
                d["slug"] = C.make_slug(txt)
            ok, err = C.slug_available(d["slug"])
            if not ok:
                send(m.chat.id, f"⚠️ {h(err)}. Boshqa slug yozing:")
                return
            W[uid]["step"] = "phone"
            send(m.chat.id,
                 "3/5 — Biznes egasining telefon raqami:\n"
                 "<i>masalan: +998 90 123 45 67</i>\n\n"
                 "Bu raqam <b>login</b> bo'ladi — egasi botga birinchi "
                 "kirganda shu raqamni yuborib tasdiqlaydi.")
            return

        if st == "phone":
            ph = C.norm_phone(txt)
            if len(ph) < 9:
                send(m.chat.id, "⚠️ Raqam noto'g'ri. Qaytadan yozing:")
                return
            exists = C.get_tenant_by_phone(ph)
            if exists:
                send(m.chat.id,
                     f"⚠️ Bu raqam allaqachon <b>{h(exists['name'])}</b> "
                     f"biznesiga bog'langan. Boshqa raqam kiriting:")
                return
            d["phone"] = ph
            W[uid]["step"] = "owner"
            send(m.chat.id, "4/5 — Egasining ism-familiyasi:")
            return

        if st == "owner":
            d["owner"] = txt
            W[uid]["step"] = "package"
            kb = types.InlineKeyboardMarkup(row_width=1)
            for key, (pname, codes, price) in C.PACKAGES.items():
                kb.add(types.InlineKeyboardButton(
                    f"{pname} — {money(price)} so'm/oy ({len(codes)} modul)",
                    callback_data=f"np:{key}"))
            kb.add(types.InlineKeyboardButton("🧩 Modullarni o'zim tanlayman",
                                              callback_data="np:custom"))
            send(m.chat.id, "5/5 — Tarif paketini tanlang:", reply_markup=kb)
            return

    @bot.callback_query_handler(func=lambda c: c.data.startswith("np:"))
    def new_package(call):
        uid = call.from_user.id
        if not is_owner(uid) or uid not in W:
            ack(call)
            return
        key = call.data.split(":", 1)[1]
        d = W[uid]["data"]
        modules = (["core"] if key == "custom"
                   else list(C.PACKAGES[key][1]))
        try:
            tid = C.create_tenant(
                name=d["name"], slug=d["slug"], owner_phone=d["phone"],
                owner_name=d.get("owner", ""), modules=modules,
                plan="" if key == "custom" else key, created_by=uid)
        except ValueError as e:
            ack(call, str(e))
            send(call.message.chat.id, f"❌ {h(e)}", reply_markup=main_kb())
            W.pop(uid, None)
            return
        W.pop(uid, None)
        ack(call, "Yaratildi")
        try:
            bot.edit_message_reply_markup(call.message.chat.id,
                                          call.message.message_id,
                                          reply_markup=None)
        except Exception:
            pass
        send(call.message.chat.id,
             f"✅ <b>{h(d['name'])}</b> yaratildi!\n\n"
             f"🔗 Egasiga yuboring:\n<code>{h(C.owner_link(d['slug']))}</code>\n\n"
             f"Egasi havolani bosib, <b>{h(d['phone'])}</b> raqamini "
             f"yuborsa — boshliq sifatida kiradi.",
             reply_markup=main_kb())
        show_tenant(call.message.chat.id, tid)


# ─────────────────────── Bizneslar ro'yxati ───────────────────────

STATE_ICON = {"trial": "🧪", "active": "🟢", "grace": "🟠",
              "locked": "🔴", "suspended": "⛔️"}


if bot:
    @bot.message_handler(func=lambda m: m.text == "📋 Bizneslar")
    def list_tenants_cmd(m):
        if not guard(m):
            return
        rows = C.list_tenants()
        if not rows:
            send(m.chat.id, "Hali biznes qo'shilmagan. ➕ Yangi biznes tugmasini bosing.")
            return
        kb = types.InlineKeyboardMarkup(row_width=1)
        for t in rows:
            state, left, _ = C.license_state(t["id"])
            kb.add(types.InlineKeyboardButton(
                f"{STATE_ICON.get(state,'•')} {t['name']} · "
                f"{money(C.monthly_price(t['id']))} so'm",
                callback_data=f"t:{t['id']}"))
        send(m.chat.id, f"📋 <b>Bizneslar ({len(rows)})</b>", reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("t:"))
    def open_tenant(call):
        if not is_owner(call.from_user.id):
            ack(call)
            return
        ack(call)
        show_tenant(call.message.chat.id, int(call.data.split(":")[1]))


def tenant_card(tid):
    t = C.get_tenant(tid)
    if not t:
        return "Topilmadi", None
    state, left, ends = C.license_state(tid)
    mods = C.enabled_modules(tid)
    bito = C.get_bito(tid)
    users = C.tenant_user_count(tid)

    mod_names = [m["name"] for m in C.all_modules() if m["code"] in mods]
    plan_label = (C.PACKAGES[t["plan"]][0] if t["plan"] in C.PACKAGES
                  else "Qo'lda tanlangan")

    txt = (
        f"{STATE_ICON.get(state,'•')} <b>{h(t['name'])}</b>\n"
        f"<code>{h(t['slug'])}</code>\n\n"
        f"👤 {h(t['owner_name'] or '—')} · <code>+{h(t['owner_phone'])}</code>\n"
        f"{'✅ Telegram bog‘langan' if t['owner_tg_id'] else '⏳ Hali botga kirmagan'}"
        f" · 👥 {users} foydalanuvchi\n\n"
        f"💳 <b>{h(C.license_text(tid))}</b>\n"
        f"📦 Tarif: <b>{h(plan_label)}</b> · {money(C.monthly_price(tid))} so'm/oy\n"
        f"🧩 Modullar ({len(mods)}): {h(', '.join(mod_names))}\n\n"
        f"🔌 Bito: {'✅ ulangan' if C.bito_ready(tid) else '❌ ulanmagan'}"
    )
    if bito.get("last_error"):
        txt += f"\n   ⚠️ {h(bito['last_error'][:80])}"
    txt += f"\n🤖 Bugungi AI chaqiruvlari: {C.ai_calls_today(tid)}"
    txt += f"\n\n🔗 <code>{h(C.owner_link(t['slug']))}</code>"

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("🧩 Modullar", callback_data=f"mod:{tid}"),
           types.InlineKeyboardButton("💳 Muddat", callback_data=f"lic:{tid}"))
    kb.add(types.InlineKeyboardButton("💰 To'lov qayd etish", callback_data=f"pay:{tid}"),
           types.InlineKeyboardButton("🔗 Havolalar", callback_data=f"lnk:{tid}"))
    if t["status"] == "suspended":
        kb.add(types.InlineKeyboardButton("▶️ Qayta yoqish", callback_data=f"sus:{tid}:0"))
    else:
        kb.add(types.InlineKeyboardButton("⛔️ To'xtatish", callback_data=f"sus:{tid}:1"))
    kb.add(types.InlineKeyboardButton("📜 Tarix", callback_data=f"log:{tid}"),
           types.InlineKeyboardButton("⬅️ Ro'yxat", callback_data="back:list"))
    return txt, kb


def show_tenant(chat_id, tid, edit_mid=None):
    txt, kb = tenant_card(tid)
    if edit_mid:
        try:
            bot.edit_message_text(txt, chat_id, edit_mid, parse_mode="HTML",
                                  reply_markup=kb, disable_web_page_preview=True)
            return
        except Exception:
            pass
    send(chat_id, txt, reply_markup=kb)


# ─────────────────────── Modullarni boshqarish ───────────────────────

if bot:
    @bot.callback_query_handler(func=lambda c: c.data.startswith("mod:"))
    def modules_view(call):
        if not is_owner(call.from_user.id):
            ack(call)
            return
        tid = int(call.data.split(":")[1])
        ack(call)
        _render_modules(call.message.chat.id, tid, call.message.message_id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("mt:"))
    def module_toggle(call):
        if not is_owner(call.from_user.id):
            ack(call)
            return
        _, tid, code = call.data.split(":")
        tid = int(tid)
        on = C.has_module(tid, code)
        if not C.set_module(tid, code, not on):
            ack(call, "Yadroni o'chirib bo'lmaydi")
            return
        C.log(call.from_user.id, tid,
              "module_off" if on else "module_on", code)
        ack(call, f"{code}: {'o‘chirildi' if on else 'yoqildi'}")
        _render_modules(call.message.chat.id, tid, call.message.message_id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("pkg:"))
    def package_apply(call):
        if not is_owner(call.from_user.id):
            ack(call)
            return
        _, tid, key = call.data.split(":")
        tid = int(tid)
        C.apply_package(tid, key)
        C.log(call.from_user.id, tid, "package", key)
        ack(call, C.PACKAGES[key][0])
        _render_modules(call.message.chat.id, tid, call.message.message_id)


def _render_modules(chat_id, tid, mid=None):
    t = C.get_tenant(tid)
    mods = C.enabled_modules(tid)
    kb = types.InlineKeyboardMarkup(row_width=1)
    for m in C.all_modules():
        on = m["code"] in mods
        lock = " 🔒" if m["is_core"] else ""
        kb.add(types.InlineKeyboardButton(
            f"{'✅' if on else '☐'} {m['name']} — {money(m['price'])}{lock}",
            callback_data=f"mt:{tid}:{m['code']}"))
    kb.add(types.InlineKeyboardButton("── Tayyor paketlar ──", callback_data="noop"))
    for key, (pname, codes, price) in C.PACKAGES.items():
        kb.add(types.InlineKeyboardButton(f"📦 {pname} — {money(price)} so'm",
                                          callback_data=f"pkg:{tid}:{key}"))
    kb.add(types.InlineKeyboardButton("⬅️ Orqaga", callback_data=f"t:{tid}"))

    txt = (f"🧩 <b>{h(t['name'])}</b> — modullar\n\n"
           f"Jami: <b>{money(C.monthly_price(tid))} so'm/oy</b>\n"
           f"<i>Tugmani bosib yoqing yoki o'chiring. "
           f"O'zgarish 30 soniyada kuchga kiradi.</i>")
    if mid:
        try:
            bot.edit_message_text(txt, chat_id, mid, parse_mode="HTML", reply_markup=kb)
            return
        except Exception:
            pass
    send(chat_id, txt, reply_markup=kb)


# ─────────────────────── Litsenziya muddati ───────────────────────

if bot:
    @bot.callback_query_handler(func=lambda c: c.data.startswith("lic:"))
    def license_view(call):
        if not is_owner(call.from_user.id):
            ack(call)
            return
        tid = int(call.data.split(":")[1])
        t = C.get_tenant(tid)
        price = C.monthly_price(tid)
        kb = types.InlineKeyboardMarkup(row_width=2)
        for months in (1, 3, 6, 12):
            kb.add(types.InlineKeyboardButton(
                f"+{months} oy — {money(price * months)} so'm",
                callback_data=f"le:{tid}:{months}"))
        kb.add(types.InlineKeyboardButton("+14 kun (sinov)", callback_data=f"le:{tid}:t"))
        kb.add(types.InlineKeyboardButton("⬅️ Orqaga", callback_data=f"t:{tid}"))
        ack(call)
        try:
            bot.edit_message_text(
                f"💳 <b>{h(t['name'])}</b>\n\n{h(C.license_text(tid))}\n\n"
                f"Oylik hisob: <b>{money(price)} so'm</b>\n\n"
                f"Muddatni uzaytiring:",
                call.message.chat.id, call.message.message_id,
                parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass

    @bot.callback_query_handler(func=lambda c: c.data.startswith("le:"))
    def license_extend(call):
        if not is_owner(call.from_user.id):
            ack(call)
            return
        _, tid, arg = call.data.split(":")
        tid = int(tid)
        if arg == "t":
            ends = C.start_license(tid, days=14, period="trial", amount=0,
                                   created_by=call.from_user.id)
        else:
            months = int(arg)
            amount = C.monthly_price(tid) * months
            ends = C.start_license(tid, months=months,
                                   period={1: "monthly", 3: "quarterly",
                                           6: "half", 12: "yearly"}[months],
                                   amount=amount, created_by=call.from_user.id)
        ack(call, f"Uzaytirildi → {ends}")
        show_tenant(call.message.chat.id, tid, call.message.message_id)
        _notify_owner_of(tid, f"✅ Obunangiz <b>{ends}</b> gacha uzaytirildi.")


# ─────────────────────── To'lov ───────────────────────

if bot:
    @bot.callback_query_handler(func=lambda c: c.data.startswith("pay:"))
    def pay_start(call):
        if not is_owner(call.from_user.id):
            ack(call)
            return
        tid = int(call.data.split(":")[1])
        W[call.from_user.id] = {"step": "pay_amount", "data": {"tid": tid}}
        ack(call)
        t = C.get_tenant(tid)
        send(call.message.chat.id,
             f"💰 <b>{h(t['name'])}</b> — to'lov summasini yozing (so'm):\n"
             f"<i>Oylik hisob: {money(C.monthly_price(tid))}</i>",
             reply_markup=cancel_kb())

    @bot.message_handler(func=lambda m: is_owner(m.from_user.id)
                         and (m.text or "") not in MENU_TEXTS
                         and W.get(m.from_user.id, {}).get("step") == "pay_amount")
    def pay_amount(m):
        uid = m.from_user.id
        raw = "".join(ch for ch in (m.text or "") if ch.isdigit())
        if not raw:
            send(m.chat.id, "⚠️ Faqat raqam yozing:")
            return
        tid = W[uid]["data"]["tid"]
        C.record_payment(tid, int(raw), "qo'lda", recorded_by=uid)
        W.pop(uid, None)
        t = C.get_tenant(tid)
        send(m.chat.id,
             f"✅ <b>{h(t['name'])}</b> — {money(raw)} so'm to'lov qayd etildi.\n\n"
             f"Muddatni ham uzaytirishni unutmang 👇",
             reply_markup=main_kb())
        show_tenant(m.chat.id, tid)

    @bot.message_handler(func=lambda m: m.text == "💳 To'lovlar")
    def payments_cmd(m):
        if not guard(m):
            return
        rows = C.qall("""SELECT p.*, t.name FROM payments p
                         JOIN tenants t ON t.id=p.tenant_id
                         ORDER BY p.paid_at DESC LIMIT 20""")
        if not rows:
            send(m.chat.id, "Hali to'lov qayd etilmagan.")
            return
        out = ["💳 <b>Oxirgi to'lovlar</b>", ""]
        for r in rows:
            out.append(f"• {h(r['name'])} — <b>{money(r['amount'])}</b> so'm "
                       f"<i>({h(r['paid_at'][:10])}, {h(r['period_label'])})</i>")
        send(m.chat.id, "\n".join(out))


# ─────────────────────── Havolalar ───────────────────────

if bot:
    @bot.callback_query_handler(func=lambda c: c.data.startswith("lnk:"))
    def links_view(call):
        if not is_owner(call.from_user.id):
            ack(call)
            return
        tid = int(call.data.split(":")[1])
        t = C.get_tenant(tid)
        slug = t["slug"]
        invs = C.invites_of(tid)
        out = [f"🔗 <b>{h(t['name'])}</b> havolalari", "",
               "👑 <b>Egasi uchun</b>",
               f"<code>{h(C.owner_link(slug))}</code>", "",
               "⭐ <b>Mijoz baholash (QR)</b>",
               f"<code>{h(C.review_link(slug))}</code>", ""]
        if invs:
            out.append("👥 <b>Hodim taklif havolalari</b>")
            for i in invs[:5]:
                lim = (f"{i['used_count']}/{i['max_uses']}" if i['max_uses']
                       else f"{i['used_count']}/∞")
                exp = f", {i['expires_at']} gacha" if i["expires_at"] else ""
                out.append(f"<code>{h(C.employee_link(slug, i['token']))}</code>\n"
                           f"   <i>{lim}{exp}</i>")
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("➕ Hodim havolasi yaratish",
                                          callback_data=f"newinv:{tid}"))
        kb.add(types.InlineKeyboardButton("⬅️ Orqaga", callback_data=f"t:{tid}"))
        ack(call)
        try:
            bot.edit_message_text("\n".join(out), call.message.chat.id,
                                  call.message.message_id, parse_mode="HTML",
                                  reply_markup=kb, disable_web_page_preview=True)
        except Exception:
            send(call.message.chat.id, "\n".join(out), reply_markup=kb)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("newinv:"))
    def new_invite(call):
        if not is_owner(call.from_user.id):
            ack(call)
            return
        tid = int(call.data.split(":")[1])
        C.create_invite(tid, "employee", days=0, max_uses=0,
                        created_by=call.from_user.id)
        ack(call, "Yaratildi")
        call.data = f"lnk:{tid}"
        links_view(call)


# ─────────────────────── To'xtatish / tarix ───────────────────────

if bot:
    @bot.callback_query_handler(func=lambda c: c.data.startswith("sus:"))
    def suspend_cb(call):
        if not is_owner(call.from_user.id):
            ack(call)
            return
        _, tid, on = call.data.split(":")
        tid, on = int(tid), on == "1"
        C.suspend(tid, on, actor=call.from_user.id)
        ack(call, "To'xtatildi" if on else "Qayta yoqildi")
        show_tenant(call.message.chat.id, tid, call.message.message_id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("log:"))
    def log_view(call):
        if not is_owner(call.from_user.id):
            ack(call)
            return
        tid = int(call.data.split(":")[1])
        rows = C.recent_log(tid, 15)
        out = [f"📜 <b>Tarix</b>", ""]
        for r in rows:
            out.append(f"<code>{h(r['at'][5:16])}</code> {h(r['action'])} "
                       f"{h(r['detail'])}")
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("⬅️ Orqaga", callback_data=f"t:{tid}"))
        ack(call)
        try:
            bot.edit_message_text("\n".join(out) if rows else "Tarix bo'sh.",
                                  call.message.chat.id, call.message.message_id,
                                  parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass

    @bot.callback_query_handler(func=lambda c: c.data == "back:list")
    def back_list(call):
        if not is_owner(call.from_user.id):
            ack(call)
            return
        ack(call)
        list_tenants_cmd(call.message)

    @bot.callback_query_handler(func=lambda c: c.data == "noop")
    def noop(call):
        ack(call)


# ─────────────────────── Hisobot ───────────────────────

if bot:
    @bot.message_handler(func=lambda m: m.text == "📊 Hisobot")
    def report_cmd(m):
        if not guard(m):
            return
        month_sum, total_sum, active, mrr = C.revenue_summary()
        tenants = C.list_tenants()
        by_state = {}
        for t in tenants:
            s = C.license_state(t["id"])[0]
            by_state[s] = by_state.get(s, 0) + 1
        lines = [f"📊 <b>Platforma hisoboti</b>", "",
                 f"🏢 Bizneslar: <b>{len(tenants)}</b>"]
        for s, n in sorted(by_state.items()):
            lines.append(f"   {STATE_ICON.get(s,'•')} {s}: {n}")
        lines += ["",
                  f"💰 Bu oy tushum: <b>{money(month_sum)}</b> so'm",
                  f"💵 Jami tushum: <b>{money(total_sum)}</b> so'm",
                  f"📈 Kutilayotgan oylik (MRR): <b>{money(mrr)}</b> so'm", ""]
        mods = {}
        for t in tenants:
            for c in C.enabled_modules(t["id"]):
                mods[c] = mods.get(c, 0) + 1
        lines.append("🧩 <b>Modul mashhurligi</b>")
        for m_ in C.all_modules():
            lines.append(f"   {m_['name']}: {mods.get(m_['code'], 0)}")
        send(m.chat.id, "\n".join(lines))

    @bot.message_handler(func=lambda m: m.text == "⏰ Muddati yaqinlar")
    def expiring_cmd(m):
        if not guard(m):
            return
        rows = C.expiring_soon(7)
        if not rows:
            send(m.chat.id, "✅ Yaqin 7 kunda muddati tugaydigan biznes yo'q.")
            return
        kb = types.InlineKeyboardMarkup(row_width=1)
        out = ["⏰ <b>Muddati yaqinlashganlar</b>", ""]
        for t, state, left, ends in sorted(rows, key=lambda r: r[2]):
            out.append(f"{STATE_ICON.get(state,'•')} <b>{h(t['name'])}</b> — "
                       f"{h(C.license_text(t['id']))}")
            kb.add(types.InlineKeyboardButton(f"{t['name']}",
                                              callback_data=f"t:{t['id']}"))
        send(m.chat.id, "\n".join(out), reply_markup=kb)

    @bot.message_handler(func=lambda m: m.text == "🧩 Modul narxlari")
    def prices_cmd(m):
        if not guard(m):
            return
        out = ["🧩 <b>Modul katalogi</b>", ""]
        for mo in C.all_modules():
            flags = []
            if mo["is_core"]:
                flags.append("majburiy")
            if mo["needs_bito"]:
                flags.append("Bito")
            if mo["ai_cost"]:
                flags.append("AI")
            f = f" <i>({', '.join(flags)})</i>" if flags else ""
            out.append(f"<b>{h(mo['name'])}</b> — {money(mo['price'])} so'm{f}\n"
                       f"<i>{h(mo['description'])}</i>\n")
        out.append("📦 <b>Paketlar</b>")
        for key, (pname, codes, price) in C.PACKAGES.items():
            out.append(f"• {pname} — <b>{money(price)}</b> so'm/oy "
                       f"({len(codes)} modul)")
        out.append("\n<i>Narxni o'zgartirish uchun: /narx &lt;kod&gt; &lt;summa&gt;</i>")
        send(m.chat.id, "\n".join(out))

    @bot.message_handler(commands=["narx"])
    def set_price_cmd(m):
        if not guard(m):
            return
        parts = (m.text or "").split()
        if len(parts) != 3:
            send(m.chat.id, "Foydalanish: <code>/narx ombor 350000</code>")
            return
        code = parts[1]
        amount = "".join(ch for ch in parts[2] if ch.isdigit())
        if not C.module_info(code) or not amount:
            send(m.chat.id, "⚠️ Modul kodi yoki summa noto'g'ri.")
            return
        C.q("UPDATE modules SET price=? WHERE code=?", (int(amount), code))
        C._bust_cache()
        send(m.chat.id, f"✅ <b>{h(code)}</b> narxi {money(amount)} so'm bo'ldi.")


# ─────────────────────── Eslatma oqimi ───────────────────────

def _notify_owner_of(tid, text):
    """Biznes egasiga ASOSIY bot orqali xabar yuboradi (agar token bo'lsa)."""
    t = C.get_tenant(tid)
    if not t or not t["owner_tg_id"]:
        return
    main_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not main_token:
        return
    try:
        telebot.TeleBot(main_token).send_message(
            t["owner_tg_id"], text, parse_mode="HTML")
    except Exception as e:
        print("NOTIFY ERR:", str(e)[:100], flush=True)


def reminder_thread():
    """Kuniga bir marta: muddati yaqinlashganlar haqida sizga xabar."""
    last = None
    while True:
        try:
            today = C.today_str()
            if today != last and OWNER_ID and bot:
                rows = C.expiring_soon(7)
                if rows:
                    last = today
                    out = ["⏰ <b>Obuna eslatmasi</b>", ""]
                    for t, state, left, ends in sorted(rows, key=lambda r: r[2]):
                        out.append(f"{STATE_ICON.get(state,'•')} "
                                   f"<b>{h(t['name'])}</b> — {h(C.license_text(t['id']))}")
                    send(OWNER_ID, "\n".join(out))
                else:
                    last = today
        except Exception as e:
            print("ADMIN REMINDER ERR:", str(e)[:150], flush=True)
        time.sleep(3600)


# ─────────────────────── Ishga tushirish ───────────────────────

def start_admin_bot():
    """Admin botni alohida threadda ishga tushiradi (bot.py ichidan chaqirish uchun)."""
    if not ADMIN_TOKEN:
        print("ℹ️  ADMIN_BOT_TOKEN yo'q — litsenziya boti ishga tushmadi.", flush=True)
        return False
    if not OWNER_ID:
        print("⚠️  SAAS_OWNER_ID yo'q — litsenziya boti hech kimga javob bermaydi.",
              flush=True)
    C.init_central()
    threading.Thread(target=reminder_thread, daemon=True).start()

    def _poll():
        while True:
            try:
                print("🏢 Litsenziya boti ishga tushdi", flush=True)
                bot.infinity_polling(timeout=30, long_polling_timeout=30,
                                     skip_pending=True)
            except Exception as e:
                print("ADMIN POLLING ERR:", str(e)[:150], flush=True)
                time.sleep(5)

    threading.Thread(target=_poll, daemon=True).start()
    return True


if __name__ == "__main__":
    if not ADMIN_TOKEN:
        print("❌ ADMIN_BOT_TOKEN muhit o'zgaruvchisi kerak.")
        raise SystemExit(1)
    C.init_central()
    threading.Thread(target=reminder_thread, daemon=True).start()
    print("🏢 Litsenziya boti ishga tushdi", flush=True)
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=30,
                                 skip_pending=True)
        except Exception as e:
            print("ADMIN POLLING ERR:", str(e)[:150], flush=True)
            time.sleep(5)
