# SPDX-FileCopyrightText: 2021 Gabriel J. Schwarzkopf <sispo-devs@outlook.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
The package provides a Space Imaging Simulator for Proximity Operations (SISPO)

The package creates images of a 3D object using blender. The images are render
in a flyby scenario. UCAC4 star catalogue to create the background. Afterwards
hese images are used with openMVG and openMVS to reconstruct the 3D model and
reconstruct the trajectory.
"""

import argparse
import cProfile
import io
import json
import logging
###############################################################################
################## Hack to enable JPEG2000 format in OpenCV ###################
######## See https://github.com/opencv/opencv/issues/14058 for details ########
import os

os.environ["OPENCV_IO_ENABLE_JASPER"] = "TRUE"
###############################################################################
import pstats
import sys
import time
from datetime import datetime
from pathlib import Path

from .__init__ import __version__
from .compression import *
from .plugins import plugins
from .reconstruction import *
from .sim import *

logger = logging.getLogger(__name__)


def _create_parser():
    """
    Creates argparser for SISPO which can be used for CLI and options
    """
    parser = argparse.ArgumentParser(usage="%(prog)s [OPTION] ...",
                                     description=__file__.__doc__)
    parser.add_argument("-i", "--inputdir",
                        action="store",
                        default=None,
                        type=str,
                        help="Path to 'definition.json' file")
    parser.add_argument("-o", "--outputdir",
                        action="store",
                        default=None,
                        type=str,
                        help="Path to results directory")
    parser.add_argument("-n", "--name",
                        action="store",
                        default=None,
                        type=str,
                        help="Name of simulation scenario")
    parser.add_argument("--verbose",
                        action="store_true",
                        help="Verbose output, displays log also on STDOUT")
    parser.add_argument("--with-sim",
                        action="store_true",
                        dest="with_sim",
                        help="If set, SISPO will simulate the scenario")
    parser.add_argument("--with-render",
                        action="store_true",
                        dest="with_render",
                        help="If set, SISPO will render the scenario")
    parser.add_argument("--with-compression",
                        action="store_true",
                        dest="with_compression",
                        help="If set, SISPO will compress images")
    parser.add_argument("--with-reconstruction",
                        action="store_true",
                        dest="with_reconstruction",
                        help="If set, SISPO will attempt reconstruction.")
    parser.add_argument("--restart",
                        action="store_true",
                        help="Use cProfiler and write results to log.")
    parser.add_argument("--opengl",
                        action="store_true",
                        help="Use OpenGL based rendering")
    parser.add_argument("--profile",
                        action="store_true",
                        help="Use cProfiler and write results to log.")
    parser.add_argument("-v", "--version",
                        action="store_true",
                        help="Prints version number.")
    parser.add_argument("--with-plugins",
                        action="store_true",
                        dest="with_plugins",
                        help="Plugins that are run before rendering.")
    return parser


def read_input():
    """
    Reads CLI input and then parses input file.
    """
    parser = _create_parser()
    args = parser.parse_args()

    if args.version:
        print(f"v{__version__}")
        return None

    inputfile = _parse_input_filepath(args.inputdir)

    settings = read_input_file(inputfile)
    settings["options"] = parser.parse_args(args=settings["options"])

    if settings["options"].version:
        print(f"v{__version__}")

    if settings["options"].restart:
        raise NotImplementedError()

    else:

        # If all options are false it is default case and all steps are done
        if (not settings["options"].with_sim and
            not settings["options"].with_render and
            not settings["options"].with_compression and
            not settings["options"].with_reconstruction):

            settings["options"].with_sim = True
            settings["options"].with_render = True
            settings["options"].with_compression = True
            settings["options"].with_reconstruction = True

        settings = parse_input(settings)

        if args.outputdir is not None:
            res_dir = Path(args.outputdir).resolve()
            res_dir = utils.check_dir(res_dir)

            settings["res_dir"] = res_dir

        if args.name is not None:
            settings["name"] = args.name

    return settings


def read_input_file(filename):
    """
    Reads input from a given file.

    :type filename: String
    :param filename: Filename of a mission definition file.
    """
    with open(str(filename), "r") as def_file:
        settings = json.load(def_file)

    return settings


def parse_input(settings):
    """
    Parses settings from input file into correct data formats

    :type settings: dict
    :param settings: String based description of settings.
    """

    if "simulation" not in settings:
        logger.debug("No simulation settings provided!")

    if "compression" not in settings:
        logger.debug("No compression settings provided!")

    if "reconstruction" not in settings:
        logger.debug("No reconstruction settings provided!")

    settings = _parse_paths(settings)
    settings = _parse_flags(settings)

    return settings


def _parse_paths(settings):
    """
    Recursively parses all settings with _dir suffix to a Path object.

    :type settings: dict
    :param settings: Dictionary containing settings
    """
    for key in settings.keys():
        if "dir" in key:
            if "res" in key:
                path = utils.check_dir(settings[key])
            else:
                path = utils.check_dir(settings[key], False)

            settings[key] = path
        elif "file" in key:
            file = Path(settings[key])
            file = file.resolve()
            if not file.is_file():
                raise RuntimeError(f"File {file} does not exist.")
            else:
                settings[key] = file
        elif isinstance(settings[key], dict):
            settings[key] = _parse_paths(settings[key])

    return settings


def _parse_flags(settings):
    """
    Recursively parses all settings containing with_ prefix to a bool.

    :type settings: dict
    :param settings: Dictionary containing settings
    """
    for key in settings.keys():
        if "with" in key:
            settings[key] = bool(settings[key])
        elif isinstance(settings[key], dict):
            settings[key] = _parse_flags(settings[key])

    return settings


def _parse_input_filepath(filepath):
    """
    Parse input file path either from CLI argument or default file path.
    """
    if filepath is None:
        root_dir = Path(__file__).resolve().parent.parent
        filename = root_dir / "data" / "input" / "definition.json"
    else:
        filename = Path(filepath).resolve()

        if not filename.exists():
            root_dir = Path(__file__).resolve().parent.parent
            filename = root_dir / "data" / "input" / filepath.name

    return filename


def serialize(o):
    """
    Serializes Path or Namespace objects into strings or dicts respectively.
    """
    if isinstance(o, Path):
        return str(o)
    elif isinstance(o, argparse.Namespace):
        return vars(o)
    raise TypeError(f"Object of type {type(o)} not serializable!")


def main():
    """
    Main function to run when executing file
    """
    settings = read_input()

    if settings is None:
        return

    # Initialise logging
    now = datetime.now().strftime("%Y-%m-%dT%H%M%S%z")
    filename = (now + "_sispo.log")
    log_dir = settings["res_dir"]
    if not log_dir.is_dir:
        Path.mkdir(log_dir, parents=True)
    log_file = log_dir / filename
    log_handlers = [logging.FileHandler(log_file)]

    if settings["options"].verbose:
        term_logger = logging.StreamHandler(sys.stdout)
        term_logger.setLevel(logging.DEBUG)
        log_handlers.append(term_logger)

    # Force logging reset to ensure correct style
    logging.basicConfig(handlers=log_handlers, level=logging.DEBUG,
                        format="%(asctime)s - %(name)s - %(funcName)s - %(message)s")

    logger.debug("\n\n################### NEW SISPO LOG ###################\n")

    logger.debug("Settings:")
    logger.debug(f"{json.dumps(settings, indent=4, default=serialize)}")

    sim_settings = settings["simulation"]
    comp_settings = settings["compression"]
    recon_settings = settings["reconstruction"]

    if settings["options"].profile:
        pr = cProfile.Profile()
        logger.debug("Start Profiling")
        pr.enable()

    t_start = time.time()

    logger.debug("Run full pipeline")

    if settings["options"].with_sim or settings["options"].with_render:
        logger.debug("With either simulation or rendering")
        env = Environment(**sim_settings, opengl_renderer=settings["options"].opengl)

        if settings["options"].with_sim:
            env.simulate()

        if settings["options"].with_plugins:
            plugins.try_plugins(settings["plugins"], settings, env)

        if settings["options"].with_render:
            env.render()

    if settings["options"].with_compression:
        logger.debug("With compression")
        comp = compression.Compressor(**comp_settings)
        comp.comp_decomp_series()

    if settings["options"].with_reconstruction:
        logger.debug("With reconstruction")
        recon = Reconstructor(**recon_settings)
        recon.reconstruct()

    t_end = time.time()

    if settings["options"].profile:
        pr.disable()
        logger.debug("Stop Profile")

        s = io.StringIO()
        sortby = pstats.SortKey.CUMULATIVE
        ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        ps.print_stats()

        logger.debug("\n##################### Pstats #####################\n")
        logger.debug("\n" + s.getvalue() + "\n")
        logger.debug("\n##################################################\n")

    logger.debug(f"Total time: {t_end - t_start} s")
    logger.debug("Finished sispo main")


def run():
    """Alias for :py:func:`main` ."""
    main()


if __name__ == "__main__":
    print('Please run using `python -m sispo <arguments>` from project root')
    # main()
