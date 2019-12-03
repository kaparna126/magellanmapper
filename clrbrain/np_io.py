#!/bin/bash
# Numpy archive import/export.
# Author: David Young, 2019
"""Import/export for Numpy-based archives such as ``.npy`` and ``.npz`` formats.
"""

import numpy as np

from clrbrain import config
from clrbrain import importer
from clrbrain import transformer


def load_blobs(img_path, scaled_shape=None, scale=None):
    """Load blobs from an archive and compute scaling.
    
    Args:
        img_path (str): Base path to blobs.
        scaled_shape (List): Shape of image to calculate scaling factor
            this factor cannot be found from a transposed file's metadata;
            defaults to None.
        scale (int, float): Scalar scaling factor, used to find a
            transposed file; defaults to None.

    Returns:
        :obj:`np.ndarray`, List, List: Array of blobs; sequence of scaling
        factors to a scaled or resized image, or None if not loaded or given;
        and the resolutions of the full-sized image in which the blobs
        were detected. 

    """
    filename_base = importer.filename_to_base(
        img_path, config.series)
    info = np.load(filename_base + config.SUFFIX_INFO_PROC)
    blobs = info["segments"]
    print("loaded {} blobs".format(len(blobs)))
    # get scaling from source image, which can be rescaled/resized image 
    # since contains scaling image
    load_size = config.register_settings["target_size"]
    img_path_transposed = transformer.get_transposed_image_path(
        img_path, scale, load_size)
    scaling = None
    res = None
    if scale is not None or load_size is not None:
        _, img_info = importer.read_file(
            img_path_transposed, config.series, return_info=True)
        scaling = img_info["scaling"]
        res = np.multiply(config.resolutions[0], scaling)
        print("retrieved scaling from resized image:", scaling)
        print("rescaled resolution for full-scale image:", res)
    elif scaled_shape is not None:
        # fall back to scaling based on comparison to original image
        image5d = importer.read_file(
            img_path_transposed, config.series)
        scaling = importer.calc_scaling(
            image5d, None, scaled_shape=scaled_shape)
        res = config.resolutions[0]
        print("using scaling compared to full image:", scaling)
        print("resolution from full-scale image:", res)
    return blobs, scaling, res