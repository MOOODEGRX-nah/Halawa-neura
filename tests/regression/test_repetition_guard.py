"""N006: a degenerate generation loop stops early with a clear reason."""
from src.core.invoice_orchestrator import RepetitionGuard


def test_guard_trips_on_a_long_identical_line_loop_split_across_chunks():
    guard = RepetitionGuard()
    line = 'tfoot button:disabled:focus-visible{outline:2px solid #000}\n'
    text = 'body{margin:0}\n' + line * 14
    tripped = any(guard.feed(text[i:i + 7]) for i in range(0, len(text), 7))
    assert tripped and guard.line.startswith('tfoot button')


def test_guard_ignores_short_repeated_lines_and_normal_code():
    guard = RepetitionGuard()
    assert not guard.feed('}\n' * 40 + '</div>\n' * 30)
    css = ''.join('.item-%d{color:#111;padding:%dpx}\n' % (i, i) for i in range(60))
    assert not guard.feed(css)
    assert not guard.feed(('const value = compute(item);\n' * 11) + 'done();\n')
