import os
import xmlrpc.client
from dotenv import load_dotenv

load_dotenv()

ODOO_URL = os.getenv("ODOO_URL")
ODOO_DB = os.getenv("ODOO_DB")
ODOO_USERNAME = os.getenv("ODOO_USERNAME")
ODOO_API_KEY = os.getenv("ODOO_API_KEY")

# Connect to Odoo
common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
uid = common.authenticate(ODOO_DB, ODOO_USERNAME, ODOO_API_KEY, {})
models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

print("🔍 Searching for waiting pickings from Las Vegas...")

# Step 1: Get pickings in "waiting" state from LV warehouse (location_id = 101 assumed)
picking_ids = models.execute_kw(ODOO_DB, uid, ODOO_API_KEY,
    'stock.picking', 'search',
    [[
        ('state', '=', 'confirmed'),
        ('location_id', '=', 101),  # LV internal location
        ('picking_type_code', '=', 'outgoing')
    ]])

print(f"🔎 Found {len(picking_ids)} waiting pickings from Las Vegas.")

for picking_id in picking_ids:
    picking = models.execute_kw(ODOO_DB, uid, ODOO_API_KEY,
        'stock.picking', 'read', [picking_id],
        {'fields': ['name', 'origin', 'scheduled_date']})[0]

    print(f"\n📦 {picking['name']} | Origin: {picking['origin']} | Scheduled: {picking['scheduled_date']}")

    # Step 2: Read the stock moves
    moves = models.execute_kw(ODOO_DB, uid, ODOO_API_KEY,
        'stock.move', 'search_read',
        [[('picking_id', '=', picking_id)]],
        {'fields': ['id', 'product_id', 'product_uom_qty', 'quantity_done', 'state']})

    updates_needed = False
    for move in moves:
        if move['state'] in ('confirmed', 'assigned') and move['quantity_done'] == 0 and move['product_uom_qty'] > 0:
            models.execute_kw(ODOO_DB, uid, ODOO_API_KEY,
                'stock.move', 'write',
                [[move['id']], {'quantity_done': move['product_uom_qty']}])
            print(f"✅ Updated quantity_done for {move['product_id'][1]} to {move['product_uom_qty']}")
            updates_needed = True
        else:
            print(f"✔️ Already OK: {move['product_id'][1]}")

    # Step 3: Validate the delivery if any updates were made
    if updates_needed:
        try:
            models.execute_kw(ODOO_DB, uid, ODOO_API_KEY,
                'stock.picking', 'button_validate', [[picking_id]])
            print("🎉 Delivery validated.")
        except Exception as e:
            print(f"❌ Error validating picking {picking['name']}: {str(e)}")
    else:
        print("⚠️ No updates needed. Skipping validation.")