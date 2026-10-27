import ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]


def test_active_sources_parse():
    files=list((ROOT/'src').rglob('*.py'))+list((ROOT/'tools').glob('*.py'))+[ROOT/'neura-launcher.py']
    for path in files:
        if path.name.endswith('_snippet.py'):continue
        ast.parse(path.read_text(encoding='utf-8'),filename=str(path))


def test_active_code_never_imports_retired_engines():
    for path in (ROOT/'src').rglob('*.py'):
        tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):
                assert node.module not in {'legacy','core.neura_chat','src.core.neura_chat','src.core.model_switcher'}
