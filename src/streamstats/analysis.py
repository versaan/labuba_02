from collections import Counter
from typing import Any

from .models import Event


class LogAnal:
    def __init__(self):
        self.total_events = 0  # Общий счётчик событий
        self.events_by_level = Counter()  # Счётчик по уровням
        self.events_by_source = Counter()  # Счётчик по источникам
        self.first_event = None
        self.last_event = None
        self.error_sources = Counter()  # Топ-5 источников сбоев

    def process(self, event: Event) -> None:
        """Принимает один объект события и инкрементирует счётчик."""
        self.total_events += 1
        self.events_by_level[event.level] += 1
        self.events_by_source[event.source] += 1
        if self.first_event is None or event.timestamp < self.first_event:
            self.first_event = event.timestamp
        if self.last_event is None or event.timestamp > self.last_event:
            self.last_event = event.timestamp
        if event.level in ("ERROR", "CRITICAL"):
            self.error_sources[event.source] += 1

    def get_stats(self) -> dict[str, int | str | None | dict[str, Any]]:
        """Возвращает агрегированную статистику по всем обработанным событиям."""
        return {
            "total_events": self.total_events,
            "events_by_level": dict(self.events_by_level),
            "events_by_source": dict(self.events_by_source),
            "first_event": self.first_event.isoformat() if self.first_event else None,
            "last_event": self.last_event.isoformat() if self.last_event else None,
            "top_error_sources": dict(self.error_sources.most_common(5)),
        }
