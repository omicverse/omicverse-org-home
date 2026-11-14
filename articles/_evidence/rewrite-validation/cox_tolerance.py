from pathlib import Path
from workspace_paths import WORKSPACE
import time,json,numpy as np,pandas as pd
from scipy import io
from scissor_py import fit_path
root=WORKSPACE/'outputs/scissor-discrepancy-audit';out=Path(__file__).parent/'cox';out.mkdir(exist_ok=True)
X=np.fromfile(root/'survival_X.bin',dtype='<f8').reshape((471,4102),order='F')
y=pd.read_csv(root/'survival_y.csv').values;A=io.mmread(root/'r_graph.mtx').tocsr()
lambdas=pd.read_csv(root/'python_cox_cv.csv')['lambda'].values
start=time.perf_counter()
fit=fit_path(X,y,A,family='cox',alpha=.05,semantics='corrected',lambdas=lambdas,thresh=1e-9)
np.save(out/'python_path_1e9.npy',fit.coefficients)
(out/'python_summary.json').write_text(json.dumps({'seconds':time.perf_counter()-start,'shape':list(fit.coefficients.shape)}))
print('Completed tighter-tolerance full path',flush=True)
