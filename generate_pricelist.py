#!/usr/bin/env python3
"""
Генерація прайс-файлу для avto.pro з таблиці-моста Airtable.

Читає таблицю avto.pro → формує CSV у форматі avto.pro:
  A = Производитель, B = Код, C = Цена, D = Количество

Кількість = Qty Kyiv + Qty Lviv (з lookup через Product).
Якщо немає прив'язки Product → Кількість = 0 (немає в наявності).

Файл зберігається як pricelist.csv у корені репозиторію.
GitHub Actions комітить його → avto.pro читає за raw-посиланням.
"""

import os
import sys
import csv
import requests

AIRTABLE_TOKEN = os.environ.get("AIRTABLE_TOKEN", "")
AIRTABLE_BASE_ID = "appTBCTC4YhAW69K2"
AVTOPRO_TABLE = "tblQ3fnNWWDtbeNym"

# Назви полів (Airtable повертає значення по назвах)
NAME_BRAND = "Виробник avto.pro"
NAME_CODE = "Код avto.pro"
NAME_PRICE = "Ціна"
NAME_QTY_KYIV = "Qty Kyiv (WMS)"
NAME_QTY_LVIV = "Qty Lviv (WMS)"
NAME_PRODUCT = "Product"

OUTPUT_FILE = "pricelist.csv"


def get_avtopro_records():
    """Завантажує всі рядки таблиці avto.pro."""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AVTOPRO_TABLE}"
    headers = {"Authorization": f"Bearer {AIRTABLE_TOKEN}"}
    params = {"pageSize": 100}
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


def extract_qty(value):
    """Lookup повертає список або число. Нормалізуємо в int."""
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
    records = get_avtopro_records()
    print(f"  Отримано {len(records)} рядків")

    rows = []
    with_stock = 0
    no_product = 0

    for rec in records:
        fields = rec.get("fields", {})
        code = str(fields.get(NAME_CODE, "")).strip()
        brand = str(fields.get(NAME_BRAND, "")).strip()
        price = fields.get(NAME_PRICE, "")

        if not code or not brand:
            continue  # пропускаємо неповні рядки

        # Кількість — тільки якщо є прив'язка Product
        has_product = bool(fields.get(NAME_PRODUCT))
        if has_product:
            qty_kyiv = extract_qty(fields.get(NAME_QTY_KYIV))
            qty_lviv = extract_qty(fields.get(NAME_QTY_LVIV))
            qty = qty_kyiv + qty_lviv
            with_stock += 1
        else:
            qty = 0  # немає прив'язки → немає в наявності
            no_product += 1

        # Ціна — ціле число або порожнє
        try:
            price_val = int(float(price)) if price != "" else ""
        except (ValueError, TypeError):
            price_val = ""

        # Порядок колонок: A=Производитель, B=Код, C=Цена, D=Количество
        rows.append([brand, code, price_val, qty])

    # Записуємо CSV
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        for row in rows:
            writer.writerow(row)

    print(f"\nЗгенеровано {OUTPUT_FILE}:")
    print(f"  Всього рядків: {len(rows)}")
    print(f"  З прив'язкою Product (реальний залишок): {with_stock}")
    print(f"  Без прив'язки (кількість 0): {no_product}")
    print("\nГотово.")


if __name__ == "__main__":
    main()
