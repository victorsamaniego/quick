from app import app, db
from models import Business

with app.app_context():
    negocios = Business.query.all()
    print('\n NEGOCIOS EN LA BASE DE DATOS:')
    print('='*60)
    for n in negocios:
        print(f'ID: {n.id}')
        print(f'Nombre: {n.name}')
        codigo = n.activation_code if n.activation_code else 'SIN CODIGO'
        print(f'Codigo: {codigo}')
        expira = n.code_expires_at if n.code_expires_at else 'N/A'
        print(f'Expira: {expira}')
        print(f'Estado: {n.subscription_status}')
        print('-'*60)