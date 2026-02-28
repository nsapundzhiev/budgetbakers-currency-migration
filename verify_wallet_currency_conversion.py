#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


DEFAULT_RECORDS_DIR = Path("Wallet Records")
DEFAULT_SOURCE_DIR = Path("Accounts Data")
DEFAULT_CONVERTED_DIR = Path("Accounts Data EUR")
DEFAULT_SOURCE_CURRENCY = "BGN"
DEFAULT_TARGET_CURRENCY = "EUR"
DEFAULT_RATE = Decimal("1.95583")
REQUIRED_HEADERS = {"currency", "amount", "ref_currency_amount"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify Wallet currency conversion outputs by comparing source and "
            "converted CSV files with matching names."
        )
    )
    parser.add_argument(
        "--records-dir",
        type=Path,
        default=DEFAULT_RECORDS_DIR,
        help="Directory containing the original yearly Wallet export CSV files.",
    )
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help="Directory containing the original CSV files.",
    )
    parser.add_argument(
        "--converted-dir",
        type=Path,
        default=DEFAULT_CONVERTED_DIR,
        help="Directory containing the converted CSV files.",
    )
    parser.add_argument(
        "--source-currency",
        default=DEFAULT_SOURCE_CURRENCY,
        help="Currency code converted from.",
    )
    parser.add_argument(
        "--target-currency",
        default=DEFAULT_TARGET_CURRENCY,
        help="Currency code converted to.",
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
        help="Number of decimal places expected in converted amounts.",
    )
    parser.add_argument(
        "--keep-ref-amounts",
        action="store_true",
        help=(
            "Expect ref_currency_amount to stay unchanged for rows already in the "
            "target currency."
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


def validate_headers(fieldnames: list[str] | None, source: Path) -> list[str]:
    if not fieldnames:
        raise ValueError(f"{source} has no header row")
    actual = list(fieldnames)
    missing = REQUIRED_HEADERS.difference(actual)
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ValueError(f"{source} is missing required headers: {missing_list}")
    return actual


def list_csv_files(directory: Path) -> dict[str, Path]:
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")
    if not directory.is_dir():
        raise ValueError(f"Path is not a directory: {directory}")
    files = {
        path.name: path
        for path in sorted(directory.iterdir())
        if path.is_file() and path.suffix.lower() == ".csv"
    }
    if not files:
        raise FileNotFoundError(f"No CSV files found in {directory}")
    return files


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        headers = validate_headers(reader.fieldnames, path)
        return headers, list(reader)


def summarize_rows(
    rows: list[dict[str, str]],
    rate: Decimal,
    source_currency: str,
    target_currency: str,
    scale: int,
) -> dict[str, Decimal | int]:
    row_count = len(rows)
    amount_total = Decimal("0")
    expected_converted_total = Decimal("0")
    source_currency_rows = 0
    target_currency_rows = 0
    other_currency_rows = 0

    for row in rows:
        amount = parse_decimal(row["amount"]) or Decimal("0")
        amount_total += amount

        currency = (row.get("currency") or "").strip()
        if currency == source_currency:
            expected_converted_total += Decimal(
                convert_amount(row["amount"], rate, scale) or "0"
            )
            source_currency_rows += 1
        else:
            expected_converted_total += amount
            if currency == target_currency:
                target_currency_rows += 1
            else:
                other_currency_rows += 1

    return {
        "rows": row_count,
        "amount_total": amount_total,
        "expected_converted_total": expected_converted_total,
        "source_currency_rows": source_currency_rows,
        "target_currency_rows": target_currency_rows,
        "other_currency_rows": other_currency_rows,
    }


def summarize_files(
    files: dict[str, Path],
    rate: Decimal,
    source_currency: str,
    target_currency: str,
    scale: int,
) -> dict[str, Decimal | int]:
    total_rows = 0
    total_amount = Decimal("0")
    total_expected_converted = Decimal("0")
    total_source_currency_rows = 0
    total_target_currency_rows = 0
    total_other_currency_rows = 0

    for path in files.values():
        _, rows = read_rows(path)
        summary = summarize_rows(
            rows=rows,
            rate=rate,
            source_currency=source_currency,
            target_currency=target_currency,
            scale=scale,
        )
        total_rows += int(summary["rows"])
        total_amount += Decimal(summary["amount_total"])
        total_expected_converted += Decimal(summary["expected_converted_total"])
        total_source_currency_rows += int(summary["source_currency_rows"])
        total_target_currency_rows += int(summary["target_currency_rows"])
        total_other_currency_rows += int(summary["other_currency_rows"])

    return {
        "rows": total_rows,
        "amount_total": total_amount,
        "expected_converted_total": total_expected_converted,
        "source_currency_rows": total_source_currency_rows,
        "target_currency_rows": total_target_currency_rows,
        "other_currency_rows": total_other_currency_rows,
    }


def verify_pair(
    source_path: Path,
    converted_path: Path,
    rate: Decimal,
    source_currency: str,
    target_currency: str,
    scale: int,
    keep_ref_amounts: bool,
) -> tuple[bool, list[str], dict[str, str]]:
    source_headers, source_rows = read_rows(source_path)
    converted_headers, converted_rows = read_rows(converted_path)
    issues: list[str] = []

    if source_headers != converted_headers:
        issues.append("header mismatch")
    if len(source_rows) != len(converted_rows):
        issues.append(
            f"row count mismatch: source={len(source_rows)} converted={len(converted_rows)}"
        )

    source_amount_total = Decimal("0")
    expected_amount_total = Decimal("0")
    actual_amount_total = Decimal("0")
    converted_row_count = 0
    normalized_row_count = 0

    for index, source_row in enumerate(source_rows):
        if index >= len(converted_rows):
            break

        converted_row = converted_rows[index]
        source_amount = parse_decimal(source_row["amount"]) or Decimal("0")
        converted_amount = parse_decimal(converted_row["amount"]) or Decimal("0")
        source_amount_total += source_amount
        actual_amount_total += converted_amount

        source_row_currency = (source_row.get("currency") or "").strip()
        converted_row_currency = (converted_row.get("currency") or "").strip()

        if source_row_currency == source_currency:
            expected_amount = Decimal(convert_amount(source_row["amount"], rate, scale) or "0")
            expected_ref_amount = Decimal(
                convert_amount(source_row["ref_currency_amount"], rate, scale) or "0"
            )
            expected_amount_total += expected_amount
            converted_row_count += 1

            if converted_row_currency != target_currency:
                issues.append(
                    f"row {index + 2}: currency expected {target_currency}, got {converted_row_currency}"
                )
            if converted_row["amount"] != format_decimal(expected_amount, scale):
                issues.append(f"row {index + 2}: amount mismatch")
            if converted_row["ref_currency_amount"] != format_decimal(expected_ref_amount, scale):
                issues.append(f"row {index + 2}: ref_currency_amount mismatch")
        else:
            expected_amount_total += source_amount
            if source_row_currency == target_currency:
                normalized_row_count += 1
                expected_ref = (
                    source_row["ref_currency_amount"]
                    if keep_ref_amounts
                    else normalize_amount(source_row["amount"], scale)
                )
                if converted_row["ref_currency_amount"] != expected_ref:
                    issues.append(f"row {index + 2}: target ref_currency_amount mismatch")
            if converted_row["amount"] != source_row["amount"]:
                issues.append(f"row {index + 2}: non-converted amount changed")
            if converted_row_currency != source_row_currency:
                issues.append(f"row {index + 2}: unexpected currency change")

    summary = {
        "rows": str(len(source_rows)),
        "converted_rows": str(converted_row_count),
        "normalized_rows": str(normalized_row_count),
        "source_amount_total": format_decimal(source_amount_total, scale),
        "expected_amount_total": format_decimal(expected_amount_total, scale),
        "actual_amount_total": format_decimal(actual_amount_total, scale),
    }
    return not issues, issues, summary


def main() -> int:
    args = parse_args()
    if args.rate <= 0:
        raise ValueError("rate must be greater than zero")

    records_files = list_csv_files(args.records_dir)
    source_files = list_csv_files(args.source_dir)
    converted_files = list_csv_files(args.converted_dir)

    missing_outputs = sorted(set(source_files) - set(converted_files))
    extra_outputs = sorted(set(converted_files) - set(source_files))

    if missing_outputs:
        print("Missing converted files:")
        for name in missing_outputs:
            print(f"  {name}")
    if extra_outputs:
        print("Extra converted files with no source match:")
        for name in extra_outputs:
            print(f"  {name}")

    checked = 0
    failures = 0

    for name in sorted(set(source_files).intersection(converted_files)):
        passed, issues, summary = verify_pair(
            source_path=source_files[name],
            converted_path=converted_files[name],
            rate=args.rate,
            source_currency=args.source_currency,
            target_currency=args.target_currency,
            scale=args.scale,
            keep_ref_amounts=args.keep_ref_amounts,
        )
        checked += 1
        status = "PASS" if passed else "FAIL"
        print(
            f"{status} {name} | rows={summary['rows']} | "
            f"converted={summary['converted_rows']} | "
            f"normalized={summary['normalized_rows']} | "
            f"source_total={summary['source_amount_total']} | "
            f"expected_total={summary['expected_amount_total']} | "
            f"actual_total={summary['actual_amount_total']}"
        )
        if issues:
            failures += 1
            for issue in issues[:10]:
                print(f"  - {issue}")
            if len(issues) > 10:
                print(f"  - ... {len(issues) - 10} more issues")

    print("-----------------------")

    records_summary = summarize_files(
        files=records_files,
        rate=args.rate,
        source_currency=args.source_currency,
        target_currency=args.target_currency,
        scale=args.scale,
    )
    source_summary = summarize_files(
        files=source_files,
        rate=args.rate,
        source_currency=args.source_currency,
        target_currency=args.target_currency,
        scale=args.scale,
    )
    converted_summary = summarize_files(
        files=converted_files,
        rate=args.rate,
        source_currency=args.source_currency,
        target_currency=args.target_currency,
        scale=args.scale,
    )

    aggregate_failures = 0

    records_vs_source_pass = (
        int(records_summary["rows"]) == int(source_summary["rows"])
        and Decimal(records_summary["amount_total"])
        == Decimal(source_summary["amount_total"])
    )
    records_vs_converted_pass = (
        int(records_summary["rows"]) == int(converted_summary["rows"])
        and Decimal(records_summary["expected_converted_total"])
        == Decimal(converted_summary["amount_total"])
    )

    if not records_vs_source_pass:
        aggregate_failures += 1
    if not records_vs_converted_pass:
        aggregate_failures += 1

    print(
        "WALLET RECORDS | "
        f"files={len(records_files)} | "
        f"rows={records_summary['rows']} | "
        f"amount_total={format_decimal(Decimal(records_summary['amount_total']), args.scale)} | "
        f"expected_converted_total={format_decimal(Decimal(records_summary['expected_converted_total']), args.scale)} | "
        f"other_currency_rows={records_summary['other_currency_rows']}"
    )
    print(
        "ACCOUNTS DATA | "
        f"files={len(source_files)} | "
        f"rows={source_summary['rows']} | "
        f"amount_total={format_decimal(Decimal(source_summary['amount_total']), args.scale)} | "
        f"source_currency_rows={source_summary['source_currency_rows']} | "
        f"target_currency_rows={source_summary['target_currency_rows']} | "
        f"other_currency_rows={source_summary['other_currency_rows']} | "
        f"{'PASS' if records_vs_source_pass else 'FAIL'} vs Wallet Records"
    )
    print(
        "ACCOUNTS DATA TARGET | "
        f"files={len(converted_files)} | "
        f"rows={converted_summary['rows']} | "
        f"amount_total={format_decimal(Decimal(converted_summary['amount_total']), args.scale)} | "
        f"target_currency_rows={converted_summary['target_currency_rows']} | "
        f"other_currency_rows={converted_summary['other_currency_rows']} | "
        f"{'PASS' if records_vs_converted_pass else 'FAIL'} vs expected converted Wallet Records total"
    )
    if not records_vs_source_pass:
        print(
            "  - Accounts Data does not match Wallet Records aggregate rows or total amount"
        )
    if not records_vs_converted_pass:
        print(
            "  - Accounts Data EUR does not match the expected converted aggregate total from Wallet Records"
        )

    print(
        f"Checked {checked} matching files | "
        f"failures={failures} | "
        f"aggregate_failures={aggregate_failures} | "
        f"missing_outputs={len(missing_outputs)} | "
        f"extra_outputs={len(extra_outputs)}"
    )
    return 1 if failures or aggregate_failures or missing_outputs else 0


if __name__ == "__main__":
    raise SystemExit(main())
