/* Markdown tokens become an allowlisted DOM tree; assistant HTML is always text. */
(()=>{
  const factory=typeof module!=='undefined'&&module.exports?require('./vendor/markdown-it.min.js'):window.markdownit;
  const parser=factory({html:false,linkify:false,typographer:false,breaks:true,maxNesting:20});
  const allowed=new Set(['p','ul','ol','li','strong','em','s','blockquote','h1','h2','h3','h4','h5','h6','table','thead','tbody','tr','th','td']);
  function safeURL(value){try{if(/[\u0000-\u0020\u007f\\]/.test(value))return null;const url=new URL(value);return ['http:','https:'].includes(url.protocol)&&url.hostname&&!url.username&&!url.password?url.href:null;}catch(_){return null;}}
  function tree(text){
    const root={children:[]},stack=[root];
    const add=node=>stack[stack.length-1].children.push(node);
    function tokens(items){for(const token of items){
      if(token.type==='inline'){tokens(token.children||[]);continue;}
      if(token.type==='fence'||token.type==='code_block'){add({tag:'pre',code:token.content,language:token.info.trim().split(/\s+/)[0].slice(0,40)});continue;}
      if(token.type==='code_inline'){add({tag:'code',children:[{text:token.content}]});continue;}
      if(token.type==='softbreak'||token.type==='hardbreak'){add({tag:'br',children:[]});continue;}
      if(token.type==='hr'){add({tag:'hr',children:[]});continue;}
      if(token.type==='image'){add({text:token.content||'صورة'});continue;}
      if(token.nesting===1){
        const tag=token.type==='link_open'?'a':allowed.has(token.tag)?token.tag:'span';
        const node={tag,children:[]};
        if(tag==='a'){const href=safeURL(token.attrGet('href')||'');if(href)node.href=href;else node.tag='span';const title=token.attrGet('title');if(title)node.title=title.slice(0,500);}
        if(tag==='ol'){const start=Number(token.attrGet('start'));if(Number.isInteger(start)&&start>1&&start<100000)node.start=start;}
        add(node);stack.push(node);continue;
      }
      if(token.nesting===-1){if(stack.length>1)stack.pop();continue;}
      if(token.content)add({text:token.content});
    }}
    if(text.length>200000)return [{text:text.slice(0,200000)+'\n[تجاوز الرد حد العرض]'}];
    tokens(parser.parse(String(text),{}));return root.children;
  }
  function render(text,{document:doc=globalThis.document,codeBlock,onLink}={}){
    const fragment=doc.createDocumentFragment();
    function append(parent,nodes){for(const node of nodes){
      if(node.text!==undefined){parent.append(doc.createTextNode(node.text));continue;}
      if(node.code!==undefined&&codeBlock){parent.append(codeBlock(node.code.replace(/\n$/,''),node.language));continue;}
      const item=doc.createElement(node.tag);
      if(node.code!==undefined){const code=doc.createElement('code');code.textContent=node.code;item.append(code);}
      if(node.href){item.href=node.href;item.rel='noopener noreferrer';item.onclick=event=>{event.preventDefault();if(event.isTrusted&&onLink)onLink(node.href);};}
      if(node.title)item.title=node.title;
      if(node.start)item.start=node.start;
      append(item,node.children||[]);parent.append(item);
    }}
    append(fragment,tree(String(text)));return fragment;
  }
  const api={tree,render,safeURL};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  if(typeof window!=='undefined')window.NeuraMarkdown=api;
})();
