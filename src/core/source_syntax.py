"""Parsers only. Generated JavaScript/CSS is never evaluated by this module."""
import re
from tree_sitter import Language,Parser
import tree_sitter_javascript
import tinycss2

JS_LANGUAGE=Language(tree_sitter_javascript.language())


def javascript(text):
    tree=Parser(JS_LANGUAGE).parse(text.encode('utf-8'))
    stack=[tree.root_node]
    jsx=False
    while stack:
        node=stack.pop()
        if node.type=='ERROR' or node.is_missing:
            raise ValueError(f'JavaScript syntax error at {node.start_point.row+1}:{node.start_point.column+1}')
        if node.type.startswith('jsx_'):jsx=True
        stack.extend(node.children)
    return {'build_required':jsx}


def css(text,*,declarations=False):
    # CSS parsers recover from EOF in a block. Keep that visibly incomplete
    # draft out of a committed preview even where the browser could repair it.
    stack=[];quote=None;comment=False;escape=False;url=False;i=0
    matching={'}':'{',')':'(',']':'['}
    while i<len(text):
        ch=text[i]
        if comment:
            if text[i:i+2]=='*/':comment=False;i+=2;continue
            i+=1;continue
        if escape:escape=False;i+=1;continue
        if ch=='\\':escape=True;i+=1;continue
        if quote:
            if ch==quote:quote=None
            i+=1;continue
        if ch in ('\"',"'"):quote=ch;i+=1;continue
        if url:
            if ch==')':url=False;stack.pop()
            i+=1;continue
        if text[i:i+2]=='/*':comment=True;i+=2;continue
        if text[i:i+4].lower()=='url(' and (i==0 or not re.match(r'[\w-]',text[i-1])):
            stack.append('(');url=True;i+=4;continue
        if ch in '({[':stack.append(ch)
        if ch in ')}]':
            if not stack or stack.pop()!=matching[ch]:raise ValueError('CSS delimiter mismatch')
        i+=1
    if stack or quote or comment:raise ValueError('CSS has an incomplete block, string or comment')
    parser=tinycss2.parse_declaration_list if declarations else tinycss2.parse_stylesheet
    nodes=list(parser(text,skip_comments=True,skip_whitespace=True))
    while nodes:
        node=nodes.pop()
        if node.type=='error':raise ValueError('CSS syntax error: '+node.message)
        if node.type in ('qualified-rule','at-rule') and node.content is not None:
            nodes.extend(tinycss2.parse_blocks_contents(node.content,skip_comments=True,skip_whitespace=True))
