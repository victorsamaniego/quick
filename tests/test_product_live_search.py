import unittest
from models import db, Product, Business, Category
from merchant_feature_support import FeatureFixture


class ProductLiveSearchTest(FeatureFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.login_as(self.buyer)
        with self.client.session_transaction() as session:
            session['user_latitude'], session['user_longitude'] = -25, -57
        self.product = Product.query.filter_by(business_id=self.business.id).one()
        self.product.name='Cerveza local'
        db.session.commit()

    def search(self,q):
        return self.client.get('/api/products/search',query_string={'q':q})

    def test_empty_short_trim_case_and_no_match(self):
        for q in ('',' ','c','  c  ','inexistente'):
            self.assertEqual(self.search(q).json,[])
        for q in ('ce','CER','  cerveza  '):
            self.assertEqual([row['id'] for row in self.search(q).json],[self.product.id])
        self.assertEqual(self.search('a'*201).status_code,400)
        self.assertEqual(self.client.post('/api/products/search').status_code,405)

    def test_product_and_business_states(self):
        for attr,value in [('stock',0),('is_active',False)]:
            previous=getattr(self.product,attr);setattr(self.product,attr,value);db.session.commit()
            self.assertEqual(self.search('cer').json,[])
            setattr(self.product,attr,previous);db.session.commit()
        for attr,value in [('is_active',False),('approval_status','pending'),('approval_status','rejected')]:
            previous=getattr(self.business,attr);setattr(self.business,attr,value);db.session.commit()
            self.assertEqual(self.search('cer').json,[])
            setattr(self.business,attr,previous);db.session.commit()
        self.business.is_open=False;db.session.commit()
        self.assertEqual(len(self.search('cer').json),1) # Closed remains visible, like the catalog.

    def test_coverage_quickgold_and_catalog_parity(self):
        self.business.latitude=0;self.business.longitude=0;db.session.commit()
        self.assertEqual(self.search('cer').json,[])
        self.assertNotIn('Cerveza local',self.client.get('/products?search=cer').text)
        self.business.is_quickgold=True;db.session.commit()
        self.assertEqual(len(self.search('cer').json),1)
        self.assertIn('Cerveza local',self.client.get('/products?search=cer').text)
        with self.client.session_transaction() as session:
            session['user_latitude']=None;session['user_longitude']=None
        self.assertEqual(len(self.search('cer').json),1)
        self.business.is_active=False;db.session.commit()
        self.assertEqual(self.search('cer').json,[])

    def test_public_fields_limit_and_category(self):
        for n in range(12):
            db.session.add(Product(name=f'Cerveza {n}',price=100,precio_compra=60,stock=2,business_id=self.business.id))
        category=Category(name='Other',business_id=self.business.id);db.session.add(category);db.session.commit()
        rows=self.search('cer').json
        self.assertEqual(len(rows),10)
        self.assertEqual(set(rows[0]),{'id','name','price','image','image_original','business_name','url'})
        self.assertTrue(rows[0]['url'].startswith('/product/'))
        self.assertEqual(self.client.get('/api/products/search',query_string={'q':'cer','category':category.id}).json,[])

    def test_rate_limit_and_form_fallback(self):
        statuses=[self.search('xx').status_code for _ in range(121)]
        self.assertEqual(statuses[:120],[200]*120)
        self.assertEqual(statuses[-1],429)
        page=self.client.get('/products?search=Cerveza').text
        self.assertIn('method="GET"',page)
        self.assertIn('type="submit"',page)
        self.assertIn('Cerveza local',page)
