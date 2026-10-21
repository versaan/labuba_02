# streamstats

Высокопроизводительная CLI-утилита для потокового анализа структурированных логов (JSONL, CSV) с расчетом метрик в режиме одного прохода и минимальным потреблением памяти.

Вместо описания стандартных требований из ТЗ ниже разобраны нетривиальные инженерные решения, эволюция архитектуры и грабли, которые были сознательно обойдены в процессе реализации.

---

## Ключевые архитектурные решения

### 1. Эволюция модуля парсеров: почему шаблонный метод (Template Method)?

В первых набросках парсинг строился на изолированных процедурных функциях `parse_jsonl()` и `parse_csv()`. Однако такой подход быстро показал свои минусы:

* Дублирование логики: в каждой функции приходилось копировать обработку флага `--skip-invalid`, инкремент счётчиков и форматирование логов.
* Раздувание контекста: обогащение ошибок строкой и путём к файлу приходилось переписывать заново под каждый формат.

В итоге модуль был перепроектирован на паттерн **Template Method (`BaseParser`)**:

* **Базовый класс `BaseParser**` берёт на себя всю оркестрацию: открытие дескриптора в UTF-8, безопасную итерацию, перехват исключений модели, обогащение их контекстом (`line_number`, `file_path`), управление счётчиком `skipped_count` и логирование `WARNING` в режиме `--skip-invalid`.
* **Наследники (`JSONLParser`, `CSVParser`)** реализуют ровно два изолированных низкоуровневых шага:
1. `_iter_raw_items(file)` — как физически достать сырую порцию данных (строку или кортеж).
2. `_parse_item(item)` — как десериализовать сырой фрагмент в `dict[str, Any]`.



Благодаря этому добавление любого нового формата (например, TSV, Syslog или бинарного протокола) занимает 15 строк кода без изменения пайплайна валидации.

### 2. Подводные камни CSV: разделители, пустые строки и нумерация

Обработка CSV часто ломается на граничных случаях:

* **Динамический разделитель (`,` vs `;`) и пустые строки в заголовке:** метод `_preparer` предварительно просматривает файл, определяет разделитель и считает смещение, если файл начинается с пустых строк.
* **Ловушка «пустая строка vs пустая запись»:** если в CSV встречается строка `,,,`, стандартный `DictReader` отдаёт словарь с пустыми строками `""`. Простая проверка `if not any(row.values())` ошибочно посчитала бы такую строку пустой и пропустила её. В парсере разделены физически пустые строки файла (`all(v is None for v in row.values())`, которые просто игнорируются) и строки с пустыми значениями полей (которые являются невалидными записями и корректно триггерят `InvalidEventError` либо уходят в `skipped_count`).
* **Точная адресация ошибок:** номер строки высчитывается как `reader.line_num + counter_of_empty_lines`, что даёт 100% совпадение с реальной физической строкой в файле даже при наличии пустых строк в заголовке.
* **Лишние колонки:** проверка `if None in item` мгновенно отлавливает строки, где разделителей оказалось больше, чем заголовков.

### 3. Чистота доменной модели `Event`

Класс `Event` спроектирован полностью изолированным от инфраструктурного слоя:

* Он ничего не знает о файлах, строках или формате источника. Его задача — строгая защита доменных инвариантов: соответствие стандарту ISO 8601, допустимый список уровней логирования (`VALID_LEVELS`), непустой источник и строковые типы данных.
* В методе `__eq__` при сравнении с объектом чужого типа возвращается `NotImplemented` вместо `False` — идиоматичный подход в Python, позволяющий вызывающей стороне передать право сравнения обратному оператору.
* Обогащение исключений контекстом места сбоя происходит исключительно на уровне парсера через цепочку `raise ... from error`.

### 4. Генерация отчётов и плоский CSV (Bonus challenge)

Модуль `report.py` поддерживает сохранение агрегированных метрик как в JSON, так и в CSV без дублирования вычислений:

* Перед записью родительские директории создаются автоматически (`path.parent.mkdir(parents=True, exist_ok=True)`), что исключает падения, если путь вывода указывает во вложенную несуществующую папку.
* Для формата CSV реализовано автоматическое уплощение (flattening) вложенных структур через точечную нотацию (`events_by_level.INFO`, `top_error_sources.auth_service`), благодаря чему древовидная статистика ложится в плоский двухколоночный формат `(metric, value)`.

### 5. Архитектура CLI и синхронизация кодов выхода

В стандартном модуле `argparse` ошибки синтаксиса аргументов сразу вызывают `sys.exit(2)` с неконтролируемым выводом.

* В проекте создан `StreamStatsArgumentParser`, переопределяющий метод `.error()`, который выбрасывает кастомное исключение `CLIConfigError`.
* Весь пайплайн выполнения в `__main__.py` обёрнут в единый блок перехвата базового класса `StreamStatsError`.
* Это гарантирует, что любая ошибка — от некорректных флагов консоли и отсутствующих файлов до битых данных внутри логов — централизованно выводится в `sys.stderr`, возвращая единый код завершения `2` согласно спецификации.

---

## Запуск и использование

### Анализ логов

```bash
# Базовый запуск с автоматическим определением формата по расширению
poetry run python -m streamstats analyze logs/app.jsonl logs/server.csv --output reports/summary.json

# Запуск с принудительным форматом и пропуском некорректных записей
poetry run python -m streamstats analyze input_data --format jsonl --skip-invalid --output reports/summary.json

# Формирование отчёта в формате CSV
poetry run python -m streamstats analyze logs/app.csv --output reports/summary.csv

```

---

## Качество кода и тестирование

Проект протестирован с помощью `pytest` (36 тестов, покрывающих граничные случаи, Unicode, разные типы разделителей, пустые файлы, режимы fail-fast / skip-invalid и интеграцию с CLI).

Запуск проверок качества:

```bash
# Тесты
poetry run pytest -v

# Статический анализ и линтинг
poetry run ruff check .

# Проверка форматирования
poetry run black --check .

# Строгая статическая типизация
poetry run mypy src tests

```
## Архитектура системы

```mermaid
flowchart TB
    %% ============ СТИЛИ ============
    classDef cli      fill:#E3F2FD,stroke:#1565C0,stroke-width:2px,color:#0D47A1,font-weight:bold
    classDef ing      fill:#E8F5E9,stroke:#2E7D32,stroke-width:2px,color:#1B5E20,font-weight:bold
    classDef dom      fill:#F3E5F5,stroke:#6A1B9A,stroke-width:2px,color:#4A148C,font-weight:bold
    classDef ana      fill:#FFF3E0,stroke:#E65100,stroke-width:2px,color:#BF360C,font-weight:bold
    classDef rep      fill:#E0F2F1,stroke:#00695C,stroke-width:2px,color:#004D40,font-weight:bold
    classDef err      fill:#FFEBEE,stroke:#C62828,stroke-width:2px,color:#B71C1C,font-weight:bold
    classDef data     fill:#FAFAFA,stroke:#37474F,stroke-width:1.5px,color:#263238
    classDef decision fill:#FFFDE7,stroke:#F9A825,stroke-width:2px,color:#F57F17,font-weight:bold
    classDef file     fill:#ECEFF1,stroke:#546E7A,stroke-width:1.5px,color:#263238

    %% ============ CLI LAYER ============
    subgraph CLI["🟦  CLI Layer — __main__.py"]
        direction TB
        ARGS["StreamStatsArgumentParser<br/>разбор аргументов"]:::cli
        ORCH["Оркестрация пайплайна<br/>INPUT…, --format, --skip-invalid"]:::cli
        EXIT["sys.exit(code=2)<br/>сообщение в stderr"]:::err
        ARGS --> ORCH
        ORCH -.->|CLIConfigError| EXIT
    end

    %% ============ INGESTION LAYER ============
    subgraph ING["🟩  Ingestion Layer — parsers.py"]
        direction TB
        FACTORY["get_parser(path, format)"]:::ing
        FMT{"Формат?"}:::decision
        JSONL["JSONLParser.parse()"]:::ing
        CSV["CSVParser.parse()"]:::ing
        BASE["BaseParser · Template Method<br/>UTF-8, skipped_count,<br/>обогащение ошибок line_number + file_path"]:::ing
        CHECK{"Ошибка<br/>парсинга?"}:::decision
        SKIP["WARNING · skipped_count++"]:::err
        FAIL["fail-fast<br/>InvalidEventError"]:::err

        FACTORY --> FMT
        FMT -->|".jsonl"| JSONL
        FMT -->|".csv"| CSV
        BASE -.->|"управляет"| JSONL
        BASE -.->|"управляет"| CSV
        JSONL --> CHECK
        CSV --> CHECK
        CHECK -->|"--skip-invalid"| SKIP
        CHECK -->|"строгий режим"| FAIL
    end

    %% ============ DOMAIN LAYER ============
    subgraph DOM["🟪  Domain Layer — models.py · constants.py · errors.py"]
        direction TB
        EVENT["Event (immutable)<br/>timestamp · level · source · message<br/>ISO 8601 · VALID_LEVELS · __eq__ → NotImplemented"]:::dom
        ERRORS["StreamStatsError<br/>├── CLIConfigError<br/>├── UnsupportedFormatError<br/>└── InvalidEventError → InvalidTimestampError"]:::dom
    end

    %% ============ ANALYTICS LAYER ============
    subgraph ANA["🟧  Analytics Layer — analysis.py"]
        direction TB
        PROCESS["LogAnal.process(event)<br/>Counter обновляется на лету · O(1)"]:::ana
        STATS["LogAnal.get_stats()<br/>dict[str, Any]"]:::ana
        PROCESS --> STATS
    end

    %% ============ REPORTING LAYER ============
    subgraph REP["🟩  Reporting Layer — report.py"]
        direction TB
        WRITE["write_report(dict, path, format)<br/>создание директорий parents=True"]:::rep
        OUTJSON["report.json<br/>indent=2"]:::file
        OUTCSV["report.csv<br/>flattening: events_by_level.INFO → (metric, value)"]:::file
        WRITE --> OUTJSON
        WRITE --> OUTCSV
    end

    %% ============ ПОТОК ДАННЫХ ============
    ORCH  ==>|"1. INPUT[]"| FACTORY
    JSONL ==>|"2. yield Event"| EVENT
    CSV   ==>|"2. yield Event"| EVENT
    EVENT ==>|"3. event"| PROCESS
    STATS ==>|"4. dict"| WRITE
    WRITE ==>|"5. запись на диск"| OUTJSON
    WRITE ==>|"5. запись на диск"| OUTCSV

    %% ============ ОБРАБОТКА ОШИБОК ============
    FAIL -.->|"raise"| ERRORS
    ORCH -.->|"raise"| ERRORS
    ERRORS -.->|"перехват StreamStatsError"| EXIT
    FAIL -.-> EXIT

    %% ============ НЕВИДИМЫЕ РЁБРА ДЛЯ КОМПОНОВКИ ============
    CLI ~~~ ING
    ING ~~~ DOM
    DOM ~~~ ANA
    ANA ~~~ REP
```
