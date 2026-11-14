from pathlib import Path
from workspace_paths import WORKSPACE
import sys,time,json
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.spatial import cKDTree,ConvexHull
from anndata import AnnData
ROOT=WORKSPACE;out=Path(__file__).parent/'spatial'
sys.path[:0]=[str(ROOT/'repos/rewrite-split'),str(ROOT/'repos/rewrite-spata2')]
import splitst,spata2py
f=np.load(ROOT/'repos/rewrite-split/examples/data/split_dlpfc_151673.npz')
meta=pd.read_csv(out/'split_control_metadata.csv',index_col=0)
w=pd.DataFrame(f['weights'],index=f['cells'],columns=f['types']);ref=pd.DataFrame(f['reference'],index=f['types'],columns=f['genes'])
rows=[]
for threshold in [.05,.15,.3,.5]:
 for swap in [False,True]:
  a=AnnData(f['counts'].copy(),obs=meta.copy(),var=pd.DataFrame(index=f['genes']));a.layers['counts']=a.X.copy();a.obsm['spatial']=f['coords']
  for key in ['first_type_neighborhood_agreement','first_type_class_neighborhood_agreement']:
   a.obs[key]=meta[key].astype(str).str.lower().eq('true')
  splitst.purify(a,w,ref);splitst.spatial_score(a,w,a.obs.first_type,k=12)
  score_error=np.max(abs(a.obs.neighborhood_weights_second_type-meta.neighborhood_weights_second_type))
  splitst.balance(a,threshold=threshold,spot_class_key='spot_class',swap_labels=swap)
  tag=f't{threshold}_swap{int(swap)}';r=pd.read_csv(out/f'balanced_{tag}.csv',index_col=0).T
  py=pd.DataFrame(a.layers['split_balanced'].toarray(),index=a.obs_names,columns=a.var_names).loc[r.index,r.columns]
  rm=pd.read_csv(out/f'metadata_{tag}.csv',index_col=0)
  row=dict(threshold=threshold,swap=swap,max_expression_error=np.max(abs(py.values-r.values)),score_error=score_error,
           swap_disagreements=int((a.obs.loc[rm.index,'split_shift_swap'].values!=rm['swap'].values).sum()),
           status_disagreements=int((a.obs.loc[rm.index,'split_balance_status'].values!=rm['purification_status'].values).sum()),
           rejected_retained_python=int((a.obs.spot_class=='reject').sum()),r_cells=len(r),swapped=int(a.obs.split_shift_swap.sum()))
  rows.append(row)
  np.savez_compressed(out/f'split_{tag}_comparison.npz',r=r.values,python=py.values)
pd.DataFrame(rows).to_csv(out/'split_metrics.csv',index=False);print(rows)
# Sensitivity on complete real coordinates and separately identified controls.
f=np.load(ROOT/'repos/rewrite-spata2/examples/data/dlpfc_coords.npz');coords=f['coords'];a=AnnData(sparse.csr_matrix((len(coords),1)));a.obsm['spatial']=coords
base=float(np.median(cKDTree(coords[:-5]).query(coords[:-5],k=2)[0][:,1]))
rows=[]
for factor in [1.05,1.25,1.5,2.]:
 for neighbors in [2,3,5]:
  start=time.perf_counter();flags=spata2py.identify_spatial_outliers(a,radius=base*factor,min_neighbors=neighbors).values;t=time.perf_counter()-start
  rows.append(dict(radius_factor=factor,min_neighbors=neighbors,native_flags=int(flags[:-5].sum()),control_hits=int(flags[-5:].sum()),seconds=t))
pd.DataFrame(rows).to_csv(out/'spata_sensitivity.csv',index=False)
np.save(out/'spata_python_outline.npy',spata2py.identify_tissue_outline(a[:-5].copy()).values)
