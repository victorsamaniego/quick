from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# 👑 RATE LIMITER GLOBAL (Seguridad contra fuerza bruta)
# Se define aquí para evitar importaciones circulares
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)