# Botni yangi joyda ishga tushirish

Bu arxiv — ishlab turgan botning **aynan nusxasi**. Kod o'zgartirilmagan.

Manba: `jekloviyapoya/market-bot` · commit `2c752a4` · `bot.py` 21 099 qator

---

## 1. Arxivdagi fayllar

| Fayl | Nima |
|---|---|
| `bot.py` | Butun bot: Telegram + Flask webapp + PWA |
| `requirements.txt` | Python kutubxonalari |
| `replit.nix`, `.replit` | Replit uchun (Railway ishlatmaydi) |
| `.gitignore` | **Yangi** — maxfiy fayllar GitHub'ga chiqmasin |
| `.env.example` | **Yangi** — kerakli o'zgaruvchilar ro'yxati |
| `O'RNATISH.md` | Shu fayl |

Baza fayli **yo'q** va bo'lmasligi kerak — bot birinchi ishga tushganda
jadvallarni o'zi yaratadi.

---

## 2. Yangi bot yaratish

1. Telegram'da **@BotFather** → `/newbot` → nom va username
2. Token olinadi (`123456789:AA...`) — uni hech kimga bermang

---

## 3. GitHub

```bash
# Arxivni ochib, papkaga kiring
git init
git add .
git commit -m "Boshlang'ich nusxa"
git branch -M main
git remote add origin https://github.com/<akkaunt>/<yangi-repo>.git
git push -u origin main
```

Repo **private** bo'lsin.

`.gitignore` allaqachon tayyor — `.env`, baza fayllari va tokenlar
GitHub'ga chiqmaydi.

---

## 4. Railway

1. **New Project** → **Deploy from GitHub repo** → yangi repo
2. Branch: **`main`**, **Auto deploys** yoqilgan bo'lsin
3. **Volume qo'shish** (juda muhim):
   - Service → Settings → Volumes → **Add Volume**
   - Mount path: **`/data`**
   - Hajm: 1–5 GB
   > Volume bo'lmasa har deployda **butun baza yo'qoladi** — xodimlar,
   > vazifalar, sozlamalar, hammasi.
4. **Variables** bo'limiga o'zgaruvchilar kiritiladi (pastda)
5. Deploy o'zi boshlanadi

Build/Start buyrug'i sozlash **shart emas** — Railway `railpack` bilan
Python'ni o'zi aniqlaydi va `python bot.py` ni ishga tushiradi.

---

## 5. Environment Variables

### Majburiy — bo'lmasa bot ishga tushmaydi

| Nomi | Nima |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather bergan token |
| `SUPER_ADMIN_ID` | Egasining Telegram ID raqami |
| `BITO_API_KEY` | Bito ERP kaliti |
| `ANTHROPIC_API_KEY` | Hujjat o'qish va tahlil |

> Telegram ID ni bilish uchun: @userinfobot ga yozing.

### Ixtiyoriy

| Nomi | Bo'lmasa nima bo'ladi |
|---|---|
| `OPENAI_API_KEY` | AI poster yasalmaydi (oddiy montaj ishlaydi) |
| `GROQ_API_KEY` | Ovozli xabar matnga o'girilmaydi |
| `GEMINI_API_KEY` | Ovoz uchun zaxira yo'l ishlamaydi |
| `APP_JWT_SECRET` | PWA ilovasiga kirish ishlamaydi |
| `IG_USER_ID`, `IG_ACCESS_TOKEN` | Instagram'ga post joylanmaydi |

### ⚠️ Bito sozlamalari — diqqat bilan o'qing

Kodda quyidagi ID'lar **standart qiymat** bilan turibdi:

```
BITO_ORG_ID          693fea06ff2118868c955b6c
BITO_WAREHOUSE_ID    69424f36a3a3cc43da908320
BITO_SALE_PRICE_ID   694250a9c9b42022084696f6
BITO_PLU_FIELD_ID    69426b2ec75f38c3f5d9e91e
BITO_KG_MEASURE_ID   693fea08ff2118868c955d18
```

Bular **manba do'konning** qiymatlari.

- **Bito akkaunt o'zgarmasa** (o'sha do'kon, faqat yangi bot) —
  hech narsa kiritmang, shundayligicha ishlaydi
- **Boshqa Bito akkaunti bo'lsa** — bu o'zgaruvchilarni **albatta**
  kiriting. Aks holda bot xato bermaydi, shunchaki **eski do'konning
  omboriga yozadi** — bu jimgina va sezilmasdan sodir bo'ladi

Yangi ID'larni topish: Bito → Sozlamalar, yoki API orqali
`organization/get-all`, `warehouse/get-all`, `price/get-all`.

---

## 6. Birinchi ishga tushirish

1. Railway → **Deploy Logs** ni oching
2. Quyidagi qatorlarni kuting:
   ```
   ✅ ... bot ishga tushdi...
   🧩 BUILD sha=XXXXXXXXXX | handlerlar=NNN
   ```
3. Telegram'da yangi botga **`/start`** yozing
4. `SUPER_ADMIN_ID` to'g'ri bo'lsa — sizga **boshliq** menyusi chiqadi

---

## 7. Tekshirish ro'yxati

- [ ] `/start` — menyu chiqdi
- [ ] «📦 Ombor hisoboti» — qoldiq ko'rinadi (Bito ulanishi ishlayapti)
- [ ] «⏱ Davomat» — «Keldim» bosiladi
- [ ] «📋 Vazifa berish» — vazifa xodimga boradi
- [ ] «💰 Pul taqvimi» — kassa qoldig'i chiqadi
- [ ] «🧾 Nakladnoy» — rasm yuborib sinash
- [ ] «📱 Chiroyli tahrirlash» — webapp ochiladi
- [ ] Railway restart → bot qayta ishga tushdi, **ma'lumotlar joyida**

Oxirgi band eng muhim: restartdan keyin xodimlar va sozlamalar
saqlanib qolgan bo'lsa — volume to'g'ri ulangan.

---

## 8. Bilib qo'yish kerak

- **Bir token — bitta bot.** Eski va yangi bot bir tokenda ishlay olmaydi
- **Railway «Redeploy»** o'sha kartadagi commitni quradi. Yangi kod uchun
  yangi commit push qiling
- Bot **polling** bilan ishlaydi — webhook sozlash shart emas
- Baza `/data` ichida. Volume mount path aynan **`/data`** bo'lishi shart
- Kod bitta faylda (21 000 qator) — bu ataylab shunday, bo'lish shart emas
