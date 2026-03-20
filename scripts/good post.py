import json
import xmlrpc.client
from pathlib import Path
from datetime import datetime, date
import base64
import sys
import re
import os

# Odoo connection setup
ODOO_URL = "https://cheetahman-eric-kandies-world-canada.odoo.com"
ODOO_DB = "cheetahman-eric-kandies-world-canada-main-17627416"
ODOO_USERNAME = "eric@kandiesworld.com"
ODOO_PASSWORD = "20a792fc10db3831805e2d7f38d6f6617beb6908"

# Catch the Category ID from the command line (sent by ocr_to_odoo.sh)
passed_category_id = sys.argv[1] if len(sys.argv) > 1 else None

INPUT_DIR = Path(__file__).resolve().parent.parent / 'output'

common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common", allow_none=True)
uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD, {})
models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object", allow_none=True)

print(f"🔐 Authenticated as {ODOO_USERNAME} (uid={uid})")


def parse_date_safe(date_str):
    if not date_str:
        return date.today().isoformat()
    try:
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
            card_suffix = ""
            lines = text.splitlines()
            for i, line in enumerate(lines):
                line_lower = line.lower()
                if "account number" in line_lower and re.search(r"\*{2,4}\s*\d{4}", line):
                    card_suffix = line.strip()
                    break
                elif re.search(r"\*{2,4}\s*\d{4}", line):
                    next_lines = lines[i + 1:i + 3]
                    for next_line in next_lines:
                        if re.search(r"(visa|mastercard|amex|discover)", next_line, re.IGNORECASE):
                            card_suffix = f"{next_line.strip()} {line.strip()}"
                            break
                    if card_suffix:
                        break
                elif re.search(r"(visa|mastercard|amex|discover)", line, re.IGNORECASE):
                    for j in range(i + 1, min(i + 3, len(lines))):
                        if re.search(r"\*{2,4}\s*\d{4}", lines[j]):
                            card_suffix = f"{line.strip()} {lines[j].strip()}"
                            break
                    if card_suffix:
                        break
            if not card_suffix:
                match = re.search(r"(\*{2,4}\s*\d{4})", text)
                if match:
                    card_suffix = match.group(1).replace(' ', '')
            if card_suffix:
                data["card"] = card_suffix

    if not data.get("invoice_number") or not data.get("total"):
        print(f"⚠️ Skipping {parsed_file.name}: missing key fields (invoice_number or total)")
        continue

    # Vendor Logic
    vendor_id = None
    vendor_name = ""

    if passed_category_id and passed_category_id.isdigit():
        vendor_id = int(passed_category_id)
        vendor_data = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'read', [[vendor_id], ['name']])
        if vendor_data:
            vendor_name = vendor_data[0]['name']
            print(f"🎯 Category Mode: Using Fixed Odoo Contact '{vendor_name}' (ID {vendor_id})")
    else:
        vendor_info = data.get("vendor")
        if isinstance(vendor_info, list):
            vendor_info = vendor_info[0] if vendor_info else None
        vendor_name = vendor_info.strip() if isinstance(vendor_info, str) else None

        if not vendor_name:
            print(f"⚠️ Skipping {parsed_file.name}: missing vendor name and no Category ID provided.")
            continue

        vendor_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'search',
                                       [[['name', '=', vendor_name]]])
        if vendor_ids:
            vendor_id = vendor_ids[0]
            print(f"📌 Found vendor '{vendor_name}' with ID {vendor_id}")
        else:
            vendor_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.partner', 'create', [{
                'name': vendor_name,
                'supplier_rank': 1,
            }])
            print(f"➕ Created new vendor '{vendor_name}' with ID {vendor_id}")

    card_suffix = data.get("card", "").strip()
    fallback_account_id = 1022
    account_id = data.get("account_id", fallback_account_id)

    subtotal = data.get("subtotal")
    total = data.get("total")
    price_unit_str = subtotal if subtotal else total

    if not price_unit_str:
        continue

    try:
        price_unit = float(str(price_unit_str).replace(",", ""))
    except (ValueError, AttributeError):
        continue

    invoice_line = {
        'product_id': data.get('product_id', 6053),
        'name': data.get('product', "Web expense product"),
        'quantity': 1,
        'price_unit': price_unit,
        'account_id': account_id,
    }

    # Tax Handling
    matched_tax_ids = []
    if "taxes" in data and isinstance(data["taxes"], list):
        for tax_item in data["taxes"]:
            tax_rate = tax_item.get("rate")
            if tax_rate:
                try:
                    tax_rate_f = float(tax_rate)
                    all_taxes = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'account.tax', 'search_read',
                                                  [[['company_id', '=', 6], ['type_tax_use', '=', 'purchase']]],
                                                  {'fields': ['id', 'amount']})
                    for tax in all_taxes:
                        if abs(tax['amount'] - tax_rate_f) < 0.1:
                            matched_tax_ids.append(tax['id'])
                            break
                except:
                    pass

    if matched_tax_ids:
        invoice_line["tax_ids"] = [(6, 0, matched_tax_ids)]

    invoice_ref = data.get("invoice_number")
    invoice_date = parse_date_safe(data.get("date"))

    # Duplication check
    try:
        domain = [['move_type', '=', 'in_invoice'], ['partner_id', '=', vendor_id], ['ref', '=', invoice_ref]]
        if models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'account.move', 'search', [domain]):
            print(f"⏭️ Bill already exists for '{vendor_name}' ref '{invoice_ref}'. Skipping.")
            continue
    except:
        pass

    # Currency logic
    currency_name = "USD" if vendor_name.lower() == "pirate ship" else "CAD"
    currency_ids = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'res.currency', 'search',
                                     [[('name', '=', currency_name)]])
    currency_id = currency_ids[0] if currency_ids else None

    invoice_lines = [[0, 0, invoice_line]]
    if card_suffix:
        invoice_lines.append([0, 0, {'display_type': 'line_note', 'name': f"Paid with {card_suffix}"}])

    move_vals = {
        'company_id': 6,
        'move_type': 'in_invoice',
        'partner_id': vendor_id,
        'invoice_date': invoice_date,
        'ref': invoice_ref,
        'invoice_line_ids': invoice_lines,
        'currency_id': currency_id,
    }

    move_id = models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'account.move', 'create', [move_vals])
    print(f"🧾 Created vendor bill ID {move_id} for '{vendor_name}'")

    # === UPDATED ATTACHMENT LOGIC ===
    # Grabs the base receipt name (e.g., receipt_uuid)
    original_stem = parsed_file.name.split('.')[0]
    input_dir = Path(__file__).resolve().parent.parent / 'input'

    found_attachment = False
    for match in input_dir.glob(f"{original_stem}*"):
        if match.suffix.lower() in [".pdf", ".jpg", ".jpeg", ".png"]:
            try:
                with open(match, "rb") as img_f:
                    encoded_data = base64.b64encode(img_f.read()).decode('utf-8')

                    ext = match.suffix.lower()
                    mimetype = 'application/pdf' if ext == '.pdf' else f"image/{ext[1:]}"
                    if mimetype == "image/jpg": mimetype = "image/jpeg"

                    models.execute_kw(ODOO_DB, uid, ODOO_PASSWORD, 'ir.attachment', 'create', [{
                        'name': match.name,
                        'res_model': 'account.move',
                        'res_id': move_id,
                        'type': 'binary',
                        'datas': encoded_data,
                        'mimetype': mimetype,
                        'company_id': 6,
                    }])
                print(f"📎 Attached original file: {match.name}")
                found_attachment = True
                break
            except Exception as e:
                print(f"❌ Failed to attach file {match.name}: {e}")

    if not found_attachment:
        print(f"⚠️ No original image found in {input_dir} for {original_stem}")