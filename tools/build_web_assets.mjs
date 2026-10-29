import {mkdir,copyFile,readFile,writeFile} from 'node:fs/promises';
const root=new URL('../',import.meta.url),pkg=new URL('node_modules/markdown-it/',root);
const metadata=JSON.parse(await readFile(new URL('package.json',pkg),'utf8'));
if(metadata.version!=='15.0.3')throw Error('Unexpected Markdown parser version');
const output=new URL('web/vendor/',root);await mkdir(output,{recursive:true});
await copyFile(new URL('dist/browser/markdown-it.umd.min.js',pkg),new URL('markdown-it.min.js',output));
await copyFile(new URL('LICENSE',pkg),new URL('markdown-it.LICENSE.txt',output));
const seen=new Set(),notices=[];
async function notice(name){
 if(seen.has(name))return;seen.add(name);
 const folder=new URL('node_modules/'+name+'/',root),meta=JSON.parse(await readFile(new URL('package.json',folder),'utf8'));
 for(const filename of ['LICENSE','LICENSE.txt','LICENSE.md','LICENSE-MIT']){
  try{notices.push(name+' '+meta.version+' ('+meta.license+')\n\n'+await readFile(new URL(filename,folder),'utf8'));break;}catch(error){if(error.code!=='ENOENT')throw error;}
 }
 for(const dependency of Object.keys(meta.dependencies||{}))await notice(dependency);
}
await notice('markdown-it');
await writeFile(new URL('markdown-it.NOTICES.txt',output),notices.join('\n\n--------------------\n\n'));
console.log('Bundled markdown-it '+metadata.version+' for offline use');
