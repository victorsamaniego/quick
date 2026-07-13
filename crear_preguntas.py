from app import app, db
from models import SecurityQuestion

with app.app_context():
    print("🔧 Creando preguntas de seguridad...")
    count = SecurityQuestion.seed_default_questions()
    print(f"✅ Se crearon {count} preguntas nuevas")
    
    # Mostrar todas las preguntas
    questions = SecurityQuestion.query.all()
    print(f"\n📋 Total de preguntas disponibles: {len(questions)}")
    for i, q in enumerate(questions, 1):
        print(f"  {i}. {q.question}")