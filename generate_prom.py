#!/usr/bin/env python3
"""
Генерація Excel-прайсу для Prom.ua на основі шаблону-експорту.

Підхід: беремо оригінальний експорт Prom (prom_template.xlsx) як основу —
він містить усі 108 колонок, які Prom розуміє. Оновлюємо в ньому ТІЛЬКИ
три колонки для товарів, що мають Prom ID в Airtable:
  - Ціна          = avto.pro Ціна(грн) × 1.2 (округлення вгору)
  - Наявність     = '+' якщо залишок > 0, інакше '-'
  - Кількість     = Qty Kyiv + Qty Lviv

Зіставлення: Ідентифікатор_товару (Prom ID) у шаблоні = Prom ID в Airtable.

Товари в шаблоні, яких немає в Airtable (сторонні iPhone, EcoFlow, мастила),
залишаються без змін.

Результат: prom.xlsx — той самий формат, що Prom віддає на експорті.
"""

import os
import sys
import math
import requests
import pandas as pd

AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN", "")
AIRTABLE_BASE_ID = "appTBCTC4YhAW69K2"
AVTOPRO_TABLE = "tblQ3fnNWWDtbeNym"

FIELD_PROM_ID = "fldFCJybMlLQ2Yg7h"
FIELD_PRICE = "fldz926sEy2QmMdqq"
FIELD_QTY_KYIV = "fldMKMA8nGstCxV6G"
FIELD_QTY_LVIV = "fld5GbIHhKlgf7YD8"
FIELD_PRODUCT = "fldUkIKXgn0rLLmdr"

PROM_MARKUP = 1.2

TEMPLATE_FILE = "prom_template.xlsx"
OUTPUT_FILE = "prom.xlsx"
SHEET_NAME = "Export Products Sheet"


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

    if not os.path.exists(TEMPLATE_FILE):
        print(f"ПОМИЛКА: не знайдено шаблон {TEMPLATE_FILE}")
        print("Покладіть оригінальний експорт Prom у репозиторій під назвою prom_template.xlsx")
        sys.exit(1)

    print("Завантажую дані Airtable...")
    records = get_records()
    print(f"  Отримано {len(records)} рядків Avto.pro")

    prom_data = {}
    for rec in records:
        f = rec.get("fields", {})
        prom_id = str(f.get(FIELD_PROM_ID, "")).strip()
        if not prom_id or not f.get(FIELD_PRODUCT):
            continue
        qty = lookup_sum(f.get(FIELD_QTY_KYIV)) + lookup_sum(f.get(FIELD_QTY_LVIV))
        try:
            price_av = float(f.get(FIELD_PRICE))
        except (ValueError, TypeError):
            price_av = 0
        price = math.ceil(price_av * PROM_MARKUP) if price_av > 0 else 0
        prom_data[prom_id] = {
            "price": price,
            "available": "+" if qty > 0 else "-",
            "qty": max(qty, 0),
        }

    print(f"  Товарів з Prom ID для оновлення: {len(prom_data)}")

    print(f"Читаю шаблон {TEMPLATE_FILE}...")
    df = pd.read_excel(TEMPLATE_FILE, sheet_name=SHEET_NAME, dtype={"Ідентифікатор_товару": str})

    updated = 0
    not_in_airtable = 0
    for idx, row in df.iterrows():
        pid = row.get("Ідентифікатор_товару")
        if pd.isna(pid):
            continue
        pid = str(pid).strip()
        if pid.endswith(".0"):
            pid = pid[:-2]
        if pid in prom_data:
            d = prom_data[pid]
            if d["price"] > 0:
                df.at[idx, "Ціна"] = d["price"]
            df.at[idx, "Наявність"] = d["available"]
            df.at[idx, "Кількість"] = d["qty"]
            updated += 1
        else:
            not_in_airtable += 1

    df.to_excel(OUTPUT_FILE, sheet_name=SHEET_NAME, index=False)

    print(f"\nЗгенеровано {OUTPUT_FILE}:")
    print(f"  Оновлено товарів: {updated}")
    print(f"  Залишено без змін (немає в Airtable): {not_in_airtable}")
    print("\nГотово.")


if __name__ == "__main__":
    main()
