import json

from pathlib import Path

from .constants import EVENT_FIELDS
from .errors import InvalidEventError
from .errors import InvalidTimestampError
from .models import Event


def parse_jsonl(path: Path | str, skip_invalid: bool = False):
    with open(path, "r", encoding="utf-8") as f:
        for line_number, raw_line in enumerate(f, start=1):
            if raw_line.strip() == "":
                continue
            try:
                data = json.loads(raw_line)
                if not isinstance(data, dict):
                    raise InvalidEventError("Line is not a valid JSON object")
                if set(data.keys()) != EVENT_FIELDS:
                    raise InvalidEventError(
                        f"Invalid keys in event: got {set(data.keys())}, expected {set(EVENT_FIELDS)}"
                    )
                event = Event(**data)
                yield event
            except json.JSONDecodeError as error:
                if skip_invalid:
                    continue  # потом будем логировать Warning
                raise InvalidEventError(
                    f"JSON syntax error: {error}",
                    line_number=line_number,
                    file_path=str(path),
                ) from error
            except InvalidTimestampError as error:
                if skip_invalid:
                    continue  # потом будем логировать Warning
                raise InvalidTimestampError(
                    timestamp=error.timestamp, line_number=line_number, file_path=str(path)
                ) from error
            except InvalidEventError as error:
                if skip_invalid:  # потом будем логировать Warning
                    continue
                raise InvalidEventError(error.raw_message, line_number=line_number, file_path=str(path)) from error
