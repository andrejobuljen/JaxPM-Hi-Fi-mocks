import numpy as np
import jax.numpy as jnp

def fftk(shape, symmetric=True, finite=False, dtype=np.float32):
  """ Return k_vector given a shape (nc, nc, nc) and box_size
  """
  k = []
  for d in range(len(shape)):
    kd = np.fft.fftfreq(shape[d])
    kd *= 2 * np.pi
    kdshape = np.ones(len(shape), dtype='int')
    if symmetric and d == len(shape) - 1:
      kd = kd[:shape[d] // 2 + 1]
    kdshape[d] = len(kd)
    kd = kd.reshape(kdshape)

    k.append(kd.astype(dtype))
  del kd, kdshape
  return k

def gradient_kernel(kvec, direction, order=1):
  """
  Computes the gradient kernel in the requested direction
  Parameters:
  -----------
  kvec: array
    Array of k values in Fourier space
  direction: int
    Index of the direction in which to take the gradient
  Returns:
  --------
  wts: array
    Complex kernel
  """
  if order == 0:
    wts = 1j * kvec[direction]
    wts = jnp.squeeze(wts)
    wts[len(wts) // 2] = 0
    wts = wts.reshape(kvec[direction].shape)
    return wts
  else:
    w = kvec[direction]
    a = 1 / 6.0 * (8 * jnp.sin(w) - jnp.sin(2 * w))
    wts = a * 1j
    return wts

def laplace_kernel(kvec):
  """
  Compute the Laplace kernel from a given K vector
  Parameters:
  -----------
  kvec: array
    Array of k values in Fourier space
  Returns:
  --------
  wts: array
    Complex kernel
  """
  kk = sum(ki**2 for ki in kvec)
  mask = (kk == 0).nonzero()
  kk[mask] = 1
  wts = 1. / kk
  imask = (~(kk == 0)).astype(int)
  wts *= imask
  return wts

def longrange_kernel(kvec, r_split):
  """
  Computes a long range kernel
  Parameters:
  -----------
  kvec: array
    Array of k values in Fourier space
  r_split: float
    TODO: @modichirag add documentation
  Returns:
  --------
  wts: array
    kernel
  """
  if r_split != 0:
    kk = sum(ki**2 for ki in kvec)
    return np.exp(-kk * r_split**2)
  else:
    return 1.

def cic_compensation(kvec):
  """
  Computes cic compensation kernel.
  Adapted from https://github.com/bccp/nbodykit/blob/a387cf429d8cb4a07bb19e3b4325ffdf279a131e/nbodykit/source/mesh/catalog.py#L499
  Itself based on equation 18 (with p=2) of
        `Jing et al 2005 <https://arxiv.org/abs/astro-ph/0409240>`_
  Args:
    kvec: array of k values in Fourier space  
  Returns:
    v: array of kernel
  """
  kwts = [np.sinc(kvec[i] / (2 * np.pi)) for i in range(3)]
  wts = (kwts[0] * kwts[1] * kwts[2])**(-2)
  return wts

def PGD_kernel(kvec, kl, ks):
  """
  Computes the PGD kernel
  Parameters:
  -----------
  kvec: array
    Array of k values in Fourier space
  kl: float
    initial long range scale parameter
  ks: float
    initial dhort range scale parameter
  Returns:
  --------
  v: array
    kernel
  """
  kk = sum(ki**2 for ki in kvec)
  kl2 = kl**2
  ks4 = ks**4
  mask = (kk == 0).nonzero()
  kk[mask] = 1
  v = jnp.exp(-kl2 / kk) * jnp.exp(-kk**2 / ks4)
  imask = (~(kk == 0)).astype(int)
  v *= imask
  return v

def tidal_G2(delta):
    delta_k = jnp.fft.rfftn(delta)
    out_rfield = - delta**2
    kvec = fftk(delta.shape)
    kk = sum(ki**2 for ki in kvec)
    kk[kk == 0] = 1

    for i in range(3):
        for j in range(i, 3):
            dij_k = delta_k * kvec[i] * kvec[j] / kk
            dij_x = jnp.fft.irfftn(dij_k)

            if i == j:
                fac = 1.0
            else:
                fac = 2.0
            out_rfield += fac * dij_x**2

    return out_rfield