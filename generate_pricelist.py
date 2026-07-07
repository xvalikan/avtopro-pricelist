#!/usr/bin/env python3
"""
Генерація прайс-файлу для avto.pro з таблиці-моста Airtable.

Формат CSV avto.pro: A=Производитель, B=Код, C=Цена, D=Количество
Роздільник: ; (крапка з комою)

Кількість = Qty Kyiv + Qty Lviv (lookup через Product).
Немає прив'язки Product → Кількість = 0.
"""

import os
import sys
import csv
import requests

AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN", "")
AIRTABLE_BASE_ID = "appTBCTC4YhAW69K2"
AVTOPRO_TABLE = "tblQ3fnNWWDtbeNym"

# Field IDs (читаємо по ID — надійніше ніж по назвах)
FIELD_CODE = "fldQqKlxEwVC9IYaz"      # Код avto.pro
FIELD_BRAND = "fldSKZKJY5VmVbrNR"     # Виробник avto.pro
FIELD_PRICE = "fldz926sEy2QmMdqq"     # Ціна
FIELD_QTY_KYIV = "fldMKMA8nGstCxV6G"  # Qty Kyiv (lookup)
FIELD_QTY_LVIV = "fld5GbIHhKlgf7YD8"  # Qty Lviv (lookup)
FIELD_PRODUCT = "fldUkIKXgn0rLLmdr"   # Product (link)

OUTPUT_FILE = "pricelist.csv"


def get_records():
    """Завантажує всі рядки avto.pro через REST API (returnFieldsByFieldId)."""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AVTOPRO_TABLE}"
    headers = {"Authorization": f"Bearer {AIRTABLE_TOKEN}"}
    params = {
        "pageSize": 100,
        "returnFieldsByFieldId": "true",  # повертати поля по field ID
    }
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


def to_int(value):
    """Нормалізує значення (число, список, або None) в int."""
    if value is None:
        return 0
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

    print("Завантажую таблицю avto.pro...")
    records = get_records()
    print(f"  Отримано {len(records)} рядків")

    rows = []
    with_stock = 0
    no_product = 0
    zero_qty = 0

    for rec in records:
        f = rec.get("fields", {})
        code = str(f.get(FIELD_CODE, "")).strip()
        brand = str(f.get(FIELD_BRAND, "")).strip()

        if not code or not brand:
            continue

        # Ціна
        price = to_int(f.get(FIELD_PRICE))
        price_val = price if price > 0 else ""

        # Пропускаємо рядки без прив'язки Product (немає товару в обліку)
        if not f.get(FIELD_PRODUCT):
            no_product += 1
            continue

        qty = to_int(f.get(FIELD_QTY_KYIV)) + to_int(f.get(FIELD_QTY_LVIV))

        # Пропускаємо товари яких немає на складі (qty=0)
        # avto.pro не приймає рядки з нульовою кількістю
        if qty <= 0:
            zero_qty += 1
            continue

        with_stock += 1
        # A=Производитель, B=Код, C=Цена, D=Количество
        rows.append([brand, code, price_val, qty])

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, delimiter=";")
        for row in rows:
            writer.writerow(row)

    # Статистика
    with_price = sum(1 for r in rows if r[2] != "")
    in_stock = sum(1 for r in rows if r[3] > 0)
    print(f"\nЗгенеровано {OUTPUT_FILE}:")
    print(f"  Всього рядків: {len(rows)}")
    print(f"  З ціною: {with_price}")
    print(f"  У прайсі (в наявності): {with_stock}")
    print(f"  Пропущено без Product: {no_product}, з qty=0: {zero_qty}")
    print(f"  В наявності (qty>0): {in_stock}")
    print("\nГотово.")


if __name__ == "__main__":
    main()
