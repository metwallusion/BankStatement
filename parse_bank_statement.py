import pdfplumber
import csv
import re
import sys
from datetime import datetime

pattern = re.compile(r"(\d{2}/\d{2}/\d{2})\*?\s+(.*?)\s+(-?\$?\d[\d,]*\.\d{2})")

def parse_pdf(pdf_path):
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            lines = text.split("\n")
            current = None
            for line in lines:
                match = pattern.search(line)
                if match:
                    if current:
                        rows.append(current)
                    date_str, desc, amt_str = match.groups()
                    date_dt = datetime.strptime(date_str, "%m/%d/%y")
                    date_fmt = f"{date_dt.month}/{date_dt.day}/{date_dt.year}"
                    amount = float(amt_str.replace("$", "").replace(",", "").replace("-", ""))
                    current = {
                        "Date": date_fmt,
                        "Amount": amount,
                        "Deposit": amount,
                        "Withdrawal": "",
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
        writer.writerow(["Row #", "Date", "Amount", "Deposit", "Withdrawal", "Memo"])
        for i, row in enumerate(rows, 1):
            writer.writerow([
                i,
                row["Date"],
                f"{row['Amount']}",
                f"{row['Deposit']}",
                row["Withdrawal"],
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
