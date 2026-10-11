from datetime import datetime
from .errors import InvalidEventError
from .errors import InvalidTimestampError
from .constants import VALID_LEVELS
class Event():
    def __init__(self, timestamp: str, level: str, source: str, message:str):
        try:
            self.timestamp = datetime.fromisoformat(timestamp)
        except (ValueError, TypeError):
            raise InvalidTimestampError(timestamp=timestamp)
        if not isinstance(level, str) or level not in VALID_LEVELS:
            raise InvalidEventError("Unacceptable level")
        else: self.level = level
        if not isinstance(message, str):
            raise InvalidEventError("The message must be a string")
        else: self.message = message
        if not isinstance(source, str) or source == "":
            InvalidEventError("The source must be a string and must not be empty")
        else: self.source = source