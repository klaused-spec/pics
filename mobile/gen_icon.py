"""Gera icon.png 1024x1024 para o app PICS Mobile."""
from PIL import Image, ImageDraw
import math, os

SIZE = 1024
OUT  = os.path.join(os.path.dirname(__file__), 'assets', 'icon.png')
os.makedirs(os.path.dirname(OUT), exist_ok=True)

img  = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Fundo circular azul escuro
BG   = (15, 23, 42)      # slate-900
BLUE = (37, 99, 235)     # blue-600
ACC  = (96, 165, 250)    # blue-400

# Fundo quadrado arredondado (Play Store aceita quadrado com cantos arredondados)
R = 180
draw.rounded_rectangle([0, 0, SIZE, SIZE], radius=R, fill=BG)

# ── Câmera corpo ──────────────────────────────────────────────────────────────
cx, cy = SIZE // 2, SIZE // 2 + 40

# Corpo da câmera
cam_w, cam_h = 560, 380
cam_x = cx - cam_w // 2
cam_y = cy - cam_h // 2
draw.rounded_rectangle([cam_x, cam_y, cam_x + cam_w, cam_y + cam_h], radius=60, fill=BLUE)

# Saliência do topo (viewfinder bump)
bump_w, bump_h = 180, 70
bump_x = cx - bump_w // 2
bump_y = cam_y - bump_h + 10
draw.rounded_rectangle([bump_x, bump_y, bump_x + bump_w, bump_y + bump_h], radius=30, fill=BLUE)

# Lente — anel externo
lens_r = 110
draw.ellipse([cx - lens_r, cy - lens_r, cx + lens_r, cy + lens_r], fill=BG)

# Lente — anel azul claro
lens_r2 = 88
draw.ellipse([cx - lens_r2, cy - lens_r2, cx + lens_r2, cy + lens_r2], fill=ACC)

# Lente — centro escuro (vidro)
lens_r3 = 62
draw.ellipse([cx - lens_r3, cy - lens_r3, cx + lens_r3, cy + lens_r3], fill=BG)

# Reflexo da lente
ref_r = 20
draw.ellipse([cx - lens_r3 + 14, cy - lens_r3 + 14,
              cx - lens_r3 + 14 + ref_r, cy - lens_r3 + 14 + ref_r],
             fill=(255, 255, 255, 180))

# Flash
fl_x, fl_y, fl_r = cam_x + 80, cam_y + 70, 28
draw.ellipse([fl_x - fl_r, fl_y - fl_r, fl_x + fl_r, fl_y + fl_r], fill=ACC)

img.save(OUT, 'PNG')
print(f'Icone salvo em {OUT}  ({SIZE}x{SIZE})')
