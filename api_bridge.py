from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import os
import uuid
import subprocess

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "input"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/upload")
async def upload_receipt(
        file: UploadFile = File(...),
        category: str = Form(...),
        card: str = Form("Not Specified")
):
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"receipt_{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # CHECK THIS PRINT IN YOUR TERMINAL
    print(f"✅ RECEIVED FROM PHONE -> Category: {category} | Card: {card}")

    try:
        # CRITICAL: We pass category as $1 and card as $2
        result = subprocess.run(
            ["bash", "scripts/ocr_to_odoo.sh", str(category), str(card)],
            capture_output=True,
            text=True
        )
        print(result.stdout)
        return {"status": "Success", "card_processed": card}
    except Exception as e:
        print(f"❌ Pipeline Error: {e}")
        return {"status": "Error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)