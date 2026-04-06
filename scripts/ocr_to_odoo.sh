#!/bin/bash

# Récupération des arguments envoyés par le Bridge
CAT_ID=$1
CARD_NAME=$2
REGION=$3

echo "------------------------------------------"
echo "🛠️  PIPELINE START"
echo "📂 Base Dir: $(pwd)"
echo "🌍 Région reçue par le SH : $REGION"
echo "------------------------------------------"

# Step 1: Google Vision OCR
echo "🔍 Step 1: Google Vision..."
# CORRECTION : Nom exact selon ton screenshot
python3 scripts/vision_ocr_extract.py
echo "------------------------------------------"

# Step 2: Formatting
echo "🔄 Step 2: Formatting..."
python3 scripts/gcv_to_ocr.py
echo "------------------------------------------"

# Step 3: Parsing
echo "🧠 Step 3: Parsing..."
python3 scripts/parse_ocr_text_combined.py "$REGION"
echo "------------------------------------------"

# Step 4: Odoo Posting
echo "🧾 Step 4: Odoo Posting..."
python3 scripts/odoo_post_vendor_bill.py "$CAT_ID" "$CARD_NAME" "$REGION"

echo "------------------------------------------"
echo "✅ FINISHED"
echo "------------------------------------------"