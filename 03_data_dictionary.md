# Data dictionary — кейс 3

Четыре файла, 22 колонки: merchants (4 колонки, 20 строк), employees (4, 60), payments (7, 100), qr_links (7, 100).

## merchants (образец)

| Файл | Поле | Тип | Обяз. | Ограничение | Пример | Код ошибки |
|---|---|---|---|---|---|---|
| merchants | merchant_id | string | да | m_NNN | m_001 | — |
| merchants | name | string | да | 1–100 символов | Вкус-Сервис Тверская | — |
| merchants | status | enum | да | ACTIVE/BLOCKED/PENDING | ACTIVE | MERCHANT_BLOCKED |
| merchants | description | string | нет | 0–200 | Ресторан сети | — |

## payments (образец и три поля, которых в нём не было)

| Файл | Поле | Тип | Обяз. | Ограничение | Пример | Код ошибки |
|---|---|---|---|---|---|---|
| payments | payment_id | string | да | p_NNNN | p_0001 | — |
| payments | merchant_id | string | да | m_NNN, есть в merchants | m_001 | MERCHANT_BLOCKED |
| payments | employee_id | string | да | e_NNN, есть в employees | e_001 | EMPLOYEE_MISMATCH |
| payments | amount | decimal | да | > 0, ≤ 1 000 000 | 637.00 | AMOUNT_OUT_OF_RANGE |
| payments | tip | decimal | да | ≥ 0, ≤ amount × 0.5 | 31.85 | TIP_OUT_OF_RANGE |
| payments | status | enum | да | CREATED/PENDING/SUCCESS/DECLINED/CANCELED | SUCCESS | — |
| payments | timestamp | datetime | да | ISO 8601, UTC | 2025-11-01T18:00:00Z | — |

В образце `tip` указан как 63.70, в таблице пример взят из строки p_0001.

## employees

| Поле | Тип | Обяз. | Ограничение | Пример | Код ошибки |
|---|---|---|---|---|---|
| employee_id | string | да | e_NNN, уникален | e_001 | — |
| merchant_id | string | да | m_NNN, есть в merchants | m_001 | EMPLOYEE_MISMATCH |
| name | string | да | 1–100 символов | Иванов И. | — |
| payment_details | string | да | только маска `****NNNN` | ****1001 | BAD_REQUEST |

`payment_details` — реквизиты для выплат официанту. Клиент ими не платит и их не видит.

## qr_links

| Поле | Тип | Обяз. | Ограничение | Пример | Код ошибки |
|---|---|---|---|---|---|
| qr_id | string | да | qr_NNN, уникален | qr_001 | QR_NOT_FOUND |
| merchant_id | string | да | m_NNN, входит в подпись | m_001 | INVALID_QR, MERCHANT_BLOCKED |
| employee_id | string | да | e_NNN, сотрудник этого мерчанта | e_001 | INVALID_QR, EMPLOYEE_MISMATCH |
| receipt_id | string | да | r_NNNN, уникален для мерчанта | r_1001 | RECEIPT_MISMATCH, RECEIPT_EXISTS |
| nonce | string | да | 6 hex, одноразовый | c82561 | QR_USED |
| exp | datetime | да | ISO 8601, UTC, новый QR живёт 24 ч | 2025-11-01T23:59:00Z | QR_EXPIRED |
| signature | string | да | 16 hex, HMAC-SHA256 | 68d0f361ac38c12b | INVALID_QR |

## Что показала проверка самих данных

- Мерчанты: 18 `ACTIVE`, `m_019` `BLOCKED`, `m_020` `PENDING`. По этим двум нет ни QR, ни платежей.
- Сотрудники: по 3 у каждого мерчанта, у всех 60 только маска.
- QR: подпись верна у 100 из 100, `nonce` и `receipt_id` не повторяются, каждый сотрудник относится к своему мерчанту.
- Платежи: `SUCCESS` 70, `DECLINED` 10, `PENDING` 10, `CANCELED` 10. Чеки от 549 до 3 987 ₽, чаевые точно 5, 10 или 15%.
- Все `exp` приходятся на 1–4 ноября 2025 года, поэтому прототип работает на демо-часах (`2025-11-01T18:00:00Z`). По настоящим часам все QR были бы просрочены.
- Строки `qr_N` и `p_00NN` совпадают по мерчанту и сотруднику, поэтому `payments.csv` использован как источник суммы чека: отдельной кассы в данных нет.

## Критерий приёмки

- [x] Все 4 файла описаны (22 колонки)
- [x] Для каждого поля указан тип и ограничение
- [x] Для полей с валидацией — код ошибки из 08_errors.md
- [x] Пример взят из реального CSV
- [x] payment_details — только маска (`****NNNN`)
