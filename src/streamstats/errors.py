"""Exception hierarchy for the streamstats package."""


class StreamStatsError(Exception):
    """Base exception for all streamstats errors."""

    pass


class UnsupportedFormatError(StreamStatsError):
    """Raised when an unsupported file format is specified or encountered."""

    def __init__(self, fmt: str, message: str = "Unsupported format"):
        self.format = fmt
        super().__init__(f"{message}: '{fmt}'. Supported formats: 'csv', 'jsonl'.")


class InvalidEventError(StreamStatsError):
    """Raised when an event is missing required fields or has invalid structure."""

    def __init__(
        self,
        message: str = "Invalid event structure",
        line_number: int | None = None,
        file_path: str | None = None,
    ):
        self.raw_message = message
        self.line_number = line_number
        self.file_path = file_path

        location_parts = []
        if file_path:
            location_parts.append(f"file: {file_path}")
        if line_number is not None:
            location_parts.append(f"line: {line_number}")

        if location_parts:
            super().__init__(f"[{', '.join(location_parts)}] {message}")
        else:
            super().__init__(message)


class InvalidTimestampError(InvalidEventError):
    """Raised when an event timestamp is not valid ISO 8601."""

    def __init__(
        self,
        timestamp: str,
        line_number: int | None = None,
        file_path: str | None = None,
        message: str = "Invalid ISO 8601 timestamp",
    ):
        self.timestamp = timestamp
        detail = f"{message}: '{timestamp}'"
        super().__init__(detail, line_number=line_number, file_path=file_path)


class CLIConfigError(StreamStatsError):
    """Raised when CLI arguments or configurations are invalid."""

    def __init__(self, message: str = "CLI configuration error"):
        self.message = message
        super().__init__(message)
