#!/usr/bin/env python3
"""Test to verify Wells Fargo PDF continuation lines are properly captured."""

import os
from parse_bank_statement import parse_pdf


def test_wellsfargo_continuation_lines():
    """Verify that Wells Fargo transactions with continuation lines are properly parsed."""
    
    pdf_path = os.path.join('data', '083125 WellsFargo.pdf')
    
    if not os.path.exists(pdf_path):
        print(f"⚠ WARNING: {pdf_path} not found, skipping test")
        return True
    
    # Parse the Wells Fargo PDF
    rows = parse_pdf(pdf_path)
    
    # Expected transactions with continuation line information
    expected_with_continuation = [
        {
            "index": 0,  # Transaction 1
            "date": "8/1/2025",
            "amount": -13.99,
            "continuation_text": "FL S305212532878398 Card 6809",
            "description": "card number from Costco purchase"
        },
        {
            "index": 2,  # Transaction 3
            "date": "8/4/2025",
            "amount": -64.00,
            "continuation_text": "July Sales",
            "description": "additional context for Zelle payment"
        },
        {
            "index": 4,  # Transaction 5
            "date": "8/5/2025",
            "amount": 46.00,
            "continuation_text": "0005259 ATM ID 0913F Card 4841",
            "description": "ATM ID and card info"
        },
        {
            "index": 5,  # Transaction 6
            "date": "8/5/2025",
            "amount": -300.00,
            "continuation_text": "250805 M4600 Daniel Halem",
            "description": "reference number for ACH debit"
        },
        {
            "index": 6,  # Transaction 7
            "date": "8/8/2025",
            "amount": -182.42,
            "continuation_text": "Dan Machine",
            "description": "additional context for Zelle payment"
        },
        {
            "index": 8,  # Transaction 9
            "date": "8/11/2025",
            "amount": -35.98,
            "continuation_text": "FL S385222530097542 Card 6809",
            "description": "card number from Costco purchase"
        },
        {
            "index": 16,  # Transaction 17
            "date": "8/20/2025",
            "amount": 3.00,
            "continuation_text": "Boca Raton FL",
            "description": "location for eDeposit"
        },
    ]
    
    print("=" * 80)
    print("WELLS FARGO CONTINUATION LINES TEST")
    print("=" * 80)
    print()
    
    all_passed = True
    
    for expected in expected_with_continuation:
        idx = expected["index"]
        if idx >= len(rows):
            print(f"✗ FAIL: Transaction {idx + 1} not found in parsed results")
            all_passed = False
            continue
        
        txn = rows[idx]
        memo = txn["Memo"]
        continuation = expected["continuation_text"]
        
        # Check if the continuation text is in the memo
        if continuation.lower() in memo.lower():
            print(f"✓ PASS: Transaction {idx + 1} ({txn['Date']}, ${txn['Amount']:.2f})")
            print(f"        {expected['description']}: '{continuation}'")
        else:
            print(f"✗ FAIL: Transaction {idx + 1} ({txn['Date']}, ${txn['Amount']:.2f})")
            print(f"        Expected continuation: '{continuation}'")
            print(f"        Actual memo: '{memo}'")
            all_passed = False
        print()
    
    # Verify total count and amounts
    print("=" * 80)
    print(f"Total transactions: {len(rows)} (expected: 26)")
    
    total = sum(t["Amount"] for t in rows)
    expected_total = -313.50
    
    print(f"Transaction total: ${total:.2f} (expected: ${expected_total:.2f})")
    
    if len(rows) == 26 and abs(total - expected_total) < 0.01:
        print("\n✓ Overall totals match!")
    else:
        print("\n✗ Overall totals mismatch!")
        all_passed = False
    
    print("=" * 80)
    
    if all_passed:
        print("\n✓ All continuation lines test passed!")
    else:
        print("\n✗ Some continuation lines tests failed!")
    
    return all_passed


if __name__ == "__main__":
    success = test_wellsfargo_continuation_lines()
    exit(0 if success else 1)
