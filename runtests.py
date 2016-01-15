#!/usr/bin/env py.test
from __future__ import print_function, division

import math
from copy import deepcopy

import numpy as np
from numpy.random import RandomState
from numpy.testing import assert_allclose, assert_approx_equal
import pytest
import itertools
try:
    from numpy.random import choice
    HAVE_CHOICE = True
except ImportError:
    HAVE_CHOICE = False

import nestle

SQRTEPS = math.sqrt(float(np.finfo(np.float64).eps))  # testing closeness to 1

NMAX = 20  # many tests are run for dimensions 1 to NMAX inclusive

def test_vol_prefactor():
    assert nestle.vol_prefactor(1) == 2.
    assert nestle.vol_prefactor(2) == math.pi
    assert nestle.vol_prefactor(3) == 4./3. * math.pi
    assert nestle.vol_prefactor(4) == 1./2. * math.pi**2
    assert nestle.vol_prefactor(5) == 8./15. * math.pi**2
    assert nestle.vol_prefactor(9) == 32./945. * math.pi**4


def test_rstate_kwarg():
    """Test that rstate keyword argument works as expected."""
    rstate = RandomState(123)
    a = nestle.randsphere(10, rstate=rstate)
    np.random.seed(123)
    b = nestle.randsphere(10)

    assert np.all(a == b)

# TODO: test that points are uniform
def test_randsphere():
    """Draw a lot of points and check that they're within a unit sphere.
    """
    rstate = RandomState(0)
    npoints = 1000
    
    for n in range(1, NMAX+1):
        for i in range(npoints):
            x = nestle.randsphere(n, rstate=rstate)
            r = np.sum(x**2)
            assert r < 1.0
        

@pytest.mark.skipif("not HAVE_CHOICE")
def test_random_choice():
    """nestle.random_choice() is designed to mimic np.random.choice(),
    for numpy < v1.7.0. In cases where we have both, test that they agree.
    """
    rstate = RandomState(0)
    p = rstate.rand(10)
    p /= p.sum()
    for seed in range(10):
        rstate.seed(seed)
        i = rstate.choice(10, p=p)
        rstate.seed(seed)
        j = nestle.random_choice(10, p=p, rstate=rstate)
        assert i == j


def test_random_choice_error():
    """random_choice should raise an error when probabilities do not sum
    to one."""

    rstate = RandomState(0)
    p = rstate.rand(10)
    p /= p.sum()
    p *= 1.001
    with pytest.raises(ValueError):
        nestle.random_choice(10, p=p, rstate=rstate)


def test_ellipsoid_sphere():
    """Test that Ellipsoid works like a sphere when ``a`` is proportional to
    the identity matrix."""

    scale = 5.
    for n in range(1, NMAX+1):
        ctr = 2.0 * scale * np.ones(n)  # arbitrary non-zero center
        a = 1.0 / scale**2 * np.identity(n)
        ell = nestle.Ellipsoid(ctr, a)

        assert_allclose(ell.vol, nestle.vol_prefactor(n) * scale**n)
        assert_allclose(ell.axlens, scale * np.ones(n))
        assert_allclose(ell.axes, scale * np.identity(n))


def test_ellipsoid_vol_scaling():
    """Test that scaling an ellipse works as expected."""

    scale = 1.5 # linear scale

    for n in range(1, NMAX+1):
        # ellipsoid centered at origin with principle axes aligned with
        # coordinate axes, but random sizes.
        ctr = np.zeros(n)
        a = np.diag(np.random.rand(n))
        ell = nestle.Ellipsoid(ctr, a)

        # second ellipsoid with axes scaled.
        ell2 = nestle.Ellipsoid(ctr, 1./scale**2 * a)

        # scale volume of first ellipse to match the second.
        ell.scale_to_vol(ell.vol * scale**n)
        
        # check that the ellipses are the same.
        assert_allclose(ell.vol, ell2.vol)
        assert_allclose(ell.a, ell2.a)
        assert_allclose(ell.axes, ell2.axes)
        assert_allclose(ell.axlens, ell2.axlens)


def test_ellipsoid_contains():
    """Test Elipsoid.contains()"""
    eps = 1.e-7

    for n in range(1, NMAX+1):
        ell = nestle.Ellipsoid(np.zeros(n), np.identity(n))  # unit n-sphere
        
        # point just outside unit n-sphere:
        pt = (1. / np.sqrt(n) + eps) * np.ones(n)
        assert not ell.contains(pt)

        # point just inside unit n-sphere:
        pt = (1. / np.sqrt(n) - eps) * np.ones(n)
        assert ell.contains(pt)

        # non-equal axes ellipsoid, still aligned on axes:
        a = np.diag(np.random.rand(n))
        ell = nestle.Ellipsoid(np.zeros(n), a)

        # check points on axes
        for i in range(0, n):
            axlen = 1. / np.sqrt(a[i, i])  # length of this axis
            pt = np.zeros(n)
            pt[i] = axlen + eps
            assert not ell.contains(pt)
            pt[i] = axlen - eps
            assert ell.contains(pt)


def random_ellipsoid(n):
    """Return a random `n`-d ellipsoid centered at the origin

    This is a helper function for other tests.
    """

    # `a` in the ellipsoid must be positive definite, so we have to construct
    # a positive definite matrix. For any real, non-singular matrix A,
    # `A^T A` will be positive definite.
    det = 0.
    while abs(det) < 1.e-10:  # ensure a non-singular matrix
        A = np.random.rand(n, n)
        det = np.linalg.det(A)

    return nestle.Ellipsoid(np.zeros(n), np.dot(A.T, A))


def test_ellipsoid_sample():
    """Ensure that Ellipsoid.sample() returns samples in itself and make
    some test that they are evenly distributed."""

    nsamples = 1000  # don't make this too small
    volfrac = 0.5  # sets inner ellipse size

    for n in range(1, NMAX+1):
        ell = random_ellipsoid(n)  # random ellipsoid
        ell2 = deepcopy(ell)
        ell2.scale_to_vol(volfrac * ell2.vol)  # smaller ellipsoid

        # expected number of points that will fall within inner ellipsoid
        expect = volfrac * nsamples
        sigma = math.sqrt((1. - volfrac) * volfrac * nsamples) # normal approx.

        # sample randomly. For each point, check if point is within
        # main ellipsoid and count the number of points within the
        # inner ellipsoid.
        ninner = 0
        for i in range(nsamples):
            x = ell.sample()
            assert ell.contains(x)
            ninner += ell2.contains(x)

        # check that the number of points in the inner ellipse is what
        # we expect (practically guaranteed to be in range +/- 10 sigma!)
        assert expect - 10.*sigma < ninner < expect + 10.*sigma


def test_ellipsoid_repr():
    ell = nestle.Ellipsoid([0., 0.], [[1., 0.], [0., 1.]])
    assert repr(ell) == "Ellipsoid(ctr=[0.0, 0.0])"


def test_bounding_ellipsoid():
    """Test that bounding ellipsoid contains the points"""

    npoints = 100

    print("\ntest_bounding_ellipsoid")

    for n in range(1, NMAX+1):
        ell_gen = random_ellipsoid(n)  # random elipsoid
        x = ell_gen.samples(npoints)  # points within it
        ell = nestle.bounding_ellipsoid(x)
        for xi in x:
            assert ell.contains(xi)

        print("n={}: true_vol={}  vol={}".format(n, ell_gen.vol, ell.vol))


def test_bounding_ellipsoid_robust():
    """Test that bounding ellipsoid still works when npoints < dim but
    pointvol > 0."""

    for n in range(1, NMAX+1):
        ell_gen = random_ellipsoid(n)
        for npoints in range(1, n):
            x = ell_gen.samples(npoints)

            # check that it works
            ell = nestle.bounding_ellipsoid(x, pointvol=ell_gen.vol/npoints)

            # check that volume is as expected
            assert_allclose(ell.vol, ell_gen.vol)

            # check that points are contained
            for xi in x:
                assert ell.contains(xi)

# -----------------------------------------------------------------------------
# Case test helpers

def integrate_on_grid(f, ranges, density=100):
    """Return log of integral"""
    rs = []
    for r in ranges:
        step = (r[1] - r[0]) / density
        rmin = r[0] + step / 2.
        rmax = r[1] - step / 2.
        rs.append(np.linspace(rmin, rmax, density))


    logsum = -1.e300
    for v in itertools.product(*rs):
        logsum = np.logaddexp(logsum, f(np.array(v)))

    # adjust for prior density: divide by density^n
    logsum -= len(ranges) * np.log(density)

    return logsum

def integrate_on_grid_refine(f, ranges):
    """Integrate on grid, tuning sampling density."""

    density = 100
    logsum_old = -np.inf
    while True:
        logsum = integrate_on_grid(f, ranges, density=density)
        if abs(logsum - logsum_old) < 0.001:
            return logsum
        logsum_old = logsum
        density *= 2

# -----------------------------------------------------------------------------
# Case Test 0: completely flat likelihood & prior
# This tests if we are normalizing the integral correctly and whether we get
# h = 0 as expected.

def run_flat(method):
    logl = lambda x: 0.0
    prior = lambda x: x
    res = nestle.sample(logl, prior, 2, method=method,
                        npoints=4, rstate=RandomState(0))
    assert_allclose(res.logz, 0.0, atol=1.e-10)
    assert_allclose(res.h, 0.0, atol=1.e-10)

def test_flat_classic():
    run_flat("classic")

def test_flat_single():
    run_flat("single")

@pytest.mark.skipif("not nestle.HAVE_KMEANS")
def test_flat_multi():
    run_flat("multi")

# -----------------------------------------------------------------------------
# Case Test 1: two gaussians centered at (1, 1) and (-1, -1) with sigma = 0.1

def run_two_gaussians(method):
    sigma = 0.1
    mu1 = np.ones(2)
    mu2 = -np.ones(2)
    sigma_inv = np.identity(2) / 0.1**2

    def logl(x):
        dx1 = x - mu1
        dx2 = x - mu2
        return np.logaddexp(-np.dot(dx1, np.dot(sigma_inv, dx1)) / 2.0,
                            -np.dot(dx2, np.dot(sigma_inv, dx2)) / 2.0)

    # Flat prior, over [-5, 5] in both dimensions
    def prior(x):
        return 10.0 * x - 5.0

    #(Approximate) analytic evidence for two identical Gaussian blobs,
    # over a uniform prior [-5:5][-5:5] with density 1/100 in this domain:
    analytic_logz = np.log(2.0 * 2.0*np.pi*sigma*sigma / 100.)
    grid_logz = integrate_on_grid_refine(logl, [(-5., 5.), (-5., 5.)])

    res = nestle.sample(logl, prior, 2, method=method,
                        npoints=100, rstate=RandomState(0))
    print()
    print("{}: logz           = {:6.3f} +/- {:6.3f}"
          .format(method, res.logz, res.logzerr))
    print("        grid_logz      = {0:8.5f}".format(grid_logz))
    print("        analytic_logz  = {0:8.5f}".format(analytic_logz))
    assert abs(res.logz - grid_logz) < 3.0 * res.logzerr
    assert abs(res.weights.sum() - 1.) < SQRTEPS

def test_two_gaussians_classic():
    run_two_gaussians('classic')


def test_two_gaussians_single():
    run_two_gaussians('single')


@pytest.mark.skipif("not nestle.HAVE_KMEANS")
def test_two_gaussians_multi():
    run_two_gaussians('multi')


# -----------------------------------------------------------------------------
# Case Test 2: Eggbox

@pytest.mark.skipif("not nestle.HAVE_KMEANS")
def test_eggbox():
    tmax = 5.0 * np.pi
    constant = np.log(1.0 / tmax**2)

    def loglike(x):
        t = 2.0 * tmax * x - tmax
        return (2.0 + np.cos(t[0]/2.0)*np.cos(t[1]/2.0))**5.0

    def prior(x):
        return x

    res = nestle.sample(loglike, prior, 2, npoints=500, method='multi',
                        rstate=RandomState(0))

    grid_logz = integrate_on_grid_refine(loglike, [(0., 1.), (0., 1.)])

    print("\nEggbox")
    print("multi : logz           = {:6.3f} +/- {:6.3f}"
          .format(res.logz, res.logzerr))
    print("        grid_logz      = {0:8.5f}".format(grid_logz))

    assert abs(res.logz - grid_logz) < 3.0 * res.logzerr
    assert abs(res.weights.sum() - 1.) < SQRTEPS


#------------------------------------------------------------------------------
# test parallelization

@pytest.mark.skipif("not nestle.HAVE_KMEANS")
def test_parallel():
    futures = pytest.importorskip("concurrent.futures")
    sigma = 0.1
    mu1 = np.ones(2)
    mu2 = -np.ones(2)
    sigma_inv = np.identity(2) / 0.1**2

    def logl(x):
        dx1 = x - mu1
        dx2 = x - mu2
        return np.logaddexp(-np.dot(dx1, np.dot(sigma_inv, dx1)) / 2.0,
                            -np.dot(dx2, np.dot(sigma_inv, dx2)) / 2.0)

    # Flat prior, over [-5, 5] in both dimensions
    def prior(x):
        return 10.0 * x - 5.0

    #(Approximate) analytic evidence for two identical Gaussian blobs,
    # over a uniform prior [-5:5][-5:5] with density 1/100 in this domain:
    analytic_logz = np.log(2.0 * 2.0*np.pi*sigma*sigma / 100.)

    res = nestle.sample(logl, prior, 2, method='multi',
                        npoints=100, rstate=RandomState(0),
                        pool=nestle.FakePool(), n_queue=8)
    with futures.ThreadPoolExecutor(8) as pool:
        res_p = nestle.sample(logl, prior, 2, method='multi',
                              npoints=100, rstate=RandomState(0),
                              pool=pool, n_queue=8)

    assert res.logz == res_p.logz
# -----------------------------------------------------------------------------
# test utilities

def test_mean_and_cov():
    x = np.random.random((10, 3))
    w = np.random.random((10,))

    mean, cov = nestle.mean_and_cov(x, w)

    # check individual elements
    xd = x - np.average(x, weights=w, axis=0)
    prefactor = w.sum() / (w.sum()**2 - (w**2).sum())
    ans00 = prefactor * np.sum(w * xd[:, 0] * xd[:, 0])
    assert_approx_equal(cov[0, 0], ans00)
    ans01 = prefactor * np.sum(w * xd[:, 0] * xd[:, 1])
    assert_approx_equal(cov[0, 1], ans01)

    # If weights are all equal, covariance should come out to simple case
    w = np.repeat(0.2, 10)
    mean, cov = nestle.mean_and_cov(x, w)
    assert_allclose(cov, np.cov(x, rowvar=0))
    assert_allclose(mean, np.average(x, axis=0))


def test_resample_equal():

    N = 1000

    # N randomly weighted samples
    x = np.arange(N).reshape((N, 1))
    w = np.random.random((N,))
    w /= w.sum()

    new_x = nestle.resample_equal(x, w)
    
    # Each original sample should appear in the final sample either
    # floor(w * N) or ceil(w * N) times.
    for i in range(N):
        num = (new_x == x[i]).sum()  # number of times x[i] appears in new_x
        assert math.floor(w[i]*N) <= num <= math.ceil(w[i]*N)


def test_result():
    # test repr
    r = nestle.Result(a=1, b=2)
    assert repr(r) in [' b: 2\n a: 1', ' a: 1\n b: 2']

    # test attribute error
    with pytest.raises(AttributeError):
        r.c

    # test printing empty result
    r = nestle.Result()
    assert repr(r) == 'Result()'

    # test summary (needs specific keys):
    r = nestle.Result(niter=100, ncall=100, samples=[1., 2., 3.],
                      logz=1., logzerr=0.1, h=0.1)
    assert r.summary() == ('niter: 100\nncall: 100\nnsamples: 3\n'
                           'logz:  1.000 +/-  0.100\nh:  0.100')


def test_print_progress():
    """Check that print_progress don't error."""
    nestle.print_progress({'it': 0, 'logz': 1.})
