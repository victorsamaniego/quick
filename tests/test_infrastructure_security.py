import ast
import os
from pathlib import Path
import runpy
import secrets
import subprocess
import sys
import unittest
from unittest.mock import patch
from maintenance import require_local_maintenance

ROOT = Path(__file__).resolve().parents[1]


class InfrastructureSecurityTest(unittest.TestCase):
    def test_maintenance_never_imports_app_without_opt_in(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                runpy.run_path(str(ROOT / 'limpiar_db.py'), run_name='__main__')
            self.assertNotIn('app', sys.modules)

    def test_maintenance_rejects_import_production_and_remote_database(self):
        for module, env in [('imported', {}), ('__main__', {}),
                            ('__main__', {'ALLOW_DESTRUCTIVE_MAINTENANCE': 'YES', 'FLASK_ENV': 'production'}),
                            ('__main__', {'ALLOW_DESTRUCTIVE_MAINTENANCE': 'YES', 'MAINTENANCE_DATABASE_URL': 'postgresql://remote.invalid/db'})]:
            with patch.dict(os.environ, env, clear=True), self.assertRaises(RuntimeError):
                require_local_maintenance(module)
        with patch.dict(os.environ, {'ALLOW_DESTRUCTIVE_MAINTENANCE': 'YES', 'MAINTENANCE_DATABASE_URL': 'sqlite:///:memory:'}, clear=True):
            require_local_maintenance('__main__')
            self.assertEqual(os.environ['DATABASE_URL'], 'sqlite:///:memory:')

    def test_docker_declares_nonroot_and_sensitive_exclusions(self):
        self.assertIn('USER quickgo', (ROOT / 'Dockerfile').read_text())
        patterns = (ROOT / '.dockerignore').read_text().splitlines()
        for pattern in ['.env', '.env.*', '.git', '**/*.db', '**/*.sqlite*', '**/*.log', 'node_modules', 'limpiar_db.py']:
            self.assertIn(pattern, patterns)

    def test_actual_factory_headers_and_local_cookie_flags_in_isolated_process(self):
        # No inherited credentials, production URI, or application state.
        env = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'TEMP', 'TMP') if key in os.environ}
        env.update(DATABASE_URL='sqlite:///:memory:', SECRET_KEY=secrets.token_urlsafe(40),
                   FLASK_ENV='testing', PYTHONUTF8='1', CLOUDINARY_CLOUD_NAME='',
                   CLOUDINARY_API_KEY='', CLOUDINARY_API_SECRET='')
        script = '''
from app import app
from flask import jsonify
app.config['SESSION_COOKIE_SECURE'] = False
@app.route('/api/security-probe')
def probe(): return jsonify(ok=True)
client = app.test_client()
response = client.get('/api/security-probe')
assert response.status_code == 200
assert 'no-store' in response.headers['Cache-Control']
assert "frame-ancestors 'self'" in response.headers['Content-Security-Policy']
assert 'geolocation=(self)' in response.headers['Permissions-Policy']
assert response.headers['X-Content-Type-Options'] == 'nosniff'
assert app.config['SESSION_COOKIE_HTTPONLY']
assert app.config['REMEMBER_COOKIE_HTTPONLY']
assert app.config['REMEMBER_COOKIE_SAMESITE'] == 'Lax'
response = client.get('/static/css/style.css')
assert 'no-store' not in response.headers.get('Cache-Control', '')
'''
        result = subprocess.run([sys.executable, '-c', script], cwd=ROOT, env=env, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
