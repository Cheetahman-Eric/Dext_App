#!/bin/bash

# $1 is Category, $2 is Card
CATEGORY_ID=$1
CARD_NAME=$2

# Ensure we are in the scripts directory
cd "$(dirname "$0")"

echo "🚀 Starting DEXT OCR to Odoo pipeline"
echo "📂 Category ID: $CATEGORY_ID"
echo "💳 Payment Method: $CARD_NAME"

echo "🧹 Cleaning up previous OCR output..."
rm -f ../output/*.json

echo "📝 Step 1-3: OCR Extraction..."
python ocr_extract.py
python vision_ocr_extract.py
python gcv_to_ocr.py

echo "📝 Step 4: Parse OCR text..."
python parse_ocr_text_combined.py

echo "📝 Step 5: Upload to Odoo..."
# PASS BOTH TO THE FINAL SCRIPT
python odoo_post_vendor_bill.py "$CATEGORY_ID" "$CARD_NAME"