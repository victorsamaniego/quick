"""Decode supported images before upload; PDFs are receipts only, not images."""
from io import BytesIO
from pathlib import PurePath
import warnings
from PIL import Image, UnidentifiedImageError

MAX_UPLOAD_BYTES = 16 * 1024 * 1024
FORMATS = {'jpg': 'JPEG', 'jpeg': 'JPEG', 'png': 'PNG', 'webp': 'WEBP'}


def validated_upload(file, allow_pdf=False):
    extension = PurePath(file.filename or '').suffix.lower().lstrip('.')
    content = file.stream.read(MAX_UPLOAD_BYTES + 1)
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise ValueError('Invalid upload size')
    if extension == 'pdf' and allow_pdf:
        if not content.startswith(b'%PDF-') or b'%%EOF' not in content[-1024:]:
            raise ValueError('Invalid PDF')
        # Signature checks are not a malware or active-content scanner.
        stream = BytesIO(content)
        stream.name = 'receipt.pdf'
        return stream, 'raw'
    if extension not in FORMATS:
        raise ValueError('Unsupported upload type')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content), formats=list(set(FORMATS.values()))) as image:
                if image.format != FORMATS[extension] or max(image.size) > 10000 or image.width * image.height > 25000000:
                    raise ValueError('Invalid image dimensions or type')
                image.verify()
            with Image.open(BytesIO(content), formats=list(set(FORMATS.values()))) as image:
                image.load()
                stream = BytesIO()
                image.save(stream, format=FORMATS[extension])
                stream.seek(0)
                return stream, 'image'
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as error:
        raise ValueError('Invalid image') from error
