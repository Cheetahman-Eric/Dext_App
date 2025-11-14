import os
import fitz  # PyMuPDF
import pytesseract
import json
from PIL import Image
from pathlib import Path

INPUT_DIR = Path(__file__).resolve().parent.parent / 'input' / 'inbox'
OUTPUT_DIR = Path(__file__).resolve().parent.parent / 'output'

def convert_pdf_to_images(pdf_path):
    images = []
    doc = fitz.open(pdf_path)
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=300)
        img_path = OUTPUT_DIR / f"{pdf_path.stem}_page_{page_num}.png"
        pix.save(img_path)
        images.append(img_path)
    return images

def ocr_image(image_path):
    try:
        with Image.open(str(image_path)) as img:
            return pytesseract.image_to_string(img)
    except Exception as e:
        print(f"❌ Failed to OCR {image_path.name}: {e}")
        # Fallback: try to load Google Vision output
        gcv_path = OUTPUT_DIR / f"{image_path.stem}.gcv.json"
        if gcv_path.exists():
            try:
                with open(gcv_path, 'r', encoding='utf-8') as f:
                    gcv_data = json.load(f)
                    full_text = ""

                    # NEW: First try 'text' directly
                    if 'text' in gcv_data and gcv_data['text'].strip():
                        full_text = gcv_data['text'].strip()

                    # Try textAnnotations[0].description
                    if not full_text and 'textAnnotations' in gcv_data and len(gcv_data['textAnnotations']) > 0:
                        full_text = gcv_data['textAnnotations'][0].get('description', '').strip()

                    # Try full_text_annotation.text
                    if not full_text:
                        full_text = gcv_data.get('full_text_annotation', {}).get('text', '').strip()

                    output_file = OUTPUT_DIR / f"{image_path.stem}.ocr.json"
                    with open(output_file, 'w', encoding='utf-8') as f_out:
                        json.dump({'text': full_text}, f_out, ensure_ascii=False, indent=2)
                    if full_text:
                        print(f"✅ Saved OCR output to: {output_file.name}")
                    else:
                        print(f"⚠️ OCR returned empty text for {image_path.name}, but continuing to save.")
                    return full_text
            except Exception as gcv_err:
                print(f"❌ Failed to read fallback GCV file: {gcv_err}")
        return ""

def process_pdf(pdf_path):
    print(f"Processing: {pdf_path.name}")
    full_text = ""
    if pdf_path.suffix.lower() in [".jpg", ".jpeg", ".png"]:
        full_text = ocr_image(pdf_path)
        if not full_text:
            print(f"⚠️ OCR returned empty text for {pdf_path.name}, but continuing to save.")
    else:
        images = convert_pdf_to_images(pdf_path)
        for image in images:
            text = ocr_image(image)
            full_text += text + "\n"
            os.remove(image)  # Clean up image file
    if full_text:
        output_file = OUTPUT_DIR / f"{pdf_path.stem}.ocr.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({'text': full_text}, f, ensure_ascii=False, indent=2)
        print(f"Saved OCR output to: {output_file.name}")

def main():
    if not OUTPUT_DIR.exists():
        OUTPUT_DIR.mkdir(parents=True)
    for file in INPUT_DIR.glob("*"):
        if file.suffix.lower() in [".pdf", ".jpg", ".jpeg", ".png"]:
            process_pdf(file)

if __name__ == "__main__":
    main()