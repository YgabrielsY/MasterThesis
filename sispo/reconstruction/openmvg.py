"""Class to control openMVG behaviour."""

from pathlib import Path
import subprocess

import utils

logger = utils.create_logger("openmvg")

class OpenMVGControllerError(RuntimeError):
    """Generic openMVG error."""
    pass


class OpenMVGController():
    """Controls behaviour of openMVG data processing."""

    def __init__(self, res_dir):
        
        self.root_dir = Path(__file__).parent.parent.parent
        self.openMVG_dir = self.root_dir / "software" / "openMVG" / "build_openMVG"
        self.openMVG_dir = self.openMVG_dir / "Windows-AMD64-Release" / "Release"
        self.sensor_database = self.root_dir / "data" / "sensor_database" / "sensor_width_camera_database.txt"

        logger.info("openMVG executables dir %s", str(self.openMVG_dir))

        #self.input_dir = self.root_dir / "data" / "ImageDataset_SceauxCastle-master" / "images"
        self.input_dir = res_dir / "rendering"
        self.res_dir = res_dir

    def analyse_images(self,
                       focal=65437,
                       intrinsics=None,
                       cam_model=1,
                       prior=True,
                       p_weights=(1.0,1.0,1.0)):
        """ImageListing step of reconstruction."""
        logger.info("Start Imagelisting")

        self.matches_dir = self.res_dir / "matches"
        self.matches_dir = utils.check_dir(self.matches_dir)

        exe = str(self.openMVG_dir / "openMVG_main_SfMInit_ImageListing")
        args = [exe]
        args.extend(["-i", str(self.input_dir)])
        args.extend(["-d", str(self.sensor_database)])
        args.extend(["-o", str(self.matches_dir)])
        args.extend(["-f", str(focal)])
        if intrinsics is not None:
            args.extend(["-k", intrinsics])
        args.extend(["-c", str(cam_model)])
        if prior:
            args.extend(["-P"])
            args.extend(["-W", ";".join([str(value) for value in p_weights])])

        ret = subprocess.run(args)
        logger.info("Image analysis returned: %s", str(ret))

    def compute_features(self):
        """Compute features in images."""
        logger.info("Compute features of listed images")
 
        self.sfm_data = self.matches_dir / "sfm_data.json"

        exe = str(self.openMVG_dir / "openMVG_main_ComputeFeatures")

        ret = subprocess.run([exe,
                              "-i", str(self.sfm_data),
                              "-o", str(self.matches_dir), 
                              "-m", "SIFT",
                              "-f", "0", 
                              "-p", "ULTRA"])
        logger.info("Feature computation returned: %s", str(ret))

    def match_features(self):
        """Match computed features of images."""
        logger.info("Match features of images")

        exe = str(self.openMVG_dir / "openMVG_main_ComputeMatches")

        ret = subprocess.run([exe,
                              "-i", str(self.sfm_data),
                              "-o", str(self.matches_dir), 
                              "-f", "0", 
                              "-n", "FASTCASCADEHASHINGL2",
                              "-v", "3"])
        logger.info("Feature matching returned: %s", str(ret))

    def reconstruct_seq(self):
        """Reconstruct 3D models sequentially."""
        #set manually the initial pair to avoid the prompt question
        logger.info("Do incremental/sequential reconstructions")

        self.reconstruction_dir = self.res_dir / "sequential"
        self.reconstruction_dir = utils.check_dir(self.reconstruction_dir)

        exe = str(self.openMVG_dir / "openMVG_main_IncrementalSfM")

        ret = subprocess.run([exe,
                              "-i", str(self.sfm_data),
                              "-m", str(self.matches_dir), 
                              "-o", str(self.reconstruction_dir),
                              "-P"])#,"-f","ADJUST_ALL","-c","3"] )
        logger.info("Incremental reconstruction returned: %s", str(ret))

    def export_MVS(self):
        """Export 3D model to MVS format."""
        logger.info("Exporting MVG result to MVS format")

        input_file = self.reconstruction_dir / "sfm_data.bin"
        self.export_dir = utils.check_dir(self.res_dir / "export")
        self.export_scene = self.export_dir / "scene.mvs"
        self.undistorted_dir = utils.check_dir(self.export_dir / "undistorted")

        exe = str(self.openMVG_dir / "openMVG_main_openMVG2openMVS")

        ret = subprocess.run([exe,
                              "-i", str(input_file),
                              "-o", str(self.export_scene),
                              "-d", str(self.undistorted_dir)])
        logger.info("Exporting to MVS returned: %s", str(ret))