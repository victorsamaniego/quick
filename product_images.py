"""Non-destructive catalog delivery. URL construction makes no network/API calls."""
import re
from urllib.parse import urlsplit, urlunsplit
from flask import url_for
from cloudinary.utils import generate_transformation_string


def product_original_image(value):
    placeholder = url_for('static', filename='images/product-placeholder.svg')
    if not isinstance(value, str) or not value or any(c in value for c in ('\\', '\r', '\n', '\x00')):
        return placeholder
    try:
        parsed = urlsplit(value)
        if parsed.scheme in ('https', 'http') and parsed.hostname and not parsed.username and not parsed.password:
            # Existing remote images stay available; only HTTPS Cloudinary is transformed.
            return value
        if not parsed.scheme and not parsed.netloc and not value.startswith('//'):
            path = parsed.path.removeprefix('/static/').removeprefix('static/')
            if not path.startswith('/') and '..' not in path.split('/'):
                return url_for('static', filename=path)
    except ValueError:
        pass
    return placeholder


def product_catalog_image(value):
    original = product_original_image(value)
    try:
        parsed = urlsplit(original)
        if parsed.scheme != 'https' or parsed.netloc != 'res.cloudinary.com' or parsed.query or parsed.fragment:
            return original
        match = re.fullmatch(r'/([a-zA-Z0-9_-]+)/image/upload/(.+)', parsed.path)
        if not match:
            return original
        asset = match[2]
        # Signed or already-transformed URLs are preserved, not reconstructed.
        if asset.startswith('s--') or any(',' in part or re.match(r'(c|e|w|h|q|f|t|b|g)_', part)
                                           for part in asset.split('/')[:-1]):
            return original
        transformation, _ = generate_transformation_string(transformation=[
            {'effect': 'background_removal'},
            {'width': 600, 'height': 600, 'crop': 'pad', 'gravity': 'center', 'background': 'white'},
            {'fetch_format': 'auto', 'quality': 'auto'},
        ])
        return urlunsplit(('https', parsed.netloc,
                          f'/{match[1]}/image/upload/{transformation}/{asset}', '', ''))
    except Exception:
        # SDK/configuration failure must never prevent a product page or upload.
        return original
