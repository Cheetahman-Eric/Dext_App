# export_odoo_vendors.py
import xmlrpc.client
import json

ODOO_URL = "https://cheetahman-eric-kandies-world-canada.odoo.com"
ODOO_DB = "cheetahman-eric-kandies-world-canada-main-17627416"
ODOO_USERNAME = "eric@kandiesworld.com"
ODOO_PASSWORD = "Kandies69$$"  # Replace with your real app password

common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD, {})
models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

# Only vendors that are companies
domain = [
    ['supplier_rank', '>', 0],         # Vendors
    ['is_company', '=', True]          # Only companies (not individuals)
]

vendors = models.execute_kw(
    ODOO_DB, uid, ODOO_PASSWORD,
    'res.partner', 'search_read',
    [domain],
    {'fields': ['name'], 'limit': 1000}
)

vendor_dict = {
    v['name'].strip().lower(): v['name'].strip()
    for v in vendors if v.get('name')
}

with open("known_vendors.json", "w") as f:
    json.dump(vendor_dict, f, indent=2)

print(f"✅ Exported {len(vendor_dict)} vendor names to known_vendors.json (companies only)")