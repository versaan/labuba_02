import argparse
import logging
import sys

from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from .analysis import LogAnal
from .errors import CLIConfigError
from .errors import StreamStatsError
from .parsers import get_parser
from .report import write_report


class StreamStatsArgumentParser(argparse.ArgumentParser):
    """Парсер аргументов CLI, выбрасывающий CLIConfigError при ошибках синтаксиса."""

    def error(self, message: str) -> NoReturn:
        raise CLIConfigError(message)


def build_parser() -> StreamStatsArgumentParser:
    """Создаёт и настраивает парсер аргументов командной строки."""
    parser = StreamStatsArgumentParser(
        prog="streamstats",
        description="Утилита потокового анализа логов.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Проанализировать файлы логов и сформировать отчёт.",
    )
    analyze_parser.add_argument(
        "inputs",
        nargs="+",
        help="Пути к одному или нескольким входным файлам.",
    )
    analyze_parser.add_argument(
        "--format",
        dest="fmt",
        default=None,
        help="Формат входных файлов (csv или jsonl). Если не указан, определяется по расширению.",
    )
    analyze_parser.add_argument(
        "--output",
        required=True,
        help="Путь для сохранения итогового отчёта.",
    )
    analyze_parser.add_argument(
        "--skip-invalid",
        action="store_true",
        help="Пропускать некорректные записи с выводом предупреждения в лог.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Основная точка входа CLI."""
    logging.basicConfig(
        level=logging.WARNING,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    parser = build_parser()

    try:
        args = parser.parse_args(argv)

        if args.command == "analyze":
            analyzer = LogAnal()
            total_skipped = 0

            for raw_path in args.inputs:
                file_path = Path(raw_path)
                if not file_path.is_file():
                    raise CLIConfigError(f"Input file not found: '{file_path}'")

                log_parser = get_parser(
                    path=file_path,
                    fmt=args.fmt,
                    skip_invalid=args.skip_invalid,
                )
                for event in log_parser.parse():
                    analyzer.process(event)
                total_skipped += log_parser.skipped_count

            stats = analyzer.get_stats()
            if args.skip_invalid:
                stats["skipped_lines"] = total_skipped

            write_report(stats, args.output)

    except StreamStatsError as error:
        sys.stderr.write(f"Error: {error}\n")
        sys.exit(2)
    except OSError as error:
        sys.stderr.write(f"OS Error: {error}\n")
        sys.exit(2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
