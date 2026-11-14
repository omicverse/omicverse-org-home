"""Build a portable, explicitly unpublished HTML/PDF review bundle."""
from pathlib import Path
import argparse
import importlib.util
import json
import re
import shutil
import sys

parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
repo=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(repo/'scripts'))
import build_articles as builder

out=args.output.resolve();(out/'articles').mkdir(parents=True,exist_ok=True)
builder.OUT_ASSETS=out/'assets/articles'
shutil.copytree(repo/'src/assets/brand',out/'assets/brand',dirs_exist_ok=True)
for name in ['styles.css','script.js','articles.js']:
    shutil.copy2(repo/'src'/name,out/name)
items=[]
for slug in ['splitst','spata2py','pycytotrace','scissor-validation']:
    directory=repo/'articles'/slug
    meta=builder.load(directory)
    blocks=builder.parse_article((directory/'article.md').read_text(encoding='utf-8'))
    fig_url=builder.web_figures(meta,directory)
    body,toc,figs=builder.render_blocks_html(blocks,meta,fig_url)
    refs=sum(len(b['items']) for b in blocks if b['t']=='refs')
    html=builder.article_page(meta,body,toc,figs,None,refs).replace('Published','Draft dated')
    html=re.sub(r'^.*<meta name="citation_[^\n]*\n','',html,flags=re.M)
    html=re.sub(r'<a class="paper-pdf-inline.*?</a>','',html,flags=re.S)
    card=f'<div class="side-card"><p>Author review copy; not published.</p><a href="../assets/articles/{slug}/review.pdf">Read full review PDF</a><br><a href="../benchmark-evidence.zip">Experiment evidence</a></div>'
    html=re.sub(r'<div class="side-card side-pdf">.*?</div>',card,html,flags=re.S)
    html=html.replace('<body>','<body><div style="padding:16px;background:#fff3cd;text-align:center;font-weight:bold">AUTHOR REVIEW COPY - NOT PUBLISHED</div>')
    (out/'articles'/f'{slug}.html').write_text(html,encoding='utf-8')
    shutil.copy2(directory/'review.pdf',builder.OUT_ASSETS/slug/'review.pdf')
    items.append({'slug':slug,'figures':len(figs),'references':refs,'pdf':'assets/articles/'+slug+'/review.pdf'})
    assert len(figs)==3 and refs>=4
shutil.copy2(repo/'articles/_evidence/rewrite-validation/evidence.zip',out/'benchmark-evidence.zip')
cards=''.join(f'<li><a href="articles/{i["slug"]}.html">{i["slug"]}</a> - <a href="{i["pdf"]}">6-page PDF</a></li>' for i in items)
(out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Report author review</title><link rel="stylesheet" href="styles.css"><main style="max-width:1000px;margin:60px auto"><h1>Four scoped technical reports</h1><p>Author review copies, not published. Prepared 2026-11-14.</p><ul>'+cards+'</ul></main>',encoding='utf-8')
(out/'review-summary.json').write_text(json.dumps(items,indent=2)+'\n',encoding='utf-8')
print(json.dumps(items))
