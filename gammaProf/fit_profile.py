import pdb
import copy
import numpy as np
from lensing_system import obs_lens_system
from analytic_profiles import NFW
from scipy import optimize
from mass_concentration import child2018
import matplotlib.pyplot as plt

def fit_nfw_profile_lstq(data, profile, rad_bounds, conc_bounds = [0,10], cM_relation=None, 
                         bootstrap=False, bootN = 1000, bootF = 0.5, Nsigma = 1):
    """
    Fits an NFW-predicted :math:`\\Delta\\Sigma(r)` profile to a background shear dataset. To use
    this function, the user should first instantiate a `obs_lens_system` object, which will hold the
    observed data to fit to, and an `NFW` object, which will describe the analytic form which should
    describe the data. The present function is then the mediator between these objects that will
    facilitate the minimization routine. Parameter errors can be estaimted via a bootstrap routine
    (turned off by default).

    Parameters
    ----------
    data : `obs_len_system` class instance
        An instance of a `obs_lens_system` object as provided by `lensing_system.py`. 
        This is an object representing a lensing system, and contains data vectors 
        describing properties of a cluster's background sources
    profile : `NFW` class instance
        An instance of a `NFW` object as provided by `analytic_profiles.py`. This is
        an object representing an analytic NFW profile, and computes the predicted 
        projected surface density
    rad_bounds : 2-element list
        The bounds (tophat prior) for the first fitting parameter, :math:`r_{200c}`
    conc_bounds : 2-element list, optional
        The bounds (tophat prior) for the second fitting parameter, :math:`c`. Defaults to [0,10]
    cM_relation : string, optional
        The name of a :math:`c-M` relation to use in the fitting procedure. If `None`, then the 
        minimization will proceed with respect to both :math:`r_200c` and :math:`c`. If provided
        as a `string`, then infer the concentration from the :math:`c-M` relation on each iteration of 
        the least squares routine (in this case, the `conc_bounds` arg need not be passed). Options are 
        `{'child2018'}`. Defaults to `None`.
    bootstrap : boolean
        Whether or not to perform fitted parameter bootstrap error estaimtion
    bootN: int
        The number of realizations from the input data given by `data` to include in the bootstrap
    bootF:
        The fraction of the initial dataset `data` to include in each bootstrap realization
    Nsigma:
        The bootstrap confidence interval to return; `Nsigma=1` will return :math:`1\\sigma`, or ~68%, intervals

    Returns
    -------
    list: [SciPy `OptimizeResult` object, list]
        Fields for the first element of the return list are defined as detailed in the return signature 
        of `scipy.optimize.least_squares`. See documentation here: 
        https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html
        The second element is a list of the bootstrap errors, for the radius and concentration parameters
    """
    
    # get the background data, and scale the tangential shear to ΔΣ 
    sources = data.get_background()
    Ec = data.calc_sigma_crit()
    dSigma_data = sources['yt'] * Ec
    r = sources['r']

    # get parameter guesses from initial NFW form
    rad_init = profile.r200c
    conc_init = profile.c

    # initiate the fitting algorithm
    if(cM_relation is None):
        fit_params = [rad_init, conc_init]
        bounds = ([rad_bounds[0], conc_bounds[0]],
                  [rad_bounds[1], conc_bounds[1]])
    else:
        cM_func = {'child2018':child2018}[cM_relation]
        fit_params = [rad_init]
        bounds = ([rad_bounds[0], rad_bounds[1]])
    
    res = optimize.least_squares(_nfw_fit_residual, fit_params, 
                                 args=(profile, r, dSigma_data, cM_relation), 
                                 bounds = bounds)
    
    # if inferring the concentration from a c-M relation, then the 
    # final minimization iteration updated the radius only; update c before return
    if(cM_relation is not None):
        m200c = profile.radius_to_mass()
        c_final = cM_func(m200c)
        profile.c = c_final
    
    # if bootstrap==True, then repeat the entire process above bootN times to estimate the
    # recovered parameter errors, else return errors of 0
    if(bootstrap):
        bootstrap_profile = copy.deepcopy(profile)
        params_bootstrap = np.zeros((bootN, 2))
        for n in range(bootN):
            bootstrap_profile.r200c = rad_init
            bootstrap_profile.c = conc_init
            boot_i = np.random.choice(np.arange(len(r)), int(len(r)*bootF), replace=True)
            res_i = optimize.least_squares(_nfw_fit_residual, fit_params, 
                                           args=(bootstrap_profile, r[boot_i], dSigma_data[boot_i], 
                                           cM_relation), bounds = bounds)
            if(cM_relation is not None):
                m200c = bootstrap_profile.radius_to_mass()
                c_final = cM_func(m200c)
                params_bootstrap[n][0] = res_i.x[0]
                params_bootstrap[n][1] = c_final
            else:
                params_bootstrap[n] = res_i.x
        param_err = Nsigma * np.std(params_bootstrap, axis=0)
    else:
        param_err = [0, 0]

    return [res, param_err]


    
def _nfw_fit_residual(fit_params, profile, r, dSigma_data, cM_relation):
    """
    Evaluate the residual of an NFW profile fit to data, given updated parameter values. 
    This function meant to be called iteratively from `fit_nfw_profile_lstq` only.

    Parameters
    ----------
    fit_params : float list
        The NFW parameter(s) to update for this least squares iteration 
        (either a single-element list including the radius, [r200c], or also including
        the concentration parameter=, [r200c, c])
    profile : `NFW` class instance
        An instance of a `NFW` object as provided by `analytic_profiles.py`. This is the 
        object that is being augmented per-iteration in the calling least squares routine 
    r : float array
        The halo-centric radial distances for the sources whose shears are given by yt_data
        (the NFW profile fitting form will be evaluated at these locations)
    dSigma_data : float array
        tangential shear values for a collection of background sources, against which to fit
        the profile
    cM_relation:
        The name of a :math:`c-M` relation to use in the fitting procedure. If `None`, then the 
        minimization will proceed with respect to both :math:`r_200c` and :math:`c`. If provided
        as a `string`, then infer the concentration from the :math:`c-M` relation on each iteration of 
        the least squares routine. Options are `{'child2018'}`.

    Returns
    -------
    residuals : float array
        The residuals between the data `dSigma_data`, and the NFW result given the `fit_params`, `dSigma_nfw`. 
        The residuals, in this case, are the difference `dSigma_data - dSigma_nfw`.
    """
   
    # update the NFW profile object
    if(len(fit_params) > 1):
        
        # floating concentration
        r200c, c = fit_params[0], fit_params[1]
        profile.r200c = r200c
        profile.c = c
    
    else:
        
        # concentration modeled from c-M relation
        r200c = fit_params[0]
        profile.r200c = r200c
        
        cM_func = {'child2018':child2018}[cM_relation]
        m200c = profile.radius_to_mass()
        c_new = cM_func(m200c)
        profile.c = c_new
        
    
    # evaluate NFW form
    dSigma_nfw = profile.delta_sigma(r)
    
    # residuals
    residuals = dSigma_nfw - dSigma_data
    return residuals 


def fit_nfw_profile_gridscan(data, profile, rad_bounds, conc_bounds = [0,10], n = 100):
    """
    Performs an NFW parameter sweep on :math:`r_{200c}` and :math:`c_{200c}`, evaluating
    the squared sum of residuals against the input data for each sample point in the
    parametre space.

    Parameters
    ----------
    data : `obs_len_system` class instance
        An instance of a `obs_lens_system` object as provided by `lensing_system.py`. 
        This is an object representing a lensing system, and contains data vectors 
        describing properties of a cluster's background sources
    profile : `NFW` class instance
        An instance of a `NFW` object as provided by `analytic_profiles.py`. This is
        an object representing an analytic NFW profile, and computes the predicted 
        projected surface density
    rad_bounds : 2-element list
        The bounds (tophat prior) for the first fitting parameter, :math:`r_{200c}`
    conc_bounds : 2-element list, optional
        The bounds (tophat prior) for the second fitting parameter, :math:`c`. Defaults to [0,10]
    n : int
        The number of sample points in each dimension of the parameter grid, which will be 
        distributed linearly between the limits given by `rad_bounds` and `conc_bounds`

    Return
    ------
    list of two 2d numpy arrays
        First element is a meshgrid giving the radius and concentration values of each sample 
        point used. Second element is the :math:`\\chi^2` at each one of those points.
    """

    profile = copy.deepcopy(profile)

    rsamp = np.linspace(rad_bounds[0], rad_bounds[1], n)
    csamp = np.linspace(conc_bounds[0], conc_bounds[1], n)
    
    # get the background data, and scale the tangential shear to ΔΣ 
    sources = data.get_background()
    Ec = data.calc_sigma_crit()
    dSigma_data = sources['yt'] * Ec
    r = sources['r']
   
    cost = np.zeros((n, n))

    for i in range(n):
        for j in range(n):
            grid_params = [rsamp[j], csamp[i]]
            residuals = _nfw_fit_residual(grid_params, profile, r, dSigma_data, cM_relation=None)
            cost[i][j] = np.sum(residuals**2) 

    return [np.meshgrid(rsamp, csamp), cost]
