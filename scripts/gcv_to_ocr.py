import os
import json
from pathlib import Path

INPUT_DIR = Path(__file__).resolve().parent.parent / 'output'

def convert_gcv_to_ocr(gcv_path):
    with open(gcv_path, 'r') as f:
        gcv_data = json.load(f)

    # Detect new or old format
    if "textAnnotations" in gcv_data:
        # OLD format from Google Vision
        text = gcv_data.get("textAnnotations", [{}])[0].get("description", "")
    elif "text" in gcv_data:
        # NEW format from vision_ocr_extract.py
        text = gcv_data.get("text", "")
    else:
        print(f"⚠️ No recognizable text found in: {gcv_path.name}")
        text = ""

    output_data = {"text": text}

    # 🏷️ Preserve the card_used tag if available
    if "card_used" in gcv_data:
        output_data["card_used"] = gcv_data["card_used"]
    else:
        # Fallback: Try to infer from folder name
        if "visa_" in str(gcv_path).lower():
            folder_name = gcv_path.parent.name
            if "visa_" in folder_name.lower():
                output_data["card_used"] = folder_name.replace("_", " ").title()

    output_path = gcv_path.with_name(gcv_path.stem + ".ocr.json")
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"✅ Saved OCR output to: {output_path.name}")

for gcv_file in INPUT_DIR.glob("*.gcv.json"):
    convert_gcv_to_ocr(gcv_file)