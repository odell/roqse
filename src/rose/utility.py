"""
Useful utility functions that I don't want to clutter up other modules with.
"""
from enum import Enum
from collections.abc import Callable

import numpy as np
import numpy.typing as npt
import pandas as pd
from pathlib import Path
from numba import njit

from scipy.sparse import diags, lil_matrix
from scipy.misc import derivative
from scipy.special import eval_legendre

from .constants import MASS_N, MASS_P, HBARC, AMU


class Projectile(Enum):
    neutron = 0
    proton = 1


def finite_difference_first_derivative(s_mesh: npt.ArrayLike, sparse: bool = False):
    """
    Computes a finite difference matrix that (when applied) represent the first
    derivative.
    """
    dx = s_mesh[1] - s_mesh[0]
    assert np.all(
        np.abs(s_mesh[1:] - s_mesh[:-1] - dx) < 1e-14
    ), """
Spacing must be consistent throughout the entire mesh.
    """
    n = s_mesh.size
    coefficients = np.array([1, -8, 8, -1]) / (12 * dx)
    if sparse:
        D1 = lil_matrix(diags(coefficients, [-2, -1, 1, 2], shape=(n, n)))
    else:
        D1 = lil_matrix(diags(coefficients, [-2, -1, 1, 2], shape=(n, n))).toarray()

    # Use O(dx^2) forward difference approximations for the first 2 rows.
    D1[0, :5] = np.array([-3, 4, -1, 0, 0]) / (2 * dx)
    D1[1, :5] = np.array([0, -3, 4, -1, 0]) / (2 * dx)

    # Use O(dx^2) backward difference approximations for the last 2 rows.
    D1[-2, -5:] = np.array([0, 1, -4, 3, 0]) / (2 * dx)
    D1[-1, -5:] = np.array([0, 0, 1, -4, 3]) / (2 * dx)

    return D1


def finite_difference_second_derivative(s_mesh: npt.ArrayLike, sparse: bool = False):
    """
    Computes a finite difference matrix that represents the second derivative
    (w.r.t. s or rho) operator in coordinate space.
    """
    dx = s_mesh[1] - s_mesh[0]
    assert np.all(
        np.abs(s_mesh[1:] - s_mesh[:-1] - dx) < 1e-14
    ), """
Spacing must be consistent throughout the entire mesh.
    """
    n = s_mesh.size
    coefficients = np.array([-1, 16, -30, 16, -1]) / (12 * dx**2)
    if sparse:
        D2 = lil_matrix(diags(coefficients, [-2, -1, 0, 1, 2], shape=(n, n)))
    else:
        D2 = diags(coefficients, [-2, -1, 0, 1, 2], shape=(n, n)).toarray()

    # Use O(dx^2) forward difference approximation for the first 2 rows.
    D2[0, :5] = np.array([2, -5, 4, -1, 0]) / dx**2
    D2[1, :5] = np.array([0, 2, -5, 4, -1]) / dx**2

    # Use O(dx^2) backward difference approximation for the last 2 rows.
    D2[-2, -5:] = np.array([-1, 4, -5, 2, 0]) / dx**2
    D2[-1, -5:] = np.array([0, -1, 4, -5, 2]) / dx**2

    return D2


@njit
def regular_inverse_r(r, r_c):
    if isinstance(r, float):
        return 1 / (2 * r_c) * (3 - (r / r_c) ** 2) if r < r_c else 1 / r
    else:
        ii = np.where(r <= r_c)[0]
        jj = np.where(r > r_c)[0]
        return np.hstack((1 / (2 * r_c) * (3 - (r[ii] / r_c) ** 2), 1 / r[jj]))


@njit
def regular_inverse_s(s, s_c):
    if isinstance(s, float) or isinstance(s, int):
        return 1 / (2 * s_c) * (3 - (s / s_c) ** 2) if s < s_c else 1 / s
    else:
        ii = np.where(s <= s_c)[0]
        jj = np.where(s > s_c)[0]
        within_cutoff = np.zeros(ii.shape)
        if ii.size > 0:
            within_cutoff = 1.0 / (2.0 * s_c) * (3.0 - (s[ii] / s_c) ** 2)

        return np.hstack((within_cutoff, 1.0 / s[jj]))


@njit
def Gamow_factor(l, eta):
    r"""This returns the... Gamow factor.
    See [Wikipedia](https://en.wikipedia.org/wiki/Gamow_factor).

    Parameters:
        l (int): angular momentum
        eta (float): Sommerfeld parameter (see
            [Wikipedia](https://en.wikipedia.org/wiki/Sommerfeld_parameter))

    Returns:
        C_l (float): Gamow factor

    """
    if eta == 0.0:
        if l == 0:
            return 1
        else:
            return 1 / (2 * l + 1) * Gamow_factor(l - 1, 0)
    elif l == 0:
        return np.sqrt(2 * np.pi * eta / (np.exp(2 * np.pi * eta) - 1))
    else:
        return np.sqrt(l**2 + eta**2) / (l * (2 * l + 1)) * Gamow_factor(l - 1, eta)


def eval_assoc_legendre(n, x):
    if n == 0:
        return np.zeros(x.size)
    else:
        return -((1 - x**2) ** (1 / 2)) * derivative(
            lambda z: eval_legendre(n, z), x, dx=1e-9
        )


def get_AME_binding_energy(A, Z):
    r"""Calculates binding in MeV/c^2 given mass number, A, proton number, Z, by AME2020 lookup"""
    # look up nuclide in AME2020 table
    ame_table_fpath = Path(__file__).parent.resolve() / Path(
        "../../data/mass_1.mas20.txt"
    )
    assert ame_table_fpath.is_file()
    df = pd.read_csv(ame_table_fpath, delim_whitespace=True)
    mask = (df["A"] == A) & (df["Z"] == Z)
    if mask.any():
        # use AME if data exists
        # format is Eb/A [keV/nucleon]
        return float(df[mask]["BINDING_ENERGY/A"]) * A / 1e3
    return None


@njit
def semiempirical_binding_energy(A, Z):
    r"""Calculates binding in MeV/c^2 given mass number, A, proton number, Z, by semi-empriical mass fomrula"""
    N = A - Z
    delta = 0
    if N % 2 == 0 and Z % 2 == 0:
        delta = 12.0 / np.sqrt(A)
    elif N % 2 != 0 and Z % 2 != 0:
        delta = -12.0 / np.sqrt(A)

    Eb = (
        15.8 * A
        - 18.3 * A ** (2 / 3)
        - 0.714 * Z * (Z - 1) / (A ** (1 / 3))
        - 23.2 * (N - Z) ** 2 / A
        + delta
    )
    return Eb


def get_binding_energy(A, Z):
    r"""Calculates binding in MeV/c^2 given mass number, A, proton number, Z, by AME2020 lookup if possible,
    or semi-empriical mass fomrula if not
    """
    Eb = get_AME_binding_energy(A, Z)
    if Eb is None:
        Eb = semiempirical_binding_energy(A, Z)
    return Eb


@njit
def mass(A, Z, Eb):
    r"""Calculates rest mass in MeV/c^2 given mass number, A, proton number, Z, and binding energy in MeV/c^2"""
    N = A - Z
    return Z * MASS_P + N * MASS_N - Eb


def kinematics(
    target: tuple,
    projectile: tuple,
    E_lab: float = None,
    E_com: float = None,
    binding_model: Callable[[int, int], float] = get_binding_energy,
):
    r"""Calculates the reduced mass, COM frame kinetic energy and wavenumber for a projectile (A,Z)
    scattering on a target nuclide (A,Z), with binding energies from binding_model, which defaults
    to lookup in AME2020 mass table. Uses relatavistic approximation of Ingemarsson, 1974:
    https://doi.org/10.1088/0031-8949/9/3/004
    Parameters:
        t : target (A,Z)
        p : projectile (A,Z)
        E_lab: bombarding energy in the lab frame [MeV]. Either E_lab or E_com must be provided, not both.
        E_com: bombarding energy in the com frame [MeV]. Either E_lab or E_com must be provided, not both.
        binding_model : optional callable taking in (A,Z) and returning binding energy in [MeV/c^2],
                        defaults to lookup in AME2020, and semi-empirical mass formula if not available
                        there
    Returns:
        mu (float) : reduced mass in MeV/c^2
        E_com (float) : center-of-mass frame energy in MeV
        k (float) : center-of-mass frame wavenumber in fm^-1
    """
    Eb_target = binding_model(*target)
    Eb_projectile = binding_model(*projectile)
    m_t = mass(*target, Eb_target)
    m_p = mass(*projectile, Eb_projectile)

    if E_lab is None:
        assert E_com is not None
        E_lab = (m_t + m_p) / m_t * E_com
    else:
        assert E_com is None
        E_com = m_t / (m_t + m_p) * E_lab

    Ep = E_com + m_p

    # relativisitic correction from A. Ingemarsson 1974, Eqs. 17 & 20
    k = (
        m_t
        * np.sqrt(E_lab * (E_lab + 2 * m_p))
        / np.sqrt((m_t + m_p) ** 2 + 2 * m_t * E_lab)
        / HBARC
    )
    mu = k**2 * Ep / (Ep**2 - m_p * m_p) * HBARC**2

    return mu, E_com, k
