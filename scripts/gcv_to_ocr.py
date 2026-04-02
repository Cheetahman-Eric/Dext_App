import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"


def simplify_gcv():
    # Cherche les fichiers bruts de Google Vision
    json_files = list(OUTPUT_DIR.glob("*.gcv.json"))

    if not json_files:
        print("📭 Aucun fichier .gcv.json trouvé.")
        return

    for json_file in json_files:
        print(f"🔄 Simplification de : {json_file.name}")
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # On nettoie le nom pour enlever le .gcv
        clean_name = json_file.name.replace(".gcv.json", ".ocr.json")

        simple_data = {
            "filename": json_file.name.replace(".gcv.json", ""),
            "text": data.get("text", "")
        }

        with open(OUTPUT_DIR / clean_name, 'w', encoding='utf-8') as f:
            json.dump(simple_data, f, indent=4)

        json_file.unlink()  # Supprime le .gcv.json
        print(f"✅ Créé : {clean_name}")


if __name__ == "__main__":
    simplify_gcv()