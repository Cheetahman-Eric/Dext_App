#!/bin/bash

# Define paths
PROCESS_FOLDER="to_process"
DONE_FOLDER="processed"

cd "$(dirname "$0")"

echo "🚀 Starting DEXT OCR to Odoo pipeline..."
echo "🧹 Cleaning up previous OCR output..."
rm -f ../output/*.json

echo "📝 Step 1: OCR Extraction (PyMuPDF/Tesseract)..."
python ocr_extract.py || echo "⚠️ ocr_extract.py had errors"

echo "📝 Step 2: Google Vision OCR..."
python vision_ocr_extract.py || echo "⚠️ vision_ocr_extract.py had errors"

echo "📝 Step 3: Convert GCV to OCR format..."
python gcv_to_ocr.py || echo "⚠️ gcv_to_ocr.py had errors"

echo "📝 Step 4: Parse OCR text..."
python parse_ocr_text_combined.py || echo "⚠️ parse_ocr_text_combined.py had errors"

echo "📝 Step 5: Upload to Odoo..."
python odoo_post_vendor_bill.py || echo "⚠️ odoo_post_vendor_bill.py had errors"

# Exit status
if [ $? -eq 0 ]; then
  echo "✅ Pipeline completed successfully."
else
  echo "❌ Pipeline encountered an error."
fi