#!/usr/bin/env python3
"""Test script to validate PDF parsing for all statement formats."""

import os
from parse_bank_statement import parse_pdf


def test_all_pdfs():
    """Test parsing of all PDFs in the data directory."""
    data_dir = 'data'
    
    # Define expected working PDFs
    previously_working = [
        '02_2025 (1).pdf',
        '03_2025.pdf', 
        '04_2025 (1).pdf',
        '083125 WellsFargo.pdf',
        '2025-06-06.pdf',
        '2025-08-26_am ex.pdf',
        '2025-09.pdf'
    ]
    
    # Define previously failing PDFs that should now work
    previously_failing = [
        'View PDF Statement_2025-09-03.pdf',
        'View PDF Statement_2025-10-03.pdf',
        'View PDF Statement_2025-11-03.pdf'
    ]
    
    all_pdfs = previously_working + previously_failing
    
    print("=" * 80)
    print("PDF PARSING TEST RESULTS")
    print("=" * 80)
    
    success_count = 0
    fail_count = 0
    
    for pdf_name in all_pdfs:
        pdf_path = os.path.join(data_dir, pdf_name)
        
        if not os.path.exists(pdf_path):
            print(f"✗ SKIP: {pdf_name} (file not found)")
            continue
            
        try:
            rows = parse_pdf(pdf_path)
            
            if len(rows) > 0:
                status = "✓ PASS"
                success_count += 1
                
                # Show sample transaction
                sample = rows[0]
                sample_str = f"{sample['Date']:12} ${sample['Amount']:8.2f} {sample['Memo'][:30]}"
                
                # Mark if this was previously failing
                note = " (FIXED!)" if pdf_name in previously_failing else ""
                print(f"{status}: {pdf_name:45} {len(rows):3} txns{note}")
                print(f"       Sample: {sample_str}")
            else:
                print(f"✗ FAIL: {pdf_name:45} 0 transactions found")
                fail_count += 1
                
        except Exception as e:
            print(f"✗ ERROR: {pdf_name:45} {str(e)}")
            fail_count += 1
    
    print("=" * 80)
    print(f"SUMMARY: {success_count} passed, {fail_count} failed")
    print("=" * 80)
    
    if fail_count == 0:
        print("\n✓ All tests passed!")
        return True
    else:
        print(f"\n✗ {fail_count} test(s) failed")
        return False


if __name__ == "__main__":
    success = test_all_pdfs()
    exit(0 if success else 1)
