import pdfplumber
import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Matches either ``MM/DD/YY`` or ``MM/DD`` followed by a description and amount.
# Amounts may contain a space after ``$`` and may use a trailing ``-`` to denote
# a negative value.
pattern = re.compile(
    r"^(?:(\d{2}/\d{2}/\d{2})|(\d{2}/\d{2}))\*?\s+(.*?)\s+(-?\$?\s?\d[\d,]*\.\d{2}-?)$"
)

# Additional patterns for multi-line and tabular statements
DATE_START = re.compile(r"^(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\*?\b(.*)$")
MONEY_INLINE = re.compile(r"(-?\$?\s?\d[\d,]*\.\d{2})")
AMOUNT_ONLY = re.compile(r"^\s*-?\$?\s?\d[\d,]*\.\d{2}(?:\s*[⧫♦])?\s*$")
AMOUNT_WITH_BALANCE = re.compile(r"^\s*(-?\$?\s?\d[\d,]*\.\d{2})\s+[\d,]*\.\d{2}\s*$")
MONEY_STRIPPER = re.compile(r"[^\d.\-]")
HEADER_RE = re.compile(r"(detail|summary|payments?|closing|account|page|new\s+charges?)", re.I)
MEMO_CLEAN_RE = re.compile(r"(summary|detail|closing|account|page|new\s+charges?)", re.I)


def infer_year_from_filename(path_or_name: str) -> Optional[int]:
    """Infer year from a file name if possible."""
    if not path_or_name:
        return None
    m = re.search(r"(20\d{2})", path_or_name)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d{6})", path_or_name)
    if m:
        return 2000 + int(m.group(1)[-2:])
    return None


def normalize_date(ds: str, year_hint: Optional[int]) -> datetime:
    """Normalize a date string to a ``datetime`` object."""
    ds = ds.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(ds, fmt)
        except ValueError:
            pass
    if year_hint is None:
        year_hint = datetime.today().year
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(f"{ds}/{year_hint}", fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date: {ds}")


def clean_amount_str(s: str) -> float:
    """Extract and normalize a money string to a float."""
    m = MONEY_INLINE.search(s)
    if not m:
        raise ValueError("No monetary value found")
    token = m.group(1)
    negative = "-" in token
    cleaned = MONEY_STRIPPER.sub("", token)
    if not cleaned:
        raise ValueError("Empty monetary value")
    amount = float(cleaned)
    return -amount if negative else amount


def guess_sign(desc: str, amount_has_minus: bool) -> int:
    """Guess sign based on description when amount lacks explicit sign."""
    if amount_has_minus:
        return -1
    desc_l = desc.lower()
    neg_kw = [
        "purchase",
        "withdrawal",
        "card",
        "fee",
        "check",
        "ach debit",
        "payment",
    ]
    pos_kw = [
        "deposit",
        "refund",
        "credit",
        "zelle from",
        "edeposit",
        "atm cash deposit",
    ]
    for kw in neg_kw:
        if kw in desc_l:
            return -1
    for kw in pos_kw:
        if kw in desc_l:
            return 1
    return -1


def parse_amount_from_line(line: str, memo_so_far: str):
    """Return (amount, leftover_memo) if line contains an amount."""
    token = None
    leftover = line
    m = AMOUNT_ONLY.match(line)
    if m:
        token = m.group(0)
        leftover = ""
    else:
        m = AMOUNT_WITH_BALANCE.match(line)
        if m:
            token = m.group(1)
            start, end = m.span(1)
            leftover = (line[:start] + line[end:]).strip()
        else:
            m = MONEY_INLINE.search(line)
            if m:
                token = m.group(1)
                start, end = m.span(1)
                leftover = (line[:start] + line[end:]).strip()
    if not token:
        return None, line.strip()
    raw = clean_amount_str(token)
    amount_has_minus = raw < 0
    desc_for_sign = (memo_so_far + " " + leftover).strip()
    sign = guess_sign(desc_for_sign, amount_has_minus)
    amount = abs(raw) * sign
    leftover = MONEY_INLINE.sub('', leftover).strip()
    if MEMO_CLEAN_RE.search(leftover):
        leftover = MEMO_CLEAN_RE.split(leftover)[0].strip()
    return amount, leftover


def parse_pdf(pdf_source):
    """Parse a bank statement PDF supporting multiple layouts."""

    rows = []
    file_name = None
    if isinstance(pdf_source, (str, Path)):
        file_name = str(pdf_source)
    elif hasattr(pdf_source, "name"):
        file_name = pdf_source.name
    year_hint = infer_year_from_filename(file_name) if file_name else None

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
            mode = None  # 'pattern' or 'sm'

            for raw_line in lines:
                line = raw_line.strip()
                if not line:
                    continue

                match = pattern.search(line)
                if match:
                    if current_tx:
                        if mode == "pattern" or (mode == "sm" and current_tx.get("Amount") is not None):
                            rows.append(current_tx)
                    date_full, date_short, desc, amt_str = match.groups()
                    if date_full:
                        date_dt = datetime.strptime(date_full, "%m/%d/%y")
                        current_year = date_dt.year
                    else:
                        if current_year is None:
                            current_year = year_hint or datetime.today().year
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
                    if amt_str.strip().startswith("-") or amt_str.strip().endswith("-"):
                        amount = -amount
                    current_tx = {"Date": date_fmt, "Amount": amount, "Memo": desc.strip()}
                    mode = "pattern"
                    continue

                date_match = DATE_START.match(line)
                if date_match:
                    if current_tx:
                        if mode == "pattern" or (mode == "sm" and current_tx.get("Amount") is not None):
                            rows.append(current_tx)
                    date_raw, rest = date_match.groups()
                    if HEADER_RE.search(rest):
                        rest = rest[:HEADER_RE.search(rest).start()]
                    rest = rest.strip()
                    date_dt = normalize_date(date_raw, current_year or year_hint)
                    current_year = date_dt.year
                    current_tx = {
                        "Date": f"{date_dt.month}/{date_dt.day}/{date_dt.year}",
                        "Memo": rest.strip(),
                        "Amount": None,
                    }
                    mode = "sm"
                    if rest.strip():
                        amt, leftover = parse_amount_from_line(rest.strip(), current_tx["Memo"])
                        if amt is not None:
                            if leftover:
                                current_tx["Memo"] = leftover
                            current_tx["Amount"] = amt
                            rows.append(current_tx)
                            current_tx = None
                            mode = None
                    continue

                if mode == "pattern" and current_tx:
                    current_tx["Memo"] += " " + line
                    continue

                if mode == "sm" and current_tx:
                    if HEADER_RE.search(line):
                        continue
                    amt, leftover = parse_amount_from_line(line, current_tx["Memo"])
                    if amt is not None:
                        if leftover:
                            current_tx["Memo"] = (current_tx["Memo"] + " " + leftover).strip()
                        current_tx["Amount"] = amt
                        rows.append(current_tx)
                        current_tx = None
                        mode = None
                    else:
                        current_tx["Memo"] = (current_tx["Memo"] + " " + line).strip()
                    continue

                if HEADER_RE.search(line):
                    continue

            if current_tx and (mode == "pattern" or (mode == "sm" and current_tx.get("Amount") is not None)):
                rows.append(current_tx)

    cleaned = []
    for r in rows:
        if MEMO_CLEAN_RE.search(r["Memo"]):
            r["Memo"] = MEMO_CLEAN_RE.split(r["Memo"])[0].strip()
        cleaned.append(r)
    deduped = []
    seen = set()
    for r in cleaned:
        key = (r["Date"], round(r["Amount"], 2), r["Memo"])
        if key not in seen:
            deduped.append(r)
            seen.add(key)
    return deduped


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