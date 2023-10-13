r"""`SchroedingerEquation` is a high-fidelity (HF), Schrödinger-equation solver for
local, complex interactions.

By default, `rose` will provide HF solution using `scipy.integrate.solve_ivp`.
For details about providing your own solutions, see [Basis
documentation](basis.md).

"""
from collections.abc import Callable

import numpy as np
from scipy.integrate import solve_ivp
from scipy.interpolate import interp1d
from scipy.misc import derivative

from .interaction import Interaction
from .schroedinger import SchroedingerEquation


class NumerovSolver(SchroedingerEquation):
    """
    Solver for the single-channel, reduced, radial Schrödinger equation using the Numerov method:
    https://en.wikipedia.org/wiki/Numerov%27s_method
    """

    def __init__(
        self,
        interaction: Interaction,
        mesh_size: int,
        domain: tuple,
    ):
        r"""Solves the Shrödinger equation for local, complex potentials.

        Parameters:
            interaction (Interaction): See [Interaction documentation](interaction.md).
            mesh_size (int) : the number of grid points in the radial mesh to use
                for the Numerov solve
            domain (tuple) : the upper and lower bounds of the problem domain $s$

        Returns:
            solver (NumerovSolver): instance of `NumerovSolver`

        """
        self.domain = domain
        self.mesh_size = int(mesh_size)
        self.s_mesh = np.linspace(self.domain[0], self.domain[1], self.mesh_size)

        super().__init__(interaction, None)

    def clone_for_new_interaction(self, interaction: Interaction):
        return NumerovSolver(interaction, self.mesh_size, self.domain)

    def phi(
        self,
        alpha: np.array,
        s_mesh: np.array = None,
        l: int = 0,
        rho_0=None,
        phi_threshold=SchroedingerEquation.PHI_THRESHOLD,
    ):
        r"""Computes the reduced, radial wave function $\phi$ (or $u$) on `s_mesh` using the
        Numerov method.

        Parameters:
            alpha (ndarray): parameter vector
            s_mesh (ndarray): values of $s$ at which $\phi$ is evaluated; uses self.mesh if None.
                If s_mesh is supplied, simply calculates on self.s_mesh and interpolates solution
                onto s_mesh. Must be contained in the domain.
            l (int): angular momentum
            rho_0 (float): starting point for the solver
            phi_threshold (float): minimum $\phi$ value; The wave function is
                considered zero below this value.

        Returns:
            phi (ndarray): reduced, radial wave function

        """
        assert s_mesh[0] >= self.domain[0]
        assert s_mesh[1] <= self.domain[1]

        # determine initial conditions
        rho_0, initial_conditions = self.initial_conditions(
            alpha, phi_threshold, l, rho_0
        )
        S_C = self.interaction.momentum(alpha) * self.interaction.coulomb_cutoff(alpha)

        y = numerov_kernel(
            self.s_mesh[0],
            self.s_mesh[1] - self.s_mesh[0],
            self.mesh_size,
            initial_conditions,
            lambda s: -self.radial_se_deriv2(s, l, alpha, S_C),
        )
        mask = np.where(self.s_mesh < rho_0)[0]
        y[mask] = 0

        if s_mesh is None:
            return y
        else:
            return np.interp(s_mesh, self.s_mesh, y)

    def rmatrix(
        self,
        alpha: np.array,
        l: int,
        s_0: float,
        phi_threshold=SchroedingerEquation.PHI_THRESHOLD,
    ):
        r"""Calculates the $\ell$-th partial wave R-matrix element at the specified energy,
            using the Numerov method for integrating the Radial SE

        Parameters:
            alpha (ndarray): parameter vector
            l (int): angular momentum
            rho_0 (float): initial $\rho$ (or $s$) value; starting point for the
                solver
            phi_threshold (float): minimum $\phi$ value; The wave function is
                considered zero below this value.

        Returns:
            rl (float)  : r-matrix element, or logarithmic derivative of wavefunction at the channel
                radius; s_0
        """
        assert s_0 >= self.domain[0] and s_0 < self.domain[1]

        # determine initial conditions
        rho_0, initial_conditions = self.initial_conditions(alpha, phi_threshold, l)
        S_C = self.interaction.momentum(alpha) * self.interaction.coulomb_cutoff(alpha)

        y = numerov_kernel(
            self.s_mesh[0],
            self.s_mesh[1] - self.s_mesh[0],
            self.mesh_size,
            initial_conditions,
            lambda s: -self.radial_se_deriv2(s, l, alpha, S_C),
        )
        u = interp1d(self.s_mesh, y, bounds_error=True)
        rl = 1 / s_0 * (u(s_0) / derivative(u, s_0, 1.0e-6))
        return rl


# @njit
def numerov_kernel(
    x0: np.double,
    dx: np.double,
    N: np.int,
    initial_conditions: tuple,
    g: Callable[[np.double], np.double],
):
    r"""Solves the the equation y'' + g(x)  y = 0 via the Numerov method,
    for complex functions over real domain

    Returns:
    value of y evaluated at the points x_grid

    Parameters:
        x_grid : the grid of points on which to run the solver and evaluate the solution.
                 Must be evenly spaced and monotonically increasing.
        initial_conditions : the value of y and y' at the minimum of x_grid
        g : callable for g(x)
    """

    # convenient factor
    f = dx * dx / 12.0

    # intialize domain walker
    xnm = x0

    # intial conditions
    ynm = initial_conditions[0]
    yn = ynm + initial_conditions[1] * dx

    # initialize range walker
    y = np.empty(N, dtype=np.cdouble)
    y[0] = ynm
    y[1] = yn

    def forward_stepy(n, ynm, yn, ynp):
        y[n] = ynp
        return yn, ynp

    for n in range(2, y.shape[0]):
        # determine next y
        gnm = g(xnm)
        gn = g(xnm + dx)
        gnp = g(xnm + dx + dx)
        ynp = (2 * yn * (1.0 - 5.0 * f * gn) - ynm * (1.0 + f * gnm)) / (1.0 + f * gnp)

        # forward step
        ynm, yn = forward_stepy(n, ynm, yn, ynp)
        xnm += dx

    return y
