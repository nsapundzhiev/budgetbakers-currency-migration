# Wallet CSV Migration Helpers

This directory contains three scripts for preparing BudgetBakers Wallet exports for a main-currency migration via import functionality.

## Why This Project Exists

This project exists because Wallet currently does not support changing the main or base currency while keeping your existing data.

According to BudgetBakers' support article, the current supported path is:
- export your data
- delete your existing data
- choose the new main currency
- continue using the app, but without your old data...

That limitation is described here:
- [Change the main currency](https://support.budgetbakers.com/hc/en-us/articles/9663226850706-Change-the-main-currency)

This repository helps bridge that gap by:
- restructuring exported Wallet CSV files into import-friendly per-account files
- chunking large files so they fit Wallet's import recommendation
- converting values from the old currency to the new currency using the fixed rate, between the old and the new currency
- highlighting records that need manual review before import

The main goal is to make the export-delete-recreate-import workflow safer, repeatable, and easier to validate before you re-import data into Wallet.

Expected folder layout:
- `scripts`: the Python scripts and this README
- `Wallet Records`: original exported Wallet CSV files
- `Accounts Data`: generated per-account CSV files
- `Accounts Data EUR`: generated converted CSV files ready for import

In your current workspace, the scripts live directly in the same directory as these folders.

The scripts are designed to:
- read existing Wallet CSV exports without modifying them
- split yearly exports into per-account CSV files
- convert amounts from one currency to another into a separate output folder
- verify that the converted files match the expected fixed-rate conversion

All scripts expect Wallet-style CSV files with semicolon-separated columns and these headers:

`account;category;currency;amount;ref_currency_amount;type;payment_type;note;date;transfer;payee;labels`

## Files

### `split_wallet_records_by_account.py`

Reads the yearly Wallet CSV exports and creates one CSV per account in a target folder.

What it does:
- reads, e.g. `wallet_records_2022.csv`, `wallet_records_2023.csv`, `wallet_records_2024.csv`, and `wallet_records_2025.csv` from `Wallet Records` by default
- merges rows from all years by the `account` column
- optionally sorts rows by `date`
- splits large account files (1,000+ records) into `part1`, `part2`, and so on, cause Wallet’s import guidance recommends up to 1,000 rows per import file

Default input folder:
- `Wallet Records`

Default output folder:
- `Accounts Data`

Example:

```bash
python3 ./split_wallet_records_by_account.py --sort-by-date
```

Useful options:
- `--output-dir "Some Folder"`: choose a different output folder
- `--max-rows-per-file 1000`: set the maximum rows per generated file
- `--max-rows-per-file 0`: disable chunking

You can also pass explicit input files:

```bash
python3 ./split_wallet_records_by_account.py \
  "/Wallet Records/wallet_records_2022.csv" \
  "/Wallet Records/wallet_records_2023.csv" \
  --sort-by-date
```

### `convert_wallet_currency.py`

Reads Wallet CSV files from a source folder and writes converted copies into a separate folder.

What it does:
- reads all `.csv` files from a source directory, or a single CSV file
- converts rows where `currency` matches the source currency
- converts both `amount` and `ref_currency_amount`
- changes `currency` to the target currency for converted rows
- normalizes `ref_currency_amount` for rows already in the target currency unless `--keep-ref-amounts` is used
- flags rows whose `currency` is neither the source nor target currency so you can review them manually
- preserves the original filenames

Default source folder:
- `Accounts Data`

Default output folder:
- `Accounts Data <TARGET_CURRENCY>`

Example:

```bash
python3 ./convert_wallet_currency.py
```

Example with explicit settings:

```bash
python3 ./convert_wallet_currency.py \
  "./Accounts Data" \
  --source-currency BGN \
  --target-currency EUR \
  --rate 1.95583
```

Useful options:
- `--output-dir "Accounts Data EUR"`: choose a different output folder
- `--source-currency BGN`: old currency
- `--target-currency EUR`: new currency
- `--rate 1.95583`: fixed conversion rate
- `--scale 2`: number of decimal places
- `--keep-ref-amounts`: do not normalize existing target-currency `ref_currency_amount`
- `--dry-run`: print what would be created or overwritten without writing files

Dry-run example:

```bash
python3 ./convert_wallet_currency.py --dry-run
```

### `verify_wallet_currency_conversion.py`

Compares the source account files and the converted account files to confirm the conversion output is consistent.

What it checks:
- source and converted files exist with matching names
- headers match
- row counts match
- converted rows changed as expected using the fixed rate
- non-converted rows stayed unchanged where appropriate
- per-file total `amount` matches the expected converted total

Default folders:
- source: `Accounts Data`
- converted: `Accounts Data EUR`

Example:

```bash
python3 ./verify_wallet_currency_conversion.py
```

Example with explicit settings:

```bash
python3 ./verify_wallet_currency_conversion.py \
  --source-dir "./Accounts Data" \
  --converted-dir "./Accounts Data EUR" \
  --source-currency BGN \
  --target-currency EUR \
  --rate 1.95583
```

## Recommended Step-by-Step Usage

### 1. Keep the original exports as the source of truth

Your original exports should stay untouched in:
- `Wallet Records/wallet_records_2022.csv`
- `Wallet Records/wallet_records_2023.csv`
- `Wallet Records/wallet_records_2024.csv`
- `Wallet Records/wallet_records_2025.csv`

### 2. Split the yearly exports into per-account files

Run:

```bash
python3 ./split_wallet_records_by_account.py --sort-by-date
```

This creates or overwrites files in:
- `Accounts Data`

### 3. Preview the currency conversion without writing files

Run:

```bash
python3 ./convert_wallet_currency.py --dry-run
```

This shows:
- which files would be created or overwritten
- how many rows would be converted
- how many rows would have `ref_currency_amount` normalized
- how many rows use an unexpected third currency and need manual validation

### 4. Create the converted account files

Run:

```bash
python3 ./convert_wallet_currency.py
```

This creates or overwrites files in:
- `Accounts Data EUR`

### 5. Verify the conversion results

Run:

```bash
python3 ./verify_wallet_currency_conversion.py
```

You should get `PASS` for all matching files and a final summary with:
- `failures=0`
- `missing_outputs=0`

### 6. Import into Wallet

Operational note from the Wallet import flow:
- import into the correct destination account, one account at a time
- for chunked files such as `Cash_part1.csv` and `Cash_part2.csv`, import all parts into the same Wallet account
- create the destination accounts in the new main currency before importing

Wallet's import procedure and rules are documented here:
- [Import your transactions or files](https://support.budgetbakers.com/hc/en-us/articles/7077275632274-Import-your-transactions-or-files)

Key import details to keep in mind:
- imports are done in the Wallet Web App, not in the mobile app
- you select the destination account first, then import the file into that account
- imports are available only for General accounts
- all records in a single import file must be in one currency, and that currency must match the destination account currency
- supported file types include CSV, XLS/XLSX, and OFX
- supported delimiters include semicolon `;`, which is what Wallet exports use
- Wallet recommends a maximum of 1,000 rows per import file
- during import, you must map at least `Amount` and `Date`, and you can optionally map fields such as `Note`, `Payee`, and `Currency`

Practical import sequence after conversion:
- create or recreate the destination accounts in Wallet with the new main currency
- open the Wallet Web App and start an import
- choose the matching account
- import every file from `Accounts Data EUR` for that account
- if an account has multiple parts, import all parts into the same account in order
- review the preview carefully before confirming the import

## Typical Full Run

```bash
python3 ./split_wallet_records_by_account.py --sort-by-date
python3 ./convert_wallet_currency.py --dry-run
python3 ./convert_wallet_currency.py
python3 ./verify_wallet_currency_conversion.py
```

## Notes

- The scripts only read `.csv` files relevant to their purpose.
- The original yearly exports in `Wallet Records` are never modified.
- Generated files are overwritten if you rerun the scripts.
- Rows with currencies other than the selected source and target are left unchanged and logged for manual review.
- If you use a different currency pair, pass `--source-currency`, `--target-currency`, and `--rate` consistently to both the converter and verifier.
