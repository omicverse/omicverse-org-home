"""Render the four author-review PDFs with the repository's article template.

This never promotes drafts into the public website tree.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import yaml

parser=argparse.ArgumentParser()
parser.add_argument('--template',type=Path,required=True)
parser.add_argument('--tectonic',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
repo=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(repo/'scripts'))
import build_articles as article_builder

slugs=['splitst','spata2py','pycytotrace','scissor-validation']
output=args.output.resolve();pdf_dir=output/'pdf';pdf_dir.mkdir(parents=True,exist_ok=True)
footer=r'''% Compatibility with the older fancyhdr bundled in Tectonic.
\newcommand{\ovreviewfooter}{\parbox[t]{0.8\textwidth}{\footnotesize\raggedright\textcopyright~2026 The Authors. Author review copy, not published. Revision 2; prepared November 14, 2026.}}
\fancypagestyle{pdfirst}{\fancyhf{}\renewcommand{\headrulewidth}{0pt}\renewcommand{\footrulewidth}{0pt}\fancyfoot[L]{\ovreviewfooter}\fancyfoot[R]{\footnotesize\thepage}}
'''
records=[]
for slug in slugs:
    art=repo/'articles'/slug
    source=output/'latex'/slug;source.mkdir(parents=True,exist_ok=True)
    for name in ['pdarticle.cls','numbered.bst','LICENSE']:
        shutil.copy2(args.template/name,source/name)
    shutil.copytree(args.template/'logos',source/'logos',dirs_exist_ok=True)
    shutil.copytree(art/'figures',source/'figures',dirs_exist_ok=True)
    meta=yaml.safe_load((art/'meta.yaml').read_text(encoding='utf-8'))
    blocks=article_builder.parse_article((art/'article.md').read_text(encoding='utf-8'))
    tex=article_builder.tex_document(meta,article_builder.render_blocks_tex(blocks,meta,'figures'))
    lines=[]
    for line in tex.splitlines():
        if line.startswith(r'\licenseline'):
            line=r'\licenseline{Author review copy. Not published. Revision 2; prepared November 14, 2026.}'
        if line.startswith(r'\journalinfo'):
            line=r'\journalinfo{OmicVerse Technical Reports - Author review copy}'
        lines.append(line)
    tex='\n'.join(lines)+'\n'
    tex=re.sub(r'\\texttt\{([^{}]{35,})\}',lambda m:r'\nolinkurl{'+m[1].replace(r'\_','_')+'}',tex)
    tex=tex.replace(r'\begin{document}',footer+'\n'+r'\begin{document}',1)
    (source/(slug+'.tex')).write_text(tex,encoding='utf-8')
    result=subprocess.run([str(args.tectonic),'-X','compile','--untrusted','--keep-logs',
                           '--outdir',str(pdf_dir),slug+'.tex'],cwd=source,capture_output=True)
    log=(result.stdout+result.stderr).decode('utf-8',errors='replace')
    (output/(slug+'-compile.log')).write_text(log,encoding='utf-8')
    if result.returncode:
        raise RuntimeError(slug+' compilation failed: '+log[-1500:])
    pdf=pdf_dir/(slug+'.pdf')
    records.append({'slug':slug,'pdf':str(pdf),'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),
                    'overfull_warnings':len(re.findall('Overfull',log)),
                    'missing_glyphs':'Missing character' in log,'published':False})
    print(slug,'compiled',flush=True)
(output/'pdf-build.json').write_text(json.dumps(records,indent=2)+'\n',encoding='utf-8')
