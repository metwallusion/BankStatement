import csv
import re
import sys
from datetime import datetime
from pathlib import Path

import pdfplumber

# Regular expressions used to incrementally build a transaction.  ``DATE_START``
# matches the beginning of a new transaction.  ``AMOUNT_ONLY`` and
# ``AMOUNT_WITH_BALANCE`` catch lines that contain a terminal amount even when
# the description and amount are split across lines or columns.
DATE_START = re.compile(r"^(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\*?\s+(.*)$")
AMOUNT_ONLY = re.compile(r"^\s*-?\$?\s?\d[\d,]*\.\d{2}(?:\s*[⧫♦◆])?\s*$")
AMOUNT_WITH_BALANCE = re.compile(
    r"^\s*(-?\$?\s?\d[\d,]*\.\d{2})\s+[\d,]*\.\d{2}\s*$"
)
MONEY_INLINE = re.compile(r"(-?\$?\s?\d[\d,]*\.\d{2})")
MONEY_STRIPPER = re.compile(r"[^\d.\-]")

# Keywords used to infer the sign of an amount when the statement omits an
# explicit minus sign.  This list is intentionally small and easily extensible.
POSITIVE_HINTS = ("deposit", "payment", "credit", "refund")
NEGATIVE_HINTS = ("purchase", "withdrawal", "fee", "debit")

def parse_pdf(pdf_source):
    """Parse a bank statement PDF.

    ``pdf_source`` may be a file path or a file-like object.  When a file-like
    object is provided, the file name (if available) is used to infer the
    statement year.
    """

    rows: list[dict] = []
    year_hint = None

    # Try to pull a year from the file name as a fallback. This helps when the
    # statement omits the year on individual transaction lines.  First look for
    # a four-digit year; if absent, fall back to an ``MMDDYY`` pattern such as
    # ``083125`` -> ``2025``.
    file_name = None
    if isinstance(pdf_source, (str, Path)):
        file_name = str(pdf_source)
    elif hasattr(pdf_source, "name"):
        file_name = pdf_source.name
    if file_name:
        m = re.search(r"(20\d{2})", file_name)
        if m:
            year_hint = int(m.group(1))
        else:
            m = re.search(r"(\d{6})", file_name)
            if m:
                yy = int(m.group(1)[-2:])
                year_hint = 2000 + yy

    if hasattr(pdf_source, "seek"):
        pdf_source.seek(0)

    with pdfplumber.open(pdf_source) as pdf:

        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            lines = text.split("\n")
            current_tx = None
            current_year = year_hint

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                m = DATE_START.match(line)
                if m:
                    # Starting a new transaction: flush the previous one if complete.
                    if current_tx and "Amount" in current_tx:
                        rows.append(current_tx)

                    date_raw, desc_part = m.groups()

                    # Determine the transaction date, inferring the year when
                    # necessary.
                    try:
                        # ``%y`` accepts 1- or 2-digit years; ``%Y`` accepts 4 digits.
                        if date_raw.count("/") == 2:
                            last = date_raw.split("/")[-1]
                            fmt = "%m/%d/%y" if len(last) == 2 else "%m/%d/%Y"
                            date_dt = datetime.strptime(date_raw, fmt)
                            current_year = date_dt.year
                        else:
                            raise ValueError
                    except ValueError:
                        if current_year is None:
                            current_year = year_hint or datetime.today().year
                        date_dt = datetime.strptime(
                            f"{date_raw}/{current_year}", "%m/%d/%Y"
                        )

                    date_fmt = f"{date_dt.month}/{date_dt.day}/{date_dt.year}"

                    current_tx = {"Date": date_fmt, "Memo": desc_part.strip()}

                    # Some statements include the amount on the same line as the
                    # date. If so, capture it immediately but keep the transaction
                    # open to allow subsequent memo lines (e.g., categories).
                    money_match = MONEY_INLINE.search(desc_part)
                    if money_match:
                        amt_raw = money_match.group(1)
                        memo = desc_part[: money_match.start()].strip()
                        current_tx["Memo"] = memo
                        amt_clean = MONEY_STRIPPER.sub("", amt_raw).replace("-", "")
                        amount = float(amt_clean)
                        has_minus = "-" in amt_raw
                        if not has_minus:
                            memo_low = memo.lower()
                            if any(k in memo_low for k in NEGATIVE_HINTS):
                                has_minus = True
                            elif any(k in memo_low for k in POSITIVE_HINTS):
                                has_minus = False
                        if has_minus:
                            amount = -amount
                        current_tx["Amount"] = amount
                    continue

                if not current_tx:
                    # Ignore lines until a date is encountered.
                    continue

                # Check for lines that contain a terminal amount.  Some statements
                # place the amount on its own line, while others place the amount
                # adjacent to a running balance column.  ``MONEY_INLINE`` is used to
                # extract the raw numeric portion from whichever pattern matches.
                if AMOUNT_ONLY.match(line) or AMOUNT_WITH_BALANCE.match(line) or MONEY_INLINE.search(line):
                    if "Amount" in current_tx:
                        current_tx["Memo"] += " " + line.strip()
                        continue
                    money_match = MONEY_INLINE.search(line)
                    if not money_match:
                        # ``AMOUNT_ONLY`` guarantees the line is just an amount.
                        money_match = re.search(r"\S+", line)
                    amt_raw = money_match.group(0)
                    amt_clean = MONEY_STRIPPER.sub("", amt_raw).replace("-", "")
                    amount = float(amt_clean)

                    has_minus = "-" in amt_raw
                    if not has_minus:
                        memo_low = current_tx["Memo"].lower()
                        if any(k in memo_low for k in NEGATIVE_HINTS):
                            has_minus = True
                        elif any(k in memo_low for k in POSITIVE_HINTS):
                            has_minus = False

                    if has_minus:
                        amount = -amount

                    current_tx["Amount"] = amount
                    rows.append(current_tx)
                    current_tx = None
                else:
                    current_tx["Memo"] += " " + line.strip()

            if current_tx and "Amount" in current_tx:
                rows.append(current_tx)
                current_tx = None
    return rows

def write_csv(rows, out_path):
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Row #", "Date", "Amount", "Memo"])
        for i, row in enumerate(rows, 1):
            writer.writerow([
                i,
                row["Date"],
                f"{row['Amount']}",
                row["Memo"],
            ])

def main():
    if len(sys.argv) < 3:
        print("usage: python parse_bank_statement.py input.pdf output.csv")
        return
    rows = parse_pdf(sys.argv[1])
    write_csv(rows, sys.argv[2])

if __name__ == "__main__":
    main()