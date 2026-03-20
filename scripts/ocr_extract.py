import os
import fitz  # PyMuPDF
import pytesseract
import json
from PIL import Image
from pathlib import Path

INPUT_DIR = Path(__file__).resolve().parent.parent / 'input'
OUTPUT_DIR = Path(__file__).resolve().parent.parent / 'output'


def extract_text_with_pymupdf(pdf_path):
    """Try to extract text directly from PDF using PyMuPDF"""
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        return text.strip()
    except Exception as e:
        print(f"❌ PyMuPDF failed for {pdf_path.name}: {e}")
        return ""


def convert_pdf_to_images(pdf_path):
    """Convert PDF pages to images for OCR"""
    images = []
    try:
        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            pix = page.get_pixmap(dpi=300)
            img_path = OUTPUT_DIR / f"{pdf_path.stem}_page_{page_num}.png"
            pix.save(img_path)
            images.append(img_path)
    except Exception as e:
        print(f"❌ Failed to convert PDF to images: {e}")
    return images


def ocr_image(image_path):
    """OCR an image using Tesseract"""
    try:
        with Image.open(str(image_path)) as img:
            text = pytesseract.image_to_string(img)
            return text.strip()
    except Exception as e:
        print(f"❌ Failed to OCR {image_path.name}: {e}")
        return ""


def process_pdf(pdf_path):
    """Process a PDF file with PyMuPDF first, then Tesseract if needed"""
    print(f"🔍 Processing: {pdf_path}")

    # Check if output already exists (skip if Google Vision already processed it)
    output_file = OUTPUT_DIR / f"{pdf_path.stem}.ocr.json"
    if output_file.exists():
        print(f"⏭️  Skipping {pdf_path.name} - already processed")
        return

    full_text = ""

    # For image files, go straight to OCR
    if pdf_path.suffix.lower() in [".jpg", ".jpeg", ".png"]:
        print(f"📷 Image detected, using Tesseract OCR...")
        full_text = ocr_image(pdf_path)

    # For PDFs, try PyMuPDF first (fast for text-based PDFs)
    else:
        print(f"📄 Detected PDF, extracting text with PyMuPDF...")
        full_text = extract_text_with_pymupdf(pdf_path)

        # If PyMuPDF got no text, try converting to images and OCR
        if not full_text:
            print(f"❌ No text found in PDF.")
            print(f"🔄 Converting to images for Tesseract OCR...")
            images = convert_pdf_to_images(pdf_path)
            if images:
                for image in images:
                    text = ocr_image(image)
                    full_text += text + "\n"
                    os.remove(image)  # Clean up temp image
                full_text = full_text.strip()

    # Only save if we actually got text
    if full_text:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({'text': full_text}, f, ensure_ascii=False, indent=2)
        print(f"✅ Saved OCR output to: {output_file.name}")
    else:
        print(f"⚠️  No text extracted from {pdf_path.name} - will try Google Vision next")


def main():
    if not OUTPUT_DIR.exists():
        OUTPUT_DIR.mkdir(parents=True)

    # Process all PDFs and images in input directory
    for root, dirs, files in os.walk(INPUT_DIR):
        for file in files:
            file_path = Path(root) / file
            if file_path.suffix.lower() in [".pdf", ".jpg", ".jpeg", ".png"]:
                try:
                    process_pdf(file_path)
                except Exception as e:
                    print(f"❌ Error processing {file}: {e}")
                    continue


if __name__ == "__main__":
    main()