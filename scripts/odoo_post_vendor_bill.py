import json
import xmlrpc.client
import sys
import base64
from pathlib import Path
from datetime import date

# --- CONFIGURATION ODOO ---
URL = "https://cheetahman-eric-kandies-world-canada.odoo.com"
DB = "cheetahman-eric-kandies-world-canada-main-17627416"
USER = "eric@kandiesworld.com"
PASS = "20a792fc10db3831805e2d7f38d6f6617beb6908"

# --- ARGUMENTS ---
PASSED_PRODUCT_ID = sys.argv[1] if len(sys.argv) > 1 else "8101"
PASSED_CARD = sys.argv[2] if len(sys.argv) > 2 else "Not Specified"
REGION = sys.argv[3] if len(sys.argv) > 3 else "CAN"

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"

MAPPING = {
    "8101": 14959, "8102": 14960, "8103": 14961,
    "8104": 14962, "8105": 14963, "8106": 14964, "8107": 14965
}


def post_to_odoo():
    common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
    uid = common.authenticate(DB, USER, PASS, {})
    models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

    USD_ID = 1
    CAD_ID = 3
    final_vendor_id = MAPPING.get(PASSED_PRODUCT_ID, 14959)

    parsed_files = list(OUTPUT_DIR.glob("*.parsed.json"))

    for p_file in parsed_files:
        print(f"📦 Traitement de {p_file.name}...")
        with open(p_file, "r") as f:
            data = json.load(f)

        total_extracted = float(data.get("total", 0))

        extracted_date = data.get("date")
        if extracted_date:
            bill_date = extracted_date
        else:
            bill_date = date.today().isoformat()
            print(f"🕒 Date non trouvée, utilisation date d'aujourd'hui.")

        tax_ids = []
        price_to_send = total_extracted
        current_region = str(REGION).upper()

        if "USA" in current_region or "US" in current_region:
            final_currency_id = USD_ID
            price_to_send = total_extracted
            print(f"🇺🇸 MODE USA - Date Facture: {bill_date}")
        else:
            final_currency_id = CAD_ID
            try:
                search_taxes = models.execute_kw(DB, uid, PASS, 'account.tax', 'search_read',
                                                 [[['type_tax_use', '=', 'purchase'], ['company_id', '=', 6]]],
                                                 {'fields': ['id', 'amount']})
                for t in search_taxes:
                    if abs(t['amount'] - 5.0) < 0.1 or abs(t['amount'] - 9.975) < 0.1:
                        tax_ids.append(t['id'])
            except:
                pass
            price_to_send = total_extracted / 1.14975
            print(f"🇨🇦 MODE CANADA - Date Facture: {bill_date}")

        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': final_vendor_id,
            'payment_reference': PASSED_CARD,
            'invoice_date': bill_date,
            'company_id': 6,
            'currency_id': final_currency_id,
            'invoice_line_ids': [[0, 0, {
                'product_id': int(PASSED_PRODUCT_ID),
                'name': f"Reçu [{current_region}] - {PASSED_CARD}",
                'quantity': 1,
                'price_unit': price_to_send,
                'tax_ids': [[6, 0, tax_ids]] if (final_currency_id == CAD_ID and tax_ids) else []
            }]]
        }

        try:
            bill_id = models.execute_kw(DB, uid, PASS, 'account.move', 'create', [bill_vals])
            print(f"✅ Facture créée ! ID Odoo: {bill_id} | Date Odoo: {bill_date}")

            stem = p_file.name.replace(".parsed.json", "")
            image_path = None
            for ext in ['.JPG', '.jpg', '.jpeg', '.png', '.PNG']:
                img_test = INPUT_DIR / (stem + ext)
                if img_test.exists():
                    image_path = img_test
                    break

            if image_path:
                with open(image_path, "rb") as img_file:
                    models.execute_kw(DB, uid, PASS, 'ir.attachment', 'create', [{
                        'name': image_path.name, 'res_model': 'account.move', 'res_id': bill_id,
                        'type': 'binary', 'datas': base64.b64encode(img_file.read()).decode('utf-8'),
                    }])
                print(f"📎 Photo attachée.")

            p_file.unlink()
            if image_path: image_path.unlink()

        except Exception as e:
            print(f"❌ Erreur Odoo : {e}")


if __name__ == "__main__":
    post_to_odoo()