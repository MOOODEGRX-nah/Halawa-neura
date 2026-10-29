import subprocess
from pathlib import Path


def test_markdown_semantics_and_allowlisted_dom_tree():
    root=Path(__file__).resolve().parents[2]
    script=r'''
const assert=require('node:assert/strict');
const md=require('./web/markdown.js');
const flatten=nodes=>nodes.flatMap(n=>[n,...flatten(n.children||[])]);
const source='فقرة عربية with **bold**, *emphasis*, `inline <tag>` and [link](https://example.com/path).\n\n- واحد\n- two\n\n1. first\n2. second\n\n```js\n<script>fetch("/skills/authorize")</script>\n```';
const nodes=flatten(md.tree(source));
for(const tag of ['p','strong','em','code','a','ul','ol','li','pre'])assert(nodes.some(n=>n.tag===tag),tag);
assert(nodes.some(n=>n.code==='<script>fetch("/skills/authorize")</script>\n'));
assert(nodes.some(n=>n.href==='https://example.com/path'));
for(const raw of ['javascript:alert(1)','JavaScript:alert(1)','data:text/html,bad','file:///etc/passwd','vbscript:bad','https://user:pw@example.com','https://example.com\\@evil.com','https://example.com\n/path'])assert.equal(md.safeURL(raw),null,raw);
const attack='<script>fetch("/skills/authorize")</script><img src=x onerror="alert(1)">\n\n[bad](javascript:alert(1))\n\n![image](https://example.com/tracker.png)';
const dangerous=flatten(md.tree(attack));
assert(!dangerous.some(n=>['script','img','iframe','object','style','svg'].includes(n.tag)));
assert(!dangerous.some(n=>n.href));
assert(dangerous.some(n=>n.text?.includes('<script>')));
for(const node of dangerous)assert(Object.keys(node).every(k=>['tag','children','text','code','language','href','title','start'].includes(k)));
assert(flatten(md.tree('```python\nprint("unfinished fence")')).some(n=>n.code?.includes('unfinished fence')));
assert(flatten(md.tree('**unfinished emphasis')).some(n=>n.text?.includes('unfinished')));
'''
    result=subprocess.run(['node','-e',script],cwd=root,text=True,capture_output=True)
    assert result.returncode==0,result.stderr
