#!/bin/bash

# --- CONFIGURATION DES CHEMINS ---
# On remonte d'un niveau depuis 'scripts' pour arriver à la racine 'DEXT'
BASE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." &> /dev/null && pwd )"

CAT_ID=$1
CARD_NAME=$2
REGION=$3

# --- DÉTECTION DU PYTHON ACTIF ---
# Au lieu de deviner le chemin du venv, on utilise le python actif du terminal
PYTHON_BIN=$(which python3)

echo "------------------------------------------"
echo "🛠️  PIPELINE START"
echo "📂 Base Dir: $BASE_DIR"
echo "🐍 Python: $PYTHON_BIN"
echo "------------------------------------------"

# Étape 1: Extraction Google Vision
echo "🔍 Step 1: Google Vision..."
$PYTHON_BIN "$BASE_DIR/scripts/vision_ocr_extract.py"

# Étape 2: Simplification GCV -> OCR
echo "🔄 Step 2: Formatting..."
$PYTHON_BIN "$BASE_DIR/scripts/gcv_to_ocr.py"

# Étape 3: Analyse (CAN vs US)
echo "🧠 Step 3: Parsing..."
$PYTHON_BIN "$BASE_DIR/scripts/parse_ocr_text_combined.py" "$REGION"

# Étape 4: Envoi Odoo
echo "🧾 Step 4: Odoo Posting..."
$PYTHON_BIN "$BASE_DIR/scripts/odoo_post_vendor_bill.py" "$CAT_ID" "$CARD_NAME" "$REGION"

echo "------------------------------------------"
echo "✅ FINISHED"
echo "------------------------------------------"