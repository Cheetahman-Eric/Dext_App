import fitz  # PyMuPDF
import os
import io
import json
from google.cloud import vision
from PIL import Image
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- GOOGLE AUTHENTICATION ---
# Pointing to the specific folder 'google vision' where your JSON key lives
KEY_FILE = Path(__file__).resolve().parent.parent / "google vision" / "odoo-receipt-ocr-484d2f7fa5c1.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(KEY_FILE)

# --- FOLDERS ---
# Root DEXT/input and DEXT/output
INPUT_FOLDER = Path(__file__).resolve().parent.parent / 'input'
OUTPUT_FOLDER = Path(__file__).resolve().parent.parent / 'output'


def process_image(file_path):
    print(f"🔍 Processing: {file_path}")
    base_filename = os.path.basename(file_path)
    # We save as .gcv.json so the next step (gcv_to_ocr.py) recognizes it
    output_filename = os.path.splitext(base_filename)[0] + ".gcv.json"
    output_path = OUTPUT_FOLDER / output_filename

    # Ensure output directory exists
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    if file_path.lower().endswith(".pdf"):
        print("📄 Detected PDF, extracting text with PyMuPDF...")
        try:
            doc = fitz.open(file_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()

            if not text.strip():
                print("❌ No text found in PDF.")
                return

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump({"text": text, "card_used": "Mobile Upload"}, f, indent=2)

            print(f"✅ Text extracted and saved: {output_filename}")
        except Exception as e:
            print(f"❌ PDF Processing Error: {e}")

    else:
        print("🖼️ Detected image, using Google Vision OCR...")
        try:
            client = vision.ImageAnnotatorClient()
            with io.open(file_path, 'rb') as image_file:
                content = image_file.read()

            image = vision.Image(content=content)
            response = client.text_detection(image=image)
            texts = response.text_annotations

            if not texts:
                print("❌ No text found in image.")
                return

            # The first element contains the entire block of text found
            full_text = texts[0].description

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump({"text": full_text, "card_used": "Mobile Upload"}, f, indent=2)

            print(f"✅ OCR saved: {output_filename}")
        except Exception as e:
            print(f"❌ Google Vision API Error: {e}")


def main():
    if not INPUT_FOLDER.exists():
        print(f"❌ Input folder missing: {INPUT_FOLDER}")
        return

    # Scan the input folder for new files
    files_found = False
    for file in os.listdir(INPUT_FOLDER):
        file_path = INPUT_FOLDER / file
        if file_path.is_file() and file.lower().endswith((".jpg", ".jpeg", ".png", ".pdf")):
            process_image(str(file_path))
            files_found = True

    if not files_found:
        print("📁 No files found in the input folder to process.")


if __name__ == "__main__":
    main()