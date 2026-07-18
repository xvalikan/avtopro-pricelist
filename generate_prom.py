#!/usr/bin/env python3
"""
Генерація YML-прайсу для Prom.ua з таблиці-мосту Avto.pro в Airtable.

Синхронізуємо: наявність + кількість + ціна (avto.pro Ціна(грн) × 1.2).
Ключ зіставлення: Prom ID (Ідентифікатор_товару картки Prom).

Логіка:
- беремо тільки рядки Avto.pro, де заповнений Prom ID
- кількість = Qty Kyiv + Qty Lviv (lookup через Product)
- ціна = ceil(Ціна(грн) × 1.2)
- available = true, якщо кількість > 0, інакше false
- товари без Prom ID (мастила, сторонні iPhone/EcoFlow) — не потрапляють у файл,
  тому в кабінеті Prom імпорт треба налаштувати "Товари, яких немає у файлі: Залишити без змін"

Формат: YML (Yandex Market Language) — рідний для Prom.
Prom зіставляє <offer id="{Prom ID}"> зі своєю карткою за внутрішнім ID.
"""

import os
import sys
import math
import html
import requests
from datetime import datetime

AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN", "")
AIRTABLE_BASE_ID = "appTBCTC4YhAW69K2"
AVTOPRO_TABLE = "tblQ3fnNWWDtbeNym"

# Field IDs (таблиця Avto.pro)
FIELD_PROM_ID = "fldFCJybMlLQ2Yg7h"    # Prom ID (ключ)
FIELD_CODE = "fldQqKlxEwVC9IYaz"       # Код avto.pro (для довідки)
FIELD_PRICE = "fldz926sEy2QmMdqq"      # Ціна (грн)
FIELD_QTY_KYIV = "fldMKMA8nGstCxV6G"   # Qty Kyiv (lookup)
FIELD_QTY_LVIV = "fld5GbIHhKlgf7YD8"   # Qty Lviv (lookup)
FIELD_PRODUCT = "fldUkIKXgn0rLLmdr"    # Product (link)

PROM_MARKUP = 1.2   # Prom = avto.pro × 1.2

OUTPUT_FILE = "prom.xml"


def get_records():
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AVTOPRO_TABLE}"
    headers = {"Authorization": f"Bearer {AIRTABLE_TOKEN}"}
    params = {"pageSize": 100, "returnFieldsByFieldId": "true"}
    records = []
    offset = None
    while True:
        if offset:
            params["offset"] = offset
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records


def lookup_sum(value):
    """Lookup-поле в Airtable повертається як {linkedRecordIds, valuesByLinkedRecordId}
    або як список чисел. Нормалізуємо в int."""
    if value is None:
        return 0
    if isinstance(value, dict):
        total = 0
        for vals in value.get("valuesByLinkedRecordId", {}).values():
            if isinstance(vals, list):
                for v in vals:
                    try:
                        total += float(v)
                    except (ValueError, TypeError):
                        pass
            else:
                try:
                    total += float(vals)
                except (ValueError, TypeError):
                    pass
        return int(total)
    if isinstance(value, list):
        total = 0
        for v in value:
            try:
                total += float(v)
            except (ValueError, TypeError):
                pass
        return int(total)
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


def main():
    if not AIRTABLE_TOKEN:
        print("ПОМИЛКА: встановіть AIRTABLE_TOKEN")
        sys.exit(1)

    print("Завантажую таблицю Avto.pro...")
    records = get_records()
    print(f"  Отримано {len(records)} рядків")

    offers = []
    skipped_no_promid = 0
    skipped_no_product = 0

    for rec in records:
        f = rec.get("fields", {})
        prom_id = str(f.get(FIELD_PROM_ID, "")).strip()

        # без Prom ID — не синхронізуємо (мастила, сторонні товари)
        if not prom_id:
            skipped_no_promid += 1
            continue

        # без прив'язки Product немає залишків
        if not f.get(FIELD_PRODUCT):
            skipped_no_product += 1
            continue

        qty = lookup_sum(f.get(FIELD_QTY_KYIV)) + lookup_sum(f.get(FIELD_QTY_LVIV))

        # ціна avto.pro × 1.2, округлення вгору
        price_avtopro = f.get(FIELD_PRICE)
        try:
            price_avtopro = float(price_avtopro)
        except (ValueError, TypeError):
            price_avtopro = 0
        price_prom = math.ceil(price_avtopro * PROM_MARKUP) if price_avtopro > 0 else 0

        available = "true" if qty > 0 else "false"

        offers.append({
            "id": prom_id,
            "available": available,
            "price": price_prom,
            "qty": max(qty, 0),
        })

    # Формуємо YML
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append(f'<yml_catalog date="{date_str}">')
    lines.append('<shop>')
    lines.append('<name>Mopar</name>')
    lines.append('<company>ФОП Цимбалюк В.І.</company>')
    lines.append('<currencies><currency id="UAH" rate="1"/></currencies>')
    lines.append('<offers>')
    for o in offers:
        lines.append(f'<offer id="{html.escape(o["id"])}" available="{o["available"]}">')
        if o["price"] > 0:
            lines.append(f'<price>{o["price"]}</price>')
        lines.append('<currencyId>UAH</currencyId>')
        lines.append(f'<quantity_in_stock>{o["qty"]}</quantity_in_stock>')
        lines.append('</offer>')
    lines.append('</offers>')
    lines.append('</shop>')
    lines.append('</yml_catalog>')

    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    in_stock = sum(1 for o in offers if o["available"] == "true")
    with_price = sum(1 for o in offers if o["price"] > 0)
    print(f"\nЗгенеровано {OUTPUT_FILE}:")
    print(f"  Offer-ів у прайсі: {len(offers)}")
    print(f"  В наявності (qty>0): {in_stock}")
    print(f"  З ціною: {with_price}")
    print(f"  Пропущено без Prom ID: {skipped_no_promid}, без Product: {skipped_no_product}")
    print("\nГотово.")


if __name__ == "__main__":
    main()
