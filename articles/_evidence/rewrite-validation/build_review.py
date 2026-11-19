from pathlib import Path
from workspace_paths import WORKSPACE
import importlib.util,sys,re,shutil,json,zipfile,hashlib
ROOT=WORKSPACE;REPO=ROOT/'repos/rewrite-reports'
OUT=ROOT/'outputs/rewrite-validation/author-review-v2'
OUT.mkdir(exist_ok=True);(OUT/'articles').mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('article_builder',REPO/'scripts/build_articles.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.OUT_ASSETS=OUT/'assets/articles'
shutil.copytree(REPO/'src/assets/brand',OUT/'assets/brand',dirs_exist_ok=True)
for name in ['styles.css','script.js','articles.js']:shutil.copy2(REPO/'src'/name,OUT/name)
items=[]
for slug in ['splitst','spata2py','pycytotrace','scissor-validation']:
    directory=REPO/'articles/_drafts'/slug;meta=m.load(directory)
    blocks=m.parse_article((directory/'article.md').read_text(encoding='utf-8'))
    fig_url=m.web_figures(meta,directory)
    body,toc,figs=m.render_blocks_html(blocks,meta,fig_url)
    refs=sum(len(b['items']) for b in blocks if b['t']=='refs')
    html=m.article_page(meta,body,toc,figs,None,refs)
    html=html.replace('Published','Draft dated')
    html=re.sub(r'^.*<meta name="citation_[^\n]*\n','',html,flags=re.M)
    html=re.sub(r'<a class="paper-pdf-inline.*?</a>','',html,flags=re.S)
    html=re.sub(r'<div class="side-card side-pdf">.*?</div>','<div class="side-card"><p>Internal review: article PDF not typeset. Vector figure PDFs are included in the evidence bundle.</p><a href="../benchmark-evidence.zip">Download experiment evidence</a></div>',html,flags=re.S)
    html=html.replace('<body>','<body><div style="padding:16px;background:#fff3cd;color:#643b00;text-align:center;font-weight:bold">INTERNAL REVIEW DRAFT · revised experiments · not published</div>')
    (OUT/'articles'/f'{slug}.html').write_text(html,encoding='utf-8')
    items.append({'slug':slug,'words':len((directory/'article.md').read_text(encoding='utf-8').split()),'figures':len(figs),'panels':4*len(figs),'references':refs})
    assert len(figs)==3 and refs>=4
cards=''.join(f'<li style="margin:24px"><a href="articles/{i["slug"]}.html">{i["slug"]}</a> — {i["words"]} words; {i["figures"]} figures / {i["panels"]} panels</li>' for i in items)
(OUT/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Technical reports — internal review v2</title><link rel="stylesheet" href="styles.css"><main style="max-width:1000px;margin:60px auto"><h1>Technical reports: internal review v2</h1><p>Haoliang Zhu · Zehua Zeng · 2026-11-11. New experiments and rewritten manuscripts. These pages are excluded from the public site build.</p><ul>'+cards+'</ul><p><a href="benchmark-evidence.zip">Experiment evidence and vector figures</a></p></main>',encoding='utf-8')
# Archive measured outputs, scripts and the figure source data; no installed R libraries.
base=Path(__file__).parent
with zipfile.ZipFile(OUT/'benchmark-evidence.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in base.rglob('*'):
        if p.is_file() and p.suffix in ['.R','.py','.md','.csv','.json','.txt','.npy','.npz','.f64']:
            z.write(p,'report-v2/'+str(p.relative_to(base)).replace('\\','/'))
    for slug in [i['slug'] for i in items]:
        for p in (REPO/'articles/_drafts'/slug/'figures').glob('*.pdf'):z.write(p,f'figures/{slug}/{p.name}')
    audit=ROOT/'outputs/scissor-discrepancy-audit'
    names=['comparison.json','provenance.json','native_summary.json','binomial_cell_comparison.csv','cox_cell_comparison.csv','python_cox_cv.csv','python_binomial_cv.csv','r_cox_cv.csv','r_binomial_cv.csv','native_survival_coefficients.csv','native_tp53_coefficients.csv','python_binomial_coefficients.csv','python_cox_coefficients.csv','python_cox_path.npy','survival_X.bin','survival_y.csv','r_graph.mtx','cells.txt']
    for name in names:z.write(audit/name,'scissor-audit/'+name)
    z.write(audit/'r-cox-checkpoints/full-coefficients.f64','scissor-audit/r-cox-checkpoints/full-coefficients.f64')
    for p in (audit/'reference/luad').glob('*'):
        if p.is_file() and p.suffix in ['.R','.cpp','.h']:z.write(p,'scissor-audit/reference/luad/'+p.name)
(OUT/'review_summary.json').write_text(json.dumps(items,indent=2),encoding='utf-8')
print(json.dumps(items,indent=2));print('Evidence ZIP bytes:',(OUT/'benchmark-evidence.zip').stat().st_size)
