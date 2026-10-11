from datetime import datetime

from .constants import VALID_LEVELS
from .errors import InvalidEventError
from .errors import InvalidTimestampError


class Event:
    def __init__(self, timestamp, level: str, source: str, message: str):
        try:
            self.timestamp = datetime.fromisoformat(timestamp)
        except (ValueError, TypeError):
            raise InvalidTimestampError(timestamp=timestamp)
        if not isinstance(level, str) or level not in VALID_LEVELS:
            raise InvalidEventError("Unacceptable level")
        self.level = level
        if not isinstance(message, str):
            raise InvalidEventError("The message must be a string")
        self.message = message
        if not isinstance(source, str) or source.strip() == "":
            raise InvalidEventError("The source must be a string and must not be empty")
        self.source = source

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Event):
            return NotImplemented
        return (
            self.timestamp == other.timestamp
            and self.level == other.level
            and self.source == other.source
            and self.message == other.message
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(timestamp={self.timestamp}, level={self.level}, source={self.source}, message={self.message})"
