from app import app, db

with app.app_context():
    try:
        # Agregar columnas a la tabla users
        db.session.execute('ALTER TABLE users ADD COLUMN username VARCHAR(80)')
        print("✅ Columna 'username' agregada")
    except Exception as e:
        print(f"⚠️ Columna 'username' ya existe o error: {e}")
    
    try:
        db.session.execute('ALTER TABLE users ADD COLUMN security_question_id INTEGER')
        print("✅ Columna 'security_question_id' agregada")
    except Exception as e:
        print(f"⚠️ Columna 'security_question_id' ya existe o error: {e}")
    
    try:
        db.session.execute('ALTER TABLE users ADD COLUMN security_answer_hash VARCHAR(255)')
        print("✅ Columna 'security_answer_hash' agregada")
    except Exception as e:
        print(f"⚠️ Columna 'security_answer_hash' ya existe o error: {e}")
    
    try:
        # Crear tabla security_questions
        db.session.execute('''
            CREATE TABLE IF NOT EXISTS security_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question VARCHAR(200) NOT NULL UNIQUE,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("✅ Tabla 'security_questions' creada")
    except Exception as e:
        print(f"⚠️ Tabla 'security_questions' ya existe o error: {e}")
    
    db.session.commit()
    print("\n🎉 Migración completada!")