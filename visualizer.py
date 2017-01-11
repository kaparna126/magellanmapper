#!/bin/bash
# Author: David Young, 2017

import javabridge as jb
import bioformats as bf
import numpy as np
import math
from time import time
from mayavi import mlab
from matplotlib import pyplot as plt, cm
from scipy import stats
from skimage import restoration
from skimage import exposure
from skimage import segmentation
from skimage import measure
from skimage import morphology
from scipy import ndimage

from traits.api import HasTraits, Range, Instance, \
                    on_trait_change, Button
from traitsui.api import View, Item, HGroup, VGroup, Handler
from tvtk.pyface.scene_editor import SceneEditor
from mayavi.tools.mlab_scene_model import \
                    MlabSceneModel
from mayavi.core.ui.mayavi_scene import MayaviScene


filename = "../../Downloads/P21_L5_CONT_DENDRITE.czi"
filename = "../../Downloads/Rbp4cre_halfbrain_4-28-16_Subset3.czi"
#filename = "../../Downloads/Rbp4cre_4-28-16_Subset3_2.sis"
#filename = "/Volumes/Siavash/CLARITY/P3Ntsr1cre-tdTomato_11-10-16/Ntsr1cre-tdTomato.czi"
subset = 0 # arbitrary series for demonstration
channel = 0 # channel of interest
cube_len = 100

def start_jvm(heap_size="8G"):
    """Starts the JVM for Python-Bioformats.
    
    Args:
        heap_size: JVM heap size, defaulting to 8G.
    """
    jb.start_vm(class_path=bf.JARS, max_heap_size=heap_size)

def parse_ome(filename):
    """Parses metadata for image name and size information.
    
    Args:
        filename: Image file, assumed to have metadata in OME XML format.
    
    Returns:
        names: array of names of subsets within the file.
        sizes: array of tuples with dimensions for each subset. Dimensions
            will be given as (time, z, x, y, channels).
    """
    time_start = time()
    metadata = bf.get_omexml_metadata(filename)
    ome = bf.OMEXML(metadata)
    count = ome.image_count
    names, sizes = [], []
    for i in range(count):
        image = ome.image(i)
        names.append(image.Name)
        pixel = image.Pixels
        size = ( pixel.SizeT, pixel.SizeZ, pixel.SizeX, pixel.SizeY, pixel.SizeC )
        sizes.append(size)
    print("names: {}\nsizes: {}".format(names, sizes))
    print('time for parsing OME XML: %f' %(time() - time_start))
    return names, sizes

def find_sizes(filename):
    """Finds image size information using the ImageReader.
    
    Args:
        filename: Image file, assumed to have metadata in OME XML format.
    
    Returns:
        sizes: array of tuples with dimensions for each subset. Dimensions
            will be given as (time, z, x, y, channels).
    """
    time_start = time()
    sizes = []
    with bf.ImageReader(filename) as rdr:
        format_reader = rdr.rdr
        count = format_reader.getSeriesCount()
        for i in range(count):
            size = ( format_reader.getSizeT(), format_reader.getSizeZ(), 
                     format_reader.getSizeX(), format_reader.getSizeY(), 
                     format_reader.getSizeC() )
            print(size)
            sizes.append(size)
    print('time for finding sizes: %f' %(time() - time_start))
    return sizes

def read_file(filename, save=True, load=True, z_max=-1, offset=None):
    """Reads in an imaging file.
    
    Can load the file from a saved Numpy array and also for only a subset
    of z-planes if asked.
    
    Args:
        filename: Image file, assumed to have metadata in OME XML format.
        save: True to save the resulting Numpy array (default).
        load: If True, attempts to load a Numpy array from the same 
            location and name except for ".npz" appended to the end 
            (default). The array can be accessed as "output['image5d']".
        z_max: Number of z-planes to load, or -1 if all should be loaded
            (default).
        offset: Tuple of offset given as (z, x, y) from which to start
            loading z-plane (x, y ignored for now). Defaults to 
            (0, 0, 0).
    
    Returns:
        image5d: array of image data.
        size: tuple of dimensions given as (time, z, x, y, channels).
    """
    filename_npz = filename + ".npz"
    if load:
        try:
            time_start = time()
            output = np.load(filename_npz)
            print('file opening time: %f' %(time() - time_start))
            image5d = output["image5d"]
            size = image5d.shape
            print(size)
            return image5d, size
        except IOError as err:
            print("Unable to load {}, will attempt to reload {}".format(filename_npz, filename))
    sizes = find_sizes(filename)
    rdr = bf.ImageReader(filename, perform_init=True)
    size = sizes[subset]
    nt, nz = size[:2]
    if z_max != -1:
        nz = z_max
    if offset == None:
    	offset = (0, 0, 0) # (z, x, y)
    channels = 3 if size[4] <= 3 else size[4]
    image5d = np.empty((nt, nz, size[2], size[3], channels), np.uint8)
    #print(image5d.shape)
    time_start = time()
    for t in range(nt):
        for z in range(nz):
            print("loading planes from [{}, {}]".format(t, z))
            image5d[t, z] = rdr.read(z=(z + offset[0]), t=t, series=subset, rescale=False)
    print('file import time: %f' %(time() - time_start))
    outfile = open(filename_npz, "wb")
    if save:
        time_start = time()
        # could use compression (savez_compressed), but much slower
        np.savez(outfile, image5d=image5d)
        outfile.close()
        print('file save time: %f' %(time() - time_start))
    return image5d, size

def denoise(roi):
    """Denoises an image.
    
    Args:
        roi: Region of interest.
    
    Returns:
        Denoised region of interest.
    """
    # saturating extreme values to maximize contrast
    vmin, vmax = stats.scoreatpercentile(roi, (0.5, 99.5))
    denoised = np.clip(roi, vmin, vmax)
    denoised = (denoised - vmin) / (vmax - vmin)
    
    '''
    # denoise_bilateral apparently only works on 2D images
    t1 = time()
    bilateral = restoration.denoise_bilateral(denoised)
    t2 = time()
    print('time for bilateral filter: %f' %(t2 - t1))
    hi_dat = exposure.histogram(denoised)
    hi_bilateral = exposure.histogram(bilateral)
    plt.plot(hi_dat[1], hi_dat[0], label='data')
    plt.plot(hi_bilateral[1], hi_bilateral[0],
             label='bilateral')
    plt.xlim(0, 0.5)
    plt.legend()
    plt.title('Histogram of voxel values')
    
    sample = bilateral > 0.2
    sample = ndimage.binary_fill_holes(sample)
    open_object = morphology.opening(sample, morphology.ball(3))
    close_object = morphology.closing(open_object, morphology.ball(3))
    bbox = ndimage.find_objects(close_object)
    mask = close_object[bbox[0]]
    '''
    
    '''
    # non-local means denoising, which works but is slower
    # and doesn't seem to add much
    t3 = time()
    denoised = restoration.denoise_nl_means(denoised,
                        patch_size=5, patch_distance=7,
                        h=0.1, multichannel=False)
    t4 = time()
    print('time for non-local means denoising: %f' %(t4 - t3))
    '''
    
    # total variation denoising
    time_start = time()
    denoised = restoration.denoise_tv_chambolle(denoised, weight=0.2)
    print('time for total variation: %f' %(time() - time_start))
    
    return denoised

def segment_roi(roi, vis):
    """Segments an image, drawing contours around segmented regions.
    
    Args:
        roi: Region of interest to segment.
        vis: Visualization object on which to draw the contour.
    """
    print("segmenting...")
    # random-walker segmentation
    markers = np.zeros(roi.shape, dtype=np.uint8)
    markers[roi > 0.4] = 1
    markers[roi < 0.33] = 2
    walker = segmentation.random_walker(roi, markers, beta=1000., mode='cg_mg')
    walker = morphology.remove_small_objects(walker == 1, 200)
    labels = measure.label(walker, background=0)
    surf2 = vis.scene.mlab.contour3d(labels)

def show_roi(image5d, vis, cube_len=100, offset=(0, 0, 0)):
    """Finds and shows the region of interest.
    
    This region will be denoised and displayed in Mayavi.
    
    Args:
        image5d: Image array.
        vis: Visualization object on which to draw the contour. Any 
            current image will be cleared first.
        cube_len: Length of each side of the region of interest as a 
            cube. Defaults to 100.
        offset: Tuple of offset given as (z, x, y) for the region 
            of interest. Defaults to (0, 0, 0).
    
    Returns:
        The region of interest, including denoising.
    """
    #offset = (10, 50, 200)
    cube_slices = []
    for i in range(len(offset)):
        cube_slices.append(slice(offset[i], offset[i] + cube_len))
    print(cube_slices)
    roi = image5d[0, cube_slices[0], cube_slices[1], cube_slices[2], channel]
    #roi = image5d[0, :, :, :, 1]
    roi = denoise(roi)
    
    # Plot in Mayavi
    #mlab.figure()
    vis.scene.mlab.clf()
    
    scalars = vis.scene.mlab.pipeline.scalar_field(roi)
    # appears to add some transparency to the cube
    contour = vis.scene.mlab.pipeline.contour(scalars)
    #surf = vis.scene.mlab.pipeline.surface(contour)
    
    # removes many more extraneous points
    smooth = vis.scene.mlab.pipeline.user_defined(contour, filter='SmoothPolyDataFilter')
    smooth.filter.number_of_iterations = 400
    smooth.filter.relaxation_factor = 0.015
    # holes within cells?
    curv = vis.scene.mlab.pipeline.user_defined(smooth, filter='Curvatures')
    surf = vis.scene.mlab.pipeline.surface(curv)
    # colorizes
    module_manager = curv.children[0]
    module_manager.scalar_lut_manager.data_range = np.array([-0.6,  0.5])
    module_manager.scalar_lut_manager.lut_mode = 'RdBu'
    
    #mlab.show()
    return roi

class VisHandler(Handler):
    """Simple handler for Visualization object events.
    
    Closes the JVM when the window is closed.
    """
    def closed(self, info, is_ok):
        jb.kill_vm()

class Visualization(HasTraits):
    """GUI for choosing a region of interest and segmenting it.
    
    TraitUI-based graphical interface for selecting dimensions of an
    image to view and segment.
    
    Attributes:
        x_offset: Range editor for x-offset.
        y_offset: Range editor for y-offset.
        z_offset: Range editor for z-offset.
        scene: The main scene
        btn_redraw_trait: Button editor for drawing the reiong of 
            interest.
        btn_segment_trait: Button editor for segmenting the ROI.
        roi: The ROI.
    """
    x_offset = Range(0, 100,  0)
    y_offset = Range(0, 100, 0)
    z_offset = Range(0, 100, 0)
    scene = Instance(MlabSceneModel, ())
    btn_redraw_trait = Button("Redraw")
    btn_segment_trait = Button("Segment")
    roi = None
    
    def __init__(self):
        # Do not forget to call the parent's __init__
        HasTraits.__init__(self)
        self.roi = show_roi(image5d, self, cube_len=cube_len)
        #segment_roi(Visualization.roi, self)
    
    @on_trait_change('x_offset,y_offset,z_offset')
    def update_plot(self):
        print("x: {}, y: {}, z: {}".format(self.x_offset, self.y_offset, self.z_offset))
    
    def _btn_redraw_trait_fired(self):
        #size = sizes[subset]
        # find offset using slider values as selected percentage
        z = math.floor(float(self.z_offset) / 100 * size[1])
        x = math.floor(float(self.x_offset) / 100 * size[2])
        y = math.floor(float(self.y_offset) / 100 * size[3])
        
        # ensure that cube dimensions don't exceed array
        if z + cube_len > size[1]:
            z = size[1] - cube_len
        if x + cube_len > size[2]:
            x = size[2] - cube_len
        if y + cube_len > size[3]:
            y = size[3] - cube_len
        
        # show updated region of interest
        offset=(z, x, y)
        print(offset)
        self.roi = show_roi(image5d, self, cube_len=cube_len, offset=offset)
    
    def _btn_segment_trait_fired(self):
        #print(Visualization.roi)
        segment_roi(self.roi, self)

    # the layout of the dialog created
    view = View(Item('scene', editor=SceneEditor(scene_class=MayaviScene),
                    height=250, width=300, show_label=False),
                VGroup('x_offset', 'y_offset', 'z_offset'),
                HGroup(Item("btn_redraw_trait", show_label=False), 
                       Item("btn_segment_trait", show_label=False)),
                handler=VisHandler()
               )

# loads the image and GUI
start_jvm()
#names, sizes = parse_ome(filename)
#sizes = find_sizes(filename)
image5d, size = read_file(filename) #, z_max=cube_len)
visualization = Visualization()
visualization.configure_traits()
