import pdb
import warnings
import numpy as np
import astropy.units as units
import astropy.constants as const
from astropy.cosmology import WMAP7

class obs_lens_system:
    """
    This class constructs an object representing an observer-lens-source system, which contains the 
    lens redshift, and data vectors for the background sources of a given lens, including the lensing
    geometry, and methods to perform computations on that data.

    Parameters
    ----------
    zl : float
        The redshift of the lens.
    cosmo : object, optional
        An astropy cosmology object (defaults to `WMAP7`).

    Attributes
    ----------
    zl : float
        The redshift of the lens.
    has_sources : boolean
        Whether or not the background population has been set for this instance
        (`False` until `set_background()` is called).
    bg_theta1 : float array
        The source lens-centric azimuthal angular coordinates, in arcseconds
        (uninitialized until `set_background()` is called).
    bg_theta2 : float array
        The source lens-centric coaltitude angular coordinates, in arcseconds
        (uninitialized until `set_background()` is called).
    zs : float array
        Redshifts of background sources
        (uninitialized until `set_background()` is called).
    r : float array
        Projected separation of each source at the redshift `zl`, in comoving :math:`\\text{Mpc}/h`
        (uninitialized until `set_background()` is called).
    y1 : float array
        The real component of the source shears.
    y2 : float array
        The imaginary component of the source shears.
    yt : float array
        The source tangential shears.
    k : float array
        The source convergences.

    Methods
    -------
    set_background(theta1, theta2, zs, y1, y2)
        Defines and assigns background souce data vectors to attributes of the lens object.
    get_background()
        Returns the source population data vectors to the caller, as a list.
    calc_sigma_crit()
        Computes the critical surface density at the redshift `zl`.
    """
    
    def __init__(self, zl, cosmo=WMAP7):
        self.zl = zl
        self._cosmo = cosmo
        self._has_sources = False
        self._has_shear12 = False
        self._has_shear1 = False
        self._has_shear2 = False
        self._has_kappa = False
        self._has_rho = False
        self._theta1 = None
        self._theta2 = None
        self._zs = None
        self._r = None
        self._phi = None
        self._y1 = None
        self._y2 = None
        self._yt = None
        self._k =None


    def _check_sources(self):
        """
        Checks that set_background has been called (intended to be called before any
        operations on the attributes initialized by set_background()).
        """
        assert(self._has_sources), 'sources undefined; first run set_background()'
        

    def set_background(self, theta1, theta2, zs, y1=None, y2=None, yt=None, k=None, rho=None):
        '''
        Defines and assigns background souce data vectors to attributes of the lens object, 
        including the angular positions, redshifts, projected comoving distances from 
        the lens center in comoving :math:`\\text{Mpc}/h`, and shear components. The user 
        should either pass the shear components `y1` and `y2`, or the tangential shear `yt`; 
        if both or neither are passed, an exception will be raised.
        
        Parameters
        ----------
        theta1 : float array
            The source lens-centric azimuthal angular coordinates, in arcseconds.
        theta2 : float_array
            The source lens-centric coaltitude angular coordinates, in arcseconds.
        zs : float array
            The source redshifts.
        y1 : float array, optional
            The shear component :math:`\\gamma_1`. Must be passed along with `y2`, unless passing `yt`.
        y2 : float array, optional
            The shear component :math:`\\gamma_2`. Must be passed along with `y1`, unless passing `yt`.
        yt : float array, optional
            The tangential shear :math:`\\gamma_T`. Must be passed if not passing `y1` and `y2`.
        k : float array, optional
            The convergence :math:`\\kappa`. Not needed for any computations of this class, but is
            offered as a convenience. Defaults to `None`.
        rho : float array, optional
            The matter density at the projected source positions on the lens plane. Not needed for
            any computations of this class, but is offered as a convenience; intended use is in the
            case that the user wishes to fit `\\delta\\Sigma` directly to the projected mass density
            on the grid (output prior to ray-tracing). Defaults to `None`.
        '''

        # make sure shear was passed correctly -- either tangenetial, or components, not both
        # the _has_shear12 attribute will be used to communicate to other methods which usage
        # has been invoked
        if((y1 is None and y2 is None and yt is None) or
           ((y1 is not None or y2 is not None) and yt is not None)):
          raise Exception('Either y1 and y2 must be passed, or yt must be passed, not both.')
        
        # initialize source data vectors
        self._theta1 = np.array((np.pi/180) * (theta1/3600))
        self._theta2 = np.array((np.pi/180) * (theta2/3600))
        self._zs = np.array(zs)
        self._y1 = np.array(y1)
        self._y2 = np.array(y2)
        self._yt = np.array(yt)
        self._k = np.array(k)
        self._rho = np.array(rho)
        
        # set flags and compute additonal quantities
        if(yt is None): self._has_shear12 = True
        if(k is not None): self._has_kappa = True
        if(rho is not None): self._has_rho = True
        self._has_sources = True
        self._comp_bg_quantities()


    def _comp_bg_quantities(self):
        """
        Computes background source quantites that depend on the data vectors initialized in 
        set_baclground (this function meant to be called from the setter method of each 
        source property).
        """

        self._check_sources()
        
        # compute halo-centric projected radial separation of each source, in comoving Mpc/h
        self._r = np.linalg.norm([np.tan(self._theta1), np.tan(self._theta2)], axis=0) * \
                                  self._cosmo.comoving_distance(self.zl).value * self._cosmo.h 
        if(self._has_shear12):
            # compute tangential shear yt
            self._phi = np.arctan(self._theta2/self._theta1)
            #self._yt = -(self._y1 * np.cos(2*self._phi) + 
            #            self._y2*np.sin(2*self._phi))
            self._yt = np.sqrt(self._y1**2 + self._y2**2)
    
    
    def get_background(self):
        '''
        Returns the source population data vectors to the caller as a numpy 
        rec array, sorted in ascending order with respect to the halo-centric 
        radial distance

        Returns
        -------
        bg : 2d numpy array
            A list of the source population data vectors (2d numpy array), with
            labeled columns. 
            If shear components are being used (see docstring for `set_background()`,
            then the contents of the return array is 
            [theta1, theta2, r, zs, y1, y2, yt], where theta1 and theta2 are the 
            halo-centric angular positions of the sources in arcseconds, r is the 
            halo-centric projected radial distance of each source in comoving 
            :math:`\\text{Mpc}/h`, zs are the source redshifts, y1 and y2 are the 
            shear components of the sources, and yt are the source tangential shears.
            If only the tangential shear is being used, then y1 and y2 are omitted
        '''
        self._check_sources()
        
        bg_arrays = [(180/np.pi * self._theta1 * 3600),
                     (180/np.pi * self._theta2 * 3600),
                     self._r, self._zs, self._yt]
        bg_dtypes = [('theta1',float), ('theta2',float), ('r',float),
                     ('zs',float), ('yt',float)]
        
        if(self._has_shear12):
            bg_arrays.append(self._y1)
            bg_arrays.append(self._y2)
            bg_dtypes.append(('y1', float))
            bg_dtypes.append(('y2', float))
        if(self._has_kappa):
            bg_arrays.append(self._k)
            bg_dtypes.append(('k', float))
        if(self._has_rho):
            bg_arrays.append(self._rho)
            bg_dtypes.append(('rho', float))
       
        bg = np.rec.fromarrays(bg_arrays, dtype = bg_dtypes) 
        return bg
    

    @property
    def cosmo(self): return self._cosmo
    @cosmo.setter
    def cosmo(self, value): 
        self._cosmo = value
        self._comp_bg_quantities()

    @property
    def r(self): return self._r
    def r(self, value):
        raise Exception('Cannot change source \'r\' value; update source redshifts instead')

    @property
    def theta1(self): return self._theta1
    @theta1.setter
    def theta1(self, value): 
        self._theta1 = value
        self._comp_bg_quantities()
    
    @property
    def theta2(self): return self._theta2
    @theta2.setter
    def theta2(self, value): 
        self._theta2 = value
        self._comp_bg_quantities()
    
    @property
    def zs(self): return self._zs
    @theta1.setter
    def zs(self, value): 
        self._zs = value
        self._comp_bg_quantities()

    @property
    def k(self): return self._k
    @k.setter
    def k(self, value):
        self._k = value
        if(value is None): self._has_kappa = False
        else: self._has_kappa = True
    
    @property
    def y1(self): return self._y1
    @y1.setter
    def y1(self, value):
        if(not self._has_shear12):
            raise Exception('object initialized with yt rather than y1,y2; cannot call y1 setter')
        else:
            self._y1 = value
            self._comp_bg_quantities()
    
    @property
    def y2(self): return self._y2
    @y2.setter
    def y2(self, value): 
        if(not self._has_shear12):
            raise Exception('object initialized with yt rather than y1,y2; cannot call y2 setter')
        else:
            self._y2 = value
            self._comp_bg_quantities()
    
    @property
    def yt(self): return self._yt
    @yt.setter
    def yt(self, value): 
        self._yt = value
        if(self._has_shear12 or self._has_shear1 or self._has_shear2):
            warnings.warn('Warning: setting class attribute yt, but object was initialized' 
                          'with y1,y2 (or y1/y2 setters were called); shear components y1'
                          'and y2 being set to None')
            self._has_shear12 = False
            self._y1= None
            self._y2 = None
        self._comp_bg_quantities()
   

    def _k_rho(self):
        '''
        Rescales the convergence on the lens plane into a matter density. This is mostly offered
        for debugging purposes, and is only really meaningful in the case that the input is the
        raytracing of a single lens plane (otherwise the recovered matter density is cumulative, 
        in some sense, across the line of sight).
        
        Returns
        -------
        rho : float or float array 
            The projected mass density at the source positions on the lens plane
        '''
        rho = self._k * self.calc_sigma_crit(self._zs)
        return rho


    def calc_sigma_crit(self, zs=None):
        '''
        Computes :math:`\\Sigma_\\text{c}(z_s)`, the critical surface density as a function of source
        redshift :math:`z_s`, at the lens redshift :math:`z_l`, in comoving :math:`(M_{\\odot}/h)/(\\text{pc}/h)^2`, 
        assuming a flat cosmology

        Parameters
        ----------
        zs : float or float array, optional
            A source redshift (or array of redshifts). If None (default), then use background
            source redshifts given at object instatiation, `self.zs`
        
        Returns
        -------
        Sigma_crit : float or float array 
            The critical surface density, :math:`\\Sigma_\\text{c}`, in comoving
            :math:(`M_{\\odot}/h)/(\\text{pc}/h)^2` 
        '''
        
        if(zs is None): 
            self._check_sources()
            zs = self._zs
        
        # scale factors
        a = 1/(1+self.zl)

        # G in Mpc^3 M_sun^-1 Gyr^-2,
        # speed of light C in Mpc Gyr^-1
        # distance to lens Dl and source Ds in proper Mpc
        # --> warning: this assumes a flat cosmology; or that angular diamter distance = proper distance
        G = const.G.to(units.Mpc**3 / (units.M_sun * units.Gyr**2)).value
        C = const.c.to(units.Mpc / units.Gyr).value
        Ds = self._cosmo.angular_diameter_distance(zs).value
        Dl = self._cosmo.angular_diameter_distance(self.zl).value
        Dls = Ds - Dl
        
        # critical surface mass density Σ_c in proper (M_sun/h)/(pc/h)^2; 
        # final quotient scales to Mpc to pc, adds an h to get (M_sun/h)/(pc/h)^2, 
        # and an a^2 to get to a comoving surface area
        Sigma_crit = (C**2/(4*np.pi*G) * (Ds)/(Dl*Dls))
        Sigma_crit = Sigma_crit * a**2 / (1e12 * self._cosmo.h)

        return Sigma_crit