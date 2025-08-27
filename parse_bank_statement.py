import pdfplumber
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

# Matches either ``MM/DD/YY`` or ``MM/DD`` followed by a description and amount.
# Amounts may contain a space after ``$`` and may use a trailing ``-`` to denote
# a negative value.
pattern = re.compile(
    r"^(?:(\d{2}/\d{2}/\d{2})|(\d{2}/\d{2}))\*?\s+(.*?)\s+(-?\$?\s?\d[\d,]*\.\d{2}-?)$"
)

def parse_pdf(pdf_source):
    """Parse a bank statement PDF.

    ``pdf_source`` may be a file path or a file-like object.  When a file-like
    object is provided, the file name (if available) is used to infer the
    statement year.
    """

    rows = []
    year_hint = None

    # Try to pull a year from the file name as a fallback. This helps when the
    # statement omits the year on individual transaction lines.
    file_name = None
    if isinstance(pdf_source, (str, Path)):
        file_name = str(pdf_source)
    elif hasattr(pdf_source, "name"):
        file_name = pdf_source.name
    if file_name:
        m = re.search(r"(20\d{2})", file_name)
        if m:
            year_hint = int(m.group(1))

    if hasattr(pdf_source, "seek"):
        pdf_source.seek(0)

    with pdfplumber.open(pdf_source) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            lines = text.split("\n")
            current = None
            current_year = year_hint

            for line in lines:
                match = pattern.search(line)
                if match:
                    if current:
                        rows.append(current)

                    date_full, date_short, desc, amt_str = match.groups()

                    if date_full:
                        date_dt = datetime.strptime(date_full, "%m/%d/%y")
                        current_year = date_dt.year
                    else:
                        # Use the most recent year we have seen.  Fallback to
                        # ``year_hint`` or the current year if necessary.
                        if current_year is None:
                            current_year = datetime.today().year
                        date_dt = datetime.strptime(
                            f"{date_short}/{str(current_year)[-2:]}", "%m/%d/%y"
                        )

                    date_fmt = f"{date_dt.month}/{date_dt.day}/{date_dt.year}"

                    amt_clean = (
                        amt_str.replace("$", "")
                        .replace(",", "")
                        .replace("+", "")
                        .replace("-", "")
                        .strip()
                    )
                    amount = float(amt_clean)

                    is_withdrawal = amt_str.strip().startswith("-") or amt_str.strip().endswith("-")
                    if is_withdrawal:
                        amount = -amount

                    current = {
                        "Date": date_fmt,
                        "Amount": amount,
                        "Memo": desc.strip(),
                    }
                else:
                    if current:
                        current["Memo"] += " " + line.strip()

            if current:
                rows.append(current)
                current = None
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
