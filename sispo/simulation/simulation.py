"""Trajectory simulation and object rendering module."""

import copy
import math
import logging
import os
from pathlib import Path
import sys
import time

import bpy
import numpy as np
import matplotlib.pyplot as plt
import OpenEXR
import orekit
OREKIT_VM = orekit.initVM()  # pylint: disable=no-member
file_dir = Path(__file__).parent.resolve()
root_dir = (file_dir / ".." / "..").resolve()
orekit_data = root_dir / "data" / "orekit-data.zip"
from orekit.pyhelpers import setup_orekit_curdir
setup_orekit_curdir(str(orekit_data))
from org.orekit.time import AbsoluteDate, TimeScalesFactory  # pylint: disable=import-error
from org.orekit.python import PythonEventHandler, PythonOrekitFixedStepHandler  # pylint: disable=import-error
from org.orekit.propagation.events.handlers import EventHandler  # pylint: disable=import-error
from org.orekit.propagation.events.handlers import RecordAndContinue  # pylint: disable=import-error
from org.orekit.propagation.events import DateDetector  # pylint: disable=import-error
from org.hipparchus.geometry.euclidean.threed import Vector3D  # pylint: disable=import-error
from org.orekit.propagation.analytical import KeplerianPropagator  # pylint: disable=import-error
from org.orekit.frames import FramesFactory  # pylint: disable=import-error
from org.orekit.utils import PVCoordinates  # pylint: disable=import-error
import org.orekit.utils as utils  # pylint: disable=import-error
import org.orekit.orbits as orbits  # pylint: disable=import-error
import skimage.filters
import skimage.transform
import simplejson as json
from mpl_toolkits.mplot3d import Axes3D

from simulation.cb import TimingEvent, TimeSampler
import simulation.sc as sc
import simulation.sssb as sssb
import simulation.starcat as starcat

log_file_dir = root_dir / "data" / "logs"
log_file = log_file_dir / "sim.log"
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(funcName)s - %(message)s")
file_handler = logging.FileHandler(str(log_file))
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logger_formatter)
logger.addHandler(file_handler)
logger.info("\n\n####################  NEW LOG ####################\n")


class Environment():
    """Simulation environment."""

    def __init__(self, name):

        self.name = name

        self.ts = TimeScalesFactory.getTDB()
        self.encounter_date = AbsoluteDate(2017, 8, 19, 0, 0, 0.000, self.ts)
        self.duration = 2. * 60
        self.start_date = self.encounter_date.getDate().shiftedBy(-self.duration / 2.)
        self.end_date = self.encounter_date.getDate().shiftedBy(self.duration / 2.)

        self.frame_settings = dict()
        self.frame_settings["first"] = 0
        self.frame_settings["last"] = 2000
        self.frame_settings["step_size"] = 1

        logger.info("First frame: %d last frame: %d Step size: %d",
                    self.frame_settings['first'], self.frame_settings['last'],
                    self.frame_settings['step_size'])

        self.ref_frame = FramesFactory.getICRF()
        self.mu_sun = utils.Constants.IAU_2015_NOMINAL_SUN_GM

        self.minimum_distance = 1E5
        self.with_terminator = True
        self.with_sunnyside = False
        self.timesampler_mode = 1
        self.slowmotion_factor = 10

        self.render_settings = dict()
        self.render_settings["exposure"] = 1.554
        self.render_settings["samples"] = 48
        self.render_settings["device"] = "Auto"
        self.render_settings["tile"] = 512
        self.render_settings["x_res"] = 2464
        self.render_settings["y_res"] = 2048

        self.camera_settings = dict()
        self.camera_settings["color_depth"] = "32"
        self.camera_settings["lens"] = 230
        self.camera_settings["sensor"] = 3.45E-3 * \
            self.render_settings["x_res"]

        logger.info("Rendering settings: Exposure: %d; Samples: %d",
                    self.render_settings['exposure'], self.render_settings['samples'])

        # Setup SSSB
        self.sssb = sssb.Sssb("Didymos", self.mu_sun, AbsoluteDate(
            2017, 8, 19, 0, 0, 0.000, self.ts))
        self.sssb.setup_timesampler(self.start_date, self.end_date,
                                    self.frame_settings["last"], 
                                    self.timesampler_mode, 
                                    self.slowmotion_factor)

        # Setup SC
        state = self.calc_encounter_sc_state()
        self.spacecraft = sc.Spacecraft(
            "CI", self.mu_sun, state, self.encounter_date)
        self.spacecraft.setup_timesampler(
            self.start_date, self.end_date, self.frame_settings["last"], 
            self.timesampler_mode, self.slowmotion_factor)

    def simulate(self):
        """Do simulation."""
        logger.info("Starting simulation")

        logger.info("Propagating SSSB")
        self.sssb.propagator.propagate(
            self.start_date.getDate(), self.end_date.getDate())

        logger.info("Propagating Spacecraft")
        self.spacecraft.propagator.propagate(
            self.start_date.getDate(), self.end_date.getDate())

        logger.info("Finishing simulation")

        self.save_results()

    def save_results(self):
        """Save simulation results to a file."""
        logger.info("Saving propagation results")

        with open(str(root_dir / "data" / "results" / (self.name + ".txt")), "w+") as f:
            for (sc_state, sssb_state) in zip(self.spacecraft.event_handler.data,
                                              self.sssb.event_handler.data):

                sc_pos = sc_state.getPVCoordinates(self.spacecraft.ref_frame).getPosition()
                sssb_pos = sssb_state.getPVCoordinates(self.sssb.ref_frame).getPosition()
                sc_pos = np.asarray(sc_pos.toArray())
                sssb_pos = np.asarray(sssb_pos.toArray())

                f.write(str(sc_state.getDate()) + "\t" + str(sssb_pos) + "\t"
                        + str(sc_pos) + "\n")

        logger.info("Propagation results saved")             

    def calc_encounter_sc_state(self):
        """Calculate the sc state during encounter relative to SSSB."""
        pos, vel = self.sssb.get_state(self.encounter_date.getDate())

        sssb_direction = pos.normalize()

        if not self.with_terminator:
            if not self.with_sunnyside:
                self.minimum_distance *= -1

            sssb_direction = sssb_direction.scalarMultiply(
                self.minimum_distance)
            sc_pos = pos.subtract(sssb_direction)

        else:
            shift = sssb_direction.scalarMultiply(-0.15)
            shift = shift.add(Vector3D(0., 0., 1.))
            shift = shift.normalize()
            shift = shift.scalarMultiply(self.minimum_distance)
            sc_pos = pos.add(shift)

        sc_vel = vel.scalarMultiply((vel.getNorm() - 10000.) / vel.getNorm())

        logger.info("Spacecraft relative velocity: %s", sc_vel)
        logger.info("Spacecraft distance from sun: %s",
                    sc_pos.getNorm()/utils.Constants.IAU_2012_ASTRONOMICAL_UNIT)

        return PVCoordinates(sc_pos, sc_vel)


if __name__ == "__main__":
    env = Environment("Didymos")
    env.simulate()
