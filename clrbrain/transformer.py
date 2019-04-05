#!/bin/bash
# Transform images with multiprocessing
# Author: David Young, 2019
"""Transform large images with multiprocessing, including up/downsampling 
and image transposition.
"""

import multiprocessing as mp
from time import time

import numpy as np
from skimage import transform

from clrbrain import chunking
from clrbrain import config
from clrbrain import detector
from clrbrain import importer
from clrbrain import lib_clrbrain

class Downsampler(object):
    """Downsample (or theoretically upsample) a large image in a way 
    that allows multiprocessing without global variables.
    
    Attributes:
        sub_rois: Numpy object array containing chunked sub-ROIs.
    """
    sub_rois = None
    
    @classmethod
    def set_data(cls, sub_rois):
        """Set the class attributes to be shared during multiprocessing."""
        cls.sub_rois = sub_rois
    
    @classmethod
    def rescale_sub_roi(cls, coord, rescale, target_size, multichannel):
        """Rescale a sub-ROI.
        
        Args:
            coord: Coordinates as a tuple of (z, y, x) of the sub-ROI within the 
                chunked ROI.
            rescale: Rescaling factor. Can be None, in which case 
                ``target_size`` will be used instead.
            target_size: Target rescaling size for the given sub-ROI in 
               (z, y, x). If ``rescale`` is not None, ``target_size`` 
               will be ignored.
            multichannel: True if the final dimension is for channels.
        
        Return:
            Tuple of ``coord`` and the rescaled sub-ROI, where 
            ``coord`` is the same as the given parameter to identify 
            where the sub-ROI is located during multiprocessing tasks.
        """
        sub_roi = cls.sub_rois[coord]
        rescaled = None
        if rescale is not None:
            rescaled = transform.rescale(
                sub_roi, rescale, mode="reflect", multichannel=multichannel)
        elif target_size is not None:
            rescaled = transform.resize(
                sub_roi, target_size, mode="reflect", anti_aliasing=True)
        return coord, rescaled

def make_modifier_plane(plane):
    """Make a string designating a plane orthogonal transformation.
    
    Args:
        plane: Plane to which the image was transposed.
    
    Returns:
        String designating the orthogonal plane transformation.
    """
    return "plane{}".format(plane.upper())

def make_modifier_scale(scale):
    """Make a string designating a scaling transformation.
    
    Args:
        scale: Scale to which the image was rescaled.
    
    Returns:
        String designating the scaling transformation.
    """
    return "scale{}".format(scale)

def make_modifier_resized(target_size):
    """Make a string designating a resize transformation.
    
    Note that the final image size may differ slightly from this size as 
    it only reflects the size targeted.
    
    Args:
        target_size: Target size of rescaling in x,y,z.
    
    Returns:
        String designating the resize transformation.
    """
    return "resized({},{},{})".format(*target_size)

def get_transposed_image_path(img_path, scale=None, target_size=None):
    """Get path, modified for any transposition by :func:``transpose_npy`` 
    naming conventions.
    
    Args:
        img_path: Unmodified image path.
        scale: Scaling factor; defaults to None, which ignores scaling.
        target_size: Target size, typically given by a register profile; 
            defaults to None, which ignores target size.
    
    Returns:
        Modified path for the given transposition, or ``img_path`` unmodified 
        if all transposition factors are None.
    """
    img_path_modified = img_path
    if scale is not None or target_size is not None:
        # use scaled image for pixel comparison, retrieving 
        # saved scaling as of v.0.6.0
        modifier = None
        if scale is not None:
            # scale takes priority as command-line argument
            modifier = make_modifier_scale(scale)
            print("loading scaled file with {} modifier".format(modifier))
        else:
            # otherwise assume set target size
            modifier = make_modifier_resized(target_size)
            print("loading resized file with {} modifier".format(modifier))
        img_path_modified = lib_clrbrain.insert_before_ext(
            img_path, "_" + modifier)
    return img_path_modified

def transpose_img(filename, series, plane=None, rescale=None):
    """Transpose Numpy NPY saved arrays into new planar orientations and 
    rescaling or resizing.
    
    Saves file to a new NPY archive with "transposed" inserted just prior
    to the series name so that "transposed" can be appended to the original
    filename for future loading within Clrbrain. Files are saved through 
    memmap-based arrays to minimize RAM usage. Currently transposes all 
    channels, ignoring :attr:``config.channel`` parameter.
    
    Args:
        filename: Full file path in :attribute:cli:`filename` format.
        series: Series within multi-series file.
        plane: Planar orientation (see :attribute:plot_2d:`PLANES`). Defaults 
            to None, in which case no planar transformation will occur.
        rescale: Rescaling factor. Defaults to None, in which case no 
            rescaling will occur, and resizing based on register profile 
            setting will be used instead if available. Rescaling takes place 
            in multiprocessing.
    """
    target_size = config.register_settings["target_size"]
    if plane is None and rescale is None and target_size is None:
        print("No transposition to perform, skipping")
        return
    
    time_start = time()
    # even if loaded already, reread to get image metadata
    # TODO: consider saving metadata in config and retrieving from there
    image5d, info = importer.read_file(filename, series, return_info=True)
    sizes = info["sizes"]
    
    # make filenames based on transpositions
    modifier = ""
    if plane is not None:
        modifier = make_modifier_plane(plane) + "_"
    # either rescaling or resizing
    if rescale is not None:
        modifier += make_modifier_scale(rescale) + "_"
    elif target_size:
        # target size may differ from final output size but allows a known 
        # size to be used for finding the file later
        modifier += make_modifier_resized(target_size) + "_"
    filename_image5d_npz, filename_info_npz = importer.make_filenames(
        filename, series, modifier=modifier)
    
    # TODO: image5d should assume 4/5 dimensions
    offset = 0 if image5d.ndim <= 3 else 1
    multichannel = image5d.ndim >=5
    image5d_swapped = image5d
    
    if plane is not None and plane != config.PLANE[0]:
        # swap z-y to get (y, z, x) order for xz orientation
        image5d_swapped = np.swapaxes(image5d_swapped, offset, offset + 1)
        detector.resolutions[0] = lib_clrbrain.swap_elements(
            detector.resolutions[0], 0, 1)
        if plane == config.PLANE[2]:
            # swap new y-x to get (x, z, y) order for yz orientation
            image5d_swapped = np.swapaxes(image5d_swapped, offset, offset + 2)
            detector.resolutions[0] = lib_clrbrain.swap_elements(
                detector.resolutions[0], 0, 2)
    
    scaling = None
    if rescale is not None or target_size is not None:
        # rescale based on scaling factor or target specific size
        rescaled = image5d_swapped
        # TODO: generalize for more than 1 preceding dimension?
        if offset > 0:
            rescaled = rescaled[0]
        #max_pixels = np.multiply(np.ones(3), 10)
        max_pixels = [100, 500, 500]
        sub_roi_size = None
        if target_size:
            # fit image into even number of pixels per chunk by rounding up 
            # number of chunks and resize each chunk by ratio of total 
            # target size to chunk number
            target_size = target_size[::-1] # change to z,y,x
            shape = rescaled.shape[:3]
            num_chunks = np.ceil(np.divide(shape, max_pixels))
            max_pixels = np.ceil(
                np.divide(shape, num_chunks)).astype(np.int)
            sub_roi_size = np.floor(
                np.divide(target_size, num_chunks)).astype(np.int)
            print("target_size: {}, num_chunks: {}, max_pixels: {}, "
                  "sub_roi_size: {}"
                  .format(target_size, num_chunks, max_pixels, sub_roi_size))
        
        # rescale in chunks with multiprocessing
        overlap = np.zeros(3).astype(np.int)
        sub_rois, _ = chunking.stack_splitter(rescaled, max_pixels, overlap)
        Downsampler.set_data(sub_rois)
        pool = mp.Pool()
        pool_results = []
        for z in range(sub_rois.shape[0]):
            for y in range(sub_rois.shape[1]):
                for x in range(sub_rois.shape[2]):
                    coord = (z, y, x)
                    pool_results.append(
                        pool.apply_async(
                            Downsampler.rescale_sub_roi, 
                            args=(coord, rescale, sub_roi_size, multichannel)))
        for result in pool_results:
            coord, sub_roi = result.get()
            print("replacing sub_roi at {} of {}"
                  .format(coord, np.add(sub_rois.shape, -1)))
            sub_rois[coord] = sub_roi
        
        pool.close()
        pool.join()
        rescaled_shape = chunking.get_split_stack_total_shape(sub_rois, overlap)
        if offset > 0:
            rescaled_shape = np.concatenate(([1], rescaled_shape))
        print("rescaled_shape: {}".format(rescaled_shape))
        # rescale chunks directly into memmap-backed array to minimize RAM usage
        image5d_transposed = np.lib.format.open_memmap(
            filename_image5d_npz, mode="w+", dtype=sub_rois[0, 0, 0].dtype, 
            shape=tuple(rescaled_shape))
        chunking.merge_split_stack2(sub_rois, overlap, offset, image5d_transposed)
        
        if rescale is not None:
            # scale resolutions based on single rescaling factor
            detector.resolutions = np.multiply(
                detector.resolutions, 1 / rescale)
        else:
            # scale resolutions based on size ratio for each dimension
            detector.resolutions = np.multiply(
                detector.resolutions, 
                (image5d_swapped.shape / rescaled_shape)[1:4])
        sizes[0] = rescaled_shape
        scaling = importer.calc_scaling(image5d_swapped, image5d_transposed)
    else:
        # transfer directly to memmap-backed array
        image5d_transposed = np.lib.format.open_memmap(
            filename_image5d_npz, mode="w+", dtype=image5d_swapped.dtype, 
            shape=image5d_swapped.shape)
        if plane == config.PLANE[1] or plane == config.PLANE[2]:
            # flip upside-down if re-orienting planes
            if offset:
                image5d_transposed[0, :] = np.fliplr(image5d_swapped[0, :])
            else:
                image5d_transposed[:] = np.fliplr(image5d_swapped[:])
        else:
            image5d_transposed[:] = image5d_swapped[:]
        sizes[0] = image5d_swapped.shape
    
    # save image metadata
    print("detector.resolutions: {}".format(detector.resolutions))
    print("sizes: {}".format(sizes))
    image5d.flush()
    importer.save_image_info(
        filename_info_npz, info["names"], sizes, detector.resolutions, 
        info["magnification"], info["zoom"], image5d_transposed.dtype, 
        *importer.calc_intensity_bounds(image5d_transposed), scaling, plane)
    print("saved transposed file to {} with shape {}".format(
        filename_image5d_npz, image5d_transposed.shape))
    print("time elapsed (s): {}".format(time() - time_start))