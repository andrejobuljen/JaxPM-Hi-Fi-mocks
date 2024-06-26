import numpy as np
import jax.numpy as jnp
from jax.scipy.stats import norm

__all__ = ['power_spectrum']

def _initialize_pk(shape, boxsize, kmin, dk):
  """
       Helper function to initialize various (fixed) values for powerspectra... not differentiable!
    """
  I = np.eye(len(shape), dtype='int') * -2 + 1

  W = np.empty(shape, dtype='f4')
  W[...] = 2.0
  W[..., 0] = 1.0
  W[..., -1] = 1.0

  kmax = np.pi * np.min(np.array(shape)) / np.max(np.array(boxsize)) + dk / 2
  kedges = np.arange(kmin, kmax, dk)

  k = [
      np.fft.fftfreq(N, 1. / (N * 2 * np.pi / L))[:pkshape].reshape(kshape)
      for N, L, kshape, pkshape in zip(shape, boxsize, I, shape)
  ]
  kmag = sum(ki**2 for ki in k)**0.5

  xsum = np.zeros(len(kedges) + 1)
  Nsum = np.zeros(len(kedges) + 1)

  dig = np.digitize(kmag.flat, kedges)

  xsum.flat += np.bincount(dig, weights=(W * kmag).flat, minlength=xsum.size)
  Nsum.flat += np.bincount(dig, weights=W.flat, minlength=xsum.size)
  return dig, Nsum, xsum, W, k, kedges


def power_spectrum(field, kmin=5, dk=0.5, boxsize=False):
    """
    Calculate the powerspectra given real space field
    
    Args:
    
        field: real valued field 
        kmin: minimum k-value for binned powerspectra
        dk: differential in each kbin
        boxsize: length of each boxlength (can be strangly shaped?)
    
    Returns:
    
        kbins: the central value of the bins for plotting
        power: real valued array of power in each bin
    
    """
    shape = field.shape
    nx, ny, nz = shape
    
    #initialze values related to powerspectra (mode bins and weights)
    dig, Nsum, xsum, W, k, kedges = _initialize_pk(shape, boxsize, kmin, dk)
    
    #fast fourier transform
    fft_image = jnp.fft.fftn(field)
    
    #absolute value of fast fourier transform
    pk = jnp.real(fft_image * jnp.conj(fft_image))
    
    #calculating powerspectra
    real = jnp.real(pk).reshape([-1])
    imag = jnp.imag(pk).reshape([-1])
    
    Psum = jnp.bincount(dig, weights=(W.flatten() * imag), length=xsum.size) * 1j
    Psum += jnp.bincount(dig, weights=(W.flatten() * real), length=xsum.size)
    
    P = ((Psum / Nsum)[1:-1] * jnp.array(boxsize).prod()).astype('float32')
    
    # jnp.array(box_size).prod()
    
    #normalization for powerspectra
    norm = jnp.prod(np.array(shape[:])).astype('float32')**2
    
    #find central values of each bin
    kbins = kedges[:-1] + (kedges[1:] - kedges[:-1]) / 2
    
    return kbins, P / norm

def cross_correlation(field1, field2, kmin=5, dk=0.5, boxsize=False):
    shape = field1.shape
    nx, ny, nz = shape

    #initialze values related to powerspectra (mode bins and weights)
    dig, Nsum, xsum, W, k, kedges = _initialize_pk(shape, boxsize, kmin, dk)

    #fast fourier transform
    fft_image1 = jnp.fft.fftn(field1)
    fft_image2 = jnp.fft.fftn(field2)

    #absolute value of fast fourier transform
    pk = jnp.real(fft_image1 * jnp.conj(fft_image2))

    #calculating powerspectra
    real = jnp.real(pk).reshape([-1])
    imag = jnp.imag(pk).reshape([-1])

    Psum = jnp.bincount(dig, weights=(W.flatten() * imag), length=xsum.size) * 1j
    Psum += jnp.bincount(dig, weights=(W.flatten() * real), length=xsum.size)

    P = ((Psum / Nsum)[1:-1] * jnp.array(boxsize).prod()).astype('float32')

    #normalization for powerspectra
    norm = jnp.prod(np.array(shape[:])).astype('float32')**2

    #find central values of each bin
    kbins = kedges[:-1] + (kedges[1:] - kedges[:-1]) / 2

    return kbins, P / norm

def gaussian_smoothing(im, sigma):
  """
  im: 2d image
  sigma: smoothing scale in px 
  """
  # Compute k vector
  kvec = jnp.stack(jnp.meshgrid(jnp.fft.fftfreq(im.shape[0]),
                                jnp.fft.fftfreq(im.shape[1])),
                 axis=-1)
  k = jnp.linalg.norm(kvec, axis=-1)
  # We compute the value of the filter at frequency k
  filter = norm.pdf(k, 0, 1. / (2. * np.pi * sigma))
  filter /= filter[0,0]

  return jnp.fft.ifft2(jnp.fft.fft2(im) * filter).real

