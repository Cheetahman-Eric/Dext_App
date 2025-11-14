import json
import re
from pathlib import Path
from datetime import date

INPUT_DIR = Path(__file__).resolve().parent.parent / 'output'
OUTPUT_DIR = INPUT_DIR

# Simple helper to find the first match
def search(pattern, text, flags=0):
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match and match.lastindex else match.group(0).strip() if match else None

def parse_text(text):
    # Try to find GST and QST explicitly (fallback to TPS/TVQ/VAT if missing)
    gst = search(r"GST(?:\s*(?:Tax|Tac))?\s*[:\-]?\s*\$?\s*(\d+[.,]?\d{0,2})", text, re.IGNORECASE)
    qst = search(r"QST(?:\s*(?:Tax|Tac))?\s*[:\-]?\s*\$?\s*(\d+[.,]?\d{0,2})", text, re.IGNORECASE)
    if gst or qst:
        tax_total = 0.0
        for t in (gst, qst):
            if t:
                normalized = float(t.replace(",", "."))
                tax_total += normalized / 100 if normalized > 100 else normalized
    else:
        taxes = re.findall(r"(?:TPS|TVQ|VAT|GST|QST)[^\d]{0,10}(\d+[.,]?\d{0,2})", text, re.IGNORECASE)
        tax_total = sum(
            float(t.replace(",", ".")) / 100 if len(t.replace(",", "").replace(".", "")) > 4 else float(t.replace(",", "."))
            for t in taxes
        ) if taxes else None

    vendor = search(r"(BoomBoom Naturals Inc\.|BoomBoom Naturals|La Belle et La Boeuf)", text, re.IGNORECASE)
    if not vendor:
        vendor = search(r"^[A-Z][a-zA-Z\s&éèêàçôùîï]+", text)

    # Normalize known vendor names
    if vendor:
        vendor = vendor.strip()
        if "S&S Canada" in vendor:
            vendor = "S&S Canada"

    invoice_date = search(r"(?:Invoice Date|Date|Invoice Dated)[:\s]*([0-9]{4}[-/][0-9]{2}[-/][0-9]{2}|[0-9]{2}/[0-9]{2}/[0-9]{4})", text)
    if not invoice_date:
        invoice_date = search(r"([0-9]{2}/[0-9]{2}/[0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2})", text)

    invoice_number = search(r"(KWOR[0-9\-]+)", text)
    if not invoice_number:
        invoice_number = search(r"(?:Receipt\s*[:#]?\s*|REÇU\s*[:#]?\s*)([A-Z0-9\-]+)", text, re.IGNORECASE)
    if not invoice_number:
        invoice_number = search(r"(?:Invoice\s*[:#]?\s*)([0-9\-]+)", text, re.IGNORECASE)

    total = search(r"(?:Invoice Total \(USD\)|Order Total|Total|Amount|Amount Due|Subtotal|Sub Total)[^\d]*([\d,]+\.\d{2})", text, re.IGNORECASE)
    if not total:
        total = search(r"\nTOTAL\n\$\s*([\d,]+\.\d{2})", text)

    if not invoice_date:
        invoice_date = date.today().isoformat()

    if vendor == "BoomBoom Naturals Inc.":
        tax_total = 0.0

    parsed_data = {
        "vendor": vendor,
        "date": invoice_date,
        "invoice_number": invoice_number,
        "total": total,
        "tax": tax_total
    }

    print("🔍 Parsed fields:", parsed_data)
    return parsed_data

def main():
    for json_file in list(INPUT_DIR.glob("*.ocr.json")) + list(INPUT_DIR.glob("*.gcv.json")):
        parsed_file = OUTPUT_DIR / f"{json_file.stem.replace('.ocr', '').replace('.gcv', '')}.parsed.json"
        if parsed_file.exists():
            print(f"⏭️ Skipping {json_file.name} (already parsed)")
            continue

        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if json_file.suffixes[-2:] == ['.gcv', '.json']:
            try:
                raw_text = data["text"] if "text" in data else data["responses"][0]["fullTextAnnotation"]["text"]
            except (KeyError, IndexError):
                print(f"❌ No text found in: {json_file.name}")
                continue
        else:
            raw_text = data.get("text", "")

        # Infer card info from parent folder name (e.g., "Visa 6109")
        parent_folder = json_file.parent.name
        match = re.search(r"(visa|mastercard|amex|discover)?\s*(\d{4})", parent_folder, re.IGNORECASE)
        if match:
            brand = match.group(1).title() if match.group(1) else "Card"
            suffix = match.group(2)
            folder_card = f"{brand} ****{suffix}"
        else:
            folder_card = None

        parsed = parse_text(raw_text)

        if folder_card:
            parsed["card"] = folder_card

        with open(parsed_file, "w", encoding="utf-8") as f:
            json.dump(parsed, f, indent=2)

        if not any(parsed.values()):
            print(f"⚠️ Nothing parsed from: {json_file.name}")
        else:
            print(f"✅ Parsed: {parsed_file.name}")

if __name__ == "__main__":
    main()