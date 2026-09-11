"""Small input and transaction guards, without database schema changes."""
from decimal import Decimal, InvalidOperation
from functools import wraps
from urllib.parse import unquote, urlsplit

from flask import abort, request


def is_safe_redirect_url(target):
    """Only accept absolute internal paths (including an explicit same origin)."""
    if not isinstance(target, str) or not target or len(target) > 2048:
        return False
    decoded = unquote(target)
    if any(ord(c) < 32 or ord(c) == 127 for c in decoded) or '\\' in decoded:
        return False
    if decoded.startswith('//'):
        return False
    try:
        parsed, origin = urlsplit(target), urlsplit(request.host_url)
        if parsed.scheme or parsed.netloc:
            return (parsed.scheme in ('http', 'https') and
                    parsed.scheme == origin.scheme and parsed.netloc == origin.netloc and
                    parsed.username is None and parsed.password is None)
        return decoded.startswith('/')
    except ValueError:
        return False


def bounded_decimal(value, maximum='1000000000', minimum='0'):
    """Guarani inputs: finite, nonnegative, at most one billion by default."""
    try:
        if isinstance(value, bool) or len(str(value)) > 64:
            raise ValueError
        number = Decimal(str(value))
        if not number.is_finite() or not Decimal(minimum) <= number <= Decimal(maximum):
            raise ValueError
        return number
    except (InvalidOperation, TypeError, ValueError):
        abort(400, description='Importe o valor numérico inválido.')


def rollback_on_error(view):
    """Keep the existing response/error contract while rolling back all writes."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        from models import db
        try:
            return view(*args, **kwargs)
        except Exception:
            db.session.rollback()
            raise
    return wrapped


def lock_user_role_change(user_id):
    """Serialize role changes using the existing Super Admin rows, ordered by id."""
    from models import db, User
    rows = User.query.filter((User.id == user_id) | User.is_super_admin.is_(True)).order_by(
        User.id).populate_existing().with_for_update().all()
    target = next((user for user in rows if user.id == user_id), None)
    if target is None:
        abort(404)
    return target, rows


def validate_role_change(user, locked_users, *, active, admin, delivery, super_admin, business_id):
    if (super_admin and (delivery or admin or business_id is not None)) or (admin and delivery):
        abort(400, description='Combinación de roles incompatible.')
    if user.is_super_admin and user.is_active and not (active and super_admin):
        if not any(other.id != user.id and other.is_super_admin and other.is_active for other in locked_users):
            abort(409, description='No se puede desactivar o degradar al último Super Admin activo.')


def private_credential_response(value, title, return_url):
    """Only a direct response body: never put a generated secret in a signed cookie."""
    from flask import make_response, render_template
    response = make_response(render_template('security_credential.html', secret_value=value,
                                             title=title, return_url=return_url))
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    return response


def validate_product_access(product, location=None):
    """The geographic behavior change is opt-in until destination compatibility is accepted."""
    from flask import current_app, session
    from models import db, Business
    from routes import validar_coordenadas, calcular_distancia_negocio_km
    business = db.session.get(Business, product.business_id) if product.business_id else None
    if not business or not business.is_active or not product.is_available or product.stock <= 0:
        abort(400, description='Producto o negocio no disponible.')
    if not current_app.config.get('SECURITY_ENFORCE_COVERAGE', False):
        return
    location = location if location is not None else session.get('user_location')
    if business.is_quickgold and location is None:
        return
    try:
        if not isinstance(location, dict):
            raise ValueError
        lat, lon = validar_coordenadas(location['latitude'], location['longitude'])
        if business.is_quickgold:
            return
        business_lat, business_lon = validar_coordenadas(business.latitude, business.longitude)
        radius = float(bounded_decimal(business.delivery_radius_km, maximum='500'))
        if calcular_distancia_negocio_km(lat, lon, business_lat, business_lon) > radius:
            raise ValueError
    except (KeyError, TypeError, ValueError):
        abort(400, description='El producto está fuera de cobertura o falta una ubicación válida.')
