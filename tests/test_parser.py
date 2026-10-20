from pathlib import Path

import pytest

from streamstats.errors import InvalidEventError
from streamstats.errors import UnsupportedFormatError
from streamstats.parsers import CSVParser
from streamstats.parsers import JSONLParser
from streamstats.parsers import get_parser

# =====================================================================
# Тесты для JSONLParser
# =====================================================================


def test_jsonl_parser_valid_events(tmp_path: Path) -> None:
    file = tmp_path / "valid.jsonl"
    file.write_text(
        '{"timestamp": "2026-10-15T12:00:00Z", "level": "INFO", "source": "auth", "message": "Login success"}\n'
        '{"timestamp": "2026-10-15T12:00:05Z", "level": "ERROR", "source": "db", "message": "Connection lost"}\n',
        encoding="utf-8",
    )

    parser = JSONLParser(file)
    events = list(parser.parse())

    assert len(events) == 2
    assert events[0].level == "INFO"
    assert events[0].source == "auth"
    assert events[1].level == "ERROR"
    assert parser.skipped_count == 0


def test_jsonl_parser_empty_file(tmp_path: Path) -> None:
    file = tmp_path / "empty.jsonl"
    file.write_text("", encoding="utf-8")

    parser = JSONLParser(file)
    events = list(parser.parse())

    assert events == []
    assert parser.skipped_count == 0


def test_jsonl_parser_invalid_syntax_raises_error(tmp_path: Path) -> None:
    file = tmp_path / "broken.jsonl"
    file.write_text("NOT A JSON\n", encoding="utf-8")

    parser = JSONLParser(file, skip_invalid=False)
    with pytest.raises(InvalidEventError) as exc_info:
        list(parser.parse())

    assert exc_info.value.line_number == 1
    assert exc_info.value.file_path == str(file)


def test_jsonl_parser_skip_invalid(tmp_path: Path) -> None:
    file = tmp_path / "mixed.jsonl"
    file.write_text(
        '{"timestamp": "2026-10-15T12:00:00Z", "level": "INFO", "source": "auth", "message": "OK"}\n'
        '{"broken": "structure"}\n'
        "INVALID JSON\n"
        '{"timestamp": "2026-10-15T12:00:05Z", "level": "WARNING", "source": "auth", "message": "Retry"}\n',
        encoding="utf-8",
    )

    parser = JSONLParser(file, skip_invalid=True)
    events = list(parser.parse())

    assert len(events) == 2
    assert parser.skipped_count == 2
    assert events[0].message == "OK"
    assert events[1].message == "Retry"


# =====================================================================
# Тесты для CSVParser
# =====================================================================


def test_csv_parser_comma_delimiter(tmp_path: Path) -> None:
    file = tmp_path / "logs.csv"
    file.write_text(
        "timestamp,level,source,message\n" '2026-10-15T12:00:00Z,INFO,auth,"User logged in, successfully"\n',
        encoding="utf-8",
    )

    parser = CSVParser(file)
    events = list(parser.parse())

    assert len(events) == 1
    assert events[0].source == "auth"
    assert events[0].message == "User logged in, successfully"


def test_csv_parser_semicolon_and_leading_empty_lines(tmp_path: Path) -> None:
    file = tmp_path / "semicolon.csv"
    file.write_text(
        "\n\n  \n"  # Пустые строки перед заголовком
        "timestamp;level;source;message\n"
        "2026-10-15T12:00:00Z;WARNING;billing;Gateway timeout\n",
        encoding="utf-8",
    )

    parser = CSVParser(file)
    events = list(parser.parse())

    assert len(events) == 1
    assert events[0].level == "WARNING"
    assert events[0].source == "billing"


def test_csv_parser_extra_fields_raises_error(tmp_path: Path) -> None:
    file = tmp_path / "extra_cols.csv"
    # Незакавыченная запятая дает лишнюю 5-ю колонку
    file.write_text(
        "timestamp,level,source,message\n" "2026-10-15T12:00:00Z,WARN,billing,Gateway timeout, retrying\n",
        encoding="utf-8",
    )

    parser = CSVParser(file, skip_invalid=False)
    with pytest.raises(InvalidEventError) as exc_info:
        list(parser.parse())

    assert exc_info.value.line_number == 2


def test_csv_parser_skip_invalid(tmp_path: Path) -> None:
    file = tmp_path / "mixed.csv"
    file.write_text(
        "timestamp,level,source,message\n"
        "2026-10-15T12:00:00Z,INFO,auth,OK\n"
        "2026-10-15T12:00:01Z,ERROR,db,Fail, extra, commas\n"
        ",,,\n"  # Строка с пустыми значениями должна отбраковываться
        "2026-10-15T12:00:02Z,INFO,billing,Done\n",
        encoding="utf-8",
    )

    parser = CSVParser(file, skip_invalid=True)
    events = list(parser.parse())

    assert len(events) == 2
    assert parser.skipped_count == 2
    assert events[0].source == "auth"
    assert events[1].source == "billing"


def test_csv_parser_empty_file(tmp_path: Path) -> None:
    file = tmp_path / "empty.csv"
    file.write_text("\n   \n\n", encoding="utf-8")

    parser = CSVParser(file)
    events = list(parser.parse())

    assert events == []
    assert parser.skipped_count == 0


# =====================================================================
# Тесты для get_parser (фабрика)
# =====================================================================


def test_get_parser_format_detection(tmp_path: Path) -> None:
    csv_file = tmp_path / "test.csv"
    jsonl_file = tmp_path / "test.jsonl"
    txt_file = tmp_path / "test.txt"

    assert isinstance(get_parser(csv_file), CSVParser)
    assert isinstance(get_parser(jsonl_file), JSONLParser)

    # Явный оверрайд флагом fmt
    custom_parser = get_parser(txt_file, fmt="csv")
    assert isinstance(custom_parser, CSVParser)


def test_get_parser_unsupported_format(tmp_path: Path) -> None:
    unknown_file = tmp_path / "test.parquet"

    with pytest.raises(UnsupportedFormatError):
        get_parser(unknown_file)

    with pytest.raises(UnsupportedFormatError):
        get_parser(tmp_path / "test.log", fmt="yaml")
