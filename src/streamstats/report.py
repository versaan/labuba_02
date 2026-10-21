import csv
import json

from pathlib import Path
from typing import Any

from .errors import UnsupportedFormatError


def _write_json_report(stats: dict[str, Any], path: Path) -> None:
    """Записывает агрегированную статистику в формате JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)


def _write_csv_report(stats: dict[str, Any], path: Path) -> None:
    """Записывает агрегированную статистику в плоском формате CSV (metric, value)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        rows: list[tuple[str, Any]] = []
        for key, value in stats.items():
            if isinstance(value, dict):
                if not value:
                    rows.append((key, ""))
                else:
                    for sub_key, sub_value in value.items():
                        rows.append((f"{key}.{sub_key}", sub_value))
            elif value is None:
                rows.append((key, ""))
            else:
                rows.append((key, value))
        writer.writerow(("metric", "value"))
        writer.writerows(rows)


def write_report(stats: dict[str, Any], path: Path | str, fmt: str | None = None) -> None:
    """Универсальная функция сохранения отчёта по пути или явному формату."""
    path = Path(path)
    target_format = fmt.lower() if fmt else path.suffix.lstrip(".").lower()

    match target_format:
        case "json":
            _write_json_report(stats, path)
        case "csv":
            _write_csv_report(stats, path)
        case _:
            raise UnsupportedFormatError(fmt=target_format)
