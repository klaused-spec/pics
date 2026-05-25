#!/bin/bash
# Script para baixar os modelos ONNX necessários para reconhecimento facial
# Fonte: InsightFace buffalo_l pack

set -e

MODELS_DIR="backend/models"
mkdir -p "$MODELS_DIR"

BASE_URL="https://github.com/deepinsight/insightface/releases/download/v0.7"

declare -A MODELS=(
    ["det_10g.onnx"]="buffalo_l/det_10g.onnx"
    ["w600k_r50.onnx"]="buffalo_l/w600k_r50.onnx"
    ["1k3d68.onnx"]="buffalo_l/1k3d68.onnx"
    ["2d106det.onnx"]="buffalo_l/2d106det.onnx"
    ["genderage.onnx"]="buffalo_l/genderage.onnx"
)

echo "=== Baixando modelos InsightFace ==="
echo ""

for model in "${!MODELS[@]}"; do
    if [ -f "$MODELS_DIR/$model" ]; then
        echo "  [OK] $model já existe"
    else
        echo "  [>>] Baixando $model..."
        wget -q --show-progress -O "$MODELS_DIR/$model" \
            "$BASE_URL/${MODELS[$model]}" 2>/dev/null || \
        curl -L --progress-bar -o "$MODELS_DIR/$model" \
            "$BASE_URL/${MODELS[$model]}"
    fi
done

echo ""
echo "=== Modelos prontos em $MODELS_DIR ==="
