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
        category_id: str = Header(None, alias="category-id"),
        card_name: str = Header(None, alias="card-name"),
        region: str = Header(None),  # Cherche le header 'region'
        x_region: str = Header(None, alias="x-invoice-region")  # Fallback sur 'x-invoice-region'
):
    try:
        # 1. Sauvegarde du fichier dans le dossier input
        file_path = INPUT_DIR / file.filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 2. Logique de récupération de la région
        # On vérifie les deux headers possibles envoyés par l'App
        reg = "CAN"  # Valeur par défaut
        if region and region != "null":
            reg = str(region)
        elif x_region and x_region != "null":
            reg = str(x_region)

        # Nettoyage des métadonnées (ID catégorie et Nom de carte)
        cat = str(category_id) if (category_id and category_id not in ["null", "undefined", "0"]) else "8101"
        card = str(card_name) if (card_name and card_name not in ["null", "undefined"]) else "Not Specified"

        # --- DEBUG LOG DANS LE TERMINAL PYCHARM ---
        print("\n" + "=" * 40)
        print(f"📡 APPEL REÇU DU TÉLÉPHONE")
        print(f"🌍 RÉGION DÉTECTÉE : {reg}")
        print(f"📁 CATÉGORIE ID    : {cat}")
        print(f"💳 CARTE UTILISÉE  : {card}")
        print("=" * 40 + "\n")

        # 3. Exécution du pipeline Bash
        # On s'assure d'appeler le script .sh en lui passant les 3 arguments : cat, card, reg
        script_path = SCRIPTS_DIR / "ocr_to_odoo.sh"

        print(f"🚀 Démarrage du pipeline Bash...")

        # On utilise .run() pour que les logs s'affichent en temps réel dans PyCharm
        subprocess.run(
            ["bash", str(script_path), cat, card, reg],
            cwd=str(BASE_DIR),
            capture_output=False,
            text=True
        )

        return {"status": "success", "message": f"Pipeline terminé pour la région {reg}"}

    except Exception as e:
        print(f"❌ Erreur Bridge: {str(e)}")
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn

    # Le bridge écoute sur toutes les interfaces (0.0.0.0) pour recevoir les requêtes de Ngrok/Phone
    uvicorn.run(app, host="0.0.0.0", port=8000)