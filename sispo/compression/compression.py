"""
Module for compression and decompression investigations.

This module is the main contribution of my master thesis.
"""

import bz2
import gzip
import lzma
from pathlib import Path
import zlib

import cv2
import numpy as np

import utils

class CompressionError(RuntimeError):
    """Generic error class for compression errors."""
    pass


class Compressor():
    """Main class to interface compression module."""

    def __init__(self, res_dir, algo=None, settings=None):
        self.res_dir = res_dir
        self.image_dir = res_dir / "rendering"

        self.image_extension = ".exr"

        self.imgs = []

        if algo is None:
            algo = "lzma"
        if settings is None:
            settings = {"level": 9}

        self.select_algo(algo, settings)


    def get_frame_ids(self):
        """Extract list of frame ids from file names of Composition images."""
        scene_name = "Comp"
        image_names = scene_name + "*" + self.image_extension
        file_names = self.image_dir.glob(image_names)

        ids = []
        for file_name in file_names:
            file_name = str(file_name.name).strip(self.image_extension)
            file_name = file_name.strip(scene_name)
            ids.append(file_name.strip("_"))

        return ids

    def load_images(self, img_ids=None):
        """Load composition images using ids."""
        if img_ids is None:
            self.img_ids = self.get_frame_ids()
        else:
            self.img_ids = img_ids

        for id in self.img_ids:
            img_path = self.image_dir / ("Comp_" + id + self.image_extension)

            img = utils.read_openexr_image(img_path)
            self.imgs.append(img)

    def compress_series(self):
        """
        Compresses multiple images using :py:meth: `.compress`
        """
        compressed = []
        for img in self.imgs:
            self.compress(img)

    def compress(self, img):
        """
        Compresses images using predefined algorithm or file format.
        
        :param img: Image to be compressed.
        :returns: A compressed image.
        """
        img_cmp = self._comp_met(img, self._settings)
        with open(str(self.image_dir / self.img_ids[0]), "wb") as file:
            file.write(img_cmp)

        return img_cmp

    def decompress(self, img):
        """
        Decompresses images using predefined algorithm or file format.

        :returns: Decompressed image.
        """
        if img is None:
            with open(str(self.image_dir / self.img_ids[0]), "rb") as file:
                img = file.read()

        img_dcmp = self._decomp_met(img)

        return img_dcmp

    def select_algo(self, algo, settings):
        """
        Select compression and decompression algorithm or file format.

        :param algo: string to describe algorithm or file format to use for
            image compression.
        :param settings: dictionary to describe settings for the compression
            algorithm. Default is {"level": 9}, i.e. highest compression.
        """
        algo = algo.lower()

        ##### Compression algorithms #####
        if algo == "bz2":
            comp = self._decorate_builtin_compress(bz2.compress)
            settings["compresslevel"] = settings["level"]
            settings.pop("level")
            decomp = self._decorate_builtin_decompress(bz2.decompress)
        elif algo == "gzip":
            comp = self._decorate_builtin_compress(gzip.compress)
            settings["compresslevel"] = settings["level"]
            settings.pop("level")
            decomp = self._decorate_builtin_decompress(gzip.decompress)
        elif algo == "lzma":
            comp = self._decorate_builtin_compress(lzma.compress)
            settings["preset"] = settings["level"]
            settings.pop("level")
            decomp = self._decorate_builtin_decompress(lzma.decompress)
        elif algo == "zlib":
            comp = self._decorate_builtin_compress(zlib.compress)
            decomp = self._decorate_builtin_decompress(zlib.decompress)

        ##### File formats #####
        elif algo == "jpeg" or algo == "jpg":
            comp = self._decorate_cv_compress(cv2.imencode)
            settings["ext"] = ".jpg"
            params = (cv2.IMWRITE_JPEG_QUALITY, settings["level"] * 10)

            if "progressive" in settings:
                if isinstance(settings["progressive"], bool):
                    params += (cv2.IMWRITE_JPEG_PROGRESSIVE, 
                               settings["progressive"])
                else:
                    raise CompressionError("JPEG progressive requires bool")

            if "optimize" in settings:
                if isinstance(settings["optimize"], bool):
                    params += (cv2.IMWRITE_JPEG_OPTIMIZE, settings["optimize"])
                else:
                    raise CompressionError("JPEG optimize requires bool input")

            if "rst_interval" in settings:
                if isinstance(settings["rst_interval"], int):
                    params += (cv2.IMWRITE_JPEG_RST_INTERVAL,
                               settings["rst_interval"])
                else:
                    raise CompressionError("JPEG rst_interval requires int")

            if "luma_quality" in settings:
                if isinstance(settings["luma_quality"], int):
                    params += (cv2.IMWRITE_JPEG_LUMA_QUALITY,
                               settings["luma_quality"])
                else:
                    raise CompressionError("JPEG luma_quality requires int")

            if "chroma_quality" in settings:
                if isinstance(settings["chroma_quality"], int):
                    params += (cv2.IMWRITE_JPEG_CHROMA_QUALITY,
                               settings["chroma_quality"])
                else:
                    raise CompressionError("JPEG chroma_quality requires int")

            settings["params"] = params

            decomp = self._decorate_cv_decompress(cv2.imdecode)

        elif "png":
            comp = self._decorate_cv_compress(cv2.imencode)
            settings["ext"] = ".png"
            params = (cv2.IMWRITE_PNG_COMPRESSION, settings["level"])
            settings.pop("level")

            settings["params"] = params

            decomp = self._decorate_cv_decompress(cv2.imdecode)

        else:
            raise CompressionError("Unknown compression algorithm.")

        self._comp_met = comp
        self._decomp_met = decomp
        self._settings = settings

    @staticmethod
    def _decorate_builtin_compress(func):
        def compress(img, settings):
            img_cmp = func(img, **settings)
            return img_cmp

        return compress

    @staticmethod
    def _decorate_builtin_decompress(func):
        def decompress(img):
            img_dcmp = func(img)
            img_dcmp = np.frombuffer(img_dcmp, dtype=np.float32)
            img_dcmp = img_dcmp.reshape((2048,2464,3))
            return img_dcmp

        return decompress

    @staticmethod
    def _decorate_cv_compress(func):
        def compress(img, settings):
            img_temp = img * 255
            img = img_temp.astype(np.uint8)
            _, img_cmp = func(settings["ext"], img, settings["params"])
            img_cmp = np.array(img_cmp).tobytes()
            return img_cmp
        
        return compress

    @staticmethod
    def _decorate_cv_decompress(func):
        def decompress(img):
            img = np.frombuffer(img, dtype=np.uint8)
            img_dcmp = func(img, cv2.IMREAD_UNCHANGED)
            return img_dcmp

        return decompress