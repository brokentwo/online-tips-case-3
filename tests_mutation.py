#!/usr/bin/env python3
"""
Проверка самих тестов: намеренно ломает прототип и смотрит, заметят ли это tests_t3.py.

Запуск: python3 tests_mutation.py
Каждая поломка делается во временной копии, сам прототип не меняется.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "04_прототип.py")

MUTATIONS = [
    ("Подпись всегда верна", "return same(sign_qr(qr), qr[\"signature\"])", "return True"),
    ("Подпись без employee_id", "{qr['merchant_id']}|{qr['employee_id']}|", "{qr['merchant_id']}|"),
    ("Срок не проверяется", "return parse_time(qr[\"exp\"]) >= parse_time(now)", "return True"),
    ("Отказ подписи не пишется в журнал", "audit(\"invalid_qr\", \"\", stored[\"qr_id\"], \"\", \"\", \"\", \"client\", now)", "pass"),
    ("Отказ срока не пишется в журнал", "audit(\"qr_expired\", \"\", qr[\"qr_id\"], \"\", \"\", \"\", \"client\", now)", "pass"),
    ("Nonce можно использовать снова", "raise ApiError(\"QR_USED\")", "pass"),
    ("Nonce занят и после отказа", "ACTIVE_NONCE = {\"CREATED\", \"PENDING\", \"SUCCESS\"}", "ACTIVE_NONCE = {\"CREATED\", \"PENDING\", \"SUCCESS\", \"DECLINED\"}"),
    ("Блокировка не проверяется при оплате", "if not merchant_is_active(qr[\"merchant_id\"]):  # Q-4", "if False:  # Q-4"),
    ("PENDING считается активным мерчантом", "return bool(merchant) and merchant[\"status\"] == \"ACTIVE\"", "return bool(merchant) and merchant[\"status\"] != \"BLOCKED\""),
    ("Чек не сверяется", "if req.get(\"receipt_id\", qr[\"receipt_id\"]) != qr[\"receipt_id\"]:  # Q-5", "if False:  # Q-5"),
    ("Предел чаевых 51%", "MAX_TIP_PCT = Decimal(\"50\")", "MAX_TIP_PCT = Decimal(\"51\")"),
    ("Отрицательные чаевые разрешены", "if pct < 0 or pct > MAX_TIP_PCT or tip < 0 or", "if pct > MAX_TIP_PCT or"),
    ("Своя сумма не проверяется", " or tip > base * MAX_TIP_PCT / 100:  # Q-6", ":  # Q-6"),
    ("Ноль в чеке разрешён", "if base <= 0 or base > MAX_BASE:", "if base < 0 or base > MAX_BASE:"),
    ("Верхний предел чека не работает", "if base <= 0 or base > MAX_BASE:", "if base <= 0:"),
    ("P-3 не работает", "if total > MAX_TOTAL:  # P-3", "if False:  # P-3"),
    ("Повтор не находит платёж", "known = find_row(index, \"idempotency_key\", key)", "known = None"),
    ("Другое тело с тем же ключом проходит", "raise ApiError(\"IDEMPOTENCY_CONFLICT\")", "pass"),
    ("Округление чаевых вниз", "rounding=ROUND_HALF_UP)", "rounding=\"ROUND_DOWN\")"),
    ("Итог без чаевых", "return tip, money(base + tip)", "return tip, money(base)"),
    ("Контрольный код qr_001 убран", "CONTROL_CODES = {\"qr_001\": 0, \"qr_003\": 8}", "CONTROL_CODES = {\"qr_003\": 8}"),
    ("Контрольный код qr_003 убран", "CONTROL_CODES = {\"qr_001\": 0, \"qr_003\": 8}", "CONTROL_CODES = {\"qr_001\": 0}"),
    ("Формула другая", "hashlib.md5((qr_id + nonce + salt)", "hashlib.sha1((qr_id + nonce + salt)"),
    ("Код 8 считается успехом", "if h <= 7:", "if h <= 8:"),
    ("Отмена разрешена из PENDING", "if payment[\"status\"] != \"CREATED\":\n        raise ApiError(\"CANCEL_NOT_ALLOWED\")", "if False:\n        raise ApiError(\"CANCEL_NOT_ALLOWED\")"),
    ("Токен подтверждения не проверяется", "if not same(req.get(\"confirm_token\", \"\"), confirm_token(payment_id)):", "if False:"),
    ("Строка платежа дублируется", "    if current:\n        current.update(payment)\n        write_csv(OUT_CSV, OUT_FIELDS, rows)\n    else:\n        append_csv(OUT_CSV, OUT_FIELDS, payment)", "    append_csv(OUT_CSV, OUT_FIELDS, payment)"),
    ("Переход не пишется в журнал", "audit(action, payment[\"payment_id\"], row[\"qr_id\"], from_status, to_status, total, actor, now)", "pass"),
    ("Новый QR живёт 48 часов", "QR_TTL = timedelta(hours=24)", "QR_TTL = timedelta(hours=48)"),
    ("Второй QR на тот же чек разрешён", "raise ApiError(\"RECEIPT_EXISTS\")", "pass"),
    ("Истёкший чек нельзя выпустить заново", "if check_exp(row, now) or has_active_payment(row[\"qr_id\"]):", "if True:"),
    ("Оплаченный чек можно выпустить заново", "if check_exp(row, now) or has_active_payment(row[\"qr_id\"]):", "if check_exp(row, now):"),
    ("Сотрудник чужого заведения разрешён", "if not employee or employee[\"merchant_id\"] != req[\"merchant_id\"]:", "if not employee:"),
    ("Отчёт считает все статусы", "success = [r for r in rows if r[\"status\"] == \"SUCCESS\"]\n    if req.get(\"kind\") == \"daily\":", "success = rows\n    if req.get(\"kind\") == \"daily\":"),
    ("Отчёт официанта считает все статусы", "rows = [r for r in period_rows(req) if r[\"employee_id\"] == employee_id]\n    success = [r for r in rows if r[\"status\"] == \"SUCCESS\"]", "rows = [r for r in period_rows(req) if r[\"employee_id\"] == employee_id]\n    success = rows"),
    ("Официант видит чужие чаевые", "or (role == \"waiter\" and actor == employee_id))", "or role == \"waiter\")"),
    ("Мерчант видит чужой отчёт", "allowed = role == \"admin\" or (role == \"merchant\" and actor == merchant_id)", "allowed = role in (\"admin\", \"merchant\")"),
]


def main():
    with open(SOURCE, encoding="utf-8") as f:
        source = f.read()
    caught = 0
    missed = []
    for name, old, new in MUTATIONS:
        if source.count(old) < 1:
            print(f"[НЕ ПРИМЕНИЛАСЬ] {name}")
            missed.append(name)
            continue
        with tempfile.TemporaryDirectory(prefix="tips_mut_") as folder:
            path = os.path.join(folder, "04_прототип.py")
            with open(path, "w", encoding="utf-8") as f:
                f.write(source.replace(old, new, 1))
            env = {**os.environ, "TIPS_PROTOTYPE": path, "TIPS_NO_REPORT": "1"}
            result = subprocess.run([sys.executable, os.path.join(HERE, "tests_t3.py")], env=env,
                                    capture_output=True, text=True, encoding="utf-8")
        if result.returncode != 0:
            caught += 1
            print(f"[ПОЙМАНА] {name}")
        else:
            missed.append(name)
            print(f"[ПРОПУЩЕНА] {name}")
    print(f"Поймано {caught} из {len(MUTATIONS)}")
    sys.exit(0 if not missed else 1)


if __name__ == "__main__":
    main()
