#!/usr/bin/env python3
"""Collect real destination photo candidates for human review, without publishing pages."""
from io import BytesIO
from html import escape
import json
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PIL import Image, ImageOps
import build_experience_images as assets

ROOT=assets.ROOT
OUT=ROOT/'photo-review'
QUERIES={
 'nguuni-haller-park-mombasa-giraffes':'Nguuni giraffes',
 'mamba-village-mombasa-crocodiles':'Mamba Village Mombasa crocodiles',
 'kisite-wasini-snorkelling':'Kisite snorkeling',
 'shimba-hills-kenya':'Shimba Hills',
 'tsavo-east-red-elephant':'Tsavo East elephant',
 'masai-mara-zebra-migration':'Maasai Mara zebras',
 'amboseli-elephants-kilimanjaro':'Amboseli elephants Kilimanjaro',
 'tsavo-red-elephant-safari':'Tsavo red elephant',
 'samburu-reticulated-giraffe':'Samburu giraffe',
 'lake-nakuru-flamingos':'Lake Nakuru flamingos',
 'aberdare-forest-kenya':'Aberdare forest',
 'meru-national-park-kenya':'Meru National Park',
 'hells-gate-national-park-kenya':'Hells Gate Kenya',
 'safari-zebras-kenya':'Kenya zebras savannah',
 'nairobi-national-park-giraffe':'Nairobi National Park giraffe',
 'karen-blixen-museum-nairobi':'Karen Blixen Museum Nairobi',
 'karura-forest-nairobi':'Karura Forest',
 'nairobi-city-market':'Nairobi City Market',
 'lake-naivasha-boat':'Lake Naivasha boat',
 'ngong-hills-kenya':'Ngong Hills',
 'limuru-tea-farm':'Limuru tea plantation',
 'nairobi-skyline-at-night':'Nairobi skyline night',
 'nairobi-kicc-skyline':'Nairobi skyline KICC',
}


def api(params):
    params={'action':'query','format':'json',**params}
    url='https://commons.wikimedia.org/w/api.php?'+urlencode(params)
    for attempt in range(3):
        try:
            req=Request(url,headers={'User-Agent':'PwaniStays-PhotoReview/1.0 (https://pwanistays.com; destination photo attribution)'})
            with urlopen(req,timeout=35) as response:return json.load(response)
        except Exception:
            if attempt==2:raise
            time.sleep(3)


def candidate(info, title, stem, index):
    data=urlopen(Request(info.get('thumburl') or info['url'],headers={'User-Agent':'PwaniStays-PhotoReview/1.0 (https://pwanistays.com)'}),timeout=35).read(16*1024*1024)
    with Image.open(BytesIO(data)) as im:
        im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((720,540));output=BytesIO();im.save(output,'WEBP',quality=76,method=6)
    filename=stem+'-'+str(index)+'.webp';(OUT/filename).write_bytes(output.getvalue())
    return {'title':title,'imageinfo':info,'review_image':filename,'source':'https://commons.wikimedia.org/wiki/Special:Redirect/file/'+title.removeprefix('File:').replace(' ','_')+'?width=1200'}


def main():
    OUT.mkdir(exist_ok=True)
    rows=json.loads(assets.SOURCE.read_text())['photos'];report=[]
    for row in rows:
        record={'row':row,'candidates':[]}
        if row['source'].startswith('/images/'):
            record['local']=True;report.append(record);continue
        try:
            filename=assets.unquote(assets.urlsplit(row['source']).path.rsplit('/',1)[-1])
            exact=api({'prop':'imageinfo','titles':'File:'+filename,'iiprop':'url|extmetadata','iiurlwidth':720})
            pages=list(exact['query']['pages'].values())
            for page in pages:
                if page.get('imageinfo'):
                    record['candidates'].append(candidate(page['imageinfo'][0],page['title'],row['stem'],0));record['original_available']=True
            if not record['candidates']:
                query=QUERIES[row['stem']]
                result=api({'generator':'search','gsrnamespace':6,'gsrsearch':query+' filetype:bitmap','gsrlimit':4,'prop':'imageinfo','iiprop':'url|extmetadata','iiurlwidth':720})
                for index,page in enumerate(result.get('query',{}).get('pages',{}).values(),1):
                    if page.get('imageinfo'):
                        try:record['candidates'].append(candidate(page['imageinfo'][0],page['title'],row['stem'],index))
                        except Exception as exc:record.setdefault('candidate_errors',[]).append(str(exc))
        except Exception as exc:record['error']=str(exc)
        report.append(record)
        (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(row['stem'],len(record['candidates']),record.get('error',''),flush=True)
        time.sleep(.5)
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    sections=[]
    for record in report:
        cards=[]
        for c in record['candidates']:
            description=c['imageinfo'].get('extmetadata',{}).get('ImageDescription',{}).get('value','')
            cards.append('<article><img src="'+c['review_image']+'"><h3>'+escape(c['title'])+'</h3><p>'+escape(description)+'</p></article>')
        sections.append('<section id="'+record['row']['stem']+'"><h2>'+escape(record['row']['title'])+'</h2><div class="grid">'+''.join(cards)+'</div></section>')
    (OUT/'index.html').write_text('<!doctype html><html><head><meta charset="utf-8"><title>Destination photo review</title><style>*{box-sizing:border-box}body{font:14px system-ui;margin:30px}section{margin-bottom:40px}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:20px}img{width:100%;height:210px;object-fit:contain;background:#eee}h3{font-size:13px}p{font-size:11px;max-height:80px;overflow:hidden}</style></head><body>'+''.join(sections)+'</body></html>')

if __name__=='__main__':main()
