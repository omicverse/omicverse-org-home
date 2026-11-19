from pathlib import Path
from workspace_paths import WORKSPACE
import sys,time,json
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
ROOT=WORKSPACE
sys.path.insert(0,str(ROOT/'repos/rewrite-cytotrace'))
from pycytotrace import cytotrace_run
out=Path(__file__).parent/'cyto'
rows=[]
for p in sorted(out.glob('*_input.csv')):
    tag=p.name.removesuffix('_input.csv'); x=pd.read_csv(p,index_col=0)
    r=pd.read_csv(out/f'{tag}_r.csv')
    start=time.perf_counter(); res=cytotrace_run(x,input_scale='auto'); elapsed=time.perf_counter()-start
    py=pd.DataFrame(dict(cell=res.cell_names,score=res.cytotrace,rank=res.cytotrace_rank,counts=res.counts,gcs=res.gcs))
    py.to_csv(out/f'{tag}_python.csv',index=False)
    row=dict(tag=tag,n=x.shape[1],genes=x.shape[0],python_seconds=elapsed,spearman=spearmanr(r.score,py.score,nan_policy='omit').statistic)
    for key in ['score','rank','counts','gcs']:
        row[key+'_max_error']=float(np.nanmax(abs(r[key]-py[key])))
    rg=pd.read_csv(out/f'{tag}_r_genes.csv').set_index('gene').r
    joined=pd.concat([rg.rename('r'),res.cyto_genes.rename('python')],axis=1).dropna()
    row['gene_correlation_max_error']=float(abs(joined.r-joined.python).max())
    # HVG-like restriction by variance: diagnostic, not an alternative gold standard.
    variable=np.argsort(x.var(axis=1).values)[-min(3000,len(x)):]
    sub=cytotrace_run(x.iloc[variable],input_scale='auto')
    row['restricted_gene_score_rho']=spearmanr(py.score,sub.cytotrace,nan_policy='omit').statistic
    py['restricted_score']=sub.cytotrace;py.to_csv(out/f'{tag}_python.csv',index=False)
    rows.append(row);print(row,flush=True)
pd.DataFrame(rows).to_csv(out/'metrics.csv',index=False)
