import json
from collections.abc import Iterator
from pathlib import Path

from .constants import EVENT_FIELDS
from .errors import InvalidEventError
from .errors import InvalidTimestampError, UnsupportedFormatError
from .models import Event
from typing import Any, TextIO
class BaseParser():
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
                        #потом будем логировать warning
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
def get_parser(path: Path|str, skip_invalid: bool = False) -> BaseParser:
    path = Path(path)
    match path.suffix:
        case ".jsonl":
            return JSONLParser(path, skip_invalid=skip_invalid)
        case _:
            raise UnsupportedFormatError(fmt=path.suffix)