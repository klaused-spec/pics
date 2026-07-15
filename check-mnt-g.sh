#!/bin/bash
# Diagnóstico e recovery para montagem de /mnt/g no WSL

echo "🔍 Verificando /mnt/g..."
echo ""

# 1. Verifica se o mount point existe
if [ -d "/mnt/g" ]; then
    echo "✓ Diretório /mnt/g existe"
else
    echo "✗ Diretório /mnt/g NÃO existe"
    exit 1
fi

# 2. Verifica se está montado
if mountpoint -q /mnt/g; then
    echo "✓ /mnt/g está montado"
else
    echo "⚠ /mnt/g NÃO está montado"
fi

# 3. Tenta listar
echo ""
echo "Tentando acessar /mnt/g..."
if timeout 2 ls -la /mnt/g 2>&1 | head -5; then
    echo "✓ Acesso OK"
else
    echo "✗ Acesso FALHOU (timeout ou erro)"
    echo ""
    echo "Tentando desmontar e remontar..."
    sudo umount /mnt/g 2>/dev/null || true
    sleep 1
    
    # Remonta manualmente
    if [ -d "/mnt/g" ]; then
        sudo mount -t drvfs G: /mnt/g
        echo "Remontado!"
        sleep 2
        ls /mnt/g | head -5
    fi
fi

echo ""
echo "📊 Configuração:"
mount | grep /mnt/g
