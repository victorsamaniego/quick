from io import BytesIO
import unittest
from unittest.mock import patch
from PIL import Image
from models import db, Product, Category
from product_images import product_catalog_image, product_original_image
from merchant_feature_support import FeatureFixture


class ProductImagesTest(FeatureFixture, unittest.TestCase):
    original='https://res.cloudinary.com/demo/image/upload/v123/quickgo/products/beer.jpg'

    def test_secure_derived_preserves_original_and_legacy(self):
        with self.app.test_request_context():
            url=product_catalog_image(self.original)
            self.assertIn('/e_background_removal/',url)
            self.assertIn('b_white,c_pad,g_center,h_600,w_600',url)
            self.assertIn('f_auto,q_auto',url)
            self.assertTrue(url.endswith('/v123/quickgo/products/beer.jpg'))
            self.assertEqual(product_original_image(self.original),self.original)
            self.assertEqual(product_catalog_image('uploads/old.jpg'),'/static/uploads/old.jpg')
            for url in ('https://example.com/old.jpg','https://res.cloudinary.com/demo/image/upload/s--signature--/v1/a.jpg',
                        'https://res.cloudinary.com/demo/image/upload/c_fill,w_300/v1/a.jpg'):
                self.assertEqual(product_catalog_image(url),url)
            for url in (None,'javascript:alert(1)','//evil.test/a.jpg','../private','https://user:pass@example.com/a.jpg'):
                self.assertEqual(product_catalog_image(url),'/static/images/product-placeholder.svg')

    def test_sdk_failure_fallback(self):
        with self.app.test_request_context(), patch('product_images.generate_transformation_string',side_effect=RuntimeError('unavailable')):
            self.assertEqual(product_catalog_image(self.original),self.original)

    def photo(self):
        file=BytesIO();Image.new('RGB',(4,4),'white').save(file,format='PNG');file.seek(0)
        return file,'product.png'

    def payload(self):
        return dict(name='New product',description='Example',price='100',precio_compra='50',stock='5',
                    category_id=str(self.category.id),csrf_token=self.token())

    def test_create_and_replace_keep_original_without_transform_api(self):
        self.login_as(self.seller)
        self.category=Category(name='Test',business_id=self.business.id);db.session.add(self.category);db.session.commit()
        data=self.payload();data['image']=self.photo()
        with patch('routes.cloudinary.uploader.upload',return_value={'secure_url':self.original}) as upload:
            self.assertEqual(self.client.post('/admin/products/new',data=data).status_code,302)
            self.assertNotIn('background_removal',upload.call_args.kwargs)
        product=Product.query.filter_by(name='New product').one()
        self.assertEqual(product.image_url,self.original)
        replacement=self.original.replace('beer.jpg','new.png')
        data=self.payload();data['image']=self.photo()
        with patch('routes.cloudinary.uploader.upload',return_value={'secure_url':replacement}):
            self.assertEqual(self.client.post(f'/admin/products/{product.id}/edit',data=data).status_code,302)
        self.assertEqual(product.image_url,replacement)
        self.login_as(self.buyer)
        with self.client.session_transaction() as session:
            session['user_latitude'],session['user_longitude']=-25,-57
        page=self.client.get(f'/product/{product.id}').text
        self.assertIn('data-original-src="'+replacement+'"',page)
        self.assertIn('e_background_removal',page)

    def test_upload_failure_and_no_image_do_not_block_create(self):
        self.login_as(self.seller)
        self.category=Category(name='Test',business_id=self.business.id);db.session.add(self.category);db.session.commit()
        data=self.payload();data['image']=self.photo()
        with patch('routes.cloudinary.uploader.upload',side_effect=RuntimeError('unavailable')):
            self.assertEqual(self.client.post('/admin/products/new',data=data).status_code,302)
        self.assertIsNone(Product.query.filter_by(name='New product').one().image_url)
        data=self.payload();data['name']='No image'
        self.assertEqual(self.client.post('/admin/products/new',data=data).status_code,302)
        product=Product.query.filter_by(name='No image').one()
        self.login_as(self.buyer)
        page=self.client.get(f'/product/{product.id}')
        self.assertEqual(page.status_code,200)
        self.assertIn('product-placeholder.svg',page.text)
