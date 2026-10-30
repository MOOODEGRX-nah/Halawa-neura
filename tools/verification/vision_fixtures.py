"""Exact, versioned RGB test inputs; these are not application screenshots."""
import argparse,hashlib,json,struct,zlib
from pathlib import Path
CASES=[('red-blue',['red','blue'],(255,0,0),(0,0,255)),
       ('green-yellow',['green','yellow'],(0,255,0),(255,255,0)),
       ('black-white',['black','white'],(0,0,0),(255,255,255))]
PROMPT='ما اللونان الظاهران في الصورة؟ اذكر اللونين فقط.'
def png(left,right):
    def chunk(name,data):return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data)&0xffffffff)
    raw=b''.join(b'\0'+bytes(left)*32+bytes(right)*32 for _ in range(64))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',64,64,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);rows=[]
    for name,expected,left,right in CASES:
        data=png(left,right);(a.output/(name+'.png')).write_bytes(data)
        rows.append({'file':name+'.png','sha256':hashlib.sha256(data).hexdigest(),'expected':expected,'rgb_left':left,'rgb_right':right,'prompt':PROMPT})
    (a.output/'manifest.json').write_text(json.dumps({'schema_version':1,'dimensions':[64,64],'cases':rows},ensure_ascii=False,indent=2))
