import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import norm
from math import sqrt, log, exp, cos, pi
from itertools import product
import multiprocessing as mp
import bspline
import bspline.splinelab as splinelab
import os, sys
path = os.path.join('..', 'src')
if path not in set(sys.path):
    sys.path.append(path)
from sab import falpha, SABC_HTE

def phi(x, delta, typ):
    if typ == 1:
        return delta*x
    elif typ == 2:
        return delta*np.cos(x/pi)
    elif typ == 3:
        return delta*x**2/3.
    else:
        return x

np.random.seed(1234567)

nsim = 400
B = 10000
start_n = 1000 # sample size at first analysis
typ_list = [2, 3] # phi function type list
nk_list = [(200, 5), (20, 50)] #
delta_list = [0.0, 0.10, 0.15, 0.20, 0.25, 0.30] # effect size typ three
alpha = 0.05
e = 0.5 # error variance
ms = [1, 2, 3] # alpha spending functions
lm = len(ms)

lb, ub = -2, 2

order  = 3  # order of spline (as-is; 3 = cubic)
nknots = 4  # number of knots to generate
knots = np.linspace(lb, ub, nknots)      # create a knot vector without endpoint repeats
knots = splinelab.augknt(knots, order)   # add endpoint repeats as appropriate for spline order
bases = bspline.Bspline(knots, order)    # create spline basis of order p on knots k
nfeatures = 3
p = nfeatures*(order+nknots-1)+1

rho = 0.5
cov_mat = (1-rho) * np.eye(nfeatures) + rho*np.ones((nfeatures, nfeatures))
L = np.linalg.cholesky(cov_mat).T

for (typ, (n, k), delta) in product(typ_list, nk_list, delta_list):
    
    name = 'result/HTE/'+'typ'+str(typ)+'n'+str(n)+'k'+str(k)+'delta'+str(delta)+'_nonlinear_HTE.npz'
    
#     if os.path.exists(name):
#         continue

    ratios = np.ones(k)*n
    ratios[0] = start_n
    ratios = ratios.cumsum()
    ratios = ratios*1.0/ratios[-1]
    alphas = np.zeros((lm, k))
    for idx in range(lm):
        alphas[idx,:] = falpha(ratios, alpha, ms[idx])
        
    def one_step(seed):
        np.random.seed(seed)
        
        rej_one_step = np.zeros(lm)
        
        sabcs = [SABC_HTE(alpha=alpha, B=B, p=p) for _ in range(lm)]
        
        done, target = 0, lm
        for j in range(k):
            this_n = start_n if j == 0 else n
            
            X0 = np.random.randn(this_n, nfeatures).dot(L).clip(lb, ub)
            X1 = np.random.randn(this_n, nfeatures).dot(L).clip(lb, ub)
            y0 = 1 + (X0[:,0]-X0[:,1])/2+ np.random.randn(this_n)*e
            y1 = 1 + (X1[:,0]-X1[:,1])/2 + phi((X1[:,0]+X1[:,1])/sqrt(2.), delta, typ)*(X1[:,2])**2 + np.random.randn(this_n)*e
            
            ### basis expansion
            X0 = np.hstack([bases.collmat(X0[:,i]) for i in range(X0.shape[1])])
            X1 = np.hstack([bases.collmat(X1[:,i]) for i in range(X1.shape[1])])
            X0 = sm.add_constant(X0)
            X1 = sm.add_constant(X1)
            
            for l in range(lm):
                if sabcs[l].rej == 0: # if not rejected, check this data batch
                    sabcs[l].fit(X0, y0, X1, y1, alphas[l,j], approx=False)
                    if sabcs[l].rej:  # if rejected, update done
                        rej_one_step[l] = sabcs[l].rej
                        done += 1

            if done == target:
                break
                
        return rej_one_step
    
    pool = mp.Pool(10)
    rets = pool.map(one_step, range(nsim))
    rets = np.array(rets)
    pool.close()
    
    np.savez(name, rej_sabc=rets)
