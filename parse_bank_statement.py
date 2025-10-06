import csv
import re
import sys
import zlib
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import pdfplumber

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


def detect_brand_from_text(text: str) -> str:
    txt = re.sub(r"\s+", " ", text or "").lower()
    if "wells fargo" in txt and (
        "transaction history" in txt
        or "deposits/ credits" in txt
        or "withdrawals/ debits" in txt
    ):
        return "wells"
    if "american express" in txt or "membership rewards" in txt:
        return "amex"
    return "generic"


def detect_brand(pdf) -> str:
    txt = " ".join(
        (pdf.pages[i].extract_text() or "") for i in range(min(2, len(pdf.pages)))
    )
    return detect_brand_from_text(txt)

NEGATIVE_HINTS = (
    "purchase authorized", "withdrawal", "ach debit", "zelle to",
    "payment", "check", "debit", "card", "b2p"
)
POSITIVE_HINTS = (
    "le - usa technol", "usa technol",  # WF settlements
    "deposit", "edeposit", "atm cash deposit", "credit", "refund", "zelle from"
)


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


def guess_sign(desc: str, amount_has_minus: bool, brand: str) -> int:
    d = desc.lower()
    if brand == "amex" and amount_has_minus and ("credit" in d or "refund" in d):
        return +1
    if amount_has_minus:
        return -1
    if any(k in d for k in NEGATIVE_HINTS):
        return -1
    if any(k in d for k in POSITIVE_HINTS):
        return +1
    # Brand-specific default when ambiguous:
    return +1 if brand == "wells" else -1


def parse_amount_from_line(line: str, memo_so_far: str, brand: str):
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
    sign = guess_sign(desc_for_sign, amount_has_minus, brand)
    amount = abs(raw) * sign
    leftover = MONEY_INLINE.sub('', leftover).strip()
    if MEMO_CLEAN_RE.search(leftover):
        leftover = MEMO_CLEAN_RE.split(leftover)[0].strip()
    return amount, leftover


def process_statement_lines(
    lines: Iterable[str], brand: str, year_hint: Optional[int]
) -> List[dict]:
    rows: List[dict] = []
    current_tx = None
    current_year = year_hint
    mode = None  # 'pattern' or 'sm'

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        match = pattern.search(line)
        if match:
            if current_tx and (
                mode == "pattern" or (mode == "sm" and current_tx.get("Amount") is not None)
            ):
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
            if current_tx and (
                mode == "pattern" or (mode == "sm" and current_tx.get("Amount") is not None)
            ):
                rows.append(current_tx)
            date_raw, rest = date_match.groups()
            if HEADER_RE.search(rest):
                rest = rest[: HEADER_RE.search(rest).start()]
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
                desc_part = rest.strip()
                money_match = MONEY_INLINE.search(desc_part)
                if money_match:
                    amt_raw = money_match.group(1)
                    memo = desc_part[: money_match.start()].strip()
                    current_tx["Memo"] = memo
                    raw = MONEY_STRIPPER.sub("", amt_raw).replace("-", "")
                    amount = float(raw)
                    has_minus = "-" in amt_raw
                    sign = guess_sign(memo, has_minus, brand)
                    current_tx["Amount"] = amount * (-1 if sign < 0 else 1)
                    rows.append(current_tx)
                    current_tx = None
                    mode = None
                else:
                    amt, leftover = parse_amount_from_line(desc_part, current_tx["Memo"], brand)
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
            amt, leftover = parse_amount_from_line(line, current_tx["Memo"], brand)
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

    if current_tx and (
        mode == "pattern" or (mode == "sm" and current_tx.get("Amount") is not None)
    ):
        rows.append(current_tx)

    return rows


def extract_fallback_lines(pdf_source) -> Tuple[List[str], Optional[str]]:
    data: Optional[bytes] = None
    if isinstance(pdf_source, (str, Path)):
        try:
            data = Path(pdf_source).read_bytes()
        except OSError:
            data = None
    elif hasattr(pdf_source, "read"):
        try:
            pos = pdf_source.tell()
        except (OSError, AttributeError):
            pos = None
        try:
            pdf_source.seek(0)
        except (OSError, AttributeError):
            pass
        data = pdf_source.read()
        if pos is not None:
            try:
                pdf_source.seek(pos)
            except (OSError, AttributeError):
                pass
    if not data:
        return [], None

    stream_chunks = re.findall(b"stream\r?\n(.*?)\r?\nendstream", data, re.S)
    text_parts: List[str] = []
    str_pat = re.compile(rb"\((.*?)\)\s*Tj", re.S)
    arr_pat = re.compile(rb"\[(.*?)\]\s*TJ", re.S)
    paren_pat = re.compile(rb"\((.*?)\)", re.S)

    def decode_pdf_bytes(chunk: bytes) -> str:
        return (
            chunk.replace(b"\\(", b"(")
            .replace(b"\\)", b")")
            .replace(b"\\r", b" ")
            .replace(b"\\n", b" ")
            .replace(b"\\t", b" ")
        ).decode("latin-1", errors="ignore")

    for raw_stream in stream_chunks:
        try:
            content = zlib.decompress(raw_stream)
        except Exception:
            continue
        for m in str_pat.finditer(content):
            text_parts.append(decode_pdf_bytes(m.group(1)))
        for m in arr_pat.finditer(content):
            combined = "".join(
                decode_pdf_bytes(part)
                for part in paren_pat.findall(m.group(1))
            )
            text_parts.append(combined)

    if not text_parts:
        return [], None

    full_text = re.sub(r"\s+", " ", "".join(text_parts)).strip()
    brand_hint = detect_brand_from_text(full_text)

    txn_pattern = re.compile(
        r"(?<![Oo]n\s)((?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])(?:/\d{2,4})?)\s+(.*?)(?=(?<![Oo]n\s)(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])(?:/\d{2,4})?\s+|$)",
        re.S,
    )
    segments: List[Tuple[str, str]] = []
    for match in txn_pattern.finditer(full_text):
        date = match.group(1)
        body = match.group(2).strip()
        if not body:
            continue
        if segments and segments[-1][1].endswith(" on 0") and re.match(r"0?\d", date):
            prev_date, prev_body = segments[-1]
            segments[-1] = (prev_date, prev_body[:-1] + date + " " + body)
        else:
            segments.append((date, body))

    lines: List[str] = []
    for date, body in segments:
        text = f"{date} {body}".strip()
        lower = text.lower()
        for marker in ("totals", "transaction history", "monthly service fee"):
            if marker in lower:
                text = text[: lower.index(marker)].strip()
                lower = text.lower()
        if not text or not MONEY_INLINE.search(text):
            continue
        lines.append(text)

    return lines, brand_hint


def parse_pdf(pdf_source):
    """Parse a bank statement PDF supporting multiple layouts."""

    rows: List[dict] = []
    file_name = None
    if isinstance(pdf_source, (str, Path)):
        file_name = str(pdf_source)
    elif hasattr(pdf_source, "name"):
        file_name = pdf_source.name
    year_hint = infer_year_from_filename(file_name) if file_name else None

    if hasattr(pdf_source, "seek"):
        try:
            pdf_source.seek(0)
        except (OSError, AttributeError):
            pass

    brand = "generic"
    try:
        with pdfplumber.open(pdf_source) as pdf:
            if pdf.pages:
                brand = detect_brand(pdf)
            for page in pdf.pages:
                text = page.extract_text()
                if not text:
                    continue
                page_rows = process_statement_lines(text.split("\n"), brand, year_hint)
                rows.extend(page_rows)
    except Exception:
        rows = []
    finally:
        if hasattr(pdf_source, "seek"):
            try:
                pdf_source.seek(0)
            except (OSError, AttributeError):
                pass

    # Only attempt the raw stream fallback when ``pdfplumber`` failed to
    # produce any transaction rows. This keeps the behaviour identical for
    # statements that already parse correctly while still rescuing edge-case
    # PDFs (such as the "09 2025" file) whose text needs to be inflated from
    # compressed content streams.
    if not rows:
        if hasattr(pdf_source, "seek"):
            try:
                pdf_source.seek(0)
            except (OSError, AttributeError):
                pass
        fallback_lines, brand_hint = extract_fallback_lines(pdf_source)
        if fallback_lines:
            brand = brand_hint or brand
            rows = process_statement_lines(fallback_lines, brand, year_hint)

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
    
    
# SUPPOSE TO GENERALIZE