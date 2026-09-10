from io import BytesIO
import unittest
from unittest.mock import patch
from PIL import Image
from werkzeug.datastructures import FileStorage
from uploads import validated_upload, MAX_UPLOAD_BYTES


class UploadSecurityTest(unittest.TestCase):
    def upload(self, name, content, **kwargs):
        return validated_upload(FileStorage(stream=BytesIO(content), filename=name), **kwargs)

    def test_fake_corrupt_and_disallowed_images(self):
        for filename, data in [('fake.jpg', b'<script>x</script>'), ('bad.png', b'\x89PNG\r\n'),
                               ('image.svg', b'<svg/>'), ('x.exe', b'MZ')]:
            with self.assertRaises(ValueError):
                self.upload(filename, data)

    def test_real_images_decode_and_preserve_dimensions(self):
        for fmt, ext in [('JPEG', 'jpg'), ('PNG', 'png'), ('WEBP', 'webp')]:
            content = BytesIO(); Image.new('RGB', (20, 30), 'red').save(content, fmt)
            result, kind = self.upload('image.' + ext, content.getvalue())
            self.assertEqual(kind, 'image')
            with Image.open(result) as image:
                self.assertEqual(image.size, (20, 30))

    def test_pdf_is_receipt_only_and_requires_signature(self):
        for data in [b'fake', b'%PDF-1.7\ntruncated']:
            with self.assertRaises(ValueError):
                self.upload('receipt.pdf', data, allow_pdf=True)
        with self.assertRaises(ValueError):
            self.upload('receipt.pdf', b'%PDF-1.7\n%%EOF')
        _, kind = self.upload('receipt.pdf', b'%PDF-1.7\n%%EOF', allow_pdf=True)
        self.assertEqual(kind, 'raw')

    def test_upload_size_limit(self):
        with self.assertRaises(ValueError):
            self.upload('large.jpg', b'x' * (MAX_UPLOAD_BYTES + 1))

    def test_invalid_file_never_reaches_cloudinary(self):
        from flask import Flask
        from werkzeug.exceptions import BadRequest
        import routes
        with Flask(__name__).app_context(), patch.object(routes.cloudinary.uploader, 'upload') as upload:
            with self.assertRaises(BadRequest):
                routes.upload_to_cloudinary(FileStorage(stream=BytesIO(b'fake'), filename='fake.jpg'))
            upload.assert_not_called()

    def test_cloudinary_keeps_folder_secure_url_and_image_type(self):
        from flask import Flask
        import routes
        content = BytesIO(); Image.new('RGB', (2, 2)).save(content, 'PNG'); content.seek(0)
        with Flask(__name__).app_context(), patch.object(routes.cloudinary.uploader, 'upload', return_value={'secure_url': 'https://example.test/image.png'}) as upload:
            url = routes.upload_to_cloudinary(FileStorage(stream=content, filename='test.png'), 'quickgo/products')
            self.assertEqual(url, 'https://example.test/image.png')
            self.assertEqual(upload.call_args.kwargs, {'folder': 'quickgo/products', 'resource_type': 'image'})
