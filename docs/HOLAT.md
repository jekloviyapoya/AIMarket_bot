# AIMARKETNM_BOT — multi-tenant loyihasi: holat va davom ettirish qo'llanmasi

> Bu hujjat **ishni davom ettiruvchi uchun**. Yangi sessiya boshlanganda birinchi
> shuni o'qing: nima qilingan, nega shunday qilingan, nima qolgan, nimaga
> tegmaslik kerak.
>
> Oxirgi yangilanish: 2026-08-15 · branch `multitenant` (5 commit, PR #1)

---

## 1. Loyiha nima haqida

`bot.py` — bitta do'kon (Bonnu Market) uchun yozilgan 21 900 qatorli Telegram
boti: xodimlar, davomat, vazifalar, savdo, ombor, nakladnoy, AI maslahat,
marketing. Bito ERP bilan integratsiya qilingan.

**Maqsad:** uni ~50 tagacha biznesga sotiladigan mahsulotga aylantirish.
Har bir biznes o'z ma'lumoti bilan ishlaydi, faqat sotib olgan modullaridan
foydalanadi, litsenziya muddati bilan boshqariladi.

**Egasi:** Ulugbek (`jekloviyapoya`). Platforma egasi = sotuvchi, ya'ni u
bizneslarni ochadi, modul yoqadi, to'lov qabul qiladi.

---

## 2. Asosiy arxitektura qarorlari (va nega)

### 2.1 Bitta jarayon, har biznesga alohida SQLite fayl

Uch variant ko'rib chiqilgan:

| Variant | Nega tanlanmadi / tanlandi |
|---|---|
| Har biznesga alohida bot va jarayon | Har biznesga alohida bot username kerak bo'lardi — talab bitta umumiy havola edi |
| Bitta bazaga `tenant_id` ustuni | 384 ta SQL chaqiruvini qayta yozish kerak; testsiz 21k qatorli kodda juda xavfli |
| **Bitta jarayon + tenant-per-DB** ✅ | Sxemaga tegilmaydi, chaqiruv joylari o'zgarmaydi, izolyatsiya to'liq (alohida fayl) |

Amalga oshirish: `saas/tenant.py`.

### 2.2 Uchta markaziy nuqta

Butun multi-tenantlik shu uch joyda hal qilingan — **qolgan kod o'zgarmagan**:

1. **`q()/qone()/qall()`** — joriy tenantning SQLite fayliga yo'naltiradi.
   384 ta chaqiruv joyi tegilmagan.
2. **`TDict` / `TSet`** — kaliti avtomatik tenant bilan namespace qilinadi.
   `bot.py` da faqat e'lon qatori o'zgargan (`W_TASK = {}` → `W_TASK = TDict()`),
   50 lug'at + 5 to'plam + 12 kesh.
3. **`CFG`** — `SUPER_ADMIN_ID`, `BITO_API_KEY`, `SHOP_LAT`, `PROMO_PHONE` va
   boshqalar markaziy bazadan olinadi (218 ta murojaat).

### 2.3 Sxema yozib olish (schema recording)

`bot.py` yuklanayotganda modul darajasida 67 ta `CREATE TABLE` / `ALTER TABLE`
bajariladi. `tenant.py` ularni **yozib oladi** (`_SCHEMA`) va yangi biznes
bazasi birinchi marta ochilganda qayta o'ynatadi — **ikki bosqichda**: avval
`CREATE`, keyin `ALTER`. Sabab: `bot.py:250` dagi `ALTER TABLE promo_posts`
o'z jadvalidan oldin turadi.

Natija: yangi tenantga sxemani qo'lda ko'chirish kerak emas, `bot.py` ga yangi
jadval qo'shsangiz u avtomatik hamma tenantga tarqaladi.

### 2.4 Havola formati

Telegram `t.me/bot/nom` formatini oddiy botlar uchun qo'llamaydi. Shuning uchun
`start` parametri ishlatiladi:

```
Egasi:   t.me/AIMARKETNM_BOT?start=apelsinmarket
Hodim:   t.me/AIMARKETNM_BOT?start=e-apelsinmarket-7Kd93x
Mijoz:   t.me/AIMARKETNM_BOT?start=r-apelsinmarket
Nomzod:  t.me/AIMARKETNM_BOT?start=j-apelsinmarket-14
```

Cheklov: ≤64 belgi, faqat `A-Za-z0-9_-`. Slug — kichik harf va raqam.

### 2.5 Biznes qarorlari (Ulugbek tasdiqlagan)

| Savol | Qaror |
|---|---|
| Modullar | 1 majburiy yadro + 7 sotiladigan |
| Muddat tugaganda | **"Faqat ko'rish"** — hisobotlar ochiq, yozuv/AI/Bito yopiq |
| Bito | **Ixtiyoriy** — Bitosiz "Boshlang'ich" paket bor |
| To'lov | Qo'lda qayd etiladi (Payme/Click keyingi bosqich) |
| Litsenziya boti | Alohida bot: **@BMPAINM_BOT** |
| Baza | SQLite: `central.db` + `tenants/<slug>.db` |

Modullar: `core` (majburiy), `jamoa`, `mijozlar`, `moliya`, `ombor`,
`taminot`, `ai`, `marketing`. Paketlar: Boshlang'ich 650k, Biznes 1.3M,
Premium 2.2M so'm/oy (narxlar hali yakuniy tasdiqlanmagan).

---

## 3. Fayl tuzilishi

```
bot.py                    asosiy bot (21 917 qator) — endi tenant yadrosi ustida
saas/central.py           markaziy registr: bizneslar, modullar, litsenziya,
                          to'lov, taklif havolalari, Bito kalitlarini shifrlash
saas/tenant.py            tenant yadrosi: kontekst, DB registri, TDict/TSet,
                          CFG, yo'naltirish, modul gating
saas/admin_bot.py         litsenziya boti (@BMPAINM_BOT)
saas/migrate_bonnu.py     mavjud market.db ni birinchi tenantga aylantirish
saas/README.md            sozlash va ishga tushirish qo'llanmasi
docs/HOLAT.md             shu fayl
.env.example              barcha muhit o'zgaruvchilari
.python-version           3.12 (majburiy — pastda sabab)
```

---

## 4. Bajarilgan ishlar

- [x] Markaziy registr (`central.py`) — 9 jadval, Fernet shifrlash, AI limit
- [x] Litsenziya boti — biznes ochish sehrgari, modul toggle, muddat, to'lov,
      hisobot (MRR), muddat eslatmasi
- [x] Migratsiya skripti — `market.db` ni nusxalaydi, aslini o'chirmaydi
- [x] Tenant yadrosi — DB yo'naltirish, sxema recording, `TDict`/`TSet`, `CFG`
- [x] Har update o'z biznesining kontekstida (`attach_tenant_routing`)
- [x] Deep-link ro'yxatdan o'tish — ega telefon bilan (parolsiz), hodim taklif
      havolasi bilan, Bito kaliti avtomatik aniqlash, do'kon joylashuvi
- [x] Modul gating — klaviatura filtri + markaziy tekshiruv + "faqat ko'rish"
- [x] Fon oqimlariga modul yorlig'i (14 ta)
- [x] **Kirish yopiq** — havolasiz `/start` hech qachon ro'yxatdan o'tkazmaydi
- [x] Boshliq hodim uchun taklif havolasini o'z akkauntida yaratadi
      (⚙️ Sozlamalar → 👥 Xodimlar va ballar → 🔗 Hodim taklif havolalari)
- [x] **Ikki darajali menyu** — yuqori daraja = modul. Guruhlar rol
      bo'yicha alohida (`menu_groups_adm` / `menu_groups_emp`) va yangi
      biznesga avtomatik o'rnatiladi

### Yo'l-yo'lakay tuzatilgan kamchiliklar

1. `promo_posts.kind` ustuni yangi bazada yaratilmay qolardi
2. `/admin/db-import` — butun SQLite faylni almashtirardi, faqat env token
   bilan himoyalangan edi → o'chirildi
3. `attach_tenant_routing` boshida noto'g'ri nuqtaga ulangan edi —
   pyTelegramBotAPI 4.x da `func=lambda` filtrlari
   `_run_middlewares_and_handler` ichida, ishchi oqimda baholanadi
4. **Kirish teshigi:** bizneslar soni 1 bo'lganda `/start` havolasiz
   kelgan HAR KIMNI avtomatik `employee` qilib bog'lardi va boshliqqa
   tasdiqlash so'rovi ketardi. Botni nomi bilan topgan begona odam
   shu yo'l bilan ichkariga so'rov yubora olardi — yopildi
5. **Standart menyu guruhlari faqat `DEFAULT_TENANT` ga yozilardi** —
   blok modul darajasida, import paytida turgani uchun. Keyin ochilgan
   bizneslarda guruh umuman yo'q edi va 15-29 ta tugma tekis chiqardi.
   Endi `ensure_menu_groups_seeded()` har tenant uchun dangasa ishlaydi
6. **Xodim guruh ichida modul filtri yo'q edi** — `menu_group_open`
   `EMP_MENU_ITEMS - hidden` ishlatardi, ya'ni sotib olinmagan modul
   tugmalari guruh ichida ko'rinardi. `visible_items("emp")` ga o'tdi
7. **Fon threadlari tenant kontekstini yo'qotardi** — `contextvars`
   yangi threadga ko'chmaydi, shuning uchun handlerdan ochilgan har
   qanday `threading.Thread` `DEFAULT_TENANT` ga tushib qolardi.
   Amalda: 🛒 Zakaz tavsiyasi firmalar ro'yxatini to'g'ri biznes
   kaliti bilan olib, hisoblashni boshqa biznes kaliti bilan qilardi.
   `tenant.py` da `threading.Thread.__init__` o'ralib, yaratilish
   paytidagi kontekst ko'chiriladigan bo'ldi (69 ta chaqiruv joyi
   tegilmadi)

---

## 5. ⚠️ Tegmaslik kerak bo'lgan narsalar

**Bularni buzsangiz tizim jim ishlamay qoladi — xato ham bermaydi.**

1. **`Python 3.12+` majburiy.** `bot.py:13195` da PEP 701 f-string bor
   (f-string ichida tashqi qo'shtirnoq bilan bir xil qo'shtirnoq). 3.11 da
   `SyntaxError` beradi. `.python-version` shuning uchun bor.

2. **Filtrlar ishchi oqimda baholanadi.** `attach_tenant_routing` aynan
   `_run_middlewares_and_handler` ni o'raydi. Buni `_notify_command_handlers`
   ga qaytarmang — telebot 4.x da u ishlamaydi va filtrlar noto'g'ri
   biznesning bazasini o'qiy boshlaydi.

3. **`W_ONBOARD` ataylab oddiy `dict`.** Bu holat foydalanuvchi biror biznesga
   bog'lanmasdan OLDIN yashaydi — `TDict` qilsangiz kontekst noaniq bo'ladi.

4. **Xotira lug'atlari `tg_id` bo'yicha kalitlanadi.** Bitta odam ikki
   biznesda ishlasa to'qnashadi. 1-versiyada qo'llab-quvvatlanmaydi.

5. **`MASTER_KEY` yo'qolsa barcha Bito kalitlari o'qib bo'lmas holga keladi.**
   U Railway Variables'da turishi shart, volume'dagi `.master_key` fayliga
   tayanmang.

6. **Migratsiyadan keyin eski env o'zgaruvchilarini o'chiring.**
   `BITO_API_KEY`, `BITO_ORG_ID`, `BITO_PLU_FIELD_ID`,
   `BITO_KG_MEASURE_ID`, `BITO_DEFAULT_UOM_ID` — bular tenantning O'Z
   qiymatini **bosib ketadi** (`_Cfg`: `os.getenv(...) or ...`), ya'ni
   barcha bizneslar sizning Bito hisobingizga ulanadi.
   `SUPER_ADMIN_ID`, `REVIEW_SECRET`, `PROMO_PHONE`, `PROMO_HOURS` —
   faqat tenant topilmaganda ishlatiladi, xavfi kamroq.
   Ishga tushishda `startup_checks()` ikkalasini ham logga chiqaradi.

7. **`bot.py` da `for _col in (...)` sikli ikki marta yozilgan**, birinchisining
   tanasi bo'sh (o'lik kod). Haqiqiy ishni ikkinchisi qiladi — tahrirlaganda
   adashmang.

8. **Fon threadida tenant kontekstini o'zingiz o'rnatishga urinmang.**
   `tenant.py` `threading.Thread` ni o'rab qo'ygan — kontekst yaratilish
   paytida nusxalanadi va o'zi ko'chadi. Bu o'ramni olib tashlasangiz,
   69 ta joyda jimgina noto'g'ri biznes ishlatila boshlaydi.

9. **Menyu guruhlari ROL bo'yicha alohida.** `menu_groups(scope)` —
   `menu_groups_adm` / `menu_groups_emp`. Eski `menu_groups` kaliti zaxira
   sifatida o'qiladi (bonnu shu bilan ishlaydi) — uni o'chirmang, aks holda
   allaqachon sozlangan bizneslar menyusi tekislanib ketadi.

10. **`/start` ga "havolasiz ham kirsin" fallback qo'shmang.** Bir marta
   `len(tenants)==1` bo'lsa avtomatik bog'lash bor edi — natijada botni
   qidiruvdan topgan begona odam ro'yxatdan o'ta olardi. Kirish faqat
   taklif havolasi orqali: ega `?start=<slug>` (telefon bilan), hodim
   `?start=e-<slug>-<token>` (keyin boshliq tasdig'i).

---

## 6. Qolgan ishlar (muhimlik tartibida)

### 6.1 🔴 Fon oqimlari rejalashtiruvchisi — 50 mijozdan OLDIN shart

**Muammo:** 18 ta fon oqimi bor. Hozir ular faqat `DEFAULT_TENANT`
kontekstida ishlaydi (`bot.py` → `_start_boot_threads()`), ya'ni boshqa
bizneslarga eslatma, hisobot, ombor ogohlantirishi kelmaydi.

**Noto'g'ri yechim:** har tenantga alohida thread ochish → 18 × 50 = **900
thread**, server yiqiladi.

**To'g'ri yechim:** har bir oqimning `while True:` tanasini `_tick(tenant)`
funksiyasiga ajratib, bitta rejalashtiruvchi ishlatish:

```python
JOBS = [(reminder_tick, 60, None), (stock_alert_tick, 30, "ombor"),
        (ai_advice_tick, 30, "ai"), ...]

def scheduler():                    # 1 ta thread + kichik pool
    while True:
        for slug in TEN.active_slugs():
            for fn, period, module in JOBS:
                if due(slug, fn, period) and has_module(slug, module):
                    POOL.submit(TEN.in_ctx(slug, fn))
        time.sleep(5)
```

Tayyorgarlik allaqachon qilingan: `_boot_thread(fn, module="ombor")` chaqiruvlari
modul yorlig'i bilan yozilgan (14 tasi), `TEN.for_each_tenant()` va
`TEN.active_slugs(module)` mavjud.

Oqimlar ro'yxati: `reminder_thread`, `tips_thread`, `bito_sale_thread`,
`bito_employee_bonus_thread`, `stock_alert_thread`, `ai_advice_thread`,
`license_check_thread`, `abc_auto_task_thread`, `dashboard_cache_warmer_thread`,
`nak_catalog_warmer_thread`, `marketing_thread`, `promo_daily_thread`,
`zakaz_limit_thread`, `task_overdue_thread`, `promo_sched_thread`,
`zarur_watch_thread`.

### 6.2 🔴 Telegram xabar navbati — 50 mijozdan OLDIN shart

**Muammo:** Telegram bitta botga soniyasiga ~30 xabar ruxsat beradi. Hozir kod
istalgan joyda to'g'ridan-to'g'ri `bot.send_message` chaqiradi. 50 biznes
ertalab 08:00 da bir vaqtda tarqatsa — `429 Too Many Requests` va Telegram
**butun botni** cheklaydi, ya'ni hamma mijoz zarar ko'radi.

**Yechim:** barcha yuborishlar bitta throttled navbat orqali (~25 msg/s,
tenant bo'yicha adolatli navbat), va ommaviy tarqatishlarga tenant ID asosida
bir necha daqiqalik jitter.

Amalga oshirish: `bot.send_message` ni o'rab qo'yish (monkeypatch) eng arzon
yo'l — chaqiruv joylari o'zgarmaydi, xuddi `q()` bilan qilingandek.

### 6.3 🟡 Flask / WebApp multi-tenant

`bot.py:17618` dan boshlanadigan Flask ilovasi hali tenant-aware emas. Uchta
auth sxemasi bor: JWT (`require_auth`), `dash_session` cookie, va WebApp
tokenlari (`FIRMA_TOKENS`, `MAQSAD_TOKENS` — allaqachon `TDict`).

Kerak: JWT payload'iga va cookie'ga tenant qo'shish, har route boshida
`with tenant_ctx(...)`.

### 6.4 🟡 AI limitini ulash

`CENTRAL.ai_bump(tid)` va `CENTRAL.ai_allowed(tid)` yozilgan, lekin AI
chaqiruvlariga ulanmagan. Anthropic/OpenAI/Gemini chaqiriladigan joylarda
tekshirish va hisoblash kerak. Aks holda bitta faol mijoz butun foydani yeydi.

### 6.5 🟢 Kichik ishlar

- `CFG.SUPER_ADMIN_ID` ga bog'langan 7 tugma (`🏢 Firmalar`, `💰 Pul taqvimi`,
  `🎯 Maqsadlar`, `📦 Inventarizatsiya`, `⚖️ PLU`, `🎯 Zakaz limiti`,
  `🛒 Zakaz tavsiyasi`) → `role='boss'` ga o'tkazish, aks holda menejer ko'rmaydi
- `📈 MARKETING` submenyusida boshqa modulga tegishli tugmalar bor
  (nakladnoy → `taminot`, ABC → `mijozlar`) — submenyu ko'rinishi filtrlanmagan
- CI: `python3.12 -m py_compile bot.py saas/*.py` ishlatadigan GitHub Actions
- `bot.py` ni modullarga bo'lish (21 917 qator bitta faylda)

---

## 7. Ishga tushirish tartibi

**Tartibni buzmang** — aks holda bot bo'sh baza yaratib, mavjud ma'lumotlarni
ko'rmaydi.

1. **Doimiy disk (volume) `/data` ga ulangan bo'lsin** — bo'lmasa bazalar
   konteyner ichiga yoziladi va HAR DEPLOY'DA O'CHADI. Ishga tushish
   logida `🔴 MA'LUMOT SAQLANMAYDI` chiqsa — shu.
2. Railway Variables: `MASTER_KEY`, `ADMIN_BOT_TOKEN`, `SAAS_OWNER_ID`,
   `MAIN_BOT_USERNAME`, `ADMIN_BOT_USERNAME`, `CENTRAL_DB_PATH`,
   `TENANTS_DIR` (`.env.example` ga qarang)
3. **Avval migratsiya:**
   ```bash
   python3 saas/migrate_bonnu.py --dry-run          # avval sinov
   python3 saas/migrate_bonnu.py --phone +998... \
       --owner-tg $SUPER_ADMIN_ID --bito-key "$BITO_API_KEY" --years 5
   ```
4. Eski env o'zgaruvchilarini o'chirish (5-bo'lim, 6-band)
5. Keyin botni ishga tushirish: `python3 bot.py`

### Sinov muhiti (tavsiya etiladi)

Railway'da `sinov` environment ochib, `multitenant` branchga ulash.
**Muhim:** test servis boshqa bot tokenlaridan foydalanishi shart — Telegram
bitta tokenni ikki jarayon bilan ishlatishga ruxsat bermaydi (`409 Conflict`,
ishlab turgan bot o'ladi). BotFather'da test botlar oching.

Sinovda Bito kalitini bermang (`/keyinroq`) — haqiqiy ERP'ga yozib yuboradi.

---

## 8. Sinov retsepti

Bu ishlar sinovdan o'tgan, regressiyani tekshirishda shu ro'yxatdan foydalaning:

1. Ikki tenant yaratib, sxema bir xilligini tekshirish (34 jadval, ustunlar mos)
2. Ma'lumot izolyatsiyasi: `users`, `settings` — biri ikkinchisini ko'rmasligi
3. `CFG` ajralishi: admin ID, nom, telefon, Bito kalit, PLU maydon
4. `tg_id → tenant` yo'naltirish
5. Ega ro'yxatdan o'tishi: to'g'ri va noto'g'ri telefon raqam bilan
6. Hodim taklif havolasi: muddat va foydalanish limiti
7. Klaviatura farqi: Boshlang'ich (15 tugma) vs Premium (9 guruh)
8. Yopiq modul tugmasi va buyrug'i to'silishi
9. Litsenziya tugaganda "faqat ko'rish": hisobot ochiq, yozuv yopiq
10. Admin botning barcha oqimlari

Lokal sinov uchun `CENTRAL_DB_PATH` va `TENANTS_DIR` ni vaqtinchalik papkaga
yo'naltiring, `TELEGRAM_BOT_TOKEN=123:FAKE` bilan `import bot` qilib
handlerlarni `bot.process_new_messages([...])` orqali chaqirish mumkin —
Telegram'ga chiqish shart emas.

---

## 9. Kontekst: ish qanday olib borilgan

Multi-tenant qatlami Cowork sessiyasida yozilgan va u yerda sinovdan o'tgan,
keyin patch sifatida repoga ko'chirilgan. Cowork'dan GitHub'ga push
bloklangani uchun shunday qilingan. **Bundan keyin ish to'g'ridan-to'g'ri shu
repoda davom etadi** — relay kerak emas.

Yangi ishni boshlashda: shu faylni o'qing, 6-bo'limdan keyingi punktni oling,
`multitenant` (yoki merge qilingan bo'lsa `main`) ustida branch oching.
