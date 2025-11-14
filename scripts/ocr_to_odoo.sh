#!/bin/bash

# Define paths
PROCESS_FOLDER="to_process"
DONE_FOLDER="processed"

cd "$(dirname "$0")"

echo "🚀 Starting DEXT OCR to Odoo pipeline..."
echo "🧹 Cleaning up previous OCR output..."
rm -f ../output/*.json

python vision_ocr_extract.py
python gcv_to_ocr.py                # 🧠 <-- This was missing!
python ocr_extract.py
python parse_ocr_text_combined.py
python odoo_post_vendor_bill.py

# Exit status
if [ $? -eq 0 ]; then
  echo "✅ Pipeline completed successfully."
else
  echo "❌ Pipeline encountered an error."
fi