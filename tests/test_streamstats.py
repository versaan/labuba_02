import csv
import json
import logging

from pathlib import Path

import pytest

from streamstats.__main__ import main
from streamstats.analysis import LogAnal
from streamstats.errors import CLIConfigError
from streamstats.errors import InvalidEventError
from streamstats.errors import InvalidTimestampError
from streamstats.errors import StreamStatsError
from streamstats.errors import UnsupportedFormatError
from streamstats.models import Event
from streamstats.parsers import get_parser
from streamstats.report import write_report

# =====================================================================
# 1. ТЕСТЫ МОДЕЛИ EVENT И ИЕРАРХИИ ОШИБОК (models.py, errors.py)
# =====================================================================


def test_error_hierarchy() -> None:
    """Все кастомные исключения должны наследоваться от StreamStatsError."""
    assert issubclass(UnsupportedFormatError, StreamStatsError)
    assert issubclass(InvalidEventError, StreamStatsError)
    assert issubclass(InvalidTimestampError, InvalidEventError)
    assert issubclass(CLIConfigError, StreamStatsError)


def test_event_valid_creation_and_methods() -> None:
    """Создание валидного события, проверка __eq__ и __repr__."""
    ev1 = Event("2026-10-11T08:15:30Z", "INFO", "auth", "User logged in")
    ev2 = Event("2026-10-11T08:15:30Z", "INFO", "auth", "User logged in")
    ev3 = Event("2026-10-11T08:15:30Z", "ERROR", "auth", "User logged in")

    assert ev1 == ev2
    assert ev1 != ev3
    assert ev1 != "not_an_event"
    assert "Event(" in repr(ev1)
    assert ev1.source == "auth"
    assert ev1.level == "INFO"


@pytest.mark.parametrize("bad_ts", ["not-a-date", "2026/13/45", "", None, 12345])
def test_event_invalid_timestamp(bad_ts: object) -> None:
    """Некорректная временная метка вызывает InvalidTimestampError."""
    with pytest.raises(InvalidTimestampError):
        Event(bad_ts, "INFO", "auth", "msg")  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_level", ["FATAL", "info", "WARN", "", 123])
def test_event_invalid_level(bad_level: object) -> None:
    """Недопустимый уровень логирования вызывает InvalidEventError."""
    with pytest.raises(InvalidEventError):
        Event("2026-10-11T08:15:30Z", bad_level, "auth", "msg")  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_source", ["", "   ", "\t\n", None, 42])
def test_event_invalid_source(bad_source: object) -> None:
    """Пустой или нестроковый source вызывает InvalidEventError."""
    with pytest.raises(InvalidEventError):
        Event("2026-10-11T08:15:30Z", "INFO", bad_source, "msg")  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_message", [None, 123, ["list"]])
def test_event_invalid_message(bad_message: object) -> None:
    """Нестроковое поле message вызывает InvalidEventError."""
    with pytest.raises(InvalidEventError):
        Event("2026-10-11T08:15:30Z", "INFO", "auth", bad_message)  # type: ignore[arg-type]


# =====================================================================
# 2. ТЕСТЫ ПАРСЕРОВ (parsers.py)
# =====================================================================


def test_jsonl_parser_valid_and_unicode(tmp_path: Path) -> None:
    """Чтение корректного JSONL с пустыми строками и Unicode-символами."""
    file_path = tmp_path / "logs.jsonl"
    lines = [
        "",
        json.dumps(
            {
                "timestamp": "2026-10-11T10:00:00Z",
                "level": "INFO",
                "source": "сервис_авторизации",
                "message": "Пользователь вошёл в систему 🚀",
            },
            ensure_ascii=False,
        ),
        "   ",
        json.dumps(
            {
                "timestamp": "2026-10-11T10:05:00Z",
                "level": "ERROR",
                "source": "db",
                "message": "Ошибка соединения",
            },
            ensure_ascii=False,
        ),
    ]
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    parser = get_parser(file_path)
    events = list(parser.parse())

    assert len(events) == 2
    assert events[0].source == "сервис_авторизации"
    assert events[0].message == "Пользователь вошёл в систему 🚀"
    assert events[1].level == "ERROR"
    assert parser.skipped_count == 0


@pytest.mark.parametrize("delimiter", [",", ";"])
def test_csv_parser_valid_and_delimiters(tmp_path: Path, delimiter: str) -> None:
    """Чтение CSV с разделителями ',' и ';', включая пустые строки в начале файла."""
    file_path = tmp_path / "logs.csv"
    content = (
        "\n\n"
        f"timestamp{delimiter}level{delimiter}source{delimiter}message\n"
        f"2026-10-11T08:00:00Z{delimiter}DEBUG{delimiter}cache{delimiter}Cache hit\n"
        "\n"
        f"2026-10-11T08:01:00Z{delimiter}CRITICAL{delimiter}core{delimiter}Критическая ошибка ядра\n"
    )
    file_path.write_text(content, encoding="utf-8")

    parser = get_parser(file_path)
    events = list(parser.parse())

    assert len(events) == 2
    assert events[0].level == "DEBUG"
    assert events[1].message == "Критическая ошибка ядра"


@pytest.mark.parametrize("ext", [".jsonl", ".csv"])
def test_parsers_empty_files(tmp_path: Path, ext: str) -> None:
    """Пустой файл или файл из пробелов не должен вызывать ошибок и возвращает 0 событий."""
    empty_file = tmp_path / f"empty{ext}"
    empty_file.write_text("   \n\n  ", encoding="utf-8")

    parser = get_parser(empty_file)
    assert list(parser.parse()) == []


def test_csv_header_only(tmp_path: Path) -> None:
    """CSV только с заголовком возвращает пустой список событий."""
    file_path = tmp_path / "header_only.csv"
    file_path.write_text("timestamp,level,source,message\n", encoding="utf-8")

    parser = get_parser(file_path)
    assert list(parser.parse()) == []


def test_jsonl_fail_fast_with_line_number(tmp_path: Path) -> None:
    """В строгом режиме JSONL-парсер падает на битой строке и сохраняет файл и номер строки."""
    file_path = tmp_path / "bad.jsonl"
    content = (
        '{"timestamp": "2026-10-11T08:00:00Z", "level": "INFO", "source": "app", "message": "ok"}\n'
        '{"timestamp": "not-a-timestamp", "level": "INFO", "source": "app", "message": "fail"}\n'
    )
    file_path.write_text(content, encoding="utf-8")

    parser = get_parser(file_path, skip_invalid=False)
    with pytest.raises(InvalidTimestampError) as exc_info:
        list(parser.parse())

    assert exc_info.value.line_number == 2
    assert exc_info.value.file_path == str(file_path)


def test_csv_fail_fast_line_number_with_leading_blanks(tmp_path: Path) -> None:
    """Проверка точного вычисления номера строки в CSV при наличии пустых строк в начале."""
    file_path = tmp_path / "bad.csv"
    content = (
        "\n"
        "\n"
        "timestamp,level,source,message\n"
        "2026-10-11T08:00:00Z,INFO,auth,ok\n"
        "2026-10-11T08:01:00Z,INVALID_LVL,auth,fail\n"
    )
    file_path.write_text(content, encoding="utf-8")

    parser = get_parser(file_path, skip_invalid=False)
    with pytest.raises(InvalidEventError) as exc_info:
        list(parser.parse())

    assert exc_info.value.line_number == 5
    assert exc_info.value.file_path == str(file_path)


def test_csv_extra_columns_error(tmp_path: Path) -> None:
    """Лишние колонки в строке CSV должны вызывать InvalidEventError."""
    file_path = tmp_path / "extra.csv"
    content = "timestamp,level,source,message\n" "2026-10-11T08:00:00Z,INFO,auth,msg,EXTRA_COL\n"
    file_path.write_text(content, encoding="utf-8")

    parser = get_parser(file_path)
    with pytest.raises(InvalidEventError, match="extra fields"):
        list(parser.parse())


def test_skip_invalid_mode_and_logging(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """В режиме --skip-invalid битые записи пропускаются с WARNING, а валидные читаются."""
    file_path = tmp_path / "mixed.jsonl"
    lines = [
        "{broken json",
        '["not", "a", "dict"]',
        '{"timestamp": "2026-10-11T08:00:00Z", "level": "INFO"}',
        '{"timestamp": "bad-ts", "level": "INFO", "source": "s", "message": "m"}',
        '{"timestamp": "2026-10-11T08:00:00Z", "level": "INFO", "source": "s", "message": "valid 1"}',
        '{"timestamp": "2026-10-11T08:01:00Z", "level": "BAD", "source": "s", "message": "m"}',
        '{"timestamp": "2026-10-11T08:02:00Z", "level": "ERROR", "source": "s", "message": "valid 2"}',
    ]
    file_path.write_text("\n".join(lines), encoding="utf-8")

    parser = get_parser(file_path, skip_invalid=True)
    with caplog.at_level(logging.WARNING):
        events = list(parser.parse())

    assert len(events) == 2
    assert parser.skipped_count == 5
    assert len(caplog.records) == 5


def test_get_parser_format_override_and_unsupported(tmp_path: Path) -> None:
    """Явный аргумент fmt переопределяет расширение файла; неизвестный формат вызывает ошибку."""
    custom_file = tmp_path / "data.custom_log"
    custom_file.write_text(
        '{"timestamp": "2026-10-11T08:00:00Z", "level": "INFO", "source": "s", "message": "m"}\n',
        encoding="utf-8",
    )

    parser = get_parser(custom_file, fmt="jsonl")
    assert len(list(parser.parse())) == 1

    with pytest.raises(UnsupportedFormatError):
        get_parser(tmp_path / "file.xml")


# =====================================================================
# 3. ТЕСТЫ АНАЛИТИКИ (analysis.py)
# =====================================================================


def test_analysis_empty() -> None:
    """Статистика на пустом потоке должна возвращать нули и None для дат."""
    analyzer = LogAnal()
    stats = analyzer.get_stats()

    assert stats["total_events"] == 0
    assert stats["events_by_level"] == {}
    assert stats["events_by_source"] == {}
    assert stats["first_event"] is None
    assert stats["last_event"] is None
    assert stats["top_error_sources"] == {}


def test_analysis_metrics_and_top_5_errors() -> None:
    """Проверка подсчёта метрик, диапазона дат не по порядку и отсечения топ-5 источников ошибок."""
    analyzer = LogAnal()

    # События не в хронологическом порядке
    analyzer.process(Event("2026-10-11T12:00:00Z", "INFO", "web", "ok"))
    analyzer.process(Event("2026-10-11T08:00:00Z", "DEBUG", "web", "early"))
    analyzer.process(Event("2026-10-11T19:30:00Z", "WARNING", "cache", "late"))

    # Генерируем ошибки из 6 разных источников с разной частотой (учитываются только ERROR и CRITICAL)
    error_counts = {
        "src_1": 6,
        "src_2": 5,
        "src_3": 4,
        "src_4": 3,
        "src_5": 2,
        "src_6": 1,
    }
    for src, count in error_counts.items():
        for i in range(count):
            lvl = "ERROR" if i % 2 == 0 else "CRITICAL"
            analyzer.process(Event("2026-10-11T10:00:00Z", lvl, src, "err"))

    stats = analyzer.get_stats()

    assert stats["total_events"] == 3 + sum(error_counts.values())
    assert stats["first_event"] == "2026-10-11T08:00:00+00:00"
    assert stats["last_event"] == "2026-10-11T19:30:00+00:00"

    top_errors = stats["top_error_sources"]
    assert isinstance(top_errors, dict)
    assert len(top_errors) == 5
    assert "src_6" not in top_errors
    assert "web" not in top_errors
    assert list(top_errors.keys()) == ["src_1", "src_2", "src_3", "src_4", "src_5"]


# =====================================================================
# 4. ТЕСТЫ ОТЧЁТОВ (report.py)
# =====================================================================


def test_write_json_and_csv_reports(tmp_path: Path) -> None:
    """Проверка записи отчётов в JSON и CSV (включая создание вложенных директорий)."""
    stats = {
        "total_events": 2,
        "events_by_level": {"INFO": 1, "ERROR": 1},
        "events_by_source": {"бэкенд": 2},
        "first_event": "2026-10-11T08:00:00+00:00",
        "last_event": "2026-10-11T09:00:00+00:00",
        "top_error_sources": {"бэкенд": 1},
    }

    json_out = tmp_path / "nested" / "dir" / "report.json"
    write_report(stats, json_out)
    loaded = json.loads(json_out.read_text(encoding="utf-8"))
    assert loaded == stats

    csv_out = tmp_path / "nested" / "dir" / "report.csv"
    write_report(stats, csv_out)
    with open(csv_out, encoding="utf-8") as f:
        rows = dict(csv.reader(f))
    assert rows["metric"] == "value"
    assert rows["total_events"] == "2"
    assert rows["events_by_level.ERROR"] == "1"
    assert rows["top_error_sources.бэкенд"] == "1"

    with pytest.raises(UnsupportedFormatError):
        write_report(stats, tmp_path / "report.txt")


# =====================================================================
# 5. ИНТЕГРАЦИОННЫЕ ТЕСТЫ CLI (__main__.py)
# =====================================================================


def test_cli_multiple_files_and_skip_invalid(tmp_path: Path) -> None:
    """Интеграционный тест CLI: объединение нескольких файлов и учёт --skip-invalid."""
    f1 = tmp_path / "part1.jsonl"
    f1.write_text(
        '{"timestamp": "2026-10-11T08:00:00Z", "level": "INFO", "source": "auth", "message": "login"}\n'
        '{"broken": "event"}\n',
        encoding="utf-8",
    )

    f2 = tmp_path / "part2.jsonl"
    f2.write_text(
        '{"timestamp": "2026-10-11T09:00:00Z", "level": "CRITICAL", "source": "db", "message": "down"}\n',
        encoding="utf-8",
    )

    out_file = tmp_path / "out.json"
    exit_code = main(["analyze", str(f1), str(f2), "--output", str(out_file), "--skip-invalid"])

    assert exit_code == 0
    report_data = json.loads(out_file.read_text(encoding="utf-8"))
    assert report_data["total_events"] == 2
    assert report_data["skipped_lines"] == 1
    assert report_data["top_error_sources"] == {"db": 1}


def test_cli_errors_exit_with_code_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """При любой ошибке (битая строка, нет файла, кривые флаги) CLI возвращает код 2 и пишет в stderr."""
    # 1. Несуществующий входной файл
    with pytest.raises(SystemExit) as exc_info:
        main(["analyze", str(tmp_path / "missing.csv"), "--output", str(tmp_path / "out.json")])
    assert exc_info.value.code == 2
    assert "Error:" in capsys.readouterr().err

    # 2. Битая строка без --skip-invalid
    bad_file = tmp_path / "bad.csv"
    bad_file.write_text("timestamp,level,source,message\nbad_ts,INFO,src,msg\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        main(["analyze", str(bad_file), "--output", str(tmp_path / "out.json")])
    assert exc_info.value.code == 2
    assert "Error:" in capsys.readouterr().err

    # 3. Ошибка аргументов CLI (отсутствует обязательный --output)
    with pytest.raises(SystemExit) as exc_info:
        main(["analyze", str(bad_file)])
    assert exc_info.value.code == 2
    assert "Error:" in capsys.readouterr().err
