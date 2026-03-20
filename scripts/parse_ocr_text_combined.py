from rapidfuzz import fuzz
import json
import os
import re
import hashlib
from pathlib import Path
from datetime import datetime
from abc import ABC, abstractmethod


# ----------------------------
# Load Known Vendors
# ----------------------------
def load_known_vendors(json_path="known_vendors.json"):
    if not os.path.exists(json_path):
        # Create an empty one if missing to prevent crashes
        return {}
    with open(json_path, "r") as f:
        return json.load(f)


def match_known_vendor(text, known_vendors):
    best_match, best_score, best_account = None, 0, None
    for name, meta in known_vendors.items():
        score = fuzz.partial_ratio(name.lower(), text.lower())
        if score > best_score and score > 80:
            best_score, best_match, best_account = score, name, meta.get("account_id")
    return best_match, best_account


KNOWN_VENDORS = load_known_vendors()
# Ensure pathing is correct relative to the script location
INPUT_DIR = Path(__file__).resolve().parent.parent / 'output'


# ----------------------------
# Base Parser Class
# ----------------------------
class BaseParser(ABC):
    vendor_name = None

    def __init__(self, text):
        self.text = text
        self.lines = text.splitlines()

    @abstractmethod
    def parse(self):
        pass

    def extract_date(self, patterns=None):
        if patterns is None:
            patterns = [
                r"(\d{4}-\d{2}-\d{2})",
                r"(\d{2}/\d{2}/20\d{2})",
                r"(\d{2}-\d{2}-20\d{2})",
                r"(20\d{2}/\d{2}/\d{2})",
            ]
        for pattern in patterns:
            match = re.search(pattern, self.text)
            if match:
                return match.group(1)
        return None

    def format_amount_safely(self, raw_val):
        if not raw_val: return None
        # Standardize decimal separator
        clean_val = str(raw_val).replace(',', '.').replace('$', '').replace(' ', '').strip()

        # Handle cases where OCR misses the dot (e.g., 4139 instead of 41.39)
        if '.' not in clean_val and len(clean_val) >= 3:
            try:
                return f"{float(clean_val) / 100:.2f}"
            except:
                return None

        # Ensure it has 2 decimal places
        try:
            return f"{float(clean_val):.2f}"
        except:
            return None

    def guess_vendor_from_text(self):
        blacklist = {'invoice', 'total', 'amount', 'date', 'bill to', 'solde', 'sous-total', 'tps', 'tvq', 'facture'}
        for line in self.lines[:15]:
            line = line.strip()
            if any(bad in line.lower() for bad in blacklist) or len(line) < 3:
                continue
            matched, acc = match_known_vendor(line, KNOWN_VENDORS)
            if matched: return matched
            if any(c.isalpha() for c in line) and len(line.split()) > 1:
                return line
        return "Unknown Vendor"

    def create_base_result(self):
        return {
            'vendor': self.vendor_name,
            'invoice_number': None,
            'date': None,
            'subtotal': None,
            'total': None,
            'taxes': []
        }


# ----------------------------
# Specialized Parsers
# ----------------------------
class ShopifyParser(BaseParser):
    vendor_name = "Shopify"

    def parse(self):
        result = self.create_base_result()
        match = re.search(r"TOTAL DUE\s+\$?([0-9,]+\.\d{2})", self.text, re.I)
        if match:
            result['total'] = self.format_amount_safely(match.group(1))
        result['date'] = self.extract_date()
        return result


# ----------------------------
# Generic Visa/Receipt Parser (Quebec Smart-Math)
# ----------------------------
class VisaReceiptParser(BaseParser):
    vendor_name = None

    def parse(self):
        result = self.create_base_result()

        # 1. SCRAPE ALL POTENTIAL AMOUNTS
        # Look for patterns like 41.39 or 41,39
        all_matches = re.findall(r"(\d+[.,]\d{2})", self.text)
        floats = []
        for m in all_matches:
            try:
                # Force dot separator for math
                floats.append(float(m.replace(',', '.')))
            except:
                continue

        # 2. IDENTIFY GRAND TOTAL
        # On a receipt, the highest value is almost always the Grand Total
        if floats:
            grand_total = max(floats)
            result['total'] = f"{grand_total:.2f}"
        else:
            return result

        # 3. IDENTIFY TAXES (TPS 5% / TVQ 9.975%)
        # Logic: If a number is approx 5% or 9.975% of the rest of the bill, it's a tax.
        found_tps = 0.0
        found_tvq = 0.0

        for f in floats:
            if f == grand_total: continue

            # TPS check: Is this ~5% of (Total - this number)?
            if abs((f / (grand_total - f) if grand_total - f != 0 else 0) - 0.05) < 0.006:
                found_tps = f
            # TVQ check: Is this ~9.975% of (Total - this - TPS)?
            elif abs((f / (grand_total - f - found_tps) if grand_total - f - found_tps != 0 else 0) - 0.09975) < 0.006:
                found_tvq = f

        if found_tps > 0:
            result['taxes'].append({"amount": found_tps, "rate": 5.0})
        if found_tvq > 0:
            result['taxes'].append({"amount": found_tvq, "rate": 9.975})

        # 4. CALCULATE SUB-TOTAL
        # Total minus the identified taxes
        result['subtotal'] = f"{grand_total - found_tps - found_tvq:.2f}"

        # 5. METADATA
        result['date'] = self.extract_date()
        matched_v, _ = match_known_vendor(self.text, KNOWN_VENDORS)
        result['vendor'] = matched_v or self.guess_vendor_from_text()

        # REFERENCE NUMBER (Invoice/Transaction ID)
        invoice_match = re.search(r"(?:#|TRANSACTION|INV|FACTURE)\s*#?\s*(\d+)", self.text, re.IGNORECASE)
        if invoice_match:
            result['invoice_number'] = invoice_match.group(1)
        else:
            # Fallback: Hash the text to create a unique ID to prevent Odoo duplicates
            result['invoice_number'] = hashlib.md5(self.text.encode()).hexdigest()[:10]

        return result


# ----------------------------
# Factory & Loop
# ----------------------------
class ParserFactory:
    @staticmethod
    def get_parser(text):
        t = text.lower()
        if "shopify" in t: return ShopifyParser(text)
        return VisaReceiptParser(text)


if __name__ == "__main__":
    # Look specifically for the output from Step 3 (gcv.ocr.json)
    for ocr_file in INPUT_DIR.glob("*.gcv.ocr.json"):
        try:
            # Prevent re-parsing if already done
            if ".parsed" in ocr_file.name:
                continue

            with open(ocr_file, 'r') as f:
                data = json.load(f)

            raw_text = data.get("text", "")
            if not raw_text:
                print(f"⚠️ Empty text in {ocr_file.name}")
                continue

            parser = ParserFactory.get_parser(raw_text)
            parsed = parser.parse()

            # Pass the card info if it exists in the original OCR JSON
            if "card_used" in data:
                parsed["card_info"] = data["card_used"]

            # Save the final result
            out_path = ocr_file.with_name(ocr_file.name.replace(".json", ".parsed.json"))
            with open(out_path, "w") as f:
                json.dump(parsed, f, indent=2)

            print(
                f"✅ Parsed: {parsed.get('vendor')} - Total: {parsed.get('total')} (Subtotal: {parsed.get('subtotal')})")
        except Exception as e:
            print(f"❌ Error processing {ocr_file.name}: {e}")