"""
🚚 MIGRATSIYA — mavjud Bonnu Market bazasini birinchi tenantga aylantirish
==========================================================================

Nima qiladi:
  1. Markaziy bazani (central.db) yaratadi
  2. Hozirgi market.db faylini tenants/<slug>.db ga NUSXALAYDI (asli tegilmaydi)
  3. tenants jadvaliga yozuv qo'shadi (barcha modullar yoqilgan, uzoq muddat)
  4. settings dagi Bito ID'larini tenant_bito ga ko'chiradi
  5. Barcha xodimlarning tg_id larini tenant_users ga bog'laydi

Ishlatish (avval SINOV rejimida):
    python3 saas/migrate_bonnu.py --dry-run
    python3 saas/migrate_bonnu.py --slug bonnu --name "Bonnu Market" \\
        --phone +998901234567 --years 5

Muhim: bu skript hech narsani O'CHIRMAYDI. Eski market.db joyida qoladi —
yangi kod ishlayotganiga ishonch hosil qilgach qo'lda o'chirasiz.
"""

import argparse
import os
import shutil
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import central as C  # noqa: E402

# settings kaliti  →  tenant_bito ustuni
BITO_MAP = {
    "bito_org_id": "org_id",
    "bito_warehouse_id": "warehouse_id",
    "bito_currency_id": "currency_id",
    "bito_sale_price_id": "sale_price_id",
    "bito_plu_field_id": "plu_field_id",
    "bito_kg_measure_id": "kg_measure_id",
    "bito_default_uom_id": "default_uom_id",
    "bito_box_type_id": "box_type_id",
    "bito_wo_reason_id": "wo_reason_id",
}


def find_source_db(explicit=None):
    for p in filter(None, [explicit, "/data/market.db", "market.db",
                           os.path.join(os.path.dirname(C._BASE), "market.db")]):
        if os.path.exists(p):
            return p
    return None


def read_settings(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
    except Exception:
        return {}
    finally:
        con.close()


def read_users(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(
            "SELECT tg_id, full_name, role FROM users").fetchall()]
    except Exception:
        return []
    finally:
        con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="mavjud market.db yo'li")
    ap.add_argument("--slug", default="bonnu")
    ap.add_argument("--name", default="Bonnu Market")
    ap.add_argument("--phone", default=os.getenv("OWNER_PHONE", ""))
    ap.add_argument("--owner-name", default="")
    ap.add_argument("--owner-tg", type=int,
                    default=int(os.getenv("SUPER_ADMIN_ID", "0") or "0"))
    ap.add_argument("--bito-key", default=os.getenv("BITO_API_KEY", ""))
    ap.add_argument("--lat", type=float, default=41.5566576)
    ap.add_argument("--lon", type=float, default=60.6373704)
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    src = find_source_db(a.source)
    if not src:
        print("❌ market.db topilmadi. --source bilan yo'lini ko'rsating.")
        return 1

    settings = read_settings(src)
    users = read_users(src)
    staff = [u for u in users if u["role"] in ("boss", "manager", "employee")]

    print(f"📂 Manba baza:     {src}  ({os.path.getsize(src)/1e6:.1f} MB)")
    print(f"👥 Foydalanuvchi:  {len(users)} ta (faol: {len(staff)})")
    print(f"⚙️  settings:       {len(settings)} ta kalit")
    found_bito = {k: v for k, v in settings.items() if k in BITO_MAP and v}
    print(f"🔌 Bito ID'lari:   {len(found_bito)} ta topildi")
    for k, v in found_bito.items():
        print(f"     {k:<24} {v}")
    dest = C.tenant_db_path(a.slug)
    print(f"📁 Nusxa manzili:  {dest}")
    print(f"🏢 Tenant:         {a.name} / {a.slug} / +{C.norm_phone(a.phone) or '—'}")

    if a.dry_run:
        print("\n🧪 --dry-run — hech narsa o'zgartirilmadi.")
        return 0

    if not a.phone:
        print("\n❌ --phone majburiy (egasi shu raqam bilan kiradi).")
        return 1

    C.init_central()

    if C.get_tenant_by_slug(a.slug):
        print(f"\n⚠️  '{a.slug}' tenant allaqachon mavjud. To'xtatildi.")
        return 1

    # 1) baza nusxasi (WAL fayllari bilan birga)
    os.makedirs(C.TENANTS_DIR, exist_ok=True)
    shutil.copy2(src, dest)
    for ext in ("-wal", "-shm"):
        if os.path.exists(src + ext):
            shutil.copy2(src + ext, dest + ext)
    print(f"\n✅ Baza nusxalandi → {dest}")

    # 2) tenant yozuvi — barcha modullar yoqilgan
    tid = C.create_tenant(
        name=a.name, slug=a.slug, owner_phone=a.phone,
        owner_name=a.owner_name, modules=[m[0] for m in C.DEFAULT_MODULES],
        plan="premium", trial_days=0, created_by=a.owner_tg)
    C.update_tenant(tid, shop_lat=a.lat, shop_lon=a.lon,
                    owner_tg_id=a.owner_tg or None)
    C.start_license(tid, days=365 * a.years, period="yearly", amount=0,
                    created_by=a.owner_tg)
    print(f"✅ Tenant yaratildi (id={tid}), litsenziya {a.years} yil")

    # 3) Bito
    if a.bito_key:
        try:
            C.set_bito_key(tid, a.bito_key)
            print("✅ Bito API kaliti shifrlab saqlandi")
        except ValueError as e:
            # Migratsiyani to'xtatmaymiz — kalitni keyin bot orqali kiritish
            # mumkin, qolgan ko'chirish esa allaqachon bajarilgan.
            print(f"⚠️  {e} — kalit saqlanmadi, keyin qo'lda kiriting")
    cfg = {BITO_MAP[k]: v for k, v in found_bito.items()}
    if cfg:
        C.set_bito_config(tid, **cfg)
        print(f"✅ {len(cfg)} ta Bito ID ko'chirildi")

    # 4) foydalanuvchilar
    n = 0
    for u in users:
        if not u["tg_id"]:
            continue
        C.bind_user(u["tg_id"], tid,
                    "boss" if u["role"] in ("boss", "manager") else "employee")
        n += 1
    print(f"✅ {n} ta foydalanuvchi '{a.slug}' ga bog'landi")

    C.log(a.owner_tg, tid, "migrated", f"{src} → {dest}")
    print(f"\n🎉 Tayyor. Havola: {C.owner_link(a.slug)}")
    print(f"   Eski fayl ({src}) tegilmadi — sinovdan keyin o'zingiz o'chirasiz.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
