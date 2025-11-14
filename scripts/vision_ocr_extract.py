import fitz  # PyMuPDF
import os
import io
import json
from google.cloud import vision
from PIL import Image
from pathlib import Path

from dotenv import load_dotenv
import os

load_dotenv()

INVOICE_INPUT_FOLDER = os.getenv("INVOICE_INPUT_FOLDER", "Visa_4051")
INPUT_FOLDER = Path(__file__).resolve().parent.parent / 'input' / 'inbox' / INVOICE_INPUT_FOLDER
OUTPUT_FOLDER = "../output"

def process_image(file_path):
    print(f"🔍 Processing: {file_path}")
    base_filename = os.path.basename(file_path)
    output_filename = os.path.splitext(base_filename)[0] + ".gcv.json"
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)

    if file_path.lower().endswith(".pdf"):
        print("📄 Detected PDF, extracting text with PyMuPDF...")
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()

        if not text.strip():
            print("❌ No text found in PDF.")
            return

        # Extract folder name as card info
        card_used = Path(file_path).parent.name  # Example: Visa_4051

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "text": text,
                "card_used": card_used
            }, f, indent=2)

        print(f"✅ Text extracted and saved: {output_filename}")
    else:
        print("🖼️ Detected image, using Google Vision OCR...")
        client = vision.ImageAnnotatorClient()
        with io.open(file_path, 'rb') as image_file:
            content = image_file.read()

        image = vision.Image(content=content)
        response = client.text_detection(image=image)
        texts = response.text_annotations

        if not texts:
            print("❌ No text found in image.")
            return

        full_text = texts[0].description

        # Extract folder name as card info
        card_used = Path(file_path).parent.name  # Example: Visa_4051

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "text": full_text,
                "card_used": card_used
            }, f, indent=2)

        print(f"✅ OCR saved: {output_filename}")

def main():
    for file in os.listdir(INPUT_FOLDER):
        if file.lower().endswith((".jpg", ".jpeg", ".png", ".pdf")):
            process_image(str(INPUT_FOLDER / file))

if __name__ == "__main__":
    main()