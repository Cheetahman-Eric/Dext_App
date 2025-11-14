import json
import xmlrpc.client
from pathlib import Path
from datetime import datetime, date
import base64

# Odoo connection setup
ODOO_URL="https://cheetahman-eric-kandies-world-canada.odoo.com"
ODOO_DB="cheetahman-eric-kandies-world-canada-main-17627416"
ODOO_USERNAME="eric@kandiesworld.com"
ODOO_PASSWORD = "20a792fc10db3831805e2d7f38d6f6617beb6908"

INPUT_DIR = Path(__file__).resolve().parent.parent / 'output'

common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True)
uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD, {})
models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)

print(f"🔐 Authenticated as {ODOO_USERNAME} (uid={uid})")

import re
import os
def parse_date_safe(date_str):
    if not date_str:
        return date.today().isoformat()
    try:
        # Try ISO format first
        return date.fromisoformat(date_str).isoformat()
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(date_str, fmt).date().isoformat()
        except ValueError:
            continue
    print(f"⚠️ Could not parse date '{date_str}', using today.")
    return date.today().isoformat()

# Load all parsed JSONs
for parsed_file in INPUT_DIR.glob("*.ocr.parsed.json"):
    with open(parsed_file, "r") as f:
        data = json.load(f)

    # Load associated OCR text to check for card info
    ocr_file = parsed_file.with_name(parsed_file.stem.replace(".ocr.parsed", "") + ".ocr.json")
    if ocr_file.exists():
        with open(ocr_file, "r") as f_ocr:
            ocr_data = json.load(f_ocr)
            text = ocr_data.get("text", "")
            # Combined strategy to extract card type and suffix from nearby lines
            card_suffix = ""
            lines = text.splitlines()
            for i, line in enumerate(lines):
                line_lower = line.lower()
                if "account number" in line_lower and re.search(r"\*{2,4}\s*\d{4}", line):
                    card_suffix = line.strip()
                    break
                elif re.search(r"\*{2,4}\s*\d{4}", line):
                    next_lines = lines[i+1:i+3]
                    for next_line in next_lines:
                        if re.search(r"(visa|mastercard|amex|discover)", next_line, re.IGNORECASE):
                            card_suffix = f"{next_line.strip()} {line.strip()}"
                            break
                    if card_suffix:
                        break
                elif re.search(r"(visa|mastercard|amex|discover)", line, re.IGNORECASE):
                    for j in range(i+1, min(i+3, len(lines))):
                        if re.search(r"\*{2,4}\s*\d{4}", lines[j]):
                            card_suffix = f"{line.strip()} {lines[j].strip()}"
                            break
                    if card_suffix:
                        break

            if not card_suffix:
                # fallback to just masked digits if nothing else found
                match = re.search(r"(\*{2,4}\s*\d{4})", text)
                if match:
                    card_suffix = match.group(1).replace(' ', '')

            if card_suffix:
                data["card"] = card_suffix

    if not data.get("vendor") or not data.get("invoice_number") or not data.get("total"):
        print(f"⚠️ Skipping {parsed_file.name}: missing key fields")
        continue

    # Step 1: Find or create the vendor
    vendor_info = data.get("vendor")
    if isinstance(vendor_info, list):
        vendor_info = vendor_info[0] if vendor_info else None
    vendor_name = vendor_info.strip() if isinstance(vendor_info, str) else None
    if not vendor_name:
        print(f"⚠️ Skipping {parsed_file.name}: missing vendor name.")
        continue
    vendor_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search', [[['name', '=', vendor_name]]])

    if vendor_ids:
        vendor_id = vendor_ids[0]
        print(f"📌 Found vendor '{vendor_name}' with ID {vendor_id}")
    else:
        vendor_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'create', [{
            'name': vendor_name,
            'supplier_rank': 1,
        }])
        print(f"➕ Created new vendor '{vendor_name}' with ID {vendor_id}")

    # Extract credit card suffix from parsed data
    card_suffix = ""
    if "card" in data:
        card_info = data["card"]
        if isinstance(card_info, str) and len(card_info.strip()) > 0:
            card_suffix = card_info.strip()

    line_name = f"Imported from {parsed_file.name}"
    if card_suffix:
        line_name += f" (Card: {card_suffix})"
    if data.get("card_tag", "").strip():
        line_name += f" [{data.get('card_tag').strip()}]"

    fallback_account_id = 1022  # New fallback account
    account_id = data["account_id"] if "account_id" in data and data["account_id"] else fallback_account_id

    invoice_line = {
        'product_id': data['product_id'] if 'product_id' in data else 6053,
        'name': data['product'] if 'product' in data else "Web expense product",
        'quantity': 1,
        'price_unit': float(data.get("subtotal", data["total"]).replace(",", "")),
        'account_id': account_id,
    }

    tax_data = data.get("tax")
    tax_rate = None
    tax_amount = None

    if isinstance(tax_data, dict):
        tax_rate = tax_data.get("rate")
        tax_amount = tax_data.get("amount")
    elif isinstance(tax_data, str) or isinstance(tax_data, float) or isinstance(tax_data, int):
        tax_rate = tax_data

    if tax_rate:
        try:
            tax_rate_f = float(tax_rate)
            all_taxes = models.execute_kw(
                ODOO_DB, uid, ODOO_PASSWORD, 'account.tax', 'search_read',
                [[['company_id', '=', 6], ['type_tax_use', '=', 'purchase']]],
                {'fields': ['id', 'amount', 'name']}
            )
            tax_id = None
            for tax in all_taxes:
                if abs(tax['amount'] - tax_rate_f) < 0.1:
                    tax_id = tax['id']
                    print(f"🔍 Matched tax: {tax['name']} (ID={tax_id}, Rate={tax['amount']}%)")
                    break
            if tax_id:
                invoice_line["tax_ids"] = [(6, 0, [tax_id])]
            else:
                print(f"❌ No matching tax found for {tax_rate_f}%.")
        except Exception as e:
            print(f"⚠️ Failed to match tax from value '{tax_rate}': {e}")

    invoice_ref = data.get("invoice_number")
    if not invoice_ref:
        print(f"⚠️ Missing invoice number in {parsed_file.name}, skipping to avoid search error.")
        continue

    invoice_date = parse_date_safe(data.get("date"))

    # Check for existing vendor bill with the same invoice number
    try:
        domain = [
            ['move_type', '=', 'in_invoice'],
            ['partner_id', '=', vendor_id],
            ['ref', '=', invoice_ref or '']
        ]
        existing_bills = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'account.move', 'search', [domain])
    except Exception as e:
        print(f"❌ Failed to search for existing bills for '{vendor_name}' with reference '{invoice_ref}': {e}")
        continue
    if existing_bills:
        print(f"⏭️ Vendor bill already exists for '{vendor_name}' with reference '{invoice_ref}'. Skipping.")
        continue

    # Step 2: Create vendor bill
    # Determine currency
    currency_name = "USD" if vendor_name.lower() == "pirate ship" else "CAD"
    currency_ids = models.execute_kw(
        ODOO_DB, uid, ODOO_PASSWORD, 'res.currency', 'search',
        [[('name', '=', currency_name)]],
        {'limit': 1}
    )
    currency_id = currency_ids[0] if currency_ids else None

    invoice_lines = [[0, 0, invoice_line]]

    input_path = str(parsed_file)

    # Add internal note if input_path contains a folder name (but not if 'output')
    if input_path:
        folder_name = os.path.basename(os.path.dirname(input_path))
        if folder_name.lower() != 'output':
            note_text = "Paid with " + folder_name.replace("_", " ").title()
            print(f"📌 Adding internal note: {note_text}")
            invoice_lines.append([0, 0, {
                'display_type': 'line_note',
                'name': note_text
            }])

    # Add internal note with card_suffix if available
    if card_suffix:
        note_text = f"Paid with {card_suffix}"
        print(f"📌 Adding internal note: {note_text}")
        invoice_lines.append([0, 0, {
            'display_type': 'line_note',
            'name': note_text
        }])

    # Add parsed notes if present
    notes = data.get("notes", [])
    for note in notes:
        invoice_lines.append([0, 0, {
            'display_type': 'line_note',
            'name': note
        }])

    # --- Analytic Tag logic for card_suffix ---
    tag_ids = []
    if card_suffix:
        tag_name = card_suffix.strip()
        existing_tags = models.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'account.analytic.tag', 'search_read',
            [[['name', '=', tag_name]]],
            {'fields': ['id'], 'limit': 1}
        )
        if existing_tags:
            tag_ids = [existing_tags[0]['id']]
        else:
            new_tag_id = models.execute_kw(
                ODOO_DB, uid, ODOO_PASSWORD,
                'account.analytic.tag', 'create',
                [{'name': tag_name}]
            )
            tag_ids = [new_tag_id]

    move_vals = {
        'company_id': 6,
        'move_type': 'in_invoice',
        'partner_id': vendor_id,
        'invoice_date': invoice_date,
        'invoice_date_due': invoice_date,
        'ref': invoice_ref,
        'invoice_line_ids': invoice_lines,
        'currency_id': currency_id,
        'narration': f"Paid with {card_suffix}" if card_suffix else False,
    }

    if tag_ids:
        move_vals['analytic_tag_ids'] = [(6, 0, tag_ids)]

    move_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'account.move', 'create', [move_vals])
    print(f"🧾 Created vendor bill ID {move_id} for '{vendor_name}'")

    # Step 3.5: Upload corresponding original PDF as attachment if available
    try:
        pdf_name = parsed_file.name.replace(".ocr.ocr.parsed.json", ".pdf")
        search_root = Path(__file__).resolve().parent.parent / "input" / "inbox"
        pdf_files = list(search_root.rglob(pdf_name))
        if pdf_files:
            with open(pdf_files[0], "rb") as f:
                encoded_pdf = base64.b64encode(f.read()).decode("utf-8")

            attachment_vals = {
                'name': pdf_files[0].name,
                'datas': encoded_pdf,
                'res_model': 'account.move',
                'res_id': move_id,
                'type': 'binary',
                'company_id': 6,
                'mimetype': 'application/pdf',
            }

            pdf_attachment_id = models.execute_kw(
                ODOO_DB, uid, ODOO_PASSWORD,
                'ir.attachment', 'create',
                [attachment_vals]
            )
            print(f"📎 Uploaded original PDF '{pdf_files[0].name}' as attachment (ID {pdf_attachment_id})")
        else:
            print(f"📁 No original PDF found matching {pdf_name}")
    except Exception as e:
        print(f"❌ Failed to attach original PDF: {e}")

    # Step 3: Attach original file if available (pdf/jpg/png)
    parsed_stem = parsed_file.stem.replace(".ocr.ocr.parsed", "")
    possible_extensions = [".pdf", ".jpg", ".jpeg", ".png"]
    matched_file = None

    # Search in the same input folder as the OCR came from
    ocr_origin_dir = Path(__file__).resolve().parent.parent / 'input' / 'inbox'
    for root, dirs, files in os.walk(ocr_origin_dir):
        for f in files:
            f_path = Path(root) / f
            if f_path.suffix.lower() in possible_extensions:
                # Normalize both names
                def normalize_name(name):
                    import unicodedata
                    import re
                    return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKD', name).lower())

                file_stem_normalized = normalize_name(f_path.stem)
                parsed_normalized = normalize_name(parsed_stem)

                if parsed_normalized in file_stem_normalized or file_stem_normalized in parsed_normalized:
                    matched_file = f_path
                    break
        if matched_file:
            break

    if matched_file and matched_file.exists():
        with open(matched_file, "rb") as img_f:
            image_data = img_f.read()

        attachment_vals = {
            'name': matched_file.name.replace("_", " "),
            'res_model': 'account.move',
            'res_id': move_id,
            'type': 'binary',
            'datas': base64.b64encode(image_data).decode('utf-8'),
            'mimetype': f"image/{matched_file.suffix.lower()[1:]}" if matched_file.suffix.lower() != '.pdf' else 'application/pdf',
            'company_id': 6,
        }

        attachment_id = models.execute_kw(
            ODOO_DB, uid, ODOO_PASSWORD,
            'ir.attachment', 'create',
            [attachment_vals]
        )
        print(f"📎 Attached file '{matched_file.name}' to bill ID {move_id}")
    else:
        print(f"📁 No original PDF found matching {parsed_stem}.pdf")