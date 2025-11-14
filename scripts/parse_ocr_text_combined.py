# ----------------------------
# Shopify Invoice Parser
# ----------------------------
def parse_shopify_invoice(text):
    import re, hashlib
    vendor = "Shopify"
    invoice_number = None
    subtotal = None
    total = None
    date = None
    taxes = []
    tax = None

    # Look for invoice number: Invoice #xxxxxx
    match = re.search(r"Invoice\s*#\s*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
    if match:
        invoice_number = match.group(1)
    else:
        # fallback: try "Invoice Number: xxxxx"
        match = re.search(r"Invoice\s*Number[:\s]*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
        if match:
            invoice_number = match.group(1)

    # Additional: Bill # for Shopify
    invoice_match = re.search(r"Bill\s*#\s*(\d+)", text)
    # We'll add this to the parsed_invoice return dict later, since currently only variables are set here

    # Date: look for YYYY-MM-DD or MM/DD/YYYY or similar
    match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if match:
        date = match.group(1)
    else:
        match = re.search(r"(\d{2}/\d{2}/\d{4})", text)
        if match:
            date = match.group(1)

    # Subtotal and total
    match = re.search(r"Subtotal\s*\$?\s*([0-9,]+\.\d{2})", text, re.IGNORECASE)
    if match:
        subtotal = match.group(1).replace(',', '')
    match = re.search(r"Total\s*\$?\s*([0-9,]+\.\d{2})", text, re.IGNORECASE)
    if match:
        total = match.group(1).replace(',', '')

    # Taxes: extract GST and QST using line-by-line approach
    taxes = []
    gst_match = re.search(r"GST.*?([\d\.]+)%.*?\$([\d\.]+)", text, re.IGNORECASE)
    qst_match = re.search(r"QST.*?([\d\.]+)%.*?\$([\d\.]+)", text, re.IGNORECASE)

    if gst_match:
        try:
            rate = float(gst_match.group(1))
            amount = float(gst_match.group(2))
            taxes.append({
                "rate": rate,
                "amount": str(amount)
            })
        except:
            pass

    if qst_match:
        try:
            rate = float(qst_match.group(1))
            amount = float(qst_match.group(2))
            taxes.append({
                "rate": rate,
                "amount": str(amount)
            })
        except:
            pass

    # Deduplicate and summarize
    seen_rates = set()
    unique_taxes = []
    total_tax_amount = 0.0

    for tax in taxes:
        rate = float(tax["rate"])
        amount = float(tax["amount"])
        if rate not in seen_rates:
            seen_rates.add(rate)
            unique_taxes.append({"rate": rate, "amount": tax["amount"]})
        total_tax_amount += amount

    # Prepare parsed_invoice dictionary
    parsed_invoice = {
        'vendor': vendor,
        'invoice_number': invoice_number,
        'date': date,
        'subtotal': subtotal,
        'total': total,
    }
    # Add invoice_number from Bill # if found and not already set
    invoice_match = re.search(r"Bill\s*#\s*(\d+)", text)
    if invoice_match:
        parsed_invoice["invoice_number"] = invoice_match.group(1)

    # Store unique taxes and combined tax
    if unique_taxes:
        tax_rate_sum = sum([t["rate"] for t in unique_taxes])
        parsed_invoice["taxes"] = unique_taxes
        parsed_invoice["tax"] = {
            "rate": round(tax_rate_sum, 3),
            "amount": str(round(total_tax_amount, 2))
        }
    else:
        parsed_invoice["taxes"] = []
        parsed_invoice["tax"] = None

    return parsed_invoice
from rapidfuzz import process, fuzz
import json
import os
import re
from pathlib import Path

# ----------------------------
# Load Known Vendors
# ----------------------------
def load_known_vendors(json_path="scripts/known_vendors.json"):
    if not os.path.exists(json_path):
        return {}
    with open(json_path, "r") as f:
        return json.load(f)

def match_known_vendor(text, known_vendors):
    best_match = None
    best_score = 0
    best_account = None
    for name, meta in known_vendors.items():
        score = fuzz.partial_ratio(name.lower(), text.lower())
        if score > best_score and score > 80:
            best_score = score
            best_match = name
            best_account = meta.get("account_id")
    return best_match, best_account

# Load known vendors globally
with open('known_vendors.json', 'r') as f:
    KNOWN_VENDORS = json.load(f)

INPUT_DIR = Path(__file__).resolve().parent.parent / 'output'

# ----------------------------
# Generic Vendor Guessing
# ----------------------------
def guess_vendor_name(text):
    known_vendors = load_known_vendors()
    lines = text.strip().splitlines()
    blacklist = {'invoice', 'total', 'amount due', 'date', 'bill to', 'page', 'usd', 'cad'}
    email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')

    for line in lines[:20]:
        line = line.strip()
        normalized = re.sub(r'[^\w\s@.]', '', line).strip().lower()

        if any(bad in normalized for bad in blacklist):
            continue
        if 'duplicate' in normalized:
            continue
        if email_pattern.search(line):
            continue

        if any(c.isalpha() for c in line) and len(line.split()) > 1:
            cleaned = re.sub(r'^(Invoice number|Invoice|Bill to)\s*', '', line, flags=re.IGNORECASE).strip()
            matched = match_known_vendor(cleaned, known_vendors)
            if matched:
                return matched
            return cleaned
    return None

# ----------------------------
# Pirate Ship Parser
# ----------------------------
def parse_pirate_ship(text):
    import re
    vendor = "Pirate Ship"
    invoice_number = None
    total = "0.00"
    subtotal = "0.00"
    date = None

    # Extract invoice number
    match = re.search(r"Receipt\s+#(\d+)", text)
    if match:
        invoice_number = match.group(1)

    # Extract date
    match = re.search(r"\b\w{6,9},\s+(\d{2}/\d{2}/\d{4})", text)
    if match:
        date = match.group(1)

    # Extract total from "Credit Card Payment" line or its following line
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "Credit Card Payment:" in line and "Visa" in line:
            amount_match = re.search(r"\$?(\d+\.\d{2})", line)
            if not amount_match and i + 1 < len(lines):
                amount_match = re.search(r"\$?(\d+\.\d{2})", lines[i + 1])
            if amount_match:
                total = amount_match.group(1)
                subtotal = total
                print(f"[🧾 CARD MATCH] Found Visa payment → total = {total}")
                break

    return {
        'vendor': vendor,
        'invoice_number': invoice_number,
        'date': date,
        'subtotal': subtotal,
        'total': total,
        'tax': None,
        'account_id': 1021
    }

# ----------------------------
# Klaviyo Parser
# ----------------------------
def parse_klaviyo_invoice(text):
    import re
    vendor = "Klaviyo"
    invoice_number = None
    total = None
    date = None
    tax = None

    match = re.search(r"Invoice number\s+([A-Z0-9\-]+)", text, re.IGNORECASE)
    if match:
        invoice_number = match.group(1)

    match = re.search(r"Date of issue\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", text)
    if match:
        from datetime import datetime
        try:
            date_obj = datetime.strptime(match.group(1), "%B %d, %Y")
            date = date_obj.strftime("%Y-%m-%d")
        except ValueError:
            pass

    match = re.search(r"GST.*?\$?(\d+[.,]\d{2})", text, re.IGNORECASE)
    if match:
        tax = match.group(1).replace(',', '')

    match = re.search(r"Amount due.*?\$?(\d+[.,]\d{2})", text, re.IGNORECASE)
    if match:
        total = match.group(1).replace(',', '')

    return {
        'vendor': vendor,
        'invoice_number': invoice_number,
        'date': date,
        'total': total,
        'tax': tax
    }

# ----------------------------
# Visa Receipt Parser
# ----------------------------
def parse_visa_receipt(text):
    import re, hashlib
    vendor = None
    invoice_number = None
    total = None
    date = None
    tax = None

    # Find total
    match = re.search(r"TOTAL\s*\$?\s*(\d+[.,]\d{2})", text, re.IGNORECASE)
    if not match:
        match = re.search(r"(?:VISA TEND|Amount).*?\$?(\d+[.,]\d{2})", text, re.IGNORECASE)
    if match:
        total = match.group(1).replace(',', '')

    # Fallback to max amount found
    if not total:
        amounts = re.findall(r'\$?\s?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2}))', text)
        if amounts:
            total = str(max([float(a.replace(',', '')) for a in amounts]))

    # Try to get tax
    for pattern in [r"HST\s+\d+%\s+(\d+[.,]\d{2})", r"TAX\s*\$?\s*(\d+[.,]\d{2})"]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            tax = match.group(1).replace(',', '')
            break

    # Get date
    match = re.search(r"(\d{4}/\d{2}/\d{2}|\d{2}/\d{2}/\d{4})", text)
    if match:
        date = match.group(1)

    # Match vendor
    matched_vendor, matched_account = match_known_vendor(text, KNOWN_VENDORS)
    vendor = matched_vendor or guess_vendor_name(text)

    # Fallback invoice number
    invoice_number = hashlib.md5(text.encode()).hexdigest()[:10]

    result = {
        'vendor': vendor,
        'invoice_number': invoice_number,
        'date': date,
        'total': total,
        'tax': tax
    }
    if matched_account:
        result["account_id"] = matched_account

    return result

# ----------------------------
# Home Depot Parser
# ----------------------------
def parse_home_depot(text):
    import re, hashlib
    vendor = "Home Depot"
    invoice_number = hashlib.md5(text.encode()).hexdigest()[:10]
    total = None
    subtotal = None
    tax = None
    date = None

    match = re.search(r"(\d{2}/\d{2}/\d{4})", text)
    if match:
        date = match.group(1)

    match = re.search(r"SUBTOTAL.*?(\d+[.,]\d{2})", text)
    if match:
        subtotal = match.group(1)

    match = re.search(r"TOTAL.*?(\d+[.,]\d{2})", text)
    if match:
        total = match.group(1)

    return {
        'vendor': vendor,
        'invoice_number': invoice_number,
        'date': date,
        'subtotal': subtotal,
        'total': total,
        'tax': tax
    }

# ----------------------------
# Dispatcher
# ----------------------------
for ocr_file in INPUT_DIR.glob("*.ocr.json"):
    with open(ocr_file, 'r') as f:
        data = json.load(f)
    raw_text = data.get("text", "")

    if "pirate ship" in raw_text.lower() or "arrrr" in raw_text.lower():
        parsed = parse_pirate_ship(raw_text)
        print(f"🔍 Parsed Pirate Ship invoice: {ocr_file.name} -> {parsed}")
    elif "klaviyo" in raw_text.lower():
        parsed = parse_klaviyo_invoice(raw_text)
        print(f"🔍 Parsed Klaviyo invoice: {ocr_file.name} -> {parsed}")
    elif "home depot" in raw_text.lower():
        parsed = parse_home_depot(raw_text)
        print(f"🔍 Parsed Home Depot receipt: {ocr_file.name} -> {parsed}")
    elif "shopify" in raw_text.lower():
        parsed = parse_shopify_invoice(raw_text)
        print(f"🔍 Parsed Shopify invoice: {ocr_file.name} -> {parsed}")
    elif "visa" in raw_text.lower() or "visa tend" in raw_text.lower():
        parsed = parse_visa_receipt(raw_text)
        print(f"🔍 Parsed VISA receipt: {ocr_file.name} -> {parsed}")
    else:
        parsed = parse_visa_receipt(raw_text)
        print(f"🔍 Parsed Generic invoice: {ocr_file.name} -> {parsed}")

    # Add card tag
    card_tag = Path(ocr_file).parent.name
    parsed["card_tag"] = card_tag

    # Detect Visa folder
    match = re.search(r"Visa[_\- ]?(\d{4})", str(ocr_file.parent), re.IGNORECASE)
    if match:
        card_used = f"Visa {match.group(1)}"
        parsed.setdefault("notes", []).append(card_used)

    # Save output
    out_path = ocr_file.with_name(ocr_file.stem + ".ocr.parsed.json")
    with open(out_path, "w") as f:
        json.dump(parsed, f, indent=2)
    print(f"✅ Saved: {out_path.name}")