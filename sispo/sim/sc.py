# SPDX-FileCopyrightText: 2021 Gabriel J. Schwarzkopf <sispo-devs@outlook.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Defining behaviour of the spacecraft (sc)."""

import logging
from pathlib import Path

from astropy import units as u
import numpy as np
import cv2

import orekit
from org.orekit.orbits import KeplerianOrbit # pylint: disable=import-error
from org.orekit.frames import FramesFactory # pylint: disable=import-error
from org.orekit.attitudes import Attitude, FixedRate # pylint: disable=import-error
from org.orekit.propagation.analytical import KeplerianPropagator # pylint: disable=import-error
from org.orekit.time import AbsoluteDate, TimeScalesFactory # pylint: disable=import-error
from org.orekit.utils import PVCoordinates # pylint: disable=import-error
from org.hipparchus.geometry.euclidean.threed import Vector3D  # pylint: disable=import-error

from .cb import CelestialBody

logger = logging.getLogger(__name__)

class Spacecraft(CelestialBody):
    """Handling properties and behaviour of the spacecraft."""

    def __init__(self, name, mu, state, trj_date, rot_state=None, oneshot=False):
        """Currently hard implemented for SC."""

        super().__init__(name)

        self.trj_date = trj_date
        self.auto_targeting = rot_state is None

        att_provider = []
        if rot_state is not None:
            attitude = Attitude(trj_date, self.ref_frame, rot_state)
            att_provider = [FixedRate(attitude)]

        if oneshot:
            self.date_history = [trj_date]
            self.pos_history = [state.getPosition()]
            self.vel_history = [state.getVelocity()]
            self.rot_history = [None if rot_state is None else rot_state.getRotation()]
        else:
            self.trajectory = KeplerianOrbit(state, self.ref_frame, self.trj_date, mu)
            self.propagator = KeplerianPropagator(self.trajectory, *att_provider)

        self.payload = None

        logger.debug("Init finished")

    @classmethod
    def calc_encounter_state(cls,
                             sssb_state,
                             min_dist,
                             rel_vel, 
                             terminator=True,
                             sunnyside=False):
        """Calculate the state of a Spacecraft at closest distance to SSSB."""
        (sssb_pos, sssb_vel) = sssb_state

        sc_pos = cls.calc_encounter_pos(
            sssb_pos, min_dist, terminator, sunnyside)

        sc_vel = sssb_vel.scalarMultiply(
            (sssb_vel.getNorm() - rel_vel) / sssb_vel.getNorm())

        #logger.info("Spacecraft relative velocity: %s", sc_vel)
        #logger.info("Spacecraft distance from sun: %s",
        #                 sc_pos.getNorm()/Constants.IAU_2012_ASTRONOMICAL_UNIT)

        return PVCoordinates(sc_pos, sc_vel)

    @staticmethod
    def calc_encounter_pos(sssb_pos,
                           min_dist,
                           terminator=True,
                           sunnyside=False):
        """Calculate the pos of a Spacecraft at closest distance to SSSB."""
        sssb_direction = sssb_pos.normalize()

        if terminator:
            shift = sssb_direction.scalarMultiply(-0.15)
            shift = shift.add(Vector3D(0., 0., 1.))
            shift = shift.normalize()
            shift = shift.scalarMultiply(min_dist)
            sc_pos = sssb_pos.add(shift)
        else:
            if not sunnyside:
                min_dist *= -1

            sssb_direction = sssb_direction.scalarMultiply(min_dist)
            sc_pos = sssb_pos.subtract(sssb_direction)

        return sc_pos
        

class Instrument():
    """Summarizes characteristics of an instrument."""

    def __init__(self, charas=None):
        """
        Flexible init, all values have defaults.
        
        :type charas: Dict
        :param charas: Required characteristics that describe the instrument.
        """
        
        if charas is None:
            charas = {}

        if "res" in charas:
            self.res = (charas["res"][0], charas["res"][1])
        else:
            self.res = (2456, 2054)

        if "pix_l" in charas:
            self.pix_l = charas["pix_l"] * u.micron
            self.pix_a = self.pix_l ** 2 * (1 / u.pix)
        elif "pix_a" in charas:
            self.pix_a = charas["pix_a"]
            self.pix_l = np.sqrt(self.pix_a)
        else:
            self.pix_l = 3.45 * u.micron
            self.pix_a = self.pix_l ** 2 * (1 / u.pix)    
        self.chip_w = self.pix_l * self.res[0]

        if "focal_l" in charas:
            self.focal_l = charas["focal_l"] * u.mm
        else:
            self.focal_l = 230 * u.mm

        if "aperture_d" in charas:
            self.aperture_d = charas["aperture_d"] * u.cm
        else:
            self.aperture_d = 4 * u.cm

        if "wavelength" in charas:
            self.wavelength = charas["wavelength"] * u.nm
        else:
            self.wavelength = 550 * u.nm

        if "chip_noise" in charas:
            self.chip_noise = charas["chip_noise"]
        else:
            self.chip_noise = 10

        if "quantum_eff" in charas:
            self.quantum_eff = charas["quantum_eff"]
        else:
            self.quantum_eff = 0.25
      
        if "color_depth" in charas:
            self.color_depth = charas["color_depth"]
        else:
            self.color_depth = 12

        self.aperture_a = ((2 * u.cm) ** 2 - (1.28 * u.cm) ** 2) * np.pi/4
        self.dlmult = 2

    def sense(self, flux_img):
        # Calculate Gaussian standard deviation for approx diffraction pattern
        sigma = (self.dlmult * 0.45 * self.wavelength
                * self.focal_l / (self.aperture_d
                * self.pix_l)).decompose()
        sigma = float(sigma.value)

        # Kernel size calculated to equal skimage.filters.gaussian
        # Reference:
        # https://github.com/scipy/scipy/blob/4bfc152f6ee1ca48c73c06e27f7ef021d729f496/scipy/ndimage/filters.py#L214
        kernel = int(round(4 * float(sigma)) * 2 + 1)
        kernel = max(kernel, 5) # Don't use smaller than 5
        ksize = (kernel, kernel)

        img = self.quantum_eff * flux_img
        img = cv2.GaussianBlur(img, ksize, sigma)
        img += np.random.poisson(img)

        return img
