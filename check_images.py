from app import app, db
from models import Product
import os

with app.app_context():
    products = Product.query.all()
    print("\n📦 PRODUCTOS Y SUS IMÁGENES:")
    print("=" * 100)
    
    for p in products:
        print(f"\nID: {p.id}")
        print(f"Nombre: {p.name}")
        print(f"Image URL en DB: {p.image_url}")
        
        if p.image_url:
            # Verificar si el archivo existe
            full_path = os.path.join('static', p.image_url)
            print(f"Ruta completa: {full_path}")
            print(f"¿Existe el archivo?: {os.path.exists(full_path)}")
            
            if os.path.exists(full_path):
                print("✅ La imagen existe")
            else:
                print("❌ La imagen NO existe en esa ruta")
        else:
            print("⚠️ No tiene imagen asignada")
        
        print("-" * 100)