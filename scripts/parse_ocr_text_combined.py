from rapidfuzz import fuzz
import json
import os
import re
from pathlib import Path
from datetime import datetime
from abc import ABC, abstractmethod


# ----------------------------
# Load Known Vendors
# ----------------------------
def load_known_vendors(json_path="known_vendors.json"):
    """Load known vendors from JSON file"""
    if not os.path.exists(json_path):
        return {}
    with open(json_path, "r") as f:
        return json.load(f)


def match_known_vendor(text, known_vendors):
    """Match vendor name using fuzzy matching"""
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
KNOWN_VENDORS = load_known_vendors()
INPUT_DIR = Path(__file__).resolve().parent.parent / 'output'


# ----------------------------
# Base Parser Class
# ----------------------------
class BaseParser(ABC):
    """Base class for all invoice parsers"""

    vendor_name = None  # Must be set by subclasses

    def __init__(self, text):
        self.text = text
        self.lines = text.splitlines()

    @abstractmethod
    def parse(self):
        """Main parsing method - must be implemented by subclasses"""
        pass

    def extract_date(self, patterns=None):
        """Extract date from text using common patterns"""
        if patterns is None:
            patterns = [
                r"(\d{4}-\d{2}-\d{2})",  # YYYY-MM-DD
                r"(\d{2}/\d{2}/\d{4})",  # MM/DD/YYYY or DD/MM/YYYY
                r"(\d{4}/\d{2}/\d{2})",  # YYYY/MM/DD
            ]

        for pattern in patterns:
            match = re.search(pattern, self.text)
            if match:
                return match.group(1)
        return None

    def extract_amount(self, pattern, flags=re.IGNORECASE):
        """Extract monetary amount using regex pattern"""
        match = re.search(pattern, self.text, flags)
        if match:
            return match.group(1).replace(',', '')
        return None

    def find_max_amount(self):
        """Find the largest dollar amount in the text (fallback)"""
        amounts = re.findall(r'\$?\s?(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2}))', self.text)
        if amounts:
            return str(max([float(a.replace(',', '')) for a in amounts]))
        return None

    def guess_vendor_from_text(self):
        """Try to guess vendor name from first 20 lines"""
        blacklist = {'invoice', 'total', 'amount due', 'date', 'bill to', 'page', 'usd', 'cad'}
        email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')

        for line in self.lines[:20]:
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
                matched = match_known_vendor(cleaned, KNOWN_VENDORS)
                if matched:
                    return matched
                return cleaned
        return None

    def create_base_result(self):
        """Create base result dictionary with common fields"""
        return {
            'vendor': self.vendor_name,
            'invoice_number': None,
            'date': None,
            'subtotal': None,
            'total': None,
            'taxes': []
        }


# ----------------------------
# Shopify Parser
# ----------------------------
class ShopifyParser(BaseParser):
    vendor_name = "Shopify"

    def parse(self):
        result = self.create_base_result()

        # Extract Bill number
        match = re.search(r"Bill\s*#\s*(\d+)", self.text)
        if match:
            result['invoice_number'] = match.group(1)

        # Extract date - "Paid on MMM DD, YYYY"
        date_match = re.search(r"Paid on\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", self.text)
        if date_match:
            try:
                date_obj = datetime.strptime(date_match.group(1), "%b %d, %Y")
                result['date'] = date_obj.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Fallback: try "30-day billing cycle" date
        if not result['date']:
            date_match = re.search(r"30-day billing cycle\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", self.text)
            if date_match:
                try:
                    date_obj = datetime.strptime(date_match.group(1), "%b %d, %Y")
                    result['date'] = date_obj.strftime("%Y-%m-%d")
                except ValueError:
                    pass

        # Extract Subtotal
        result['subtotal'] = self.extract_amount(r"Subtotal\s+\$?([0-9,]+\.\d{2})\s+CAD")

        # Extract Total - look for TOTAL DUE first
        result['total'] = self.extract_amount(r"TOTAL DUE\s+\$?([0-9,]+\.\d{2})\s+CAD")
        if not result['total']:
            result['total'] = self.extract_amount(r"Total\s+\$?([0-9,]+\.\d{2})\s+CAD")

        # Extract GST/TPS
        gst_match = re.search(
            r"(?:CANADA\s+)?GST/TPS[^\$]*\((\d+\.?\d*)%\)[^\$]*\$([0-9,]+\.\d{2})",
            self.text,
            re.IGNORECASE
        )
        if gst_match:
            result['taxes'].append({
                "name": "GST/TPS",
                "rate": float(gst_match.group(1)),
                "amount": gst_match.group(2).replace(',', '')
            })

        # Extract QST/TVQ
        qst_match = re.search(
            r"(?:QUEBEC\s+)?QST/TVQ[^\$]*\((\d+\.?\d*)%\)[^\$]*\$([0-9,]+\.\d{2})",
            self.text,
            re.IGNORECASE
        )
        if qst_match:
            result['taxes'].append({
                "name": "QST/TVQ",
                "rate": float(qst_match.group(1)),
                "amount": qst_match.group(2).replace(',', '')
            })

        # Validation: calculate total if missing
        if result['subtotal'] and result['taxes'] and not result['total']:
            calculated_total = float(result['subtotal'])
            for tax in result['taxes']:
                calculated_total += float(tax["amount"])
            result['total'] = f"{calculated_total:.2f}"

        return result


# ----------------------------
# Pirate Ship Parser
# ----------------------------
class PirateShipParser(BaseParser):
    vendor_name = "Pirate Ship"

    def parse(self):
        result = self.create_base_result()
        result['account_id'] = 1021

        # Extract receipt number
        match = re.search(r"Receipt\s+#(\d+)", self.text)
        if match:
            result['invoice_number'] = match.group(1)

        # Extract date
        match = re.search(r"\b\w{6,9},\s+(\d{2}/\d{2}/\d{4})", self.text)
        if match:
            result['date'] = match.group(1)

        # Extract total from Credit Card Payment line
        for i, line in enumerate(self.lines):
            if "Credit Card Payment:" in line and "Visa" in line:
                amount_match = re.search(r"\$?(\d+\.\d{2})", line)
                if not amount_match and i + 1 < len(self.lines):
                    amount_match = re.search(r"\$?(\d+\.\d{2})", self.lines[i + 1])
                if amount_match:
                    result['total'] = amount_match.group(1)
                    result['subtotal'] = result['total']
                    print(f"[🧾 CARD MATCH] Found Visa payment → total = {result['total']}")
                    break

        # Convert taxes to old format for compatibility
        result['tax'] = None
        del result['taxes']

        return result


# ----------------------------
# Klaviyo Parser
# ----------------------------
class KlaviyoParser(BaseParser):
    vendor_name = "Klaviyo"

    def parse(self):
        result = self.create_base_result()

        # Extract invoice number
        match = re.search(r"Invoice number\s+([A-Z0-9\-]+)", self.text, re.IGNORECASE)
        if match:
            result['invoice_number'] = match.group(1)

        # Extract date
        match = re.search(r"Date of issue\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", self.text)
        if match:
            try:
                date_obj = datetime.strptime(match.group(1), "%B %d, %Y")
                result['date'] = date_obj.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Extract tax
        tax_amount = self.extract_amount(r"GST.*?\$?(\d+[.,]\d{2})")

        # Extract total
        result['total'] = self.extract_amount(r"Amount due.*?\$?(\d+[.,]\d{2})")

        # Convert to old format for compatibility
        result['tax'] = tax_amount
        del result['taxes']

        return result


# ----------------------------
# Home Depot Parser
# ----------------------------
class HomeDepotParser(BaseParser):
    vendor_name = "Home Depot"

    def parse(self):
        import hashlib
        result = self.create_base_result()

        # Generate hash-based invoice number
        result['invoice_number'] = hashlib.md5(self.text.encode()).hexdigest()[:10]

        # Extract date
        result['date'] = self.extract_date([r"(\d{2}/\d{2}/\d{4})"])

        # Extract subtotal and total
        result['subtotal'] = self.extract_amount(r"SUBTOTAL.*?(\d+[.,]\d{2})")
        result['total'] = self.extract_amount(r"TOTAL.*?(\d+[.,]\d{2})")

        # Convert to old format for compatibility
        result['tax'] = None
        del result['taxes']

        return result


# ----------------------------
# U-Haul Parser
# ----------------------------
class UHaulParser(BaseParser):
    vendor_name = "U-Haul"

    def parse(self):
        result = self.create_base_result()
        result['account_id'] = 1012  # U-Haul account

        # Extract contract number
        match = re.search(r"Contract\s+(?:No|Mo)[:\s]*(\d+)", self.text, re.IGNORECASE)
        if match:
            result['invoice_number'] = match.group(1)

        # Extract date - "Tuesday, 11/18/2025 2:05 PM"
        date_match = re.search(
            r"(?:Tuesday|Monday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+(\d{1,2}/\d{1,2}/\d{4})", self.text)
        if date_match:
            result['date'] = date_match.group(1)

        # Extract subtotal
        result['subtotal'] = self.extract_amount(r"Subtotal:\s*\$?([0-9,]+\.\d{2})")

        # Extract total - look for "Total Rental Charges"
        total_match = self.extract_amount(r"Total Rental Charges:\s*\$([0-9,]+\.\d{2})")
        if total_match:
            result['total'] = total_match

        # Fallback: try "Credit Card Payment" or "Net Paid Today"
        if not result['total']:
            result['total'] = self.extract_amount(r"(?:Credit Card Payment|Net Paid Today):\s*\$?([0-9,]+\.\d{2})")

        # Extract tax
        tax_amount = self.extract_amount(r"Rental Tax:\s*\$?([0-9,]+\.\d{2})")

        # If subtotal not found, calculate it from total - tax
        if not result['subtotal'] and result['total'] and tax_amount:
            try:
                result['subtotal'] = f"{float(result['total']) - float(tax_amount):.2f}"
            except:
                pass

        # Convert to old format for compatibility
        result['tax'] = tax_amount
        del result['taxes']

        return result


# ----------------------------
# Google Workspace Parser
# ----------------------------
class GoogleWorkspaceParser(BaseParser):
    vendor_name = "Google Workspace"

    def parse(self):
        result = self.create_base_result()

        # Extract invoice number - more flexible pattern
        match = re.search(r"Invoice number[:\s.]*(\d+)", self.text, re.IGNORECASE)
        if match:
            result['invoice_number'] = match.group(1)

        # Extract date - look for "Oct 31, 2025" format after dots
        # The OCR has it on a separate line after dots
        date_match = re.search(r"\.{5,}\s*\n\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", self.text)
        if date_match:
            try:
                date_obj = datetime.strptime(date_match.group(1), "%b %d, %Y")
                result['date'] = date_obj.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Fallback: try to find date labeled as "Invoice date"
        if not result['date']:
            date_match = re.search(r"Invoice date[:\s.]*\n?\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", self.text)
            if date_match:
                try:
                    date_obj = datetime.strptime(date_match.group(1), "%b %d, %Y")
                    result['date'] = date_obj.strftime("%Y-%m-%d")
                except ValueError:
                    pass

        # Extract subtotal - handle both formats
        result['subtotal'] = self.extract_amount(r"Subtotal in CAD\s+CA\$?([0-9,]+\.\d{2})")
        if not result['subtotal']:
            # Try without "in CAD"
            result['subtotal'] = self.extract_amount(r"Subtotal\s+CA\$?([0-9,]+\.\d{2})")

        # Extract total - handle multiple patterns
        result['total'] = self.extract_amount(r"Total in CAD\s+CA\$?([0-9,]+\.\d{2})")
        if not result['total']:
            # Try the shorter pattern at the end
            result['total'] = self.extract_amount(r"Total\s+CA\$?([0-9,]+\.\d{2})")

        # If subtotal not found, use total as subtotal
        if not result['subtotal'] and result['total']:
            result['subtotal'] = result['total']

        # Extract tax (usually 0% for Google Workspace)
        tax_match = re.search(r"Tax\s+\((\d+)%\)\s+CA\$?([0-9,]+\.\d{2})", self.text)
        if tax_match and float(tax_match.group(2)) > 0:
            result['taxes'].append({
                "name": "Tax",
                "rate": float(tax_match.group(1)),
                "amount": tax_match.group(2).replace(',', '')
            })

        # If no taxes or tax is 0, convert to old format
        if not result['taxes'] or all(float(t['amount']) == 0 for t in result['taxes']):
            result['tax'] = None
            del result['taxes']

        return result


# ----------------------------
# Generic Visa Receipt Parser
# ----------------------------
class VisaReceiptParser(BaseParser):
    vendor_name = None  # Will be determined dynamically

    def parse(self):
        import hashlib
        result = self.create_base_result()

        # Extract total
        result['total'] = self.extract_amount(r"TOTAL\s*\$?\s*(\d+[.,]\d{2})")
        if not result['total']:
            result['total'] = self.extract_amount(r"(?:VISA TEND|Amount).*?\$?(\d+[.,]\d{2})")
        if not result['total']:
            result['total'] = self.find_max_amount()

        # Extract tax
        tax_patterns = [
            r"HST\s+\d+%\s+(\d+[.,]\d{2})",
            r"TAX\s*\$?\s*(\d+[.,]\d{2})"
        ]
        for pattern in tax_patterns:
            tax_amount = self.extract_amount(pattern)
            if tax_amount:
                break

        # Extract date
        result['date'] = self.extract_date()

        # Match vendor from known vendors or guess
        matched_vendor, matched_account = match_known_vendor(self.text, KNOWN_VENDORS)
        result['vendor'] = matched_vendor or self.guess_vendor_from_text()

        if matched_account:
            result['account_id'] = matched_account

        # Generate fallback invoice number
        result['invoice_number'] = hashlib.md5(self.text.encode()).hexdigest()[:10]

        # Convert to old format for compatibility
        result['tax'] = tax_amount if 'tax_amount' in locals() else None
        del result['taxes']

        return result


# ----------------------------
# Parser Factory
# ----------------------------
class ParserFactory:
    """Factory class to determine which parser to use"""

    @staticmethod
    def get_parser(text):
        """Return appropriate parser based on text content"""
        text_lower = text.lower()

        # U-Haul detection - handle bad OCR like "LJ 'HAL" or "UHAL"
        if any(pattern in text_lower for pattern in
               ["u-haul", "uhaul", "u haul", "'hal", "contract no:", "contract mo:"]):
            return UHaulParser(text)
        elif "google workspace" in text_lower or "google llc" in text_lower:
            return GoogleWorkspaceParser(text)
        elif "pirate ship" in text_lower or "arrrr" in text_lower:
            return PirateShipParser(text)
        elif "klaviyo" in text_lower:
            return KlaviyoParser(text)
        elif "home depot" in text_lower:
            return HomeDepotParser(text)
        elif "shopify" in text_lower:
            return ShopifyParser(text)
        elif "visa" in text_lower or "visa tend" in text_lower:
            return VisaReceiptParser(text)
        else:
            return VisaReceiptParser(text)  # Generic fallback


# ----------------------------
# Main Processing Loop
# ----------------------------
if __name__ == "__main__":
    for ocr_file in INPUT_DIR.glob("*.ocr.json"):
        try:
            # Load OCR data
            with open(ocr_file, 'r') as f:
                data = json.load(f)
            raw_text = data.get("text", "")

            # Get appropriate parser and parse
            parser = ParserFactory.get_parser(raw_text)
            parsed = parser.parse()

            # Determine parser type for logging
            parser_type = parser.__class__.__name__.replace("Parser", "")
            print(f"🔍 Parsed {parser_type} invoice: {ocr_file.name} -> {parsed}")

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

        except Exception as e:
            print(f"❌ Error processing {ocr_file.name}: {e}")
            continue