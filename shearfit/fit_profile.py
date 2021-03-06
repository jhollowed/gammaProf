import pdb
import copy
import numpy as np
from scipy import stats
from scipy import optimize
import matplotlib.pyplot as plt
from analytic_profiles import NFW
from mass_concentration import child2018
from lensing_system import obs_lens_system
cM_dict = {'child2018':child2018}

def fit_nfw_profile_lstq(data, profile, r200_bounds, conc_bounds = [0,10], rmin=0, rmax=None, cM_relation=None, 
                         bin_data = False, bins=None, bootstrap=False, bootN = 1000, bootF = 1.0, 
                         replace=True, skipShear=False):
    """
    Fits an NFW-predicted :math:`\\Delta\\Sigma(r)` profile to a background shear dataset. To use
    this function, the user should first instantiate a `obs_lens_system` object, which will hold the
    observed data to fit to, and an `NFW` object, which will give the analytic form which should
    describe the data. The present function is then the mediator between these objects that will
    facilitate the minimization routine. Parameter errors can be estaimted via a bootstrap routine
    (turned off by default). Note: This function modifies the input `profile` object;  
    final fit parameters, and their errors, will be given in the `r200c`, `c`, `r200c_err`, and `c_err`
    attributes of `profile`.

    Parameters
    ----------
    data : `obs_len_system` class instance
        An instance of a `obs_lens_system` object as provided by `lensing_system.py`. 
        This is an object representing a lensing system, and contains data vectors 
        describing properties of a cluster's background sources.
    profile : `NFW` class instance
        An instance of a `NFW` object as provided by `analytic_profiles.py`. This is
        an object representing an analytic NFW profile, and computes the predicted 
        projected surface density. This object is modified by the present function; the 
        final fit parameters, and their errors, will be given in the `r200c`, `c`, `r200c_err`, 
        and `c_err` attributes of `profile`.
    r200_bounds : 2-element list
        The bounds (tophat prior) for the first fitting parameter, :math:`r_{200c}`.
    conc_bounds : 2-element list, optional
        The bounds (tophat prior) for the second fitting parameter, :math:`c`. Defaults to `[0,10]`.
    rmin : float, optional
        The minimum radial distance of sources to include in the fit in Mpc (e.g. rmin = 0.3 will
        remove the inner 300kpc/h of source information). Defaults to 0.
    rmax : float, optional
        The maximum radial distance of sources to include in the fit in Mpc (e.g. rmin = 2.0 will
        trim the source popiulation beyond 2Mpc. Defaults to None, in which case rmax will automatically be
        set to the furthest radial source position. This default will also be imposed if the input rmax is 
        greater than the size of the FOV.
    cM_relation : string, optional
        The name of a :math:`c-M` relation to use in the fitting procedure. If `None`, then the 
        minimization will proceed with respect to both :math:`r_200c` and :math:`c`. If provided
        as a `string`, then infer the concentration from the :math:`c-M` relation on each iteration 
        of the least squares routine (in this case, the `conc_bounds` arg need not be passed). 
        Options are `{'child2018'}`. Defaults to `None`.
    bin_data : boolean, optional
        Whether or not to average the shears given by the `data` object in radial bins. If True, fit 
        to the resulting binned averages rather than the input data points. Defaults to `False`.
    bins : int or float array, optional
        The `bins` argument to pass to `data.calc_delta_sigma_binned`, if `bin_data` ia set to `True`. 
        Defaults to `None`, though will crash if not provided while `bin_data` is `True`.
    bootstrap : boolean, optional
        Whether or not to perform fitted parameter bootstrap error estaimtion. If False, and also using 
        a c-M relation rather than fitting the concentration, then the intrinsic scatter of the c-M relation 
        is still given as an error on the best-fit `c` value. Else, no errors are given for either parameter.
        Defaults to `False`.
    bootN : int, optional
        The number of realizations from the input data given by `data` to include in the bootstrap. 
        Defaults to `1000`.
    bootF : float, optional
        The fraction of the initial dataset `data` to include in each bootstrap realization. 
        Defaults to `1.0`.
    replace : boolean, optional
        Whether or not to perform the bootstrap resamples with replacement. Defaults to `True`.
    skipShear : boolean, optional
        **DEPRECATED** 
        If this flag is set to `True`, then rather than scaling the shear magnitude by the critical surface, 
        and then fitting, the shear itself will be ignored, and the fitting procedure will directly access
        the density estimation result (if it was computed and stored as an attribute of obs_lens_system)

    Returns
    -------
    list: [SciPy `OptimizeResult` object, list]
        Fields for the first element of the return list are defined as detailed in the return signature 
        of `scipy.optimize.least_squares`. See documentation here: 
        https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html
        The second element is a list of the bootstrap errors, for the radius and concentration parameters.
        Note that this return is redundant; this function updates the input `profile` object to contain 
        the best fit parameters, and their errors.
    """
    
    # set radial cuts, get the background data, and ΔΣ
    data.set_radial_cuts(rmin, rmax)
    sources = data.get_background()
    r_all = sources['r']
    dSigma_data_all = data.calc_delta_sigma()
    if(bin_data): 
        if(bins is None): raise Exception('bin_data set to True but bins arg not provided')
        binned_data = data.calc_delta_sigma_binned(nbins=bins)
        r = binned_data['r_mean']
        dSigma_data = binned_data['delta_sigma_mean']
    else:
        r = r_all
        dSigma_data = dSigma_data_all
    
    # get parameter guesses from initial NFW form
    rad_init = profile.r200c
    conc_init = profile.c

    # initiate the fitting algorithm
    if(cM_relation is None):
        fit_params = [rad_init, conc_init]
        bounds = ([r200_bounds[0], conc_bounds[0]],
                  [r200_bounds[1], conc_bounds[1]])
    else:
        cM_func = cM_dict[cM_relation]
        fit_params = [rad_init]
        bounds = ([r200_bounds[0], r200_bounds[1]])
    
    res = optimize.least_squares(_nfw_fit_residual, fit_params, 
                                 args=(profile, r, dSigma_data, cM_relation), 
                                 bounds = bounds)
    
    # if inferring the concentration from a c-M relation, then the final minimization 
    # iteration updated the radius only; update c before return, and calculate the 
    # intrinsic c-M scatter
    if(cM_relation is not None):
        m200c = profile.radius_to_mass()
        c_final, c_err_final = cM_func(m200c, profile.zl, profile._cosmo)
        profile.c = c_final
        profile.c_err = c_err_final
    else:
        profile.c_err = 0
    profile.r200c_err = 0
    
    # if bootstrap==True, then repeat the entire process above bootN times to estimate the
    # recovered parameter errors. Else, return zero error on the radius, and return the 
    # intrinsic c-M scatter on the concentration (zero if c is free)
    # Because we are defining a unique mask on the population per-iteration of the bootstrap, 
    # we have to bin here, rather than use the built-in binning functions offered by the 
    # 'data' object
    if(bootstrap):
        bootstrap_profile = copy.deepcopy(profile)
        params_bootstrap = np.zeros((bootN, 2))
        c_intr_scatter_bootstrap = np.zeros(bootN)

        for n in range(bootN):
            bootstrap_profile.r200c = rad_init
            bootstrap_profile.c = conc_init
            
            boot_i = np.random.choice(np.arange(len(r_all)), int(len(r_all)*bootF), replace=replace)
            if(bin_data == True):
                r_i = r_all[boot_i]
                dSigma_data_i = dSigma_data_all[boot_i]
                [dSigma_data_i,_,_] = stats.binned_statistic(r_i, dSigma_data_i, statistic='mean', bins=bins)
                [r_i,_,_] = stats.binned_statistic(r_i, r_i, statistic='mean', bins=bins)
            else:
                r_i = r[boot_i]
                dSigma_data_i = dSigma_data[boot_i]

            res_i = optimize.least_squares(_nfw_fit_residual, fit_params, 
                                           args=(bootstrap_profile, r_i, dSigma_data_i, 
                                           cM_relation), bounds = bounds)
            if(cM_relation is not None):
                m200c = bootstrap_profile.radius_to_mass()
                params_bootstrap[n][0] = res_i.x[0]
                params_bootstrap[n][1], c_intr_scatter_bootstrap[n] = cM_func(m200c, profile.zl, profile._cosmo)
            else:
                params_bootstrap[n] = res_i.x
                c_intr_scatter_bootstrap[n] = 0
        
        # estimate the parameter uncertainty as the spread of the bootstrap fit values, 
        # adding the intrinsic c-M scatter to the concentration error (zero if c is free)
        param_err = np.std(params_bootstrap, axis=0) + \
                    [0, np.mean(c_intr_scatter_bootstrap)]

        # update profile object with errors
        profile.r200c_err = param_err[0]
        profile.c_err = param_err[1]
    
    else:
        param_err = [0,0]

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
        the concentration parameter=, [r200c, c]).
    profile : `NFW` class instance
        An instance of a `NFW` object as provided by `analytic_profiles.py`. This is the 
        object that is being augmented per-iteration in the calling least squares routine.
    r : float array
        The halo-centric radial distances for the sources whose shears are given by yt_data
        (the NFW profile fitting form will be evaluated at these locations).
    dSigma_data : float array
        tangential shear values for a collection of background sources, against which to fit
        the profile.
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
        
        cM_func = cM_dict[cM_relation]
        m200c = profile.radius_to_mass()
        c_new, _ = cM_func(m200c, profile.zl, profile._cosmo)
        profile.c = c_new
        
    # evaluate NFW form
    dSigma_nfw = profile.delta_sigma(r, bootstrap=False)
    
    # residuals
    residuals = dSigma_nfw - dSigma_data
    return residuals 


def fit_nfw_profile_gridscan(data, profile, r200_bounds, conc_bounds = [0,10], rmin = 0, rmax = None, 
                             n = 100, bin_data=False, bins=None):
    """
    Performs an NFW parameter sweep on :math:`r_{200c}` and :math:`c_{200c}`, evaluating
    the squared sum of residuals against the input data for each sample point in the
    parametre space.

    Parameters
    ----------
    data : `obs_len_system` class instance
        An instance of a `obs_lens_system` object as provided by `lensing_system.py`. 
        This is an object representing a lensing system, and contains data vectors 
        describing properties of a cluster's background sources.
    profile : `NFW` class instance
        An instance of a `NFW` object as provided by `analytic_profiles.py`. This is
        an object representing an analytic NFW profile, and computes the predicted 
        projected surface density.
    r200_bounds : 2-element list
        The bounds (tophat prior) for the first fitting parameter, :math:`r_{200c}`.
    conc_bounds : 2-element list, optional
        The bounds (tophat prior) for the second fitting parameter, :math:`c`. Defaults to [0,10].
    rmin : float, optional
        The minimum radial distance of sources to include in the fit in Mpc (e.g. rmin = 0.3 will
        remove the inner 300kpc/h of source information). Defaults to 0.
    rmax : float, optional
        The maximum radial distance of sources to include in the fit in Mpc (e.g. rmin = 2.0 will
        trim the source popiulation beyond 2Mpc. Defaults to None, in which case rmax will automatically be
        set to the furthest radial source position. This default will also be imposed if the input rmax is 
        greater than the size of the FOV.
    n : int
        The number of sample points in each dimension of the parameter grid, which will be 
        distributed linearly between the limits given by `r200_bounds` and `conc_bounds`.
    bin_data : boolean, optional
        Whether or not to average the shears given by the `data` object in radial bins. If True, fit 
        to the resulting binned averages rather than the input data points. Defaults to `False`.
    bins : int or float array, optional
        The `bins` argument to pass to `data.calc_delta_sigma_binned`, if `bin_data` ia set to `True`. 
        Defaults to `None`, though will crash if not provided while `bin_data` is `True`.

    Return
    ------
    list of two 2d numpy arrays
        First element is a meshgrid giving the radius and concentration values of each sample 
        point used. Second element is the :math:`\\chi^2` at each one of those points.
    """

    profile = copy.deepcopy(profile)

    rsamp = np.linspace(r200_bounds[0], r200_bounds[1], n)
    csamp = np.linspace(conc_bounds[0], conc_bounds[1], n)
    
    # set radial cuts, get the background data, and ΔΣ
    data.set_radial_cuts(rmin, rmax)
    sources = data.get_background()
    if(bin_data): 
        if(bins is None): raise Exception('bin_data set to True but bins arg not provided')
        binned_data = data.calc_delta_sigma_binned(nbins=bins)
        r = binned_data['r_mean']
        dSigma_data = binned_data['delta_sigma_mean']
    else:
        r = sources['r']
        dSigma_data = data.calc_delta_sigma()
 
    cost = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            grid_params = [rsamp[j], csamp[i]]
            residuals = _nfw_fit_residual(grid_params, profile, r, dSigma_data, cM_relation=None)
            cost[i][j] = np.sum(residuals**2) 

    return [np.meshgrid(rsamp, csamp), cost]
