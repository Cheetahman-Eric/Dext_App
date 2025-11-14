import json
import re
from pathlib import Path


def extract_pirateship_data(text, card_used=None):
    # Extract invoice number (usually starts with # or "Invoice #:")
    invoice_match = re.search(r"#(\d+)", text)
    invoice_number = invoice_match.group(1).strip() if invoice_match else None

    # Extract date (format like "Jul 24, 2025" or "07/24/2025")
    date_match = re.search(r"\b(?:\d{1,2}[/\-]){2}\d{4}\b|\b\w{3,9} \d{1,2}, \d{4}\b", text)
    date = date_match.group().strip() if date_match else None

    # Extract subtotal (optional, not present in original code)
    subtotal_match = re.search(r"Subtotal:?\s*\$?(\d+\.\d{2})", text)
    subtotal = subtotal_match.group(1).strip() if subtotal_match else "0.00"

    # Extract total amount – either inline or on the next line (Visa line logic)
    total = "0.00"
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "Credit Card Payment:" in line and "Visa" in line:
            # Look ahead for the next line to try to extract amount
            next_idx = i + 1
            amount = None
            if next_idx < len(lines):
                # Try to find amount in next line
                next_line = lines[next_idx].strip()
                amount_match = re.search(r"\$?\s?(\d+\.\d{2})", next_line)
                if amount_match:
                    amount = amount_match.group(1)
            if not amount:
                # Try to find amount in current line
                amount_match = re.search(r"\$?\s?(\d+\.\d{2})", line)
                if amount_match:
                    amount = amount_match.group(1)
            if amount:
                total = amount
                break

    # Extract tax (optional)
    tax_match = re.search(r"Tax:?\s*\$?(\d+\.\d{2})", text)
    tax = tax_match.group(1).strip() if tax_match else None

    # Extract card suffix if present
    match = re.search(r"Credit Card Payment\s*:\s*Visa ending (?:in|with)\s*(\d{4})", text, re.IGNORECASE)
    if match:
        card_used = f"Visa_{match.group(1)}"

    return {
        "vendor": "Pirate Ship",
        "invoice_number": invoice_number,
        "date": date,
        "subtotal": subtotal,
        "total": total,
        "tax": tax,
        "account_id": 1021,
        "card_used": card_used
    }