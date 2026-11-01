#!/usr/bin/env python3
"""
Тесты прототипа: T3-1…T3-5 из 03_тесты.md, таймаут T3-6 и проверки правил.

Запуск: python3 tests_t3.py
Каждый тест идёт в своей временной папке, результат записывается в test_results.md.
"""
import csv
import hashlib
import importlib.util
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

HERE = os.path.dirname(os.path.abspath(__file__))
PROTOTYPE = os.environ.get("TIPS_PROTOTYPE", os.path.join(HERE, "04_прототип.py"))
DATA_DIR = next(p for p in (os.path.join(HERE, "ДАННЫЕ"), os.path.join(HERE, "..", "ДАННЫЕ")) if os.path.isdir(p))
AFTER_EXP = "2025-11-02T00:00:00Z"  # qr_001 действует до 2025-11-01T23:59:00Z


class Run:
    """Отдельная копия выходных файлов прототипа на один тест."""

    def __init__(self, data_dir=DATA_DIR):
        self.tmp = tempfile.mkdtemp(prefix="tips_")
        self.env = {**os.environ, "TIPS_OUT_DIR": self.tmp, "TIPS_DATA_DIR": data_dir, "PYTHONIOENCODING": "utf-8"}

    def __call__(self, **req):
        path = os.path.join(self.tmp, "request.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(req, f, ensure_ascii=False)
        out = subprocess.run([sys.executable, PROTOTYPE, path], env=self.env, capture_output=True, text=True, encoding="utf-8")
        if out.stderr:
            raise AssertionError(out.stderr)
        body = json.loads(out.stdout)
        body["exit"] = out.returncode
        return body

    def rows(self, name="payments_out.csv"):
        path = os.path.join(self.tmp, name)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


def csv_rows(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def data_with_merchant_status(merchant_id, status):
    """Копия данных с другим статусом мерчанта. Исходные файлы не меняются."""
    folder = tempfile.mkdtemp(prefix="tips_data_")
    for name in os.listdir(DATA_DIR):
        shutil.copy(os.path.join(DATA_DIR, name), folder)
    path = os.path.join(folder, "merchants.csv")
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        if row["merchant_id"] == merchant_id:
            row["status"] = status
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return folder


def check(condition, message):
    if not condition:
        raise AssertionError(message)


# ---------- T3-1…T3-6 ----------

def t3_1(run):
    r = run(qr_id="qr_001", base_amount=637.00, tip_pct=5)
    check(r["status"] == "SUCCESS", r)
    check(r["amount_total"] == 668.85 and r["tip_amount"] == 31.85, r)
    row = run.rows()[0]
    history = csv_rows("payments.csv")[0]
    check((row["amount"], row["tip"], row["status"]) == (history["amount"], history["tip"], history["status"]), row)
    return f"HTTP {r['http']}, {r['status']}, amount_total={r['amount_total']}, tip={r['tip_amount']}; сумма и чаевые совпали с p_0001"


def t3_2(run):
    r = run(qr_id="qr_003", base_amount=911.00, tip_pct=15)
    check(r["status"] == "DECLINED" and r["error_code"] == "CARD_DECLINED" and r["http"] == 402, r)
    check(r["amount_total"] == 1047.65 and r["tip_amount"] == 136.65, r)
    check(run.rows()[0]["status"] == "DECLINED", run.rows())
    return f"HTTP {r['http']}, {r['status']}, {r['error_code']}, retryable={r['retryable']}; строка со статусом DECLINED записана"


def t3_3(run):
    r1 = run(qr_id="qr_001", signature="0000000000000000", base_amount=637.00, tip_pct=5)
    check(r1["error_code"] == "INVALID_QR" and r1["http"] == 422, r1)
    r2 = run(qr_id="qr_001", employee_id="e_002", base_amount=637.00, tip_pct=5)
    check(r2["error_code"] == "INVALID_QR", r2)
    r3 = run(qr_id="qr_001", base_amount=637.00, tip_pct=5, now=AFTER_EXP)
    check(r3["error_code"] == "QR_EXPIRED" and r3["http"] == 410, r3)
    check(run.rows() == [], "платёж создан")
    actions = [e["action"] for e in run.rows("audit_out.csv")]
    check(actions == ["invalid_qr", "invalid_qr", "qr_expired"], actions)
    return f"подпись: HTTP {r1['http']} {r1['error_code']}; подмена официанта: {r2['error_code']}; истёкший QR: HTTP {r3['http']} {r3['error_code']}; строк в файле: 0, отказы в журнале: 3"


def t3_4(run):
    req = dict(qr_id="qr_002", base_amount=774.00, tip_pct=10, idempotency_key="key-1")
    r1 = run(**req)
    r2 = run(**req)
    check(r1["payment_id"] == r2["payment_id"], (r1, r2))
    check(r1["http"] == 200 and r2["http"] == 200, (r1, r2))
    check(len(run.rows()) == 1, run.rows())
    check(len([e for e in run.rows("audit_out.csv") if e["action"] == "payment_confirmed"]) == 1, "два списания")
    r3 = run(**{**req, "tip_pct": 15})
    check(r3["error_code"] == "IDEMPOTENCY_CONFLICT" and r3["http"] == 409, r3)
    return f"оба ответа: {r1['payment_id']}, HTTP 200; строк в файле: 1; списаний: 1; тот же ключ с другой суммой: HTTP {r3['http']} {r3['error_code']}"


def t3_5(run):
    created = run(action="create", qr_id="qr_002", base_amount=774.00, tip_pct=10)
    check(created["status"] == "CREATED" and created["http"] == 201, created)
    canceled = run(action="cancel", payment_id=created["payment_id"], confirm_token=created["confirm_token"])
    check(canceled["status"] == "CANCELED" and canceled["http"] == 200, canceled)
    check(run.rows()[0]["status"] == "CANCELED", run.rows())

    created = run(action="create", qr_id="qr_010", base_amount=1870.00, tip_pct=5)
    token = dict(payment_id=created["payment_id"], confirm_token=created["confirm_token"])
    pending = run(action="confirm", **token)
    check(pending["status"] == "PENDING", pending)
    refused = run(action="cancel", **token)
    check(refused["error_code"] == "CANCEL_NOT_ALLOWED" and refused["http"] == 409, refused)
    check(run.rows()[1]["status"] == "PENDING", run.rows())

    paid = run(qr_id="qr_004", base_amount=1048.00, tip_pct=5)
    check(paid["status"] == "SUCCESS", paid)
    late = run(action="cancel", payment_id=paid["payment_id"], confirm_token=paid["confirm_token"])
    check(late["error_code"] == "CANCEL_NOT_ALLOWED" and late["http"] == 409, late)
    return f"из CREATED: HTTP {canceled['http']} {canceled['status']}; из PENDING: HTTP {refused['http']} {refused['error_code']}; из SUCCESS: HTTP {late['http']} {late['error_code']}"


def t3_6(run):
    r1 = run(qr_id="qr_010", base_amount=1870.00, tip_pct=5)
    check(r1["status"] == "PENDING" and r1["error_code"] == "GATEWAY_TIMEOUT" and r1["retryable"] is True, r1)
    r2 = run(action="confirm", payment_id=r1["payment_id"], confirm_token=r1["confirm_token"])
    check(r2["payment_id"] == r1["payment_id"], r2)
    check(r2["status"] in ("SUCCESS", "DECLINED", "PENDING"), r2)
    check(len(run.rows()) == 1, run.rows())
    return f"HTTP {r1['http']}, {r1['status']}, {r1['error_code']}, retryable={r1['retryable']}; повторный опрос: {r2['status']}; строк в файле: 1"


# ---------- Правила и данные ----------

def q3_nonce(run):
    run(qr_id="qr_002", base_amount=774.00, tip_pct=10, idempotency_key="a")
    r = run(qr_id="qr_002", base_amount=774.00, tip_pct=10, idempotency_key="b")
    check(r["error_code"] == "QR_USED" and r["http"] == 409, r)
    first = run(qr_id="qr_003", base_amount=911.00, tip_pct=15, idempotency_key="c")
    second = run(qr_id="qr_003", base_amount=911.00, tip_pct=15, idempotency_key="d")
    check(first["status"] == second["status"] == "DECLINED" and first["payment_id"] != second["payment_id"], (first, second))
    return "после SUCCESS: 409 QR_USED; после DECLINED новая попытка разрешена, это второй платёж по QR"


def q4_blocked(run):
    for status in ("BLOCKED", "PENDING"):
        folder = data_with_merchant_status("m_001", status)
        blocked = Run(folder)
        try:
            r = blocked(qr_id="qr_001", base_amount=637.00, tip_pct=5)
            check(r["error_code"] == "MERCHANT_BLOCKED" and r["http"] == 403, r)
            check(blocked.rows() == [], "платёж создан")
        finally:
            blocked.close()
            shutil.rmtree(folder, ignore_errors=True)
    return "мерчант BLOCKED и PENDING: 403 MERCHANT_BLOCKED, платёж не создан"


def q5_receipt(run):
    r = run(qr_id="qr_001", receipt_id="r_9999", base_amount=637.00, tip_pct=5)
    check(r["error_code"] == "RECEIPT_MISMATCH", r)
    return "чужой receipt_id: 422 RECEIPT_MISMATCH"


def q6_tip(run):
    over = run(qr_id="qr_002", base_amount=774.00, tip_pct=51)
    check(over["error_code"] == "TIP_OUT_OF_RANGE", over)
    custom = run(qr_id="qr_002", base_amount=774.00, tip_amount="387.01", tip_pct=0)
    check(custom["error_code"] == "TIP_OUT_OF_RANGE", custom)
    negative = run(qr_id="qr_002", base_amount=774.00, tip_pct=-1)
    check(negative["error_code"] == "TIP_OUT_OF_RANGE", negative)
    edge = run(qr_id="qr_002", base_amount=774.00, tip_pct=50)
    check(edge["status"] == "SUCCESS" and edge["tip_amount"] == 387.00, edge)
    return "51%, -1% и своя сумма 387,01 ₽ при чеке 774 ₽: 422 TIP_OUT_OF_RANGE; 50%: SUCCESS, чаевые 387 ₽"


def p1_amount(run):
    for base in (0, -1, 1000000.01):
        r = run(qr_id="qr_004", base_amount=base, tip_pct=5)
        check(r["error_code"] == "AMOUNT_OUT_OF_RANGE", r)
    edge = run(qr_id="qr_004", base_amount=1000000, tip_pct=50)
    check(edge["status"] == "SUCCESS" and edge["amount_total"] == 1500000.0, edge)
    return "0, -1 и 1 000 000,01: 422 AMOUNT_OUT_OF_RANGE; 1 000 000 и 50%: SUCCESS, итог 1 500 000"


def p3_total(run):
    """P-3 недостижим при P-1 и Q-6, поэтому проверяется в коде с поднятым лимитом чека."""
    module = load_prototype(run)
    module.MAX_BASE = Decimal("3000000")
    http, body = module.handle({"action": "create", "qr_id": "qr_004", "base_amount": 2000000, "tip_pct": 1})
    check(body["error_code"] == "AMOUNT_OUT_OF_RANGE" and http == 422, body)
    return "при обычных лимитах итог не выше 1 500 000; с поднятым лимитом чека итог 2 020 000: 422 AMOUNT_OUT_OF_RANGE"


def load_prototype(run):
    os.environ["TIPS_OUT_DIR"] = run.tmp
    os.environ["TIPS_DATA_DIR"] = DATA_DIR
    spec = importlib.util.spec_from_file_location("prototype_under_test", PROTOTYPE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def token_check(run):
    created = run(action="create", qr_id="qr_002", base_amount=774.00, tip_pct=10)
    for action in ("confirm", "cancel"):
        r = run(action=action, payment_id=created["payment_id"], confirm_token="0" * 16)
        check(r["error_code"] == "BAD_CONFIRM_TOKEN" and r["http"] == 403, r)
    check(run.rows()[0]["status"] == "CREATED", run.rows())
    return "чужой токен подтверждения: 403 BAD_CONFIRM_TOKEN, статус не изменился"


def all_signatures(run):
    module = load_prototype(run)
    rows = csv_rows("qr_links.csv")
    bad = [r["qr_id"] for r in rows if not module.verify_signature(r)]
    check(not bad, bad)
    return f"подписи верны у {len(rows)} из {len(rows)} QR"


def all_amounts(run):
    rows = csv_rows("payments.csv")
    for row in rows:
        amount, tip = Decimal(row["amount"]), Decimal(row["tip"])
        matches = [p for p in (5, 10, 15) if (amount * p / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == tip]
        check(matches, row)
    rounded = run(action="create", qr_id="qr_005", base_amount=1.10, tip_pct=5)
    check(rounded["tip_amount"] == 0.06, rounded)
    return f"чаевые {len(rows)} строк payments.csv точно равны 5, 10 или 15% от чека; 5% от 1,10 ₽ округляются до 0,06 ₽"


def formula(run):
    module = load_prototype(run)
    rows = {r["qr_id"]: r for r in csv_rows("qr_links.csv")}
    codes = {k: module.formula_code(k, v["nonce"]) for k, v in rows.items()}
    check(codes["qr_001"] == 9 and codes["qr_003"] == 7, codes)
    expected = {"qr_002": "SUCCESS", "qr_019": "DECLINED", "qr_010": "PENDING"}
    amounts = {r["payment_id"]: r["amount"] for r in csv_rows("payments.csv")}
    for qr_id, status in expected.items():
        base = float(amounts["p_0" + qr_id[-3:]])
        r = run(qr_id=qr_id, base_amount=base, tip_pct=10)
        check(r["status"] == status and r["control_qr"] is False, r)
    spread = [sum(1 for c in codes.values() if c <= 7), sum(1 for c in codes.values() if c == 8), sum(1 for c in codes.values() if c == 9)]
    return f"qr_002: код {codes['qr_002']}, SUCCESS; qr_019: код 8, DECLINED; qr_010: код 9, PENDING. По формуле из 100 QR: {spread[0]} SUCCESS, {spread[1]} DECLINED, {spread[2]} TIMEOUT"


def generate(run):
    r = run(action="qr_generate", role="merchant", actor_id="m_001", merchant_id="m_001", employee_id="e_001", receipt_id="r_2001")
    check(r["http"] == 201 and r["qr_id"] == "qr_101" and re.fullmatch(r"[a-f0-9]{6}", r["nonce"]), r)
    check(r["exp"] == "2025-11-02T18:00:00Z" and r["signature"] in r["pay_url"], r)
    paid = run(qr_id=r["qr_id"], signature=r["signature"], base_amount=1000, tip_pct=10)
    check(paid["http"] in (200, 402) and paid["amount_total"] == 1100.0, paid)
    twice = run(action="qr_generate", role="merchant", actor_id="m_001", merchant_id="m_001", employee_id="e_001", receipt_id="r_2001")
    check(twice["error_code"] == "RECEIPT_EXISTS", twice)
    foreign = run(action="qr_generate", role="merchant", actor_id="m_001", merchant_id="m_001", employee_id="e_004", receipt_id="r_2002")
    check(foreign["error_code"] == "EMPLOYEE_MISMATCH", foreign)
    blocked = run(action="qr_generate", role="merchant", actor_id="m_019", merchant_id="m_019", employee_id="e_055", receipt_id="r_2003")
    check(blocked["error_code"] == "MERCHANT_BLOCKED", blocked)
    pending = run(action="qr_generate", role="merchant", actor_id="m_020", merchant_id="m_020", employee_id="e_058", receipt_id="r_2004")
    check(pending["error_code"] == "MERCHANT_BLOCKED", pending)
    alien = run(action="qr_generate", role="waiter", actor_id="e_002", merchant_id="m_001", employee_id="e_001", receipt_id="r_2005")
    check(alien["error_code"] == "FORBIDDEN", alien)
    client = run(action="qr_generate", merchant_id="m_001", employee_id="e_001", receipt_id="r_2006")
    check(client["error_code"] == "FORBIDDEN", client)
    later = "2025-11-03T00:00:00Z"  # qr_001 и qr_002 к этому времени истекли
    run(qr_id="qr_002", base_amount=774.00, tip_pct=10)
    again = run(action="qr_generate", role="merchant", actor_id="m_001", merchant_id="m_001", employee_id="e_001", receipt_id="r_1001", now=later)
    check(again["http"] == 201 and again["qr_id"] == "qr_102", again)
    paid_receipt = run(action="qr_generate", role="merchant", actor_id="m_001", merchant_id="m_001", employee_id="e_002", receipt_id="r_1002", now=later)
    check(paid_receipt["error_code"] == "RECEIPT_EXISTS", paid_receipt)
    return "новый QR действует 24 ч и принимается к оплате; второй QR на чек, чужой сотрудник, мерчант BLOCKED и PENDING, чужой официант и клиент отклонены; на истёкший неоплаченный чек QR выпускается заново, на оплаченный нет"


def reports(run):
    period = {"from": "2025-11-01", "to": "2025-11-30"}
    m = run(action="report", role="merchant", actor_id="m_001", merchant_id="m_001", **period)
    check((m["tips_total"], m["payments_count"], m["avg_tip_pct"], m["success_rate"]) == (414.85, 6, 9.0, 0.83), m)
    e = run(action="report", kind="employee", role="waiter", actor_id="e_001", employee_id="e_001", **period)
    check((e["tips_total"], e["payments_count"], e["avg_tip_amount"], e["top_day"]) == (83.6, 2, 41.8, "2025-11-03"), e)
    declined = run(action="report", kind="employee", role="admin", employee_id="e_003", **period)
    check((declined["tips_total"], declined["payments_count"]) == (136.65, 2), declined)
    d = run(action="report", kind="daily", role="admin", merchant_id="m_001", **period)
    check([(x["date"], x["tips_total"], x["payments_count"], x["avg_tip_pct"]) for x in d["daily"]]
          == [("2025-11-01", 245.9, 3, 10.0), ("2025-11-03", 168.95, 3, 7.5)], d)
    return f"m_001: {m['tips_total']} ₽, {m['payments_count']} платежей, {m['avg_tip_pct']}%, успех {m['success_rate']}; e_001: {e['tips_total']} ₽, лучший день {e['top_day']}; по дням совпало"


def rbac(run):
    period = {"from": "2025-11-01", "to": "2025-11-30"}
    cases = [
        dict(role="waiter", actor_id="e_001", kind="employee", employee_id="e_002"),
        dict(role="merchant", actor_id="m_002", kind="employee", employee_id="e_001"),
        dict(role="merchant", actor_id="m_002", merchant_id="m_001"),
        dict(role="waiter", actor_id="e_001", merchant_id="m_001"),
        dict(merchant_id="m_001"),
    ]
    for case in cases:
        r = run(action="report", **period, **case)
        check(r["error_code"] == "FORBIDDEN" and r["http"] == 403, (case, r))
    ok = run(action="report", role="merchant", actor_id="m_001", kind="employee", employee_id="e_001", **period)
    check(ok["http"] == 200, ok)
    return "чужой официант, чужой мерчант и клиент получают 403; мерчант видит своего официанта"


def audit_fields(run):
    run(qr_id="qr_002", base_amount=774.00, tip_pct=10)
    events = run.rows("audit_out.csv")
    check(list(events[0]) == ["event_id", "payment_id", "qr_id", "action", "from_status", "to_status", "amount_total", "actor", "at"], list(events[0]))
    path = [(e["from_status"], e["to_status"]) for e in events]
    check(path == [("", "CREATED"), ("CREATED", "PENDING"), ("PENDING", "SUCCESS")], path)
    text = open(os.path.join(run.tmp, "audit_out.csv"), encoding="utf-8").read() + open(os.path.join(run.tmp, "payments_out.csv"), encoding="utf-8").read()
    check("****" not in text and "payment_details" not in text, "реквизиты в выходных файлах")
    names = [e["name"] for e in csv_rows("employees.csv")]
    check(not any(name in text for name in names), "имена в выходных файлах")
    return "9 полей, каждый переход записан; реквизитов и имён сотрудников в платежах и журнале нет"


def masks(run):
    rows = csv_rows("employees.csv")
    check(all(re.fullmatch(r"\*{4}\d{4}", r["payment_details"]) for r in rows), "есть реквизит без маски")
    info = run(action="qr_info", qr_id="qr_001")
    check("payment_details" not in info and info["employee_name"] == "Иванов И." and info["base_amount"] == 637.0, info)
    return f"у всех {len(rows)} сотрудников только маска; форма клиента реквизитов не получает"


def speed(run):
    """NFR-1: проверка подписи за 50 мс."""
    module = load_prototype(run)
    qr = csv_rows("qr_links.csv")[0]
    times = []
    for _ in range(1000):
        start = time.perf_counter()
        module.verify_signature(qr)
        times.append((time.perf_counter() - start) * 1000)
    p95 = statistics.quantiles(times, n=20)[-1]
    check(p95 <= 50, p95)
    return f"95-й перцентиль {p95:.3f} мс при цели 50 мс, 1000 проверок на одной машине"


T3 = [
    ("T3-1", "Успех", "qr_001, base=637.00, tip_pct=5", "SUCCESS, amount_total=668.85, tip=31.85", t3_1),
    ("T3-2", "Отказ шлюза", "qr_003, base=911.00, tip_pct=15", "DECLINED, CARD_DECLINED", t3_2),
    ("T3-3", "Неверный QR", "QR с испорченной подписью; подмена поля; истёкший QR", "INVALID_QR (422) или QR_EXPIRED (410), платёж не создан", t3_3),
    ("T3-4", "Повтор", "тот же idempotency_key дважды", "тот же payment_id, одна строка в файле платежей", t3_4),
    ("T3-5", "Отмена", "создать платёж, отменить до подтверждения; отменить из PENDING", "CANCELED; отмена из PENDING: 409", t3_5),
    ("T3-6", "Таймаут", "qr_010, код эмулятора 9, затем повторный опрос", "PENDING, GATEWAY_TIMEOUT, retryable; один платёж", t3_6),
]
EXTRA = [
    ("Q-3", "Одноразовый nonce", q3_nonce),
    ("Q-4", "Заблокированный мерчант", q4_blocked),
    ("Q-5", "Чужой чек", q5_receipt),
    ("Q-6", "Предел чаевых", q6_tip),
    ("P-1", "Предел чека", p1_amount),
    ("P-3", "Предел итога", p3_total),
    ("Токен", "Подтверждение чужого платежа", token_check),
    ("Подпись", "Все QR из данных", all_signatures),
    ("Расчёт", "Все суммы из данных", all_amounts),
    ("Формула", "Эмулятор на обычных QR", formula),
    ("FR-1", "Генерация QR", generate),
    ("Отчёты", "Три разреза", reports),
    ("RBAC", "Права на отчёты", rbac),
    ("Аудит", "Поля и переходы", audit_fields),
    ("Маска", "Реквизиты сотрудников", masks),
    ("NFR-1", "Скорость подписи", speed),
]


def run_test(fn):
    run = Run()
    try:
        return True, fn(run)
    except AssertionError as e:
        return False, str(e)
    finally:
        run.close()


def data_md5():
    result = {}
    for name in sorted(os.listdir(DATA_DIR)):
        with open(os.path.join(DATA_DIR, name), "rb") as f:
            result[name] = hashlib.md5(f.read()).hexdigest()
    return result


def main():
    before = data_md5()
    results_t3 = []
    for test_id, name, given, expected, fn in T3:
        ok, fact = run_test(fn)
        results_t3.append((test_id, name, given, expected, fact, ok))
        print(f"[{'ОК' if ok else 'СБОЙ'}] {test_id}. {name}: {fact}")
    results_extra = []
    for test_id, name, fn in EXTRA:
        ok, fact = run_test(fn)
        results_extra.append((test_id, name, fact, ok))
        print(f"[{'ОК' if ok else 'СБОЙ'}] {test_id}. {name}: {fact}")
    after = data_md5()
    if before != after:
        results_extra.append(("Данные", "Исходные CSV", "файлы изменились", False))
    else:
        results_extra.append(("Данные", "Исходные CSV", f"md5 всех {len(after)} файлов до и после тестов совпал", True))
    print(f"[{'ОК' if before == after else 'СБОЙ'}] Данные. {results_extra[-1][2]}")

    total = len(results_t3) + len(results_extra)
    passed = sum(r[-1] for r in results_t3) + sum(r[-1] for r in results_extra)
    print(f"Итог: пройдено {passed} из {total}")

    if not os.environ.get("TIPS_NO_REPORT"):
        lines = [
            "# Результаты тестов прототипа",
            "",
            f"Запуск от {date.today().isoformat()}, Python {platform.python_version()}, {platform.system()}. Команда: `python3 tests_t3.py`.",
            f"Пройдено {passed} из {total}.",
            "",
            "## Сценарии T3-1…T3-6",
            "",
            "| Тест | Вход | Ожидание | Факт | Пройден |",
            "|---|---|---|---|---|",
        ]
        for test_id, name, given, expected, fact, ok in results_t3:
            lines.append(f"| {test_id}. {name} | {given} | {expected} | {fact} | {'да' if ok else 'нет'} |")
        lines += ["", "## Проверки правил и данных", "", "| Проверка | Что проверяли | Факт | Пройден |", "|---|---|---|---|"]
        for test_id, name, fact, ok in results_extra:
            lines.append(f"| {test_id} | {name} | {fact} | {'да' if ok else 'нет'} |")
        lines += ["", "## md5 исходных файлов", ""]
        lines += [f"- `{name}`: `{value}`" for name, value in after.items()]
        with open(os.path.join(HERE, "test_results.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
