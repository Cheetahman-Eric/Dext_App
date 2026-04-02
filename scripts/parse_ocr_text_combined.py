import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
REGION = sys.argv[1] if len(sys.argv) > 1 else "CAN"


def parse_files():
    # Cherche les fichiers .ocr.json
    files = list(OUTPUT_DIR.glob("*.ocr.json"))

    for f_path in files:
        print(f"🧠 Parsing : {f_path.name}")
        with open(f_path, "r") as f:
            content = json.load(f).get("text", "")

        # Logique de parsing ultra-simple pour le test
        prices = [float(p.replace(',', '.')) for p in re.findall(r"(\d+[\.,]\d{2})", content)]
        total = max(prices) if prices else 0.0

        result = {
            "vendor": "Unknown",
            "total": str(total),
            "subtotal": str(total),
            "date": None,
            "taxes": []
        }

        # Sauvegarde en .parsed.json
        output_name = f_path.name.replace(".ocr.json", ".parsed.json")
        with open(OUTPUT_DIR / output_name, "w") as f:
            json.dump(result, f, indent=4)

        f_path.unlink()  # Supprime le .ocr.json
        print(f"✅ Créé : {output_name}")


if __name__ == "__main__":
    parse_files()