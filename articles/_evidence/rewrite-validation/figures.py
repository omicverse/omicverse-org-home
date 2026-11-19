from pathlib import Path
from workspace_paths import WORKSPACE
import json,sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as PolygonPath
from scipy.spatial import ConvexHull,cKDTree
from scipy import sparse
from scipy.stats import spearmanr
from anndata import AnnData
ROOT=WORKSPACE;BASE=Path(__file__).parent
ART=ROOT/'repos/rewrite-reports/articles/_drafts'
sys.path[:0]=[str(ROOT/'repos/rewrite-split'),str(ROOT/'repos/rewrite-spata2')]
import splitst,spata2py
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':220})
inventory=[]
def canvas(rows=2,cols=2):
    fig,ax=plt.subplots(rows,cols,figsize=(6*cols,4.2*rows),constrained_layout=True)
    ax=np.asarray(ax).ravel()
    for i,a in enumerate(ax):a.text(-.08,1.06,chr(97+i),transform=a.transAxes,fontweight='bold',fontsize=15)
    return fig,ax
def save(fig,slug,n,panels):
    p=ART/slug/'figures';p.mkdir(exist_ok=True)
    fig.savefig(p/f'fig{n}.jpg');fig.savefig(p/f'fig{n}.pdf');plt.close(fig)
    inventory.append(dict(report=slug,figure=n,panels=panels))
def identity(ax,r,py,title):
    ax.scatter(r,py,s=8,alpha=.55);lo=min(np.nanmin(r),np.nanmin(py));hi=max(np.nanmax(r),np.nanmax(py))
    ax.plot([lo,hi],[lo,hi],color='black',lw=.8);ax.set(xlabel='R',ylabel='Python',title=title)
def spatial(ax,xy,v,title,**kw):
    m=ax.scatter(xy[:,0],xy[:,1],c=v,s=8,cmap='viridis',**kw);ax.set(title=title,xlabel='Spatial x',ylabel='Spatial y',aspect='equal');ax.invert_yaxis();return m
def ecdf(ax,values,label):
    v=np.sort(np.abs(np.asarray(values).ravel()));ax.plot(np.maximum(v,1e-18),np.arange(1,len(v)+1)/len(v),label=label)
    ax.set_xscale('log');ax.set(xlabel='Absolute difference (zero shown at 1e-18)',ylabel='Cumulative fraction')

# CytoTRACE: two real technologies, six runs, stage agreement and input sensitivity.
p=BASE/'cyto';metrics=pd.read_csv(p/'metrics.csv');rt=pd.read_csv(p/'r_timings.csv')
fig,ax=canvas()
for i,ds in enumerate(['marrow_10x','marrow_plate']):
    x=pd.read_csv(p/f'{ds}_400_input.csv',index_col=0).values
    py=pd.read_csv(p/f'{ds}_400_python.csv')
    # Display PCA on log library-normalized expression; never supplied to scoring.
    z=np.log1p(x/np.maximum(x.sum(axis=0),1)*1e4).T
    z=z[:,np.argsort(z.var(axis=0))[-1000:]];u,s,v=np.linalg.svd(z-z.mean(axis=0),full_matrices=False)
    m=ax[i].scatter(u[:,0]*s[0],u[:,1]*s[1],c=py.score,cmap='viridis',s=12,vmin=0,vmax=1)
    fig.colorbar(m,ax=ax[i],label='CytoTRACE');ax[i].set(title=ds+' (400 cells)',xlabel='Display PC1',ylabel='Display PC2')
    ax[i+2].scatter(py.counts,py.score,s=10,alpha=.6);ax[i+2].set(title=ds+': biological signal diagnostic',xlabel='Detected genes',ylabel='CytoTRACE')
save(fig,'pycytotrace',1,4)
fig,ax=canvas()
for i,ds in enumerate(['marrow_10x','marrow_plate']):
    r=pd.read_csv(p/f'{ds}_400_r.csv');py=pd.read_csv(p/f'{ds}_400_python.csv');identity(ax[i],r.score,py.score,ds+': score agreement')
    for n in [100,200,400]:
        r=pd.read_csv(p/f'{ds}_{n}_r.csv');py=pd.read_csv(p/f'{ds}_{n}_python.csv');ecdf(ax[i+2],r.gcs-py.gcs,f'n={n}')
    ax[i+2].set_title(ds+': GCS differences');ax[i+2].legend()
save(fig,'pycytotrace',2,4)
fig,ax=canvas()
for i,ds in enumerate(['marrow_10x','marrow_plate']):
    py=pd.read_csv(p/f'{ds}_400_python.csv');identity(ax[i],py.score,py.restricted_score,ds+': restricting genes changes ranks')
    ax[i].set(xlabel='All measured genes',ylabel='Top 3,000 by variance')
    mm=metrics[metrics.tag.str.startswith(ds)];rr=rt[rt.dataset==ds]
    ax[2].plot(mm.n,mm.restricted_gene_score_rho,'o-',label=ds)
    ax[3].plot(mm.n,mm.python_seconds,'o-',label=ds+' Python');ax[3].plot(rr.n,rr.seconds,'s--',label=ds+' R')
ax[2].set(xlabel='Cells',ylabel='Spearman (all vs restricted genes)',ylim=(.9,1),title='Input sensitivity across sizes');ax[2].legend()
ax[3].set(xlabel='Cells',ylabel='Elapsed seconds',title='Observed single runs (not a speed guarantee)');ax[3].legend(fontsize=8)
save(fig,'pycytotrace',3,4)

# SPLIT: real input, native R decisions, corrected shift and receiver controls.
p=BASE/'spatial';f=np.load(ROOT/'repos/rewrite-split/examples/data/split_dlpfc_151673.npz');xy=f['coords']
fig,ax=canvas();raw=f['counts'].sum(axis=1);pur=f['r_purified'].sum(axis=1);limit=max(raw.max(),pur.max())
for a,v,title in [(ax[0],raw,'Observed counts'),(ax[1],pur,'Purified counts: illustrative weights')]:fig.colorbar(spatial(a,xy,v,title,vmin=0,vmax=limit),ax=a)
fig.colorbar(spatial(ax[2],xy,f['weights'].max(axis=1),'Largest fitted layer weight',vmin=0,vmax=1),ax=ax[2])
ax[3].hist(1-pur/np.maximum(raw,1),bins=25,color='#377eb8');ax[3].set(xlabel='Fraction removed',ylabel='Spots',title='Numerical change; no clean-count ground truth')
save(fig,'splitst',1,4)
fig,ax=canvas();metrics=pd.read_csv(p/'split_metrics.csv')
for i,swap in enumerate([0,1]):
    z=np.load(p/f'split_t0.15_swap{swap}_comparison.npz');identity(ax[i],z['r'].ravel()[::10],z['python'].ravel()[::10],f'Native R balance: swap={swap}')
    for th in [.05,.15,.3,.5]:
        z=np.load(p/f'split_t{th}_swap{swap}_comparison.npz');ecdf(ax[i+2],z['r']-z['python'],f'threshold={th}')
    ax[i+2].legend();ax[i+2].set_title(f'Expression error distributions: swap={swap}')
save(fig,'splitst',2,4)
fig,ax=canvas()
for i,th in enumerate([.05,.15,.3,.5]):
    meta=pd.read_csv(p/f'metadata_t{th}_swap0.csv',index_col=0);counts=meta.purification_status.value_counts()
    ax[0].bar(i,counts.get('raw',0),color='#377eb8');ax[0].bar(i,counts.get('purified',0),bottom=counts.get('raw',0),color='#e69f00')
ax[0].set(xticks=range(4),xticklabels=['.05','.15','.30','.50'],xlabel='Balance threshold',ylabel='Retained spots',title='Native R decisions: blue raw / orange purified')
meta=pd.read_csv(p/'split_control_metadata.csv',index_col=0)
ax[1].bar(['retained','rejected','swap controls'],[234,6,31],color=['#377eb8','#777777','#e69f00']);ax[1].set(ylabel='Spots',title='Explicit controls, not biological inference')
z0=np.load(p/'split_t0.15_swap0_comparison.npz');z1=np.load(p/'split_t0.15_swap1_comparison.npz')
ax[2].hist((z1['python']-z0['python']).sum(axis=1),bins=30,color='#377eb8');ax[2].set(xlabel='Per-spot total change after swapping',ylabel='Spots',title='Label swap also changes expression')
a=AnnData(f['counts'],obs=pd.DataFrame(index=f['cells']),var=pd.DataFrame(index=f['genes']));a.layers['counts']=a.X.copy();a.obsm['spatial']=xy
w=pd.DataFrame(f['weights'],index=a.obs_names,columns=f['types']);r=pd.DataFrame(f['reference'],index=f['types'],columns=f['genes'])
splitst.purify(a,w,r);splitst.spatial_score(a,w,a.obs.first_type,k=12);splitst.balance(a)
mass=[]
for policy in ['second_type','all']:
    splitst.reassign_residuals(a,k=12,receiver_policy=policy);s=a.uns['split_residual_stats'];mass.append([s['assigned_residual_total'],s['unassigned_residual_total']])
mass=np.array(mass);ax[3].bar(['matching type','all neighbors'],mass[:,0],label='assigned');ax[3].bar(['matching type','all neighbors'],mass[:,1],bottom=mass[:,0],label='unassigned');ax[3].set(ylabel='Residual count mass',title='Recipient policy affects redistribution');ax[3].legend()
save(fig,'splitst',3,4)

# SPATA2: actual package outline and labels, parameter sensitivity, scale behavior.
f=np.load(ROOT/'repos/rewrite-spata2/examples/data/dlpfc_coords.npz');xy=f['coords'];flags=f['expected'].astype(bool)
r=pd.read_csv(p/'spata_native_outline.csv');h=np.load(p/'spata_python_outline.npy');h=np.vstack([h,h[0]])
fig,ax=canvas()
spatial(ax[0],xy[:-5],np.where(flags[:-5],1,0),'Native candidates (yellow); no artifact truth',vmin=0,vmax=1)
ax[1].scatter(xy[:-5,0],xy[:-5,1],s=2,color='#cccccc');ax[1].plot(h[:,0],h[:,1],label='Python convex')
for _,group in r.groupby('section'):ax[1].plot(group.x_orig,group.y_orig,label='R SPATA2 outline')
ax[1].set(title='A real algorithmic difference',aspect='equal',xlabel='Spatial x',ylabel='Spatial y');ax[1].invert_yaxis();ax[1].legend()
ax[2].scatter(xy[:-5,0],xy[:-5,1],s=2,label='Real tissue');ax[2].scatter(xy[-5:,0],xy[-5:,1],marker='x',label='Planted controls');ax[2].legend();ax[2].set(title='Artificial controls kept separate',xlabel='Spatial x',ylabel='Spatial y')
labels=pd.read_csv(p/'spata_native_labels.csv').tissue_section.eq('tissue_section_0').values
conf=np.array([[np.sum(~flags&~labels),np.sum(~flags&labels)],[np.sum(flags&~labels),np.sum(flags&labels)]])
ax[3].imshow(conf,cmap='Blues');ax[3].set(xticks=[0,1],xticklabels=['retained','noise'],yticks=[0,1],yticklabels=['retained','noise'],xlabel='Original SPATA2',ylabel='Python',title='Noise-label comparison')
for i in range(2):
 for j in range(2):ax[3].text(j,i,str(conf[i,j]),ha='center',va='center',color='black' if conf[i,j]<100 else 'white')
save(fig,'spata2py',1,4)
sens=pd.read_csv(p/'spata_sensitivity.csv');fig,ax=canvas()
for a,key,title in zip(ax[:2],['native_flags','control_hits'],['Native candidates vary with parameters','Planted controls recovered (of five)']):
    pivot=sens.pivot(index='min_neighbors',columns='radius_factor',values=key);im=a.imshow(pivot,cmap='viridis');a.set(xticks=range(4),xticklabels=pivot.columns,yticks=range(3),yticklabels=pivot.index,xlabel='Radius / nearest-neighbor spacing',ylabel='Minimum other neighbors',title=title);fig.colorbar(im,ax=a)
    for i in range(3):
     for j in range(4):a.text(j,i,str(pivot.iloc[i,j]),ha='center',va='center',color='white')
a=AnnData(sparse.csr_matrix((len(xy),1)));a.obsm['spatial']=xy
mad=spata2py.identify_spatial_outliers(a,method='mad').values
ax[2].bar(['DBSCAN native','MAD native','DBSCAN control','MAD control'],[flags[:-5].sum(),mad[:-5].sum(),flags[-5:].sum(),mad[-5:].sum()]);ax[2].tick_params(axis='x',rotation=20);ax[2].set(ylabel='Flagged points',title='Distinct rules, not interchangeable defaults')
spacing=cKDTree(xy[:-5]).query(xy[:-5],k=2)[0][:,1];ax[3].hist(spacing,bins=35);ax[3].set(xlabel='Nearest-neighbor distance',ylabel='Spots',title='Spacing distribution on retained tissue')
save(fig,'spata2py',2,4)
fig,ax=canvas();scale_results=[]
for scale in [.01,.1,1,10,100]:
    a.obsm['spatial']=xy*scale;ff=spata2py.identify_spatial_outliers(a).values;scale_results.append(int((ff!=flags).sum()))
ax[0].plot([.01,.1,1,10,100],scale_results,'o-');ax[0].set(xscale='log',xlabel='Coordinate scale factor',ylabel='Flag disagreements',title='Automatic radius rescales with coordinates')
roundtrip=spata2py.unit_to_pixels(spata2py.pixels_to_unit(xy,pixels_per_unit=3.7),pixels_per_unit=3.7)-xy
ecdf(ax[1],roundtrip,'coordinate round trip');ax[1].set_title('Explicit unit-conversion round trip')
def area(v):return abs(np.sum(v[:,0]*np.roll(v[:,1],-1)-v[:,1]*np.roll(v[:,0],-1)))/2
ra=sum(area(g[['x_orig','y_orig']].values) for _,g in r.groupby('section'));ha=area(h)
ax[2].bar(['R concave','Python convex'],[ra,ha]);ax[2].set(ylabel='Area (coordinate units squared)',title='Outline area is not equivalent')
xs=np.linspace(xy[:-5,0].min(),xy[:-5,0].max(),200);ys=np.linspace(xy[:-5,1].min(),xy[:-5,1].max(),200);gx,gy=np.meshgrid(xs,ys);grid=np.c_[gx.ravel(),gy.ravel()]
inside_r=np.zeros(len(grid),bool)
for _,g in r.groupby('section'):inside_r |= PolygonPath(g[['x_orig','y_orig']].values).contains_points(grid)
inside_p=PolygonPath(h).contains_points(grid);iou=np.sum(inside_r&inside_p)/np.sum(inside_r|inside_p)
ax[3].imshow((inside_p.astype(int)+inside_r.astype(int)*2).reshape(200,200),extent=[xs.min(),xs.max(),ys.max(),ys.min()],cmap='viridis');ax[3].set(title=f'Outline overlap: grid IoU {iou:.3f}',xlabel='Spatial x',ylabel='Spatial y')
from matplotlib.patches import Patch
ax[3].legend(handles=[Patch(color=plt.cm.viridis(0),label='Neither'),Patch(color=plt.cm.viridis(1/3),label='Python only'),Patch(color=plt.cm.viridis(1.),label='Both')],loc='lower left',fontsize=8)
(p/'outline_metrics.json').write_text(json.dumps({'R_area':ra,'Python_area':ha,'grid_iou':iou,'grid_resolution':200,'scale_flag_disagreements':scale_results,'unit_roundtrip_max_error':float(abs(roundtrip).max())},indent=2))
save(fig,'spata2py',3,4)

# Scissor: preserve selection, full-path and native-graph distinctions.
p=ROOT/'outputs/scissor-discrepancy-audit';fig,ax=canvas()
for i,family in enumerate(['binomial','cox']):
    r=pd.read_csv(p/f'r_{family}_cv.csv');py=pd.read_csv(p/f'python_{family}_cv.csv');ax[i].plot(py['lambda'],py.loss,label='Python');ax[i].plot(r['lambda'],r.cvm,'--',label='R');ax[i].set(xscale='log',xlabel='Lambda',ylabel='CV loss',title=family+' matched-fold CV');ax[i].legend()
    c=pd.read_csv(p/f'{family}_cell_comparison.csv');identity(ax[i+2],c.R,c.Python,family+' selected coefficients')
save(fig,'scissor-validation',1,4)
r=np.fromfile(p/'r-cox-checkpoints/full-coefficients.f64',dtype='<f8').reshape((4102,100),order='F');py=np.load(p/'python_cox_path.npy');err=abs(py-r);threshold=1e-5+1e-4*abs(r)
fig,ax=canvas();lam=pd.read_csv(p/'python_cox_cv.csv')['lambda'].values
ax[0].plot(lam,err.max(axis=0));ax[0].set(xscale='log',yscale='log',xlabel='Lambda',ylabel='Maximum coefficient difference',title='Original 1e-7 solver tolerance')
ax[1].plot(lam,(err>threshold).sum(axis=0));ax[1].set(xscale='log',xlabel='Lambda',ylabel='Entries beyond comparison tolerance',title='Whole-path failures are visible')
ecdf(ax[2],err,'1e-7 original')
q=BASE/'cox';tight={}
if (q/'r_path_1e9.f64').exists() and (q/'python_path_1e9.npy').exists():
    r2=np.fromfile(q/'r_path_1e9.f64',dtype='<f8').reshape((4102,100),order='F');p2=np.load(q/'python_path_1e9.npy');e2=abs(r2-p2)
    ecdf(ax[2],e2,'1e-9 tighter');tight={'max_error':float(e2.max()),'outside_tolerance':int((e2>1e-5+1e-4*abs(r2)).sum())};(q/'comparison.json').write_text(json.dumps(tight,indent=2))
    cert=pd.read_csv(q/'r_certificates.csv');ax[3].plot(cert['lambda'],cert.kkt);ax[3].axhline(1e-9,color='red',ls='--');ax[3].set(xscale='log',yscale='log',xlabel='Lambda',ylabel='Independent R KKT residual',title='Tighter solve convergence certificates')
else:
    ax[3].text(.1,.5,'Tighter-tolerance run not yet available',transform=ax[3].transAxes);ax[3].set_axis_off()
ax[2].legend();ax[2].set_title('Coefficient-error distributions');save(fig,'scissor-validation',2,4)
fig,ax=canvas()
for i,(tag,fam) in enumerate([('tp53','binomial'),('survival','cox')]):
    native=pd.read_csv(p/f'native_{tag}_coefficients.csv',index_col=0).iloc[:,0];fixed=pd.read_csv(p/f'python_{fam}_coefficients.csv').set_index('cell').coefficient;native=native.reindex(fixed.index)
    identity(ax[i],fixed.values,native.values,tag+': graph/workflow sensitivity');ax[i].set(xlabel='Fixed R-graph protocol',ylabel='Native Python workflow')
    cats=['negative','zero','positive'];table=np.zeros((3,3),int)
    for a0,b0 in zip(np.sign(fixed).astype(int)+1,np.sign(native).astype(int)+1):table[a0,b0]+=1
    im=ax[i+2].imshow(table,cmap='Blues');ax[i+2].set(xticks=range(3),xticklabels=cats,yticks=range(3),yticklabels=cats,xlabel='Native workflow',ylabel='Fixed protocol',title=tag+': label transition counts')
    for row in range(3):
     for col in range(3):ax[i+2].text(col,row,str(table[row,col]),ha='center',va='center',color='white' if table[row,col]>1000 else 'black')
save(fig,'scissor-validation',3,4)
(BASE/'figure_inventory.json').write_text(json.dumps(inventory,indent=2));print('Wrote',len(inventory),'figures')
