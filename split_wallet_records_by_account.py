#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path
from wallet_tabular import (
    SUPPORTED_OUTPUT_FORMATS,
    discover_directory_inputs,
    read_rows,
    resolve_output_format,
    validate_explicit_inputs,
    write_rows,
)


DEFAULT_INPUT_DIR = Path("Wallet Records")
DEFAULT_OUTPUT_DIR = "Account Data"
DEFAULT_MAX_ROWS_PER_FILE = 500
REQUIRED_HEADERS = {
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
}
OUTPUT_HEADERS = [
    "account",
    "category",
    "currency",
    "income_amount",
    "expense_amount",
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
            "Merge Wallet exports into one file per account without modifying "
            "the original files."
        )
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help=(
            "Input files to process (.csv or .xlsx). If omitted, the script uses "
            f"all supported files inside {DEFAULT_INPUT_DIR}."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(DEFAULT_OUTPUT_DIR),
        help="Directory where per-account output files will be created.",
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
    parser.add_argument(
        "--output-format",
        choices=SUPPORTED_OUTPUT_FORMATS,
        default="csv",
        help=(
            "Generated file format. Defaults to csv. Use xlsx for Excel output, "
            "or match-input to reuse the shared input format when all inputs use "
            "the same extension."
        ),
    )
    return parser.parse_args()


def discover_inputs(explicit_inputs: list[Path]) -> tuple[list[Path], list[str]]:
    if explicit_inputs:
        return validate_explicit_inputs(explicit_inputs), []
    else:
        return discover_directory_inputs(DEFAULT_INPUT_DIR)


def sanitize_filename_part(value: str) -> str:
    sanitized = re.sub(r"[^\w.-]+", "_", value.strip(), flags=re.UNICODE)
    sanitized = sanitized.strip("._")
    return sanitized or "unnamed_account"


def build_output_path(
    output_dir: Path,
    account_name: str,
    extension: str,
    chunk_index: int | None = None,
) -> Path:
    filename = sanitize_filename_part(account_name)
    if chunk_index is not None:
        filename = f"{filename}_part{chunk_index}"
    filename = f"{filename}.{extension}"
    return output_dir / filename


def load_rows(paths: list[Path]) -> tuple[list[str], dict[str, list[dict[str, str]]]]:
    rows_by_account: dict[str, list[dict[str, str]]] = defaultdict(list)
    first_headers: list[str] | None = None

    for path in paths:
        current_headers, rows = read_rows(path, REQUIRED_HEADERS)
        if first_headers is None:
            first_headers = current_headers
        elif current_headers != first_headers:
            raise ValueError(f"{path} header does not match the first input file header")

        for row in rows:
            account_name = (row.get("account") or "").strip()
            if not account_name:
                account_name = "Unnamed Account"
                row["account"] = account_name
            amount = (row.get("amount") or "").strip()
            row_type = (row.get("type") or "").strip().lower()
            income_amount = ""
            expense_amount = ""
            if row_type == "income":
                income_amount = amount
            elif row_type == "expense":
                expense_amount = amount
            transformed_row = {
                "account": row.get("account", ""),
                "category": row.get("category", ""),
                "currency": row.get("currency", ""),
                "income_amount": income_amount,
                "expense_amount": expense_amount,
                "ref_currency_amount": row.get("ref_currency_amount", ""),
                "type": row.get("type", ""),
                "payment_type": row.get("payment_type", ""),
                "note": row.get("note", ""),
                "date": row.get("date", ""),
                "transfer": row.get("transfer", ""),
                "payee": row.get("payee", ""),
                "labels": row.get("labels", ""),
            }
            rows_by_account[account_name].append(transformed_row)

    if first_headers is None:
        raise ValueError("No readable input data found")

    return OUTPUT_HEADERS, rows_by_account


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
    output_format: str,
    input_paths: list[Path],
) -> list[tuple[str, Path, int]]:
    suffixes = {path.suffix.lower() for path in input_paths}
    input_suffix = next(iter(suffixes)) if len(suffixes) == 1 else None
    extension = resolve_output_format(output_format, input_suffix)
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
            output_path = build_output_path(
                output_dir,
                account_name,
                extension,
                chunk_index,
            )
            output_existed = output_path.exists()
            write_rows(output_path, fieldnames, row_chunk, extension)
            action = "Overwrote" if output_existed else "Created"
            print(f"{action} {output_path} | {len(row_chunk)} rows")
            written.append((account_name, output_path, len(row_chunk)))

    return written


def main() -> int:
    args = parse_args()
    input_paths, skipped_messages = discover_inputs(args.inputs)
    print(f"Discovered {len(input_paths)} input file(s)")
    for message in skipped_messages:
        print(message)
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
        args.output_format,
        input_paths,
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
