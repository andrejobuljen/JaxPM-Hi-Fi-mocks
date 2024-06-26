import jax
import jax.numpy as jnp

import jax_cosmo as jc

from jaxpm.kernels import fftk, gradient_kernel, laplace_kernel, longrange_kernel, PGD_kernel
from jaxpm.painting import cic_paint, cic_read, compensate_cic
from jaxpm.growth import growth_factor, growth_rate, dGfa

def pm_forces(positions, mesh_shape=None, delta=None, r_split=0):
    """
    Computes gravitational forces on particles using a PM scheme
    """
    if mesh_shape is None:
        mesh_shape = delta.shape
    kvec = fftk(mesh_shape)

    if delta is None:
        delta_k = jnp.fft.rfftn(cic_paint(jnp.zeros(mesh_shape), positions))
    else:
        delta_k = jnp.fft.rfftn(delta)

    # Computes gravitational potential
    pot_k = delta_k * laplace_kernel(kvec) * longrange_kernel(kvec, r_split=r_split)
    # Computes gravitational forces
    return jnp.stack([cic_read(jnp.fft.irfftn(gradient_kernel(kvec, i)*pot_k), positions) 
                      for i in range(3)],axis=-1)


# def lpt(cosmo, initial_conditions, positions, a):
#     """
#     Computes first order LPT displacement
#     """
#     initial_force = pm_forces(positions, delta=initial_conditions)
#     a = jnp.atleast_1d(a)
#     dx = growth_factor(cosmo, a) * initial_force
#     p = a**2 * growth_rate(cosmo, a) * jnp.sqrt(jc.background.Esqr(cosmo, a)) * dx
#     f = a**2 * jnp.sqrt(jc.background.Esqr(cosmo, a)) * dGfa(cosmo, a) * initial_force
#     return dx, p, f

def lpt(cosmo, initial_conditions, positions, a):
    """
    Computes first order LPT displacement
    """
    initial_force = pm_forces(positions, delta=initial_conditions)
    a = jnp.atleast_1d(a)
    dx = growth_factor(cosmo, a) * initial_force
    return dx

def linear_field(mesh_shape, box_size, pk, seed):
    """
    Generate initial conditions.
    """
    kvec = fftk(mesh_shape)
    kmesh = sum((kk / box_size[i] * mesh_shape[i])**2 for i, kk in enumerate(kvec))**0.5
    pkmesh = pk(kmesh) * (mesh_shape[0] * mesh_shape[1] * mesh_shape[2]) / (box_size[0] * box_size[1] * box_size[2])

    field = jax.random.normal(seed, mesh_shape)
    field = jnp.fft.rfftn(field) * pkmesh**0.5
    field = jnp.fft.irfftn(field)
    return field

def linear_field_from_IC(IC_field, box_size, pk):
    """
    obtain linear field from IC
    """

    mesh_shape = IC_field.shape

    kvec = fftk(mesh_shape)
    kmesh = sum((kk / box_size[i] * mesh_shape[i])**2 for i, kk in enumerate(kvec))**0.5
    pkmesh = pk(kmesh) * (mesh_shape[0] * mesh_shape[1] * mesh_shape[2]) / (box_size[0] * box_size[1] * box_size[2])

    field = jnp.fft.rfftn(IC_field) * pkmesh**0.5
    field = jnp.fft.irfftn(field)
    return field

def linear_field_just_IC(mesh_shape, box_size, seed):
    """
    Generate just initial conditions.
    """
    field = jax.random.normal(seed, mesh_shape)
    return field

def generate_d12_bias(cosmo, delta_ic, particles, b1, b2):
    """
    Generate b1 * shifted_delta_1 + b2 * shifted_delta_2 (missing tidal for now...)
    """
    weights1 = cic_read(delta_ic, particles)
    weights1 -= weights1.mean()

    weights2 = weights1**2
    weights2 -= weights2.mean()

    # Move the particles using displacement field
    dx = lpt(cosmo, delta_ic, particles, a=1.0)
    pos = particles + dx

    d1 = compensate_cic(cic_paint(jnp.zeros(delta_ic.shape), pos, weights1))
    d2 = compensate_cic(cic_paint(jnp.zeros(delta_ic.shape), pos, weights2))

    return b1*d1 + b2*d2

def generate_d12_separately(cosmo, delta_ic, particles):
    """
    Generate shifted_delta_1 and shifted_delta_2
    
    """
    weights1 = cic_read(delta_ic, particles)
    weights1 -= weights1.mean()

    weights2 = weights1**2
    weights2 -= weights2.mean()

    # Move the particles using displacement field
    dx = lpt(cosmo, delta_ic, particles, a=1.0)
    pos = particles + dx

    d1 = compensate_cic(cic_paint(jnp.zeros(delta_ic.shape), pos, weights1))
    d2 = compensate_cic(cic_paint(jnp.zeros(delta_ic.shape), pos, weights2))

    return d1, d2

def whitenoise(Peps, mesh_shape, box_size, seed):
    noise = jax.random.normal(seed, mesh_shape)
    Peps *= mesh_shape[0]**3 / box_size[0]**3
    noise = jnp.fft.irfftn(jnp.fft.rfftn(noise) * Peps**0.5)
    return noise
    
def expected_noise_level(N, L):
    return (L/N)**3

def make_ode_fn(mesh_shape):
    
    def nbody_ode(state, a, cosmo):
        """
        state is a tuple (position, velocities)
        """
        pos, vel = state

        forces = pm_forces(pos, mesh_shape=mesh_shape) * 1.5 * cosmo.Omega_m

        # Computes the update of position (drift)
        dpos = 1. / (a**3 * jnp.sqrt(jc.background.Esqr(cosmo, a))) * vel
        
        # Computes the update of velocity (kick)
        dvel = 1. / (a**2 * jnp.sqrt(jc.background.Esqr(cosmo, a))) * forces
        
        return dpos, dvel

    return nbody_ode


def pgd_correction(pos, params):
    """
    improve the short-range interactions of PM-Nbody simulations with potential gradient descent method, based on https://arxiv.org/abs/1804.00671
    args:
      pos: particle positions [npart, 3]
      params: [alpha, kl, ks] pgd parameters
    """
    kvec = fftk(mesh_shape)

    delta = cic_paint(jnp.zeros(mesh_shape), pos)
    alpha, kl, ks = params
    delta_k = jnp.fft.rfftn(delta)
    PGD_range=PGD_kernel(kvec, kl, ks)
    
    pot_k_pgd=(delta_k * laplace_kernel(kvec))*PGD_range

    forces_pgd= jnp.stack([cic_read(jnp.fft.irfftn(gradient_kernel(kvec, i)*pot_k_pgd), pos) 
                      for i in range(3)],axis=-1)
    
    dpos_pgd = forces_pgd*alpha
   
    return dpos_pgd