#!/usr/bin/env python3
"""
Генерація прайс-файлу для avto.pro з таблиці-моста Airtable.

Формат CSV avto.pro: A=Производитель, B=Код, C=Цена, D=Количество, E=Описание
Роздільник: ; (крапка з комою)

Генерує три файли:
  pricelist.csv       — сумарний (Хмельницький + Львів), як було раніше
  pricelist_khm.csv   — тільки залишки складу Хмельницький
  pricelist_lviv.csv  — тільки залишки складу Львів

Окремі файли потрібні для функції "кілька складів" в кабінеті avto.pro:
кожен склад підключається своїм посиланням і показує власну наявність.

Кількість береться з lookup через Product.
Немає прив'язки Product → рядок пропускається.
Примітка: поле "Qty Kyiv" — історична назва, фактично це Хмельницький.
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
FIELD_NAME = "fldVQJCkmGnUh34LI"      # Назва (опис для avto.pro)

OUTPUT_FILE = "pricelist.csv"            # сумарний (як було)
OUTPUT_KHM = "pricelist_khm.csv"         # тільки Хмельницький
OUTPUT_LVIV = "pricelist_lviv.csv"       # тільки Львів


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


def clean_text(value):
    """Нормалізує текст опису: прибирає переноси рядків, зайві пробіли.
    CSV-екранування (лапки, ;) робить сам csv.writer."""
    if value is None:
        return ""
    text = str(value)
    # Прибираємо переноси рядків, щоб опис був одним рядком
    text = text.replace("\r", " ").replace("\n", " ")
    # Схлопуємо зайві пробіли
    text = " ".join(text.split())
    return text.strip()


def main():
    if not AIRTABLE_TOKEN:
        print("ПОМИЛКА: встановіть AIRTABLE_TOKEN")
        sys.exit(1)

    print("Завантажую таблицю avto.pro...")
    records = get_records()
    print(f"  Отримано {len(records)} рядків")

    rows = []       # сумарний
    rows_khm = []   # Хмельницький
    rows_lviv = []  # Львів
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

        qty_khm = to_int(f.get(FIELD_QTY_KYIV))    # поле зветься Kyiv, фактично Хмельницький
        qty_lviv = to_int(f.get(FIELD_QTY_LVIV))
        qty = qty_khm + qty_lviv

        # Пропускаємо товари яких немає на складі (qty=0)
        # avto.pro не приймає рядки з нульовою кількістю
        if qty <= 0:
            zero_qty += 1
            continue

        # Опис (поле Назва в таблиці-мості)
        description = clean_text(f.get(FIELD_NAME))

        with_stock += 1
        # A=Производитель, B=Код, C=Цена, D=Количество, E=Описание
        rows.append([brand, code, price_val, qty, description])
        if qty_khm > 0:
            rows_khm.append([brand, code, price_val, qty_khm, description])
        if qty_lviv > 0:
            rows_lviv.append([brand, code, price_val, qty_lviv, description])

    def write_csv(path, data):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh, delimiter=";")
            for row in data:
                writer.writerow(row)

    write_csv(OUTPUT_FILE, rows)
    write_csv(OUTPUT_KHM, rows_khm)
    write_csv(OUTPUT_LVIV, rows_lviv)

    # Статистика
    with_price = sum(1 for r in rows if r[2] != "")
    in_stock = sum(1 for r in rows if r[3] > 0)
    with_desc = sum(1 for r in rows if r[4] != "")
    print(f"\nЗгенеровано {OUTPUT_FILE}:")
    print(f"  Всього рядків: {len(rows)}")
    print(f"  З ціною: {with_price}")
    print(f"  З описом: {with_desc}")
    print(f"  У прайсі (в наявності): {with_stock}")
    print(f"  Пропущено без Product: {no_product}, з qty=0: {zero_qty}")
    print(f"  В наявності (qty>0): {in_stock}")
    print(f"\nЗгенеровано {OUTPUT_KHM} (Хмельницький):")
    print(f"  Рядків: {len(rows_khm)}, одиниць: {sum(r[3] for r in rows_khm)}")
    print(f"\nЗгенеровано {OUTPUT_LVIV} (Львів):")
    print(f"  Рядків: {len(rows_lviv)}, одиниць: {sum(r[3] for r in rows_lviv)}")
    print("\nГотово.")


if __name__ == "__main__":
    main()
