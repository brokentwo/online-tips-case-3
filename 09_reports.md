# Отчётность — кейс 3

Все числа посчитаны прототипом по `ДАННЫЕ/payments.csv` за ноябрь 2025 и проверены тестом «Отчёты».

Деньги считаются только по статусу `SUCCESS`: при отказе, отмене и ожидании чаевых никто не получил. В образце `tips_total = sum(tip)` без учёта статуса. Для m_001 это дало бы 611,20 ₽ вместо полученных 414,85 ₽. Числа образца (550,00 и 4 платежа) показывают только формат и с данными не сходятся.

## 1. Отчёт по мерчанту

**Endpoint:** `GET /api/v1/reports/tips?merchant_id=m_001&from=2025-11-01&to=2025-11-30`

**Кто видит:** мерчант своё заведение, администратор все.

| Метрика | Формула | m_001 |
|---|---|---|
| tips_total | sum(tip) по SUCCESS | 414.85 |
| payments_count | count(payments), все попытки | 6 |
| avg_tip_pct | avg(tip / amount × 100) по SUCCESS | 9.0 |
| success_rate | count(SUCCESS) / count(*) | 0.83 |

```json
{
  "merchant_id": "m_001",
  "period": "2025-11",
  "tips_total": 414.85,
  "payments_count": 6,
  "avg_tip_pct": 9.0,
  "success_rate": 0.83
}
```

## 2. Отчёт по официанту

**Endpoint:** `GET /api/v1/reports/tips?employee_id=e_001&from=2025-11-01&to=2025-11-30`

**Кто видит:** сам официант, его мерчант, администратор. Коллеги не видят: `403 FORBIDDEN`.

| Метрика | Формула | e_001 |
|---|---|---|
| tips_total | sum(tip) по SUCCESS | 83.60 |
| payments_count | count(payments), все попытки | 2 |
| avg_tip_amount | avg(tip) по SUCCESS | 41.80 |
| top_day | день с наибольшей суммой чаевых | 2025-11-03 |

```json
{
  "employee_id": "e_001",
  "period": "2025-11",
  "tips_total": 83.60,
  "payments_count": 2,
  "avg_tip_amount": 41.80,
  "top_day": "2025-11-03"
}
```

## 3. Отчёт по дням

**Endpoint:** `GET /api/v1/reports/tips/daily?merchant_id=m_001&from=2025-11-01&to=2025-11-30`

| Метрика | Формула | 2025-11-01 | 2025-11-03 |
|---|---|---|---|
| tips_total | sum(tip) по SUCCESS за день | 245.90 | 168.95 |
| payments_count | count за день, все попытки | 3 | 3 |
| avg_tip_pct | avg(tip / amount × 100) по SUCCESS за день | 10.0 | 7.5 |

```json
{
  "merchant_id": "m_001",
  "daily": [
    {"date": "2025-11-01", "tips_total": 245.90, "payments_count": 3, "avg_tip_pct": 10.0},
    {"date": "2025-11-03", "tips_total": 168.95, "payments_count": 3, "avg_tip_pct": 7.5}
  ]
}
```

Откуда берётся 2025-11-03: платежи p_0055 и p_0056 прошли (51,75 и 117,20 ₽), а p_0057 отклонён и в деньги не входит.

## 4. Критерий приёмки

- [x] Три разреза: мерчант, официант, по дням
- [x] Метрики с формулами
- [x] Примеры ответов в JSON
- [x] Данные сходятся с `payments.csv`
- [x] Указаны endpoint'ы
