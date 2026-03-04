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
- supporting both `.csv` and `.xlsx` Wallet exports as inputs throughout the pipeline
- splitting the original `amount` into `income_amount` and `expense_amount` so Wallet import can map incomes and expenses correctly
- chunking large files so they fit Wallet's import recommendation
- converting values from the old currency to the new currency using the fixed rate, between the old and the new currency
- highlighting records that need manual review before import

The main goal is to make the export-delete-recreate-import workflow safer, repeatable, and easier to validate before you re-import data into Wallet.

Expected folder layout:
- `scripts`: the Python scripts and this README
- `Wallet Records`: original exported Wallet CSV files
- `Account Data`: generated per-account CSV files
- `Account Data EUR`: generated converted CSV files ready for import

In your current workspace, the scripts live directly in the same directory as these folders.

The scripts are designed to:
- read existing Wallet `.csv` or `.xlsx` exports without modifying them
- split yearly exports into per-account CSV files
- convert amounts from one currency to another into a separate output folder
- verify that the converted files match the expected fixed-rate conversion

All scripts expect Wallet-style tabular exports with these headers:

`account;category;currency;amount;ref_currency_amount;type;payment_type;note;date;transfer;payee;labels`

## Files

### `split_wallet_records_by_account.py`

Reads the Wallet export files and creates one CSV per account in a target folder.

What it does:
- reads all supported files (`.csv` and `.xlsx`) from `Wallet Records` by default, regardless of filename
- if both `.csv` and `.xlsx` exist with the same base name, the `.csv` file is used and the `.xlsx` file is skipped to avoid duplicate imports
- merges rows from all years by the `account` column
- transforms each row into import-friendly amount columns:
  - `income_amount` when `type` is `Income`
  - `expense_amount` when `type` is `Expense`
- optionally sorts rows by `date`
- splits large account files (1,000+ records) into `part1`, `part2`, and so on, cause Wallet’s import guidance recommends up to 1,000 rows per import file

Default input folder:
- `Wallet Records`

Default output folder:
- `Account Data`

Example:

```bash
python3 ./split_wallet_records_by_account.py --sort-by-date
```

Useful options:
- `--output-dir "Some Folder"`: choose a different output folder
- `--max-rows-per-file 500`: set the maximum rows per generated file
- `--max-rows-per-file 0`: disable chunking
- `--output-format csv`: generate CSV files (default)
- `--output-format xlsx`: generate Excel files
- `--output-format match-input`: reuse the shared input format when all selected inputs use the same extension

You can also pass explicit input files:

```bash
python3 ./split_wallet_records_by_account.py \
  "/Wallet Records/wallet_records_2022.xlsx" \
  "/Wallet Records/wallet_records_2023.csv" \
  --sort-by-date
```

### `convert_wallet_currency.py`

Reads Wallet `.csv` or `.xlsx` files from a source folder and writes converted CSV copies into a separate folder.

What it does:
- reads all supported files (`.csv` and `.xlsx`) from a source directory, or a single supported file
- converts rows where `currency` matches the source currency
- converts both `income_amount` / `expense_amount` and `ref_currency_amount`
- changes `currency` to the target currency for converted rows
- normalizes `ref_currency_amount` for rows already in the target currency unless `--keep-ref-amounts` is used
- flags rows whose `currency` is neither the source nor target currency so you can review them manually
- preserves the original filenames

Default source folder:
- `Account Data`

Default output folder:
- `Account Data <TARGET_CURRENCY>`

Example:

```bash
python3 ./convert_wallet_currency.py
```

Example with explicit settings:

```bash
python3 ./convert_wallet_currency.py \
  "./Account Data" \
  --source-currency BGN \
  --target-currency EUR \
  --rate 1.95583
```

Useful options:
- `--output-dir "Account Data EUR"`: choose a different output folder
- `--source-currency BGN`: old currency
- `--target-currency EUR`: new currency
- `--rate 1.95583`: fixed conversion rate
- `--scale 2`: number of decimal places
- `--keep-ref-amounts`: do not normalize existing target-currency `ref_currency_amount`
- `--dry-run`: print what would be created or overwritten without writing files
- `--output-format csv`: generate CSV files (default)
- `--output-format xlsx`: generate Excel files
- `--output-format match-input`: preserve each source file's format

Dry-run example:

```bash
python3 ./convert_wallet_currency.py --dry-run
```

Excel output example:

```bash
python3 ./convert_wallet_currency.py --output-format xlsx
```

### `verify_wallet_currency_conversion.py`

Compares the source account files and the converted account files to confirm the conversion output is consistent.

What it checks:
- source and converted files exist with matching names
- headers match
- row counts match
- converted rows changed as expected using the fixed rate
- non-converted rows stayed unchanged where appropriate
- per-file `income_amount` and `expense_amount` match the expected converted values
- aggregate `Wallet Records` totals match `Account Data`
- aggregate expected converted totals from `Wallet Records` match `Account Data EUR`

Default folders:
- source: `Account Data`
- converted: `Account Data EUR`

Example:

```bash
python3 ./verify_wallet_currency_conversion.py
```

Example with explicit settings:

```bash
python3 ./verify_wallet_currency_conversion.py \
  --source-dir "./Account Data" \
  --converted-dir "./Account Data EUR" \
  --source-currency BGN \
  --target-currency EUR \
  --rate 1.95583
```

## Recommended Step-by-Step Usage

### 1. Keep the original exports as the source of truth

Your original exports should stay untouched in:
- `Wallet Records/*.csv`
- `Wallet Records/*.xlsx`

### 2. Split the yearly exports into per-account files

Run:

```bash
python3 ./split_wallet_records_by_account.py --sort-by-date
```

This creates or overwrites files in:
- `Account Data`

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
- `Account Data EUR`

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
- because Wallet may treat a generic `amount` column as expenses by default, this project generates separate `income_amount` and `expense_amount` columns for safer mapping

Practical import sequence after conversion:
- create or recreate the destination accounts in Wallet with the new main currency
- open the Wallet Web App and start an import
- choose the matching account
- import every file from `Account Data EUR` for that account
- if an account has multiple parts, import all parts into the same account in order
- map `income_amount` to the import income field and `expense_amount` to the import expense field
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
- When both `.csv` and `.xlsx` exist for the same export base name in one folder, the scripts prefer `.csv` and skip the `.xlsx` duplicate.
- If you want Excel output, use `--output-format xlsx`. If you do not pass an output format, the default is CSV.
- Rows with currencies other than the selected source and target are left unchanged and logged for manual review.
- If you use a different currency pair, pass `--source-currency`, `--target-currency`, and `--rate` consistently to both the converter and verifier.
