from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed
from wtforms import StringField, PasswordField, EmailField, TelField, TextAreaField, FloatField, IntegerField, SelectField, DecimalField, FileField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Optional, NumberRange, Regexp
from models import User, SecurityQuestion


class RegistrationForm(FlaskForm):
    # 🔥 NUEVO: Username obligatorio
    username = StringField('Nombre de usuario', validators=[
        DataRequired(message='El nombre de usuario es obligatorio'),
        Length(min=3, max=80, message='Entre 3 y 80 caracteres'),
        Regexp('^[a-zA-Z0-9_]+$', 
               message='Solo letras, números y guiones bajos')
    ])
    
    email = EmailField('Email', validators=[DataRequired(), Email()])
    phone = TelField('Teléfono', validators=[DataRequired(), Length(min=8, max=20)])
    
    password = PasswordField('Contraseña', validators=[
        DataRequired(), 
        Length(min=8, message='La contraseña debe tener al menos 8 caracteres')
    ])
    confirm_password = PasswordField('Confirmar Contraseña', validators=[
        DataRequired(), 
        EqualTo('password', message='Las contraseñas no coinciden')
    ])
    
    # 🔥 NUEVOS CAMPOS: Pregunta de seguridad
    security_question_id = SelectField('Pregunta de seguridad', coerce=int, validators=[
        DataRequired(message='Debés elegir una pregunta')
    ])
    
    security_answer = StringField('Tu respuesta', validators=[
        DataRequired(message='Debés responder la pregunta'),
        Length(min=2, max=100)
    ])
    
    def __init__(self, *args, **kwargs):
        super(RegistrationForm, self).__init__(*args, **kwargs)
        # Cargar preguntas disponibles
        questions = SecurityQuestion.query.filter_by(is_active=True).all()
        self.security_question_id.choices = [(q.id, q.question) for q in questions]
    
    def validate_username(self, field):
        user = User.query.filter_by(username=field.data).first()
        if user:
            raise ValidationError('Este nombre de usuario ya está en uso.')
    
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Este email ya está registrado.')
    
    def validate_password(self, field):
        errors = User.validate_strong_password(field.data)
        if errors:
            raise ValidationError(' - '.join(errors))


class LoginForm(FlaskForm):
    # 🔥 CAMBIADO: Ahora acepta username O email
    username = StringField('Usuario o Email', validators=[
        DataRequired(message='Ingresá tu usuario o email')
    ])
    
    password = PasswordField('Contraseña', validators=[
        DataRequired(message='La contraseña es obligatoria')
    ])
    
    remember_me = BooleanField('Recordarme')


class OTPVerificationForm(FlaskForm):
    code = StringField('Código de verificación', validators=[
        DataRequired(), 
        Length(min=6, max=6, message='El código debe tener 6 dígitos')
    ])


class PasswordResetRequestForm(FlaskForm):
    email = EmailField('Email', validators=[DataRequired(), Email()])


class PasswordResetForm(FlaskForm):
    password = PasswordField('Nueva Contraseña', validators=[
        DataRequired(), 
        Length(min=8, message='La contraseña debe tener al menos 8 caracteres')
    ])
    confirm_password = PasswordField('Confirmar Nueva Contraseña', validators=[
        DataRequired(), 
        EqualTo('password', message='Las contraseñas no coinciden')
    ])
    
    def validate_password(self, field):
        errors = User.validate_strong_password(field.data)
        if errors:
            raise ValidationError(' - '.join(errors))


class ProductForm(FlaskForm):
    name = StringField('Nombre del Producto', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('Descripción', validators=[Optional()])
    precio_compra = DecimalField('Precio de Compra (Gs)', validators=[DataRequired(), NumberRange(min=0)])
    price = DecimalField('Precio de Venta (Gs)', validators=[DataRequired(), NumberRange(min=0)])
    stock = IntegerField('Stock', validators=[DataRequired(), NumberRange(min=0)])
    category_id = SelectField('Categoría', coerce=int, validators=[DataRequired()])
    image = FileField('Imagen del Producto', validators=[FileAllowed(['jpg', 'png', 'jpeg'], 'Solo imágenes!')])
    submit = SubmitField('Guardar Producto')
    
    def populate_categories(self, categories):
        self.category_id.choices = [(cat.id, cat.name) for cat in categories]


class OrderForm(FlaskForm):
    shipping_address = TextAreaField('Dirección de envío', validators=[DataRequired()])
    shipping_phone = TelField('Teléfono de contacto', validators=[DataRequired(), Length(min=8, max=20)])
    shipping_reference = StringField('Referencia (opcional)', validators=[Optional()])


class AdminUserForm(FlaskForm):
    email = EmailField('Email', validators=[DataRequired(), Email()])
    phone = TelField('Teléfono', validators=[DataRequired()])
    is_active = SelectField('Estado', coerce=bool, choices=[(True, 'Activo'), (False, 'Inactivo')])
    is_admin = SelectField('Rol Admin', coerce=bool, choices=[(True, 'Sí'), (False, 'No')])


class CategoryForm(FlaskForm):
    name = StringField('Nombre de categoría', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Descripción', validators=[Optional()])