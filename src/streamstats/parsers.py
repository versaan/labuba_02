import csv
import json
import logging

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from typing import TextIO

from .constants import EVENT_FIELDS
from .errors import InvalidEventError
from .errors import InvalidTimestampError
from .errors import UnsupportedFormatError
from .models import Event

logger = logging.getLogger(__name__)


class BaseParser:
    def __init__(self, path: Path, skip_invalid: bool = False) -> None:
        self.path = path
        self.skip_invalid = skip_invalid
        self.skipped_count = 0

    def _iter_raw_items(self, file: TextIO) -> Iterator[tuple[int, Any]]:
        """Генерирует пары (номер_строки, сырые_данные). Реализуется в наследниках."""
        raise NotImplementedError

    def _parse_item(self, item: Any) -> dict[str, Any]:
        """Превращает сырой элемент строки в словарь. Реализуется в наследниках."""
        raise NotImplementedError

    def parse(self) -> Iterator[Event]:
        """Потоково считывает файл, валидирует строки и генерирует объекты Event."""
        with open(self.path, "r", encoding="utf-8") as f:
            for line_number, raw_item in self._iter_raw_items(f):
                try:
                    data = self._parse_item(raw_item)
                    if set(data.keys()) != EVENT_FIELDS:
                        raise InvalidEventError(
                            f"Invalid keys in event: got {set(data.keys())}, expected {set(EVENT_FIELDS)}"
                        )
                    yield Event(**data)
                except InvalidEventError as error:
                    if self.skip_invalid:
                        self.skipped_count += 1
                        logger.warning("Skipping invalid event at %s:%d: %s", self.path, line_number, error)
                        continue

                    if isinstance(error, InvalidTimestampError):
                        raise InvalidTimestampError(
                            timestamp=error.timestamp,
                            line_number=line_number,
                            file_path=str(self.path),
                        ) from error

                    raise InvalidEventError(
                        error.raw_message,
                        line_number=line_number,
                        file_path=str(self.path),
                    ) from error


class JSONLParser(BaseParser):
    """Парсер для построчного чтения формата JSONL."""

    def _iter_raw_items(self, file: TextIO) -> Iterator[tuple[int, str]]:
        for line_number, raw_line in enumerate(file, start=1):
            if raw_line.strip() == "":
                continue
            yield line_number, raw_line

    def _parse_item(self, item: str) -> dict[str, Any]:
        try:
            data = json.loads(item)
        except json.JSONDecodeError as error:
            raise InvalidEventError(f"JSON syntax error: {error}") from error

        if not isinstance(data, dict):
            raise InvalidEventError("Line is not a valid JSON object")
        return data


class CSVParser(BaseParser):
    """Парсер для построчного чтения формата CSV."""

    def _preparer(self, file: TextIO) -> tuple[str | None, int]:
        """Определяет разделитель (',' или ';') и считает пустые строки в начале файла."""
        counter_of_empty_lines = 0
        while True:
            line = file.readline()
            if not line:
                return (None, counter_of_empty_lines)
            if not line.strip():
                counter_of_empty_lines += 1
                continue
            if ";" in line:
                return ";", counter_of_empty_lines
            else:
                return ",", counter_of_empty_lines

    def _iter_raw_items(self, file: TextIO) -> Iterator[tuple[int, dict[str, Any]]]:
        delimiter, counter_of_empty_lines = self._preparer(file)
        if delimiter is None:
            return
        file.seek(0)
        for _ in range(counter_of_empty_lines):
            file.readline()
        reader = csv.DictReader(file, delimiter=delimiter)
        for row in reader:
            if all(value is None for value in row.values()):
                continue
            line_number = reader.line_num + counter_of_empty_lines
            yield line_number, row

    def _parse_item(self, item: dict[str, Any]) -> dict[str, Any]:
        if None in item:
            raise InvalidEventError("CSV row contains extra fields")
        return dict(item)


def get_parser(path: Path | str, fmt: str | None = None, skip_invalid: bool = False) -> BaseParser:
    """Возвращает подходящий экземпляр парсера по явному формату или расширению файла."""
    path = Path(path)
    if fmt:
        target_format = fmt.lower()
    else:
        target_format = path.suffix.lstrip(".").lower()
    match target_format:
        case "jsonl":
            return JSONLParser(path, skip_invalid=skip_invalid)
        case "csv":
            return CSVParser(path, skip_invalid=skip_invalid)
        case _:
            raise UnsupportedFormatError(fmt=target_format)
