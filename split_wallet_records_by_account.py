#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path


DEFAULT_INPUT_DIR = Path("Wallet Records")
DEFAULT_INPUT_GLOB = "wallet_records_20[2-5][0-9].csv"
DEFAULT_OUTPUT_DIR = "Accounts Data"
DEFAULT_MAX_ROWS_PER_FILE = 1000
REQUIRED_HEADERS = [
    "account",
    "category",
    "currency",
    "amount",
    "ref_currency_amount",
    "type",
    "payment_type",
    "note",
    "date",
    "transfer",
    "payee",
    "labels",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Merge Wallet yearly CSV exports into one CSV per account without "
            "modifying the original files."
        )
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help=(
            "CSV files to process. If omitted, the script uses "
            f"{DEFAULT_INPUT_GLOB!r} inside {DEFAULT_INPUT_DIR}."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(DEFAULT_OUTPUT_DIR),
        help="Directory where per-account CSV files will be created.",
    )
    parser.add_argument(
        "--sort-by-date",
        action="store_true",
        help="Sort each account file by the date column after merging.",
    )
    parser.add_argument(
        "--max-rows-per-file",
        type=int,
        default=DEFAULT_MAX_ROWS_PER_FILE,
        help=(
            "Maximum number of data rows per output file. Use 0 to disable chunking. "
            "Wallet recommends no more than 1,000 rows per import file."
        ),
    )
    return parser.parse_args()


def discover_inputs(explicit_inputs: list[Path]) -> list[Path]:
    if explicit_inputs:
        inputs = explicit_inputs
    else:
        inputs = sorted(DEFAULT_INPUT_DIR.glob(DEFAULT_INPUT_GLOB))

    if not inputs:
        raise FileNotFoundError(
            f"No input CSV files found matching {DEFAULT_INPUT_GLOB!r} in "
            f"{DEFAULT_INPUT_DIR}"
        )

    validated: list[Path] = []
    for path in inputs:
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")
        if not path.is_file():
            raise ValueError(f"Input path is not a file: {path}")
        validated.append(path)
    return validated


def sanitize_filename_part(value: str) -> str:
    sanitized = re.sub(r"[^\w.-]+", "_", value.strip(), flags=re.UNICODE)
    sanitized = sanitized.strip("._")
    return sanitized or "unnamed_account"


def build_output_path(
    output_dir: Path,
    account_name: str,
    chunk_index: int | None = None,
) -> Path:
    filename = sanitize_filename_part(account_name)
    if chunk_index is not None:
        filename = f"{filename}_part{chunk_index}"
    filename = f"{filename}.csv"
    return output_dir / filename


def validate_headers(fieldnames: Iterable[str] | None, source: Path) -> list[str]:
    if not fieldnames:
        raise ValueError(f"{source} has no header row")

    actual = list(fieldnames)
    missing = [name for name in REQUIRED_HEADERS if name not in actual]
    if missing:
        missing_list = ", ".join(missing)
        raise ValueError(f"{source} is missing required headers: {missing_list}")
    return actual


def load_rows(paths: list[Path]) -> tuple[list[str], dict[str, list[dict[str, str]]]]:
    rows_by_account: dict[str, list[dict[str, str]]] = defaultdict(list)
    fieldnames: list[str] | None = None

    for path in paths:
        with path.open("r", newline="", encoding="utf-8-sig") as source_file:
            reader = csv.DictReader(source_file, delimiter=";")
            current_headers = validate_headers(reader.fieldnames, path)
            if fieldnames is None:
                fieldnames = current_headers
            elif current_headers != fieldnames:
                raise ValueError(
                    f"{path} header does not match the first input file header"
                )

            for row in reader:
                account_name = (row.get("account") or "").strip()
                if not account_name:
                    account_name = "Unnamed Account"
                    row["account"] = account_name
                rows_by_account[account_name].append(row)

    if fieldnames is None:
        raise ValueError("No readable input data found")

    return fieldnames, rows_by_account


def sort_rows_by_date(rows_by_account: dict[str, list[dict[str, str]]]) -> None:
    for rows in rows_by_account.values():
        rows.sort(key=lambda row: row.get("date", ""))


def chunk_rows(rows: list[dict[str, str]], max_rows_per_file: int) -> list[list[dict[str, str]]]:
    if max_rows_per_file <= 0 or len(rows) <= max_rows_per_file:
        return [rows]
    return [
        rows[index : index + max_rows_per_file]
        for index in range(0, len(rows), max_rows_per_file)
    ]


def write_outputs(
    output_dir: Path,
    fieldnames: list[str],
    rows_by_account: dict[str, list[dict[str, str]]],
    max_rows_per_file: int,
) -> list[tuple[str, Path, int]]:
    output_dir_existed = output_dir.exists()
    output_dir.mkdir(parents=True, exist_ok=True)
    if output_dir_existed:
        print(f"Using existing output directory: {output_dir}")
    else:
        print(f"Created output directory: {output_dir}")
    written: list[tuple[str, Path, int]] = []

    for account_name in sorted(rows_by_account):
        rows = rows_by_account[account_name]
        row_chunks = chunk_rows(rows, max_rows_per_file)
        print(
            f"Preparing account {account_name!r} | "
            f"{len(rows)} rows | {len(row_chunks)} output file(s)"
        )
        for index, row_chunk in enumerate(row_chunks, start=1):
            chunk_index = index if len(row_chunks) > 1 else None
            output_path = build_output_path(output_dir, account_name, chunk_index)
            output_existed = output_path.exists()
            with output_path.open("w", newline="", encoding="utf-8-sig") as target_file:
                writer = csv.DictWriter(
                    target_file,
                    fieldnames=fieldnames,
                    delimiter=";",
                    quoting=csv.QUOTE_MINIMAL,
                )
                writer.writeheader()
                writer.writerows(row_chunk)
            action = "Overwrote" if output_existed else "Created"
            print(f"{action} {output_path} | {len(row_chunk)} rows")
            written.append((account_name, output_path, len(row_chunk)))

    return written


def main() -> int:
    args = parse_args()
    input_paths = discover_inputs(args.inputs)
    print(f"Discovered {len(input_paths)} input file(s)")
    for input_path in input_paths:
        print(f"Reading {input_path}")
    fieldnames, rows_by_account = load_rows(input_paths)
    total_rows = sum(len(rows) for rows in rows_by_account.values())
    print(
        f"Loaded {total_rows} rows across {len(rows_by_account)} account(s)"
    )
    if args.sort_by_date:
        print("Sorting rows by date within each account")
        sort_rows_by_date(rows_by_account)

    written = write_outputs(
        args.output_dir,
        fieldnames,
        rows_by_account,
        args.max_rows_per_file,
    )
    print(
        f"Processed {len(input_paths)} input files into {len(written)} account files "
        f"under {args.output_dir} | {total_rows} rows total"
    )
    for account_name, output_path, row_count in written:
        print(f"{account_name}: {row_count} rows -> {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())