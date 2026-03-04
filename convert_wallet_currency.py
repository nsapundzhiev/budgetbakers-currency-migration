#!/usr/bin/env python3
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from wallet_tabular import (
    SUPPORTED_OUTPUT_FORMATS,
    discover_directory_inputs,
    read_rows,
    resolve_output_format,
    validate_explicit_inputs,
    write_rows,
)


DEFAULT_SOURCE_DIR = Path("Account Data")
DEFAULT_SOURCE_CURRENCY = "BGN"
DEFAULT_TARGET_CURRENCY = "EUR"
DEFAULT_RATE = Decimal("1.95583")
REQUIRED_HEADERS = {"currency", "income_amount", "expense_amount", "ref_currency_amount"}
MAX_LOGGED_UNEXPECTED_ROWS = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert Wallet tabular files from one currency to another by reading "
            "supported input files (.csv or .xlsx) from a source directory and "
            "writing converted output files to a separate output directory."
        )
    )
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help=(
            "Source directory containing Wallet-style .csv/.xlsx files, or a single "
            "supported input file."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "Directory for converted files. Defaults to "
            "'Account Data <TARGET_CURRENCY>'."
        ),
    )
    parser.add_argument(
        "--source-currency",
        default=DEFAULT_SOURCE_CURRENCY,
        help="Currency code to convert from.",
    )
    parser.add_argument(
        "--target-currency",
        default=DEFAULT_TARGET_CURRENCY,
        help="Currency code to convert to.",
    )
    parser.add_argument(
        "--rate",
        type=Decimal,
        default=DEFAULT_RATE,
        help="Fixed conversion rate from source currency to target currency.",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=2,
        help="Number of decimal places to write in converted amounts.",
    )
    parser.add_argument(
        "--keep-ref-amounts",
        action="store_true",
        help=(
            "Leave ref_currency_amount unchanged for rows already in the target "
            "currency. By default, those rows are normalized so "
            "ref_currency_amount matches amount."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change without creating or overwriting any files.",
    )
    parser.add_argument(
        "--output-format",
        choices=SUPPORTED_OUTPUT_FORMATS,
        default="csv",
        help=(
            "Generated file format. Defaults to csv. Use xlsx for Excel output, "
            "or match-input to mirror each source file's format."
        ),
    )
    return parser.parse_args()


def quantize_exp(scale: int) -> Decimal:
    if scale < 0:
        raise ValueError("scale must be zero or greater")
    return Decimal("1").scaleb(-scale)


def parse_decimal(value: str) -> Decimal | None:
    text = value.strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal value: {value!r}") from exc


def format_decimal(value: Decimal, scale: int) -> str:
    return str(value.quantize(quantize_exp(scale), rounding=ROUND_HALF_UP))


def convert_amount(value: str, rate: Decimal, scale: int) -> str:
    decimal_value = parse_decimal(value)
    if decimal_value is None:
        return value
    return format_decimal(decimal_value / rate, scale)


def normalize_amount(value: str, scale: int) -> str:
    decimal_value = parse_decimal(value)
    if decimal_value is None:
        return value
    return format_decimal(decimal_value, scale)


def discover_input_files(source: Path) -> tuple[list[Path], list[str]]:
    if not source.exists():
        raise FileNotFoundError(f"Source path not found: {source}")

    if source.is_file():
        return validate_explicit_inputs([source]), []

    if not source.is_dir():
        raise ValueError(
            f"Source path must be a directory or a supported input file: {source}"
        )

    return discover_directory_inputs(source)


def default_output_dir(target_currency: str) -> Path:
    return Path(f"Account Data {target_currency}")


def output_path_for(input_file: Path, output_dir: Path, output_format: str) -> Path:
    extension = resolve_output_format(output_format, input_file.suffix.lower())
    return output_dir / f"{input_file.stem}.{extension}"


def summarize_unexpected_row(row_number: int, row: dict[str, str]) -> str:
    account = (row.get("account") or "").strip() or "<no account>"
    date = (row.get("date") or "").strip() or "<no date>"
    currency = (row.get("currency") or "").strip() or "<empty>"
    amount = (
        (row.get("income_amount") or "").strip()
        or (row.get("expense_amount") or "").strip()
        or "<empty>"
    )
    return (
        f"row {row_number}: currency={currency}, amount={amount}, "
        f"account={account}, date={date}"
    )


def inspect_file(
    input_path: Path,
    source_currency: str,
    target_currency: str,
) -> tuple[int, int, int, list[str], int]:
    row_count = 0
    converted_rows = 0
    normalized_rows = 0
    unexpected_rows: list[str] = []
    unexpected_count = 0

    _, rows = read_rows(input_path, REQUIRED_HEADERS)
    for row in rows:
        row_count += 1
        currency = (row.get("currency") or "").strip()
        if currency == source_currency:
            converted_rows += 1
        elif currency == target_currency:
            normalized_rows += 1
        else:
            unexpected_count += 1
            if len(unexpected_rows) < MAX_LOGGED_UNEXPECTED_ROWS:
                unexpected_rows.append(summarize_unexpected_row(row_count + 1, row))

    return converted_rows, normalized_rows, row_count, unexpected_rows, unexpected_count


def process_file(
    input_path: Path,
    output_path: Path,
    rate: Decimal,
    source_currency: str,
    target_currency: str,
    scale: int,
    keep_ref_amounts: bool,
) -> tuple[int, int, int, list[str], int]:
    converted_rows = 0
    normalized_rows = 0
    row_count = 0
    unexpected_rows: list[str] = []
    unexpected_count = 0

    fieldnames, rows = read_rows(input_path, REQUIRED_HEADERS)
    for row in rows:
        row_count += 1
        currency = (row.get("currency") or "").strip()

        if currency == source_currency:
            row["income_amount"] = convert_amount(
                row["income_amount"], rate, scale
            )
            row["expense_amount"] = convert_amount(
                row["expense_amount"], rate, scale
            )
            row["ref_currency_amount"] = convert_amount(
                row["ref_currency_amount"], rate, scale
            )
            row["currency"] = target_currency
            converted_rows += 1
        elif not keep_ref_amounts and currency == target_currency:
            if row.get("income_amount"):
                row["income_amount"] = normalize_amount(
                    row["income_amount"], scale
                )
            if row.get("expense_amount"):
                row["expense_amount"] = normalize_amount(
                    row["expense_amount"], scale
                )
            reference_source = (
                row.get("income_amount")
                or row.get("expense_amount")
                or row.get("ref_currency_amount", "")
            )
            row["ref_currency_amount"] = normalize_amount(
                reference_source, scale
            )
            normalized_rows += 1
        elif currency != target_currency:
            unexpected_count += 1
            if len(unexpected_rows) < MAX_LOGGED_UNEXPECTED_ROWS:
                unexpected_rows.append(
                    summarize_unexpected_row(row_count + 1, row)
                )

    write_rows(
        output_path,
        fieldnames,
        rows,
        output_path.suffix.lower().lstrip("."),
    )

    return converted_rows, normalized_rows, row_count, unexpected_rows, unexpected_count


def main() -> int:
    args = parse_args()
    if args.rate <= 0:
        raise ValueError("rate must be greater than zero")

    input_files, skipped_messages = discover_input_files(args.source)
    for message in skipped_messages:
        print(message)
    output_dir = args.output_dir or default_output_dir(args.target_currency)
    if args.dry_run:
        if output_dir.exists():
            print(f"Dry run: would use existing output directory: {output_dir}")
        else:
            print(f"Dry run: would create output directory: {output_dir}")
    else:
        output_dir_existed = output_dir.exists()
        output_dir.mkdir(parents=True, exist_ok=True)
        if output_dir_existed:
            print(f"Using existing output directory: {output_dir}")
        else:
            print(f"Created output directory: {output_dir}")

    total_converted = 0
    total_normalized = 0
    total_rows = 0
    total_unexpected = 0

    for input_file in input_files:
        output_file = output_path_for(input_file, output_dir, args.output_format)
        if args.dry_run:
            (
                converted_rows,
                normalized_rows,
                row_count,
                unexpected_rows,
                unexpected_count,
            ) = inspect_file(
                input_path=input_file,
                source_currency=args.source_currency,
                target_currency=args.target_currency,
            )
            action = (
                "Would overwrite" if output_file.exists() else "Would create"
            )
        else:
            output_existed = output_file.exists()
            (
                converted_rows,
                normalized_rows,
                row_count,
                unexpected_rows,
                unexpected_count,
            ) = process_file(
                input_path=input_file,
                output_path=output_file,
                rate=args.rate,
                source_currency=args.source_currency,
                target_currency=args.target_currency,
                scale=args.scale,
                keep_ref_amounts=args.keep_ref_amounts,
            )
            action = "Overwrote" if output_existed else "Created"
        total_converted += converted_rows
        total_normalized += normalized_rows
        total_rows += row_count
        total_unexpected += unexpected_count
        print(
            f"{action} {output_file} from {input_file} | "
            f"{row_count} rows | "
            f"converted {converted_rows} {args.source_currency} rows, "
            f"normalized {normalized_rows} {args.target_currency} reference rows, "
            f"flagged {unexpected_count} unexpected-currency rows"
        )
        if unexpected_rows:
            print(
                f"Manual validation needed in {input_file}: "
                f"{unexpected_count} row(s) are neither {args.source_currency} "
                f"nor {args.target_currency}"
            )
            for item in unexpected_rows:
                print(f"  - {item}")
            if unexpected_count > len(unexpected_rows):
                print(
                    f"  - ... {unexpected_count - len(unexpected_rows)} more row(s)"
                )

    print(
        f"{'Dry run for' if args.dry_run else 'Processed'} {len(input_files)} files "
        f"into {output_dir} | "
        f"{total_rows} rows total | "
        f"converted {total_converted} rows, normalized {total_normalized} rows, "
        f"flagged {total_unexpected} unexpected-currency rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
