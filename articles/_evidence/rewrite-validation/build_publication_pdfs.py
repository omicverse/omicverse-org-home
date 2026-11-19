"""Build author-approved publication PDFs with the site's article template."""
from pathlib import Path
import argparse, json, re, shutil, subprocess, sys
import yaml
from pypdf import PdfReader

parser=argparse.ArgumentParser()
parser.add_argument('--template',type=Path,required=True)
parser.add_argument('--tectonic',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
repo=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(repo/'scripts'))
import build_articles as builder
out=args.output.resolve();pdfs=out/'pdf';pdfs.mkdir(parents=True,exist_ok=True)
footer=r'''% Keep paragraph tokens out of older fancyhdr field arguments.
\makeatletter
\newcommand{\ovpublicationfooter}{\parbox[t]{0.8\textwidth}{\pd@footfont\raggedright\textcopyright~\pd@copyright. \pd@license}}
\makeatother
\fancypagestyle{pdfirst}{\fancyhf{}\renewcommand{\headrulewidth}{0pt}\renewcommand{\footrulewidth}{0pt}\fancyfoot[L]{\ovpublicationfooter}\fancyfoot[R]{\footnotesize\thepage}}
'''
records=[]
for slug in ['splitst','spata2py','pycytotrace','scissor-validation']:
    art=repo/'articles'/slug
    meta=yaml.safe_load((art/'meta.yaml').read_text(encoding='utf-8'))
    if meta.get('release_decision')!='approved-by-authors':
        raise RuntimeError(slug+' lacks recorded author approval')
    source=out/'latex'/slug;source.mkdir(parents=True,exist_ok=True)
    for name in ['pdarticle.cls','numbered.bst','LICENSE']:
        shutil.copy2(args.template/name,source/name)
    shutil.copytree(args.template/'logos',source/'logos',dirs_exist_ok=True)
    shutil.copytree(art/'figures',source/'figures',dirs_exist_ok=True)
    blocks=builder.parse_article((art/'article.md').read_text(encoding='utf-8'))
    tex=builder.tex_document(meta,builder.render_blocks_tex(blocks,meta,'figures'))
    tex=re.sub(r'\\texttt\{([^{}]{35,})\}',lambda m:r'\nolinkurl{'+m[1].replace(r'\_','_')+'}',tex)
    tex=tex.replace(r'\begin{document}',footer+'\n'+r'\begin{document}',1)
    (source/(slug+'.tex')).write_text(tex,encoding='utf-8')
    run=subprocess.run([str(args.tectonic),'-X','compile','--untrusted','--keep-logs','--outdir',str(pdfs),slug+'.tex'],cwd=source,capture_output=True)
    log=(run.stdout+run.stderr).decode('utf-8',errors='replace');(out/(slug+'-compile.log')).write_text(log,encoding='utf-8')
    if run.returncode or 'Overfull' in log or 'Missing character' in log:
        raise RuntimeError(slug+' needs layout review: '+log[-1400:])
    pdf=pdfs/(slug+'.pdf');pages=len(PdfReader(pdf).pages)
    dest=repo/'src/assets/articles'/slug;dest.mkdir(parents=True,exist_ok=True)
    shutil.copy2(pdf,dest/pdf.name)
    info={'pages':pages,'size':f'{pdf.stat().st_size/1e6:.1f} MB'}
    (art/'pdf.json').write_text(json.dumps(info)+'\n',encoding='utf-8')
    records.append({'slug':slug,'pages':pages,'author_approved':True,'site_deployed':False})
    print(slug,pages,'pages',flush=True)
(out/'publication-build.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
