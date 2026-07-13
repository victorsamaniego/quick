from PIL import Image
import os

# Crear carpeta icons si no existe
os.makedirs('static/icons', exist_ok=True)

# Crear un icono simple (cuadrado dorado con texto)
size = 512
img = Image.new('RGB', (size, size), color='#D4AF37')

# Agregar texto "QG" en el centro
from PIL import ImageDraw, ImageFont
draw = ImageDraw.Draw(img)

# Intentar usar una fuente, si no usa la default
try:
    font = ImageFont.truetype("arial.ttf", 200)
except:
    font = ImageFont.load_default()

# Calcular posición del texto
text = "QG"
bbox = draw.textbbox((0, 0), text, font=font)
text_width = bbox[2] - bbox[0]
text_height = bbox[3] - bbox[1]
x = (size - text_width) // 2
y = (size - text_height) // 2

# Dibujar texto
draw.text((x, y), text, fill='white', font=font)

# Guardar icono grande
img.save('static/icons/icon-512x512.png')
print('✅ Creado: icon-512x512.png')

# Crear versiones más pequeñas
sizes = [72, 96, 128, 144, 152, 192, 384]
for s in sizes:
    resized = img.resize((s, s), Image.Resampling.LANCZOS)
    resized.save(f'static/icons/icon-{s}x{s}.png')
    print(f'✅ Creado: icon-{s}x{s}.png')

print('\n🎉 ¡Todos los iconos fueron creados!')