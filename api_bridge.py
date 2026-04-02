from fastapi import FastAPI, File, UploadFile, Header
from fastapi.middleware.cors import CORSMiddleware
import os
import subprocess
from pathlib import Path
import shutil

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration des chemins
BASE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = BASE_DIR / "scripts"
INPUT_DIR = BASE_DIR / "input"
INPUT_DIR.mkdir(exist_ok=True)


@app.post("/upload")
async def upload_file(
        file: UploadFile = File(...),
        category_id: str = Header(None),
        card_name: str = Header(None),
        invoice_region: str = Header("CAN", alias="x-invoice-region")
):
    try:
        # 1. Sauvegarde
        file_path = INPUT_DIR / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 2. Nettoyage métadonnées
        cat = str(category_id) if (category_id and category_id not in ["null", "undefined", "0"]) else "NO_CAT"
        card = str(card_name) if (card_name and card_name not in ["null", "undefined"]) else "Not Specified"
        reg = str(invoice_region) if (invoice_region and invoice_region != "null") else "CAN"

        print(f"✅ REÇU -> Région: {reg} | Catégorie: {cat} | Carte: {card}")

        # 3. Exécution synchrone pour VOIR les erreurs
        script_path = SCRIPTS_DIR / "ocr_to_odoo.sh"

        print(f"🚀 Démarrage du pipeline Bash...")

        # On utilise .run() au lieu de .Popen() pour forcer l'affichage dans la console PyCharm
        result = subprocess.run(
            ["bash", str(script_path), cat, card, reg],
            cwd=str(BASE_DIR),
            capture_output=False,  # Laisse les messages sortir dans le terminal
            text=True
        )

        return {"status": "success", "message": "Pipeline terminé sur le Mac."}

    except Exception as e:
        print(f"❌ Erreur Bridge: {str(e)}")
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)