# `saas/` — Multi-tenant yadro va litsenziya boti

Bu papka AIMARKETNM_BOT ni **bitta do'kon** botidan **ko'p biznesga sotiladigan**
mahsulotga aylantiruvchi qismi.

`bot.py` endi shu qatlam ustida ishlaydi: `q()/qone()/qall()` joriy biznesning
SQLite fayliga yo'naltiriladi, `W_*` lug'atlari va keshlar tenant bo'yicha
ajratiladi, `SUPER_ADMIN_ID`/`BITO_API_KEY` kabi 200+ murojaat `CFG` orqali
markaziy bazadan olinadi. **Chaqiruv joylari (384 ta SQL) o'zgarmagan.**

⚠️ Python **3.12+** kerak (bot.py da PEP 701 f-string sintaksisi ishlatilgan).

| Fayl | Vazifasi |
|---|---|
| `central.py` | Markaziy registr: bizneslar, modullar, litsenziya, to'lov, havolalar |
| `admin_bot.py` | Litsenziya boti (faqat platforma egasi uchun) |
| `migrate_bonnu.py` | Mavjud `market.db` ni birinchi tenantga aylantirish |
| `tenant.py` | `bot.py` uchun tenant yadrosi: DB yo'naltirish, `TDict`/`TSet`, `CFG`, `@needs` |

---

## 1. Muhit o'zgaruvchilari

| O'zgaruvchi | Majburiy | Nima |
|---|---|---|
| `ADMIN_BOT_TOKEN` | ha | Litsenziya botining tokeni (@BotFather) |
| `SAAS_OWNER_ID` | ha | Sizning Telegram ID'ingiz — botga faqat siz kira olasiz |
| `MASTER_KEY` | **ha** | Bito API kalitlari shu bilan shifrlanadi. Berilmasa avtomatik yaratiladi va `.master_key` fayliga yoziladi — **uni Railway Variables'ga ko'chiring**, aks holda volume yo'qolsa barcha Bito kalitlari o'qib bo'lmas holga keladi |
| `MAIN_BOT_USERNAME` | yo'q | Standart: `AIMARKETNM_BOT` — havolalar shu nom bilan yasaladi |
| `CENTRAL_DB_PATH` | yo'q | Standart: `/data/central.db` |
| `TENANTS_DIR` | yo'q | Standart: `/data/tenants` |
| `TRIAL_DAYS` | yo'q | Standart 14 |
| `GRACE_DAYS` | yo'q | Standart 3 |
| `AI_DAILY_LIMIT` | yo'q | Standart 300 — tenantga kunlik AI chaqiruv limiti |

`MASTER_KEY` yaratish:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## 2. Ishga tushirish

```bash
pip install -r requirements.txt

# markaziy bazani yaratish va modul katalogini ko'rish
python3 saas/central.py

# litsenziya botini alohida ishga tushirish
ADMIN_BOT_TOKEN=... SAAS_OWNER_ID=... python3 saas/admin_bot.py
```

Asosiy bot bilan **bitta jarayonda** ishlatish uchun `bot.py` oxiriga:

```python
from saas.admin_bot import start_admin_bot
start_admin_bot()          # o'z threadida polling qiladi
```

---

## 3. Mavjud bazani ko'chirish

```bash
# avval sinov — hech narsa o'zgarmaydi
python3 saas/migrate_bonnu.py --dry-run

# haqiqiy
python3 saas/migrate_bonnu.py \
    --slug bonnu --name "Bonnu Market" \
    --phone +998901234567 --owner-tg $SUPER_ADMIN_ID \
    --bito-key "$BITO_API_KEY" --years 5
```

Skript `market.db` ni **nusxalaydi**, aslini o'chirmaydi.

---

## 4. Litsenziya botidagi menyu

| Tugma | Nima qiladi |
|---|---|
| ➕ Yangi biznes | 5 bosqichli sehrgar: nom → slug → telefon → ega → tarif |
| 📋 Bizneslar | Ro'yxat; har birining kartochkasi: modullar, muddat, to'lov, havolalar, to'xtatish, tarix |
| 💳 To'lovlar | Oxirgi 20 ta to'lov |
| 📊 Hisobot | Bizneslar holati, oylik/jami tushum, MRR, modul mashhurligi |
| ⏰ Muddati yaqinlar | 7 kun ichida tugaydiganlar (kuniga bir marta avtomatik ham keladi) |
| 🧩 Modul narxlari | Katalog; `/narx <kod> <summa>` bilan o'zgartiriladi |

---

## 5. Havola formatlari

```
Egasi:   t.me/AIMARKETNM_BOT?start=apelsinmarket
Hodim:   t.me/AIMARKETNM_BOT?start=e-apelsinmarket-7Kd93x
Mijoz:   t.me/AIMARKETNM_BOT?start=r-apelsinmarket
Nomzod:  t.me/AIMARKETNM_BOT?start=j-apelsinmarket-14
```

`central.parse_start_payload()` bularni ajratadi.

---

## 6. `bot.py` uchun API (keyingi bosqich)

Asosiy botga integratsiya qilinganda ishlatiladigan funksiyalar:

```python
import saas.central as C

t = C.tenant_of_user(tg_id)          # bu odam qaysi biznesniki?
C.has_module(t["id"], "ombor")       # modul yoqilganmi?
C.is_readonly(t["id"])               # litsenziya tugaganmi? (faqat ko'rish)
C.get_bito(t["id"])["api_key"]       # shu biznesning Bito kaliti
C.ai_allowed(t["id"]); C.ai_bump(t["id"])   # AI limiti
C.tenant_db_path(t["slug"])          # shu biznesning SQLite fayli
```

---

## 7. Holat

- [x] Markaziy registr (`central.py`) — sinovdan o'tgan
- [x] Litsenziya boti (`admin_bot.py`) — barcha oqimlar sinovdan o'tgan
- [x] Migratsiya skripti — sinovdan o'tgan
- [x] `bot.py` tenant yadrosi (`tenant.py`: DB yo'naltirish, `TDict`/`TSet`, `CFG`)
- [x] Har update o'z biznesining kontekstida (`attach_tenant_routing`)
- [x] Yangi tenantga sxema avtomatik ko'chadi (67 ta DDL yozib olinadi)
- [ ] Deep-link ro'yxatdan o'tish `bot.py` ichida (telefon bilan tasdiqlash)
- [ ] Modul gating (menyu filtri + `@needs` dekoratorini handlerlarga qo'yish)
- [ ] Fon oqimlari uchun bitta rejalashtiruvchi
- [ ] Telegram xabar navbati (throttling)
