#!/usr/bin/env python3
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from wallet_tabular import discover_directory_inputs, read_rows


DEFAULT_RECORDS_DIR = Path("Wallet Records")
DEFAULT_SOURCE_DIR = Path("Account Data")
DEFAULT_CONVERTED_DIR = Path("Account Data EUR")
DEFAULT_SOURCE_CURRENCY = "BGN"
DEFAULT_TARGET_CURRENCY = "EUR"
DEFAULT_RATE = Decimal("1.95583")
RECORD_HEADERS = {"currency", "amount", "ref_currency_amount", "type"}
ACCOUNT_HEADERS = {"currency", "income_amount", "expense_amount", "ref_currency_amount", "type"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify Wallet currency conversion outputs by comparing split source "
            "files, converted files, and aggregate totals from the original Wallet "
            "records."
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
        help="Directory containing the split per-account CSV files.",
    )
    parser.add_argument(
        "--converted-dir",
        type=Path,
        default=DEFAULT_CONVERTED_DIR,
        help="Directory containing the converted per-account CSV files.",
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


def list_supported_files(directory: Path) -> tuple[dict[str, Path], list[str]]:
    paths, skipped_messages = discover_directory_inputs(directory)
    return {path.stem: path for path in paths}, skipped_messages


def record_income_expense(row: dict[str, str]) -> tuple[str, str]:
    amount = (row.get("amount") or "").strip()
    row_type = (row.get("type") or "").strip().lower()
    if row_type == "income":
        return amount, ""
    if row_type == "expense":
        return "", amount
    return "", ""


def summarize_record_rows(
    rows: list[dict[str, str]],
    rate: Decimal,
    source_currency: str,
    target_currency: str,
    scale: int,
) -> dict[str, Decimal | int]:
    row_count = len(rows)
    income_total = Decimal("0")
    expense_total = Decimal("0")
    expected_converted_income_total = Decimal("0")
    expected_converted_expense_total = Decimal("0")
    source_currency_rows = 0
    target_currency_rows = 0
    other_currency_rows = 0

    for row in rows:
        income_text, expense_text = record_income_expense(row)
        income = parse_decimal(income_text) or Decimal("0")
        expense = parse_decimal(expense_text) or Decimal("0")
        income_total += income
        expense_total += expense

        currency = (row.get("currency") or "").strip()
        if currency == source_currency:
            expected_converted_income_total += parse_decimal(
                convert_amount(income_text, rate, scale)
            ) or Decimal("0")
            expected_converted_expense_total += parse_decimal(
                convert_amount(expense_text, rate, scale)
            ) or Decimal("0")
            source_currency_rows += 1
        else:
            expected_converted_income_total += income
            expected_converted_expense_total += expense
            if currency == target_currency:
                target_currency_rows += 1
            else:
                other_currency_rows += 1

    return {
        "rows": row_count,
        "income_total": income_total,
        "expense_total": expense_total,
        "expected_converted_income_total": expected_converted_income_total,
        "expected_converted_expense_total": expected_converted_expense_total,
        "source_currency_rows": source_currency_rows,
        "target_currency_rows": target_currency_rows,
        "other_currency_rows": other_currency_rows,
    }


def summarize_account_rows(
    rows: list[dict[str, str]],
    rate: Decimal,
    source_currency: str,
    target_currency: str,
    scale: int,
) -> dict[str, Decimal | int]:
    row_count = len(rows)
    income_total = Decimal("0")
    expense_total = Decimal("0")
    expected_converted_income_total = Decimal("0")
    expected_converted_expense_total = Decimal("0")
    source_currency_rows = 0
    target_currency_rows = 0
    other_currency_rows = 0

    for row in rows:
        income = parse_decimal(row.get("income_amount", "") or "") or Decimal("0")
        expense = parse_decimal(row.get("expense_amount", "") or "") or Decimal("0")
        income_total += income
        expense_total += expense

        currency = (row.get("currency") or "").strip()
        if currency == source_currency:
            expected_converted_income_total += parse_decimal(
                convert_amount(row.get("income_amount", "") or "", rate, scale)
            ) or Decimal("0")
            expected_converted_expense_total += parse_decimal(
                convert_amount(row.get("expense_amount", "") or "", rate, scale)
            ) or Decimal("0")
            source_currency_rows += 1
        else:
            expected_converted_income_total += income
            expected_converted_expense_total += expense
            if currency == target_currency:
                target_currency_rows += 1
            else:
                other_currency_rows += 1

    return {
        "rows": row_count,
        "income_total": income_total,
        "expense_total": expense_total,
        "expected_converted_income_total": expected_converted_income_total,
        "expected_converted_expense_total": expected_converted_expense_total,
        "source_currency_rows": source_currency_rows,
        "target_currency_rows": target_currency_rows,
        "other_currency_rows": other_currency_rows,
    }


def summarize_files(
    files: dict[str, Path],
    required_headers: set[str],
    rate: Decimal,
    source_currency: str,
    target_currency: str,
    scale: int,
) -> dict[str, Decimal | int]:
    total_rows = 0
    total_income = Decimal("0")
    total_expense = Decimal("0")
    total_expected_income = Decimal("0")
    total_expected_expense = Decimal("0")
    total_source_currency_rows = 0
    total_target_currency_rows = 0
    total_other_currency_rows = 0

    for path in files.values():
        _, rows = read_rows(path, required_headers)
        summary = (
            summarize_record_rows(rows, rate, source_currency, target_currency, scale)
            if required_headers == RECORD_HEADERS
            else summarize_account_rows(rows, rate, source_currency, target_currency, scale)
        )
        total_rows += int(summary["rows"])
        total_income += Decimal(summary["income_total"])
        total_expense += Decimal(summary["expense_total"])
        total_expected_income += Decimal(summary["expected_converted_income_total"])
        total_expected_expense += Decimal(summary["expected_converted_expense_total"])
        total_source_currency_rows += int(summary["source_currency_rows"])
        total_target_currency_rows += int(summary["target_currency_rows"])
        total_other_currency_rows += int(summary["other_currency_rows"])

    return {
        "rows": total_rows,
        "income_total": total_income,
        "expense_total": total_expense,
        "expected_converted_income_total": total_expected_income,
        "expected_converted_expense_total": total_expected_expense,
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
    source_headers, source_rows = read_rows(source_path, ACCOUNT_HEADERS)
    converted_headers, converted_rows = read_rows(converted_path, ACCOUNT_HEADERS)
    issues: list[str] = []

    if source_headers != converted_headers:
        issues.append("header mismatch")
    if len(source_rows) != len(converted_rows):
        issues.append(
            f"row count mismatch: source={len(source_rows)} converted={len(converted_rows)}"
        )

    source_income_total = Decimal("0")
    source_expense_total = Decimal("0")
    expected_income_total = Decimal("0")
    expected_expense_total = Decimal("0")
    actual_income_total = Decimal("0")
    actual_expense_total = Decimal("0")
    converted_row_count = 0
    normalized_row_count = 0

    for index, source_row in enumerate(source_rows):
        if index >= len(converted_rows):
            break

        converted_row = converted_rows[index]

        source_income = parse_decimal(source_row.get("income_amount", "") or "") or Decimal("0")
        source_expense = parse_decimal(source_row.get("expense_amount", "") or "") or Decimal("0")
        converted_income = parse_decimal(converted_row.get("income_amount", "") or "") or Decimal("0")
        converted_expense = parse_decimal(converted_row.get("expense_amount", "") or "") or Decimal("0")

        source_income_total += source_income
        source_expense_total += source_expense
        actual_income_total += converted_income
        actual_expense_total += converted_expense

        source_row_currency = (source_row.get("currency") or "").strip()
        converted_row_currency = (converted_row.get("currency") or "").strip()

        if source_row_currency == source_currency:
            expected_income_text = convert_amount(
                source_row.get("income_amount", "") or "", rate, scale
            )
            expected_expense_text = convert_amount(
                source_row.get("expense_amount", "") or "", rate, scale
            )
            expected_ref_text = convert_amount(
                source_row.get("ref_currency_amount", "") or "", rate, scale
            )
            expected_income_total += parse_decimal(expected_income_text) or Decimal("0")
            expected_expense_total += parse_decimal(expected_expense_text) or Decimal("0")
            converted_row_count += 1

            if converted_row_currency != target_currency:
                issues.append(
                    f"row {index + 2}: currency expected {target_currency}, got {converted_row_currency}"
                )
            if converted_row.get("income_amount", "") != expected_income_text:
                issues.append(f"row {index + 2}: income_amount mismatch")
            if converted_row.get("expense_amount", "") != expected_expense_text:
                issues.append(f"row {index + 2}: expense_amount mismatch")
            if converted_row.get("ref_currency_amount", "") != expected_ref_text:
                issues.append(f"row {index + 2}: ref_currency_amount mismatch")
        else:
            expected_income_total += source_income
            expected_expense_total += source_expense
            expected_income_text = source_row.get("income_amount", "") or ""
            expected_expense_text = source_row.get("expense_amount", "") or ""
            if source_row_currency == target_currency:
                normalized_row_count += 1
                if expected_income_text:
                    expected_income_text = normalize_amount(expected_income_text, scale)
                if expected_expense_text:
                    expected_expense_text = normalize_amount(expected_expense_text, scale)
                expected_ref_source = (
                    expected_income_text
                    or expected_expense_text
                    or (source_row.get("ref_currency_amount", "") or "")
                )
                expected_ref_text = (
                    source_row.get("ref_currency_amount", "") or ""
                    if keep_ref_amounts
                    else normalize_amount(expected_ref_source, scale)
                )
            else:
                expected_ref_text = source_row.get("ref_currency_amount", "") or ""

            if converted_row.get("income_amount", "") != expected_income_text:
                issues.append(f"row {index + 2}: non-converted income_amount changed")
            if converted_row.get("expense_amount", "") != expected_expense_text:
                issues.append(f"row {index + 2}: non-converted expense_amount changed")
            if converted_row.get("ref_currency_amount", "") != expected_ref_text:
                issues.append(f"row {index + 2}: target ref_currency_amount mismatch")
            if converted_row_currency != source_row_currency:
                issues.append(f"row {index + 2}: unexpected currency change")

    summary = {
        "rows": str(len(source_rows)),
        "converted_rows": str(converted_row_count),
        "normalized_rows": str(normalized_row_count),
        "source_income_total": format_decimal(source_income_total, scale),
        "source_expense_total": format_decimal(source_expense_total, scale),
        "expected_income_total": format_decimal(expected_income_total, scale),
        "expected_expense_total": format_decimal(expected_expense_total, scale),
        "actual_income_total": format_decimal(actual_income_total, scale),
        "actual_expense_total": format_decimal(actual_expense_total, scale),
    }
    return not issues, issues, summary


def main() -> int:
    args = parse_args()
    if args.rate <= 0:
        raise ValueError("rate must be greater than zero")

    records_files, record_skips = list_supported_files(args.records_dir)
    source_files, source_skips = list_supported_files(args.source_dir)
    converted_files, converted_skips = list_supported_files(args.converted_dir)
    for message in record_skips + source_skips + converted_skips:
        print(message)

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
            f"{status} {source_files[name].name} -> {converted_files[name].name} | rows={summary['rows']} | "
            f"converted={summary['converted_rows']} | "
            f"normalized={summary['normalized_rows']} | "
            f"source_income={summary['source_income_total']} | "
            f"source_expense={summary['source_expense_total']} | "
            f"expected_income={summary['expected_income_total']} | "
            f"expected_expense={summary['expected_expense_total']} | "
            f"actual_income={summary['actual_income_total']} | "
            f"actual_expense={summary['actual_expense_total']}"
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
        required_headers=RECORD_HEADERS,
        rate=args.rate,
        source_currency=args.source_currency,
        target_currency=args.target_currency,
        scale=args.scale,
    )
    source_summary = summarize_files(
        files=source_files,
        required_headers=ACCOUNT_HEADERS,
        rate=args.rate,
        source_currency=args.source_currency,
        target_currency=args.target_currency,
        scale=args.scale,
    )
    converted_summary = summarize_files(
        files=converted_files,
        required_headers=ACCOUNT_HEADERS,
        rate=args.rate,
        source_currency=args.source_currency,
        target_currency=args.target_currency,
        scale=args.scale,
    )

    aggregate_failures = 0

    records_vs_source_pass = (
        int(records_summary["rows"]) == int(source_summary["rows"])
        and Decimal(records_summary["income_total"]) == Decimal(source_summary["income_total"])
        and Decimal(records_summary["expense_total"]) == Decimal(source_summary["expense_total"])
    )
    records_vs_converted_pass = (
        int(records_summary["rows"]) == int(converted_summary["rows"])
        and Decimal(records_summary["expected_converted_income_total"])
        == Decimal(converted_summary["income_total"])
        and Decimal(records_summary["expected_converted_expense_total"])
        == Decimal(converted_summary["expense_total"])
    )

    if not records_vs_source_pass:
        aggregate_failures += 1
    if not records_vs_converted_pass:
        aggregate_failures += 1

    print(
        "WALLET RECORDS | "
        f"files={len(records_files)} | "
        f"rows={records_summary['rows']} | "
        f"income_total={format_decimal(Decimal(records_summary['income_total']), args.scale)} | "
        f"expense_total={format_decimal(Decimal(records_summary['expense_total']), args.scale)} | "
        f"expected_converted_income={format_decimal(Decimal(records_summary['expected_converted_income_total']), args.scale)} | "
        f"expected_converted_expense={format_decimal(Decimal(records_summary['expected_converted_expense_total']), args.scale)} | "
        f"other_currency_rows={records_summary['other_currency_rows']}"
    )
    print(
        "ACCOUNTS DATA | "
        f"files={len(source_files)} | "
        f"rows={source_summary['rows']} | "
        f"income_total={format_decimal(Decimal(source_summary['income_total']), args.scale)} | "
        f"expense_total={format_decimal(Decimal(source_summary['expense_total']), args.scale)} | "
        f"source_currency_rows={source_summary['source_currency_rows']} | "
        f"target_currency_rows={source_summary['target_currency_rows']} | "
        f"other_currency_rows={source_summary['other_currency_rows']} | "
        f"{'PASS' if records_vs_source_pass else 'FAIL'} vs Wallet Records"
    )
    print(
        "ACCOUNTS DATA TARGET | "
        f"files={len(converted_files)} | "
        f"rows={converted_summary['rows']} | "
        f"income_total={format_decimal(Decimal(converted_summary['income_total']), args.scale)} | "
        f"expense_total={format_decimal(Decimal(converted_summary['expense_total']), args.scale)} | "
        f"target_currency_rows={converted_summary['target_currency_rows']} | "
        f"other_currency_rows={converted_summary['other_currency_rows']} | "
        f"{'PASS' if records_vs_converted_pass else 'FAIL'} vs expected converted Wallet Records totals"
    )
    if not records_vs_source_pass:
        print(
            "  - Accounts Data does not match Wallet Records aggregate rows or income/expense totals"
        )
    if not records_vs_converted_pass:
        print(
            "  - Accounts Data EUR does not match the expected converted aggregate income/expense totals from Wallet Records"
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
