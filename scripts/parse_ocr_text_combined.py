import json
import re
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
REGION = sys.argv[1] if len(sys.argv) > 1 else "CAN"


def parse_date(text, region):
    # 1. On cherche des blocs de chiffres (ex: 4/2/2 ou 4/2/26)
    # On est très permissif sur l'année (\d{1,4}) pour attraper le "2" de ton OCR
    pattern = r'(\d{1,2})[\s\-\/\.]+(\d{1,2})[\s\-\/\.]+(\d{1,4})'
    matches = re.findall(pattern, text)

    if not matches:
        return None

    current_year = datetime.now().year  # 2026

    for m in matches:
        v1, v2, v3 = [x.strip() for x in m]

        candidates = []
        if region in ["USA", "US"]:
            # USA: MM-JJ-AA
            candidates = [(v1, v2, v3)]
        else:
            # CAN: JJ-MM-AA
            candidates = [(v1, v2, v3), (v2, v1, v3)]

        for c1, c2, c3 in candidates:
            # --- LOGIQUE DE CORRECTION D'ANNÉE ---
            # Si l'année (c3) est "2" ou "26", on la transforme en "2026"
            year_val = c3
            if len(year_val) <= 2:
                # Si c'est juste "2", on assume que c'est 202(6) ou l'année actuelle
                year_val = str(current_year)

            clean_d = f"{c1}-{c2}-{year_val}"

            for fmt in ['%m-%d-%Y', '%d-%m-%Y', '%Y-%m-%d']:
                try:
                    dt = datetime.strptime(clean_d, fmt)
                    # On accepte si c'est l'année actuelle ou l'année passée
                    if dt.year >= current_year - 1 and dt.year <= current_year + 1:
                        return dt.strftime('%Y-%m-%d')
                except:
                    continue
    return None


def parse_files():
    files = list(OUTPUT_DIR.glob("*.ocr.json"))
    for f_path in files:
        print(f"🧠 Parsing de {f_path.name}...")
        with open(f_path, "r") as f:
            content = json.load(f).get("text", "")

        # Extraction du prix
        prices = [float(p.replace(',', '.')) for p in re.findall(r"(\d+[\.,]\d{2})", content)]
        total = max(prices) if prices else 0.0

        # Extraction de la date
        extracted_date = parse_date(content, REGION)

        result = {
            "vendor": "Unknown",
            "total": str(total),
            "date": extracted_date,
            "region": REGION
        }

        output_name = f_path.name.replace(".ocr.json", ".parsed.json")
        with open(OUTPUT_DIR / output_name, "w") as f:
            json.dump(result, f, indent=4)

        f_path.unlink()
        print(f"✅ Créé : {output_name} | Date extraite: {extracted_date}")


if __name__ == "__main__":
    parse_files()