from app import create_app
from models import Product
import os

app = create_app()
with app.app_context():
    print("=" * 60)
    print("UPLOAD_FOLDER =", app.config.get('UPLOAD_FOLDER'))
    print("=" * 60)
    for p in Product.query.all():
        print(f"Producto #{p.id} '{p.name}' -> image_url = {p.image_url!r}")
        if p.image_url and not p.image_url.startswith('http'):
            ruta = os.path.join(app.config['UPLOAD_FOLDER'], p.image_url)
            print("   El archivo existe en tu PC?", os.path.exists(ruta))
    up = os.path.join(app.config['UPLOAD_FOLDER'], 'uploads')
    print("=" * 60)
    print("Archivos en la carpeta uploads:")
    if os.path.exists(up):
        for f in os.listdir(up):
            print("  -", f)
    else:
        print("  (la carpeta no existe)")