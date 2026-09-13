"""Export actual ORM queries for the isolated PostgreSQL regression runner."""
import ast
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
from sqlalchemy.orm import Query
from sqlalchemy.dialects import postgresql

sys.path.insert(0, str(Path(__file__).parents[1]))
import test_radio
import routes
from analytics_service import analytics_queries

fixture = test_radio.CoverageTest()
fixture.setUp()
try:
    original = subprocess.check_output(['git', 'show', '592f99b:routes.py'], text=True, encoding='utf-8')
    function = next(node for node in ast.parse(original).body if isinstance(node, ast.FunctionDef) and node.name == 'analytics')
    function.decorator_list = []
    module = ast.Module(body=[function], type_ignores=[])
    namespace = dict(vars(routes))
    captured = []
    def capture(query):
        captured.append(str(query.statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True})))
        return []
    exec(compile(ast.fix_missing_locations(module), '<baseline-analytics>', 'exec'), namespace)
    namespace['render_template'] = lambda *args, **kwargs: None
    with patch.object(Query, 'all', capture):
        namespace['analytics']()
    fixed = [str(query.statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True})) for query in analytics_queries()]
    print(json.dumps({'before': captured, 'after': fixed}))
finally:
    fixture.tearDown()
