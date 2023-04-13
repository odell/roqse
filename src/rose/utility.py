'''
Useful utility functions that I don't want to clutter up other modules with.
'''
import numpy as np
import numpy.typing as npt
from scipy.sparse import diags, lil_matrix

def finite_difference_first_derivative(
    s_mesh: npt.ArrayLike,
    sparse: bool = False
):
    '''
    Computes a finite difference matrix that (when applied) represent the first
    derivative.
    '''
    dx = s_mesh[1] - s_mesh[0]
    assert np.all(np.abs(s_mesh[1:] - s_mesh[:-1] - dx) < 1e-14), '''
Spacing must be consistent throughout the entire mesh.
    '''
    n = s_mesh.size
    coefficients = np.array([1, -8, 8, -1]) / (12*dx)
    if sparse:
        D1 = lil_matrix(diags(coefficients, [-2, -1, 1, 2], shape=(n, n)))
    else:
        D1 = lil_matrix(diags(coefficients, [-2, -1, 1, 2], shape=(n, n))).toarray()

    # Use O(dx^2) forward difference approximations for the first 2 rows.
    D1[0, :5] = np.array([-3, 4, -1, 0, 0]) / (2*dx)
    D1[1, :5] = np.array([0, -3, 4, -1, 0]) / (2*dx)

    # Use O(dx^2) backward difference approximations for the last 2 rows.
    D1[-2, -5:] = np.array([0, 1, -4, 3, 0]) / (2*dx)
    D1[-1, -5:] = np.array([0, 0, 1, -4, 3]) / (2*dx)

    return D1



def finite_difference_second_derivative(
    s_mesh: npt.ArrayLike,
    sparse: bool = False
):
    '''
    Computes a finite difference matrix that represents the second derivative
    (w.r.t. s or rho) operator in coordinate space.
    '''
    dx = s_mesh[1] - s_mesh[0]
    assert np.all(np.abs(s_mesh[1:] - s_mesh[:-1] - dx) < 1e-14), '''
Spacing must be consistent throughout the entire mesh.
    '''
    n = s_mesh.size
    coefficients = np.array([-1, 16, -30, 16, -1]) / (12*dx**2)
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
