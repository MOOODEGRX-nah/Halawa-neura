"""Static, allowlisted feature units. No generated JavaScript is executed here."""
import ast
import json
import re
from html.parser import HTMLParser
from src.core.application_targets import normalize
from src.core.feature_intent import validate_contract
from src.core.project_files import ProjectError

VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}


class Nodes(HTMLParser):
    def __init__(self,source):
        super().__init__(convert_charrefs=True);self.source=source;self.lines=[0];self.stack=[];self.nodes=[]
        for m in re.finditer('\n',source):self.lines.append(m.end())
        self.feed(source);self.close()
    def source_offset(self):
        row,col=self.getpos();return self.lines[row-1]+col
    def handle_starttag(self,tag,attrs):
        start=self.source_offset();node={'tag':tag,'attrs':dict(attrs),'start':start,'content_start':start+len(self.get_starttag_text()),'text':[]}
        if tag in VOID:node.update(end=node['content_start'],content_end=node['content_start']);self.nodes.append(node)
        else:self.stack.append(node)
    def handle_startendtag(self,tag,attrs):
        start=self.source_offset();self.nodes.append({'tag':tag,'attrs':dict(attrs),'start':start,'content_start':start+len(self.get_starttag_text()),'content_end':start+len(self.get_starttag_text()),'end':start+len(self.get_starttag_text()),'text':[]})
    def handle_data(self,data):
        if not any(n['tag'] in ('script','style','head') for n in self.stack):
            for node in self.stack:node['text'].append(data)
    def handle_endtag(self,tag):
        if self.stack and self.stack[-1]['tag']==tag:
            node=self.stack.pop();start=self.source_offset();end=self.source.find('>',start)
            if end<0:raise ProjectError('عنصر HTML غير مكتمل في مصدر الإزالة')
            node.update(content_end=start,end=end+1);self.nodes.append(node)


def feature(node,removals):
    if node['tag'] not in ('button','a','input'):return None
    attrs=node['attrs'];label=normalize(' '.join(node['text']) or attrs.get('aria-label') or attrs.get('value') or '')
    if 'login' in removals and re.search(r'\b(?:login|sign.?in|تسجيل الدخول|تسجيل دخول)\b',label):return 'login'
    if 'theme' in removals and (attrs.get('id')=='neura-theme-toggle' or re.search(r'\b(?:theme|dark|داكن|مظلم|ليلي)\b',label)):return 'theme'
    return None


def literal(node):
    if node is None or node.type!='string':return None
    text=node.text.decode('utf-8')
    try:value=json.loads(text) if text.startswith('"') else ast.literal_eval(text)
    except (ValueError,SyntaxError):return None
    return value if isinstance(value,str) else None


def prop(node,name):
    if node is None or node.type!='member_expression':return False
    p=node.child_by_field_name('property');return p is not None and p.text.decode()==name


def selector(node):
    if node is None or node.type!='call_expression':return None
    f=node.child_by_field_name('function');args=node.child_by_field_name('arguments')
    if not args or not args.named_children:return None
    owner=f.child_by_field_name('object') if f is not None and f.type=='member_expression' else None
    if owner is None or owner.type!='identifier' or owner.text!=b'document':return None
    value=literal(args.named_children[0])
    if value is None:return None
    if prop(f,'querySelector'):return value
    if prop(f,'getElementById'):return '#'+value
    return None


def feature_ranges(files,contract):
    """Return complete controls, owned theme blocks, and isolated listeners.

    CSS is retained. Unknown/dynamic control implementations fail explicitly.
    Only direct source nodes are eligible; model text never supplies positions.
    """
    from tree_sitter import Parser
    from src.core.source_syntax import JS_LANGUAGE,javascript
    removals={c['feature'] for c in validate_contract(contract).get('changes',[]) if c['operation']=='remove'}
    ranges={p:[] for p in files};all_nodes=[];controls=[];scripts=[];found=set();owned_blocks=set()
    if 'theme' in removals:
        from src.core.required_interactions import compile_theme
        canonical=compile_theme({'theme.html':'<html><head></head><body></body></html>'},'theme.html')[0]['theme.html']
        owned_blocks={(n['tag'],canonical[n['start']:n['end']]) for n in Nodes(canonical).nodes if n['attrs'].get('data-neura-interaction')=='theme'}
    for path,source in files.items():
        if not isinstance(source,str):continue
        if path.endswith(('.html','.htm')):
            parsed=Nodes(source);all_nodes.extend(parsed.nodes)
            for node in parsed.nodes:
                kind=feature(node,removals)
                if kind:controls.append(node);found.add(kind);ranges[path].append((node['start'],node['end']))
                owned=node['attrs'].get('data-neura-interaction')=='theme' and 'theme' in removals
                if owned and node['tag'] in ('style','script'):
                    if (node['tag'],source[node['start']:node['end']]) not in owned_blocks:raise ProjectError('كتلة theme معدلة أو غير معروفة؛ يلزم تعديل مصدر محدد بدل حذف تخميني')
                    ranges[path].append((node['start'],node['end']));found.add('theme');continue
                if node['tag']=='script' and not node['attrs'].get('src'):scripts.append((path,node['content_start'],source[node['content_start']:node['content_end']]))
        elif path.endswith('.js'):scripts.append((path,0,source))
    trees=[];injections=[]
    for path,start,code in scripts:
        javascript(code);tree=Parser(JS_LANGUAGE).parse(code.encode('utf-8'));trees.append((path,start,code,tree))
        for stmt in tree.root_node.named_children:
            expression=stmt.named_children[0] if stmt.type=='expression_statement' and stmt.named_children else None
            if expression is None or expression.type!='augmented_assignment_expression':continue
            left=expression.child_by_field_name('left');right=expression.child_by_field_name('right')
            if not prop(left,'innerHTML') or not any(c.type=='+=' for c in expression.children):continue
            value=literal(right)
            if value is None:continue
            fragment=Nodes(value);items=[n for n in fragment.nodes if n['tag'] in ('button','a','input')]
            eligible=[n for n in items if feature(n,removals)]
            if eligible and len(eligible)==len(items):
                labels={normalize(' '.join(n['text']) or n['attrs'].get('value','')) for n in eligible}
                # Other visible fragment text must belong to the removed controls.
                from src.core.edit_preservation import AcceptedHTML
                check=AcceptedHTML();check.feed(value);check.close();root_text=[normalize(t) for t in check.text]
                if any(t and t not in labels for t in root_text):continue
                controls.extend(eligible);all_nodes.extend(fragment.nodes);found.update(feature(n,removals) for n in eligible);injections.append((path,start,code,stmt))
    selectors=set()
    for node in controls:
        attrs=node['attrs']
        if attrs.get('id') and all(n in controls for n in all_nodes if n['attrs'].get('id')==attrs['id']):selectors.add('#'+attrs['id'])
        for cls in (attrs.get('class') or '').split():
            if all(n in controls for n in all_nodes if cls in (n['attrs'].get('class') or '').split()):selectors.add('.'+cls)
    def add(path,start,code,node):
        raw=code.encode('utf-8');a=start+len(raw[:node.start_byte].decode('utf-8'));b=start+len(raw[:node.end_byte].decode('utf-8'));ranges[path].append((a,b))
    for path,start,code,node in injections:add(path,start,code,node)
    for path,start,code,tree in trees:
        for stmt in tree.root_node.named_children:
            expression=stmt.named_children[0] if stmt.type=='expression_statement' and stmt.named_children else None
            call=expression if expression is not None and expression.type=='call_expression' else None
            f=call.child_by_field_name('function') if call else None
            receiver=f.child_by_field_name('object') if f is not None and f.type=='member_expression' else None
            handled=False
            if prop(f,'addEventListener') and selector(receiver) in selectors:add(path,start,code,stmt);handled=True
            elif expression is not None and expression.type=='assignment_expression':
                left=expression.child_by_field_name('left');receiver=left.child_by_field_name('object') if left is not None and left.type=='member_expression' else None
                if prop(left,'onclick') and selector(receiver) in selectors:add(path,start,code,stmt);handled=True
            if not handled:
                pending=[stmt]
                while pending:
                    node=pending.pop()
                    if selector(node) in selectors:raise ProjectError('ارتباط JavaScript غير معزول بالعنصر المطلوب؛ لم تُخمن إزالة سلوكه')
                    pending.extend(node.named_children)
    missing=removals-found
    if missing:raise ProjectError('لا يوجد عنصر مصدر معزول مدعوم لإزالة: '+', '.join(sorted(missing))+'؛ لم تُخمن حدود المصدر')
    for path,units in ranges.items():
        units.sort();last=-1
        for a,b in units:
            if a<last:raise ProjectError('وحدات الإزالة متداخلة؛ لم يُطبق تعديل')
            last=b
    return ranges
