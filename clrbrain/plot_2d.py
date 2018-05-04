# 2D plots from stacks of imaging data
# Author: David Young, 2017, 2018
"""Plots 2D views through multiple levels of a 3D stack for
comparison with 3D visualization.

Attributes:
    colormap_2d: The Matplotlib colormap for 2D plots.
    savefig: Extension of the file in which to automatically save the
        window as a figure (eg "pdf"). If None, figures will not be
        automatically saved.
    verify: If true, verification mode is turned on, which for now
        simply turns on interior borders as the picker remains on
        by default.
    padding: Padding in pixels (x, y), or planes (z) in which to show
        extra segments.
"""

import copy
import os
import math
from time import time

import numpy as np
from matplotlib import pyplot as plt, cm
from matplotlib.collections import PatchCollection
import matplotlib.gridspec as gridspec
import matplotlib.patches as patches
import matplotlib.backend_bases as backend_bases
from matplotlib.colors import LinearSegmentedColormap, NoNorm
from matplotlib_scalebar.scalebar import ScaleBar
from matplotlib_scalebar.scalebar import SI_LENGTH
from skimage import exposure
from skimage import img_as_float
from scipy import stats

from clrbrain import detector
from clrbrain import importer
from clrbrain import config
from clrbrain import lib_clrbrain
from clrbrain import plot_3d

colormap_2d = cm.inferno
CMAP_GRBK = LinearSegmentedColormap.from_list(
    config.CMAP_GRBK_NAME, ["black", "green"])
CMAP_RDBK = LinearSegmentedColormap.from_list(
    config.CMAP_RDBK_NAME, ["black", "red"])
#colormap_2d = cm.gray
savefig = None
verify = False
# TODO: may want to base on scaling factor instead
padding = (5, 5, 3) # human (x, y, z) order

SEG_LINEWIDTH = 1
ZOOM_COLS = 9
Z_LEVELS = ("bottom", "middle", "top")
PLANE = ("xy", "xz", "yz")
plane = None
CIRCLES = ("Circles", "Repeat circles", "No circles", "Full annotation")
vmax_overview = 1.0
_DOWNSAMPLE_THRESH = 1000

# need to store DraggableCircles objects to prevent premature garbage collection
_draggable_circles = []
_circle_last_picked = []
_CUT = "cut"
_COPY = "copy"

segs_color_dict = {
    -1: "none",
    0: "r",
    1: "g",
    2: "y"
}

truth_color_dict = {
    -1: None,
    0: "m",
    1: "b"
}

edgecolor_dict = {
    0: "w",
    1: "c",
    2: "y",
    3: "m",
    4: "g"
}

class DraggableCircle:
    def __init__(self, circle, segment, fn_update_seg, color="none"):
        self.circle = circle
        self.circle.set_picker(5)
        self.facecolori = -1
        for key, val in segs_color_dict.items():
            if val == color:
                self.facecolori = key
        self.press = None
        self.segment = segment
        self.fn_update_seg = fn_update_seg
    
    def connect(self):
        """Connect events to functions.
        """
        self.cidpress = self.circle.figure.canvas.mpl_connect(
            "button_press_event", self.on_press)
        self.cidrelease = self.circle.figure.canvas.mpl_connect(
            "button_release_event", self.on_release)
        self.cidmotion = self.circle.figure.canvas.mpl_connect(
            "motion_notify_event", self.on_motion)
        self.cidpick = self.circle.figure.canvas.mpl_connect(
            "pick_event", self.on_pick)
        #print("connected circle at {}".format(self.circle.center))
    
    def remove_self(self):
        self.disconnect()
        self.circle.remove()
        #segi = self.get_vis_segments_index(self.segment)
        #self.vis_segments.remove(segi)
    
    def on_press(self, event):
        """Initiate drag events with Shift-click inside a circle.
        """
        if (event.key != "shift" and event.key != "alt" 
            or event.inaxes != self.circle.axes):
            return
        contains, attrd = self.circle.contains(event)
        if not contains: return
        print("pressed on {}".format(self.circle.center))
        x0, y0 = self.circle.center
        self.press = x0, y0, event.xdata, event.ydata
        DraggableCircle.lock = self
        
        # draw everywhere except the circle itself, store the pixel buffer 
        # in background, and draw the circle
        canvas = self.circle.figure.canvas
        ax = self.circle.axes
        self.circle.set_animated(True)
        canvas.draw()
        self.background = canvas.copy_from_bbox(self.circle.axes.bbox)
        ax.draw_artist(self.circle)
        canvas.blit(ax.bbox)
    
    def on_motion(self, event):
        """Move the circle if the drag event has been initiated.
        """
        if self.press is None: return
        if event.inaxes != self.circle.axes: return
        x0, y0, xpress, ypress = self.press
        dx = None
        dy = None
        if event.key == "shift":
            dx = event.xdata - xpress
            dy = event.ydata - ypress
            self.circle.center = x0 + dx, y0 + dy
        elif event.key == "alt":
            dx = abs(event.xdata - x0)
            dy = abs(event.ydata - y0)
            self.circle.radius = max([dx, dy])
        print("initial position: {}, {}; change thus far: {}, {}"
              .format(x0, y0, dx, dy))

        # restore the saved background and redraw the circle at its new position
        canvas = self.circle.figure.canvas
        ax = self.circle.axes
        canvas.restore_region(self.background)
        ax.draw_artist(self.circle)
        canvas.blit(ax.bbox)
    
    def on_release(self, event):
        """Finalize the circle and segment's position after a drag event
        is completed with a button release.
        """
        if self.press is None: return
        print("released on {}".format(self.circle.center))
        print("segment moving from {}...".format(self.segment))
        seg_old = np.copy(self.segment)
        self.segment[1:3] += np.subtract(
            self.circle.center, self.press[0:2]).astype(np.int)[::-1]
        rad_sign = -1 if self.segment[3] < config.POS_THRESH else 1
        self.segment[3] = rad_sign * self.circle.radius
        print("...to {}".format(self.segment))
        self.fn_update_seg(self.segment, seg_old)
        self.press = None
        
        # turn off animation property, reset background
        DraggableCircle.lock = None
        self.circle.set_animated(False)
        self.background = None
        self.circle.figure.canvas.draw()
    
    def on_pick(self, event):
        """Select the verification flag with unmodified (no Ctrl of Shift)
        button press on a circle.
        """
        if (event.mouseevent.key == "control" 
            or event.mouseevent.key == "shift" 
            or event.mouseevent.key == "alt" 
            or event.artist != self.circle):
            return
        #print("color: {}".format(self.facecolori))
        if event.mouseevent.key == "x":
            # "cut" segment
            _circle_last_picked.append((self, _CUT))
            self.remove_self()
            print("cut seg: {}".format(self.segment))
        elif event.mouseevent.key == "c":
            # "copy" segment
            _circle_last_picked.append((self, _COPY))
            print("copied seg: {}".format(self.segment))
        elif event.mouseevent.key == "d":
            # delete segment
            self.remove_self()
            self.fn_update_seg(self.segment, remove=True)
            print("deleted seg: {}".format(self.segment))
        else:
            seg_old = np.copy(self.segment)
            i = self.facecolori + 1
            if i > max(segs_color_dict.keys()):
                if self.segment[3] < config.POS_THRESH:
                    _circle_last_picked.append((self, _CUT))
                    self.remove_self()
                i = -1
            self.circle.set_facecolor(segs_color_dict[i])
            self.facecolori = i
            self.segment[4] = i
            self.fn_update_seg(self.segment, seg_old)
            print("picked segment: {}".format(self.segment))

    def disconnect(self):
        """Disconnect event listeners.
        """
        self.circle.figure.canvas.mpl_disconnect(self.cidpress)
        self.circle.figure.canvas.mpl_disconnect(self.cidrelease)
        self.circle.figure.canvas.mpl_disconnect(self.cidmotion)

def _get_radius(seg):
    """Gets the radius for a segments, defaulting to 5 if the segment's
    radius is close to 0.
    
    Args:
        seg: The segments, where seg[3] is the radius.
    
    Returns:
        The radius, defaulting to 0 if the given radius value is close 
        to 0 by numpy.allclose.
    """
    radius = seg[3]
    if radius < config.POS_THRESH:
        radius *= -1
    return radius

def _circle_collection(segments, edgecolor, facecolor, linewidth):
    """Draws a patch collection of circles for segments.
    
    Args:
        segments: Numpy array of segments, generally as an (n, 4)
            dimension array, where each segment is in (z, y, x, radius).
        edgecolor: Color of patch borders.
        facecolor: Color of patch interior.
        linewidth: Width of the border.
    
    Returns:
        The patch collection.
    """
    seg_patches = []
    for seg in segments:
        seg_patches.append(patches.Circle((seg[2], seg[1]), radius=_get_radius(seg)))
    collection = PatchCollection(seg_patches)
    collection.set_edgecolor(edgecolor)
    collection.set_facecolor(facecolor)
    collection.set_linewidth(linewidth)
    return collection

def _plot_circle(ax, segment, linewidth, linestyle, fn_update_seg, 
                 alpha=0.5):
    """Create and draw a DraggableCircle from the given segment.
    
    Args:
        ax: Matplotlib axes.
        segment: Numpy array of segments, generally as an (n, 4)
            dimension array, where each segment is in (z, y, x, radius).
        linewidth: Edge line width.
        linestyle: Edge line style.
        fn_update_seg: Function to call from DraggableCircle.
        alpha: Alpha transparency level; defaults to 0.5.
    
    Returns:
        The DraggableCircle object.
    """
    facecolor = segs_color_dict[detector.get_blob_confirmed(segment)]
    edgecolor = edgecolor_dict[detector.get_blob_channel(segment)]
    circle = patches.Circle(
        (segment[2], segment[1]), radius=_get_radius(segment), 
        edgecolor=edgecolor, facecolor=facecolor, linewidth=linewidth, 
        linestyle=linestyle, alpha=alpha)
    ax.add_patch(circle)
    #print("added circle: {}".format(circle))
    draggable_circle = DraggableCircle(
        circle, segment, fn_update_seg, facecolor)
    draggable_circle.connect()
    _draggable_circles.append(draggable_circle)
    return draggable_circle

def add_scale_bar(ax, downsample=None):
    """Adds a scale bar to the plot.
    
    Uses the x resolution value and assumes that it is in microns per pixel.
    
    Args:
        ax: The plot that will show the bar.
        downsample: Downsampling factor by which the resolution will be 
            multiplied; defaults to None.
    """
    res = detector.resolutions[0][2]
    if downsample:
        res *= downsample
    scale_bar = ScaleBar(res, u'\u00b5m', SI_LENGTH, 
                         box_alpha=0, color="w", location=3)
    ax.add_artist(scale_bar)

def imshow_multichannel(ax, img2d, channel, colormaps, aspect, alpha, 
                        vmin=None, vmax=None, origin=None, interpolation=None):
    """Show multichannel 2D image with channels overlaid over one another.
    
    Args:
        ax: Axes plot.
        img2d: 2D image either as 2D (y, x) or 3D (y, x, channel) array.
        channel: Channel to display; if None, all channels will be shown.
        aspect: Aspect ratio.
        alpha: Default alpha transparency level.
        vim: Imshow vmin level.
        vmax: Imshow vmax level.
    """
    # assume that 3D array has a channel dimension
    multichannel, channels = plot_3d.setup_channels(img2d, channel, 2)
    img = []
    i = 0
    vmin_plane = None
    vmax_plane = None
    for chl in channels:
        img2d_show = img2d[..., chl] if multichannel else img2d
        if i == 1:
            # after the 1st channel, all subsequent channels are transluscent
            alpha *= 0.3
        cmap = colormaps[chl]
        # check for custom colormaps
        if cmap == config.CMAP_GRBK_NAME:
            cmap = CMAP_GRBK
        elif cmap == config.CMAP_RDBK_NAME:
            cmap = CMAP_RDBK
        if vmin is not None:
            vmin_plane = vmin[chl]
        if vmax is not None:
            vmax_plane = vmax[chl]
        #print("vmin: {}, vmax: {}".format(vmin_plane, vmax_plane))
        img_chl = ax.imshow(
            img2d_show, cmap=cmap, aspect=aspect, alpha=alpha, vmin=vmin_plane, 
            vmax=vmax_plane, origin=origin, interpolation=interpolation)
        img.append(img_chl)
        i += 1
    return img

def show_subplot(fig, gs, row, col, image5d, channel, roi_size, offset, 
                 fn_update_seg, segs_in, segs_out, segs_cmap, alpha, 
                 highlight=False, border=None, plane="xy", roi=None, 
                 z_relative=-1, labels=None, blobs_truth=None, circles=None, 
                 aspect=None, grid=False, cmap_labels=None):
    """Shows subplots of the region of interest.
    
    Args:
        fig: Matplotlib figure.
        gs: Gridspec layout.
        row: Row number of the subplot in the layout.
        col: Column number of the subplot in the layout.
        image5d: Full Numpy array of the image stack.
        channel: Channel of the image to display.
        roi_size: List of x,y,z dimensions of the ROI.
        offset: Tuple of x,y,z coordinates of the ROI.
        segs_in: Numpy array of segments within the ROI to display in the 
            subplot, which can be None. Segments are generally given as an 
            (n, 4) dimension array, where each segment is in (z, y, x, radius).
        segs_out: Subset of segments that are adjacent to rather than
            inside the ROI, which will be drawn in a different style. Can be 
            None.
        segs_cmap: Colormap for segments.
        alpha: Opacity level.
        highlight: If true, the plot will be highlighted; defaults 
            to False.
            Defaults to None.
        plane: The plane to show in each 2D plot, with "xy" to show the 
            XY plane (default) and "xz" to show XZ plane.
        roi: A denoised region of interest, to show in place of image5d for the
            zoomed images. Defaults to None, in which case image5d will be
            used instead.
        z_relative: Index of the z-plane relative to the start of the ROI; 
            defaults to -1.
    """
    ax = plt.subplot(gs[row, col])
    hide_axes(ax)
    size = image5d.shape
    # swap columns if showing a different plane
    plane_axis = get_plane_axis(plane)
    image5d_shape_offset = 1 if image5d.ndim >= 4 else 0
    if plane == PLANE[1]:
        # "xz" planes
        size = lib_clrbrain.swap_elements(size, 0, 1, image5d_shape_offset)
    elif plane == PLANE[2]:
        # "yz" planes
        size = lib_clrbrain.swap_elements(size, 0, 2, image5d_shape_offset)
        size = lib_clrbrain.swap_elements(size, 0, 1, image5d_shape_offset)
    z = offset[2]
    ax.set_title("{}={}".format(plane_axis, z))
    if border is not None:
        # boundaries of border region, with xy point of corner in first 
        # elements and [width, height] in 2nd, allowing flipping for yz plane
        border_bounds = np.array(
            [border[0:2], 
            [roi_size[0] - 2 * border[0], roi_size[1] - 2 * border[1]]])
    if z < 0 or z >= size[image5d_shape_offset]:
        print("skipping z-plane {}".format(z))
        plt.imshow(np.zeros(roi_size[0:2]))
    else:
        # show the zoomed in 2D region
        
        # calculate the region depending on whether given ROI directly and 
        # remove time dimension since roi argument does not have it
        if roi is None:
            region = [offset[2], 
                      slice(offset[1], offset[1] + roi_size[1]), 
                      slice(offset[0], offset[0] + roi_size[0])]
            roi = image5d[0]
            #print("region: {}".format(region))
        else:
            region = [z_relative, slice(0, roi_size[1]), 
                      slice(0, roi_size[0])]
        # swap columns if showing a different plane
        if plane == PLANE[1]:
            region = lib_clrbrain.swap_elements(region, 0, 1)
        elif plane == PLANE[2]:
            region = lib_clrbrain.swap_elements(region, 0, 2)
            region = lib_clrbrain.swap_elements(region, 0, 1)
        # get the zoomed region
        if roi.ndim >= 4:
            roi = roi[tuple(region + [slice(None)])]
        else:
            roi = roi[tuple(region)]
        #print("roi shape: {}".format(roi.shape))
        
        if highlight:
            # highlight borders of z plane at bottom of ROI
            for spine in ax.spines.values():
                spine.set_edgecolor("yellow")
        if grid:
            # draw grid lines by directly editing copy of image
            grid_intervals = (roi_size[0] // 4, roi_size[1] // 4)
            roi = np.copy(roi)
            roi[::grid_intervals[0], :] = roi[::grid_intervals[0], :] / 2
            roi[:, ::grid_intervals[1]] = roi[:, ::grid_intervals[1]] / 2
        
        # show the ROI, which is now a 2D zoomed image
        colormaps = config.process_settings["channel_colors"]
        imshow_multichannel(
            ax, roi, channel, colormaps, aspect, alpha)#, 0.0, vmax_overview)
        #print("roi shape: {} for z_relative: {}".format(roi.shape, z_relative))
        
        # show labels if provided and within ROI
        if labels is not None:
            for i in range(len(labels)):
                label = labels[i]
                if z_relative >= 0 and z_relative < label.shape[0]:
                    try:
                        #ax.contour(label[z_relative], colors="C{}".format(i))\
                        pass
                    except ValueError as e:
                        print(e)
                        print("could not show label:\n{}".format(label[z_relative]))
                    ax.imshow(label[z_relative], cmap=cmap_labels, norm=NoNorm())
                    #ax.imshow(label[z_relative]) # is showing only threshold
        
        if ((segs_in is not None or segs_out is not None) 
            and not circles == CIRCLES[2].lower()):
            segs_in = np.copy(segs_in)
            if circles is None or circles == CIRCLES[0].lower():
                # zero radius of all segments outside of current z to preserve 
                # the order of segments for the corresponding colormap order 
                # while hiding outside segments
                segs_in[segs_in[:, 0] != z_relative, 3] = 0
            
            # show segments from all z's as circles with colored outlines
            if segs_in is not None and segs_cmap is not None:
                if circles in (CIRCLES[1].lower(), CIRCLES[3].lower()):
                    z_diff = np.abs(np.subtract(segs_in[:, 0], z_relative))
                    r_orig = np.abs(np.copy(segs_in[:, 3]))
                    segs_in[:, 3] = np.subtract(
                        r_orig, np.divide(z_diff, 3))
                    # make circles below 3/4 of their original radius 
                    # invisible but not removed to preserve their corresponding 
                    # colormap index
                    segs_in[np.less(
                        segs_in[:, 3], np.multiply(r_orig, 3/4)), 3] = 0
                collection = _circle_collection(
                    segs_in, segs_cmap.astype(float) / 255.0, "none", 
                    SEG_LINEWIDTH)
                ax.add_collection(collection)
            
            # segments outside the ROI shown in black dotted line only for 
            # their corresponding z
            segs_out_z = None
            if segs_out is not None:
                segs_out_z = segs_out[segs_out[:, 0] == z_relative]
                collection_adj = _circle_collection(
                    segs_out_z, "k", "none", SEG_LINEWIDTH)
                collection_adj.set_linestyle("--")
                ax.add_collection(collection_adj)
            
            # overlay segments with dotted line patch and make pickable for 
            # verifying the segment
            segments_z = segs_in[segs_in[:, 3] > 0] # full annotation
            if circles == CIRCLES[3].lower():
                # when showing full annotation, include all segments in the ROI
                for i in range(len(segments_z)):
                    seg = segments_z[i]
                    if seg[0] != z_relative and seg[3] > 0:
                        # add segments to Visualizer table
                        seg[0] = z_relative
                        detector.shift_blob_abs_coords(
                            segments_z[i], (-1 * z_relative, 0, 0))
                        segments_z[i] = fn_update_seg(seg)
            else:
                # apply only to segments in their current z
                segments_z = segs_in[segs_in[:, 0] == z_relative]
                if segs_out_z is not None:
                    segs_out_z_confirmed = segs_out_z[
                        detector.get_blob_confirmed(segs_out_z) == 1]
                    if len(segs_out_z_confirmed) > 0:
                        # include confirmed blobs 
                        segments_z = np.concatenate(
                            (segments_z, segs_out_z_confirmed))
                        print("segs_out_z_confirmed:\n{}"
                              .format(segs_out_z_confirmed))
            if segments_z is not None:
                for seg in segments_z:
                    _plot_circle(
                        ax, seg, SEG_LINEWIDTH, ":", fn_update_seg)
            
            # shows truth blobs as small, solid circles
            if blobs_truth is not None:
                for blob in blobs_truth:
                    ax.add_patch(patches.Circle(
                        (blob[2], blob[1]), radius=3, 
                        facecolor=truth_color_dict[blob[5]], alpha=1))
        
        # adds a simple border to highlight the border of the ROI
        if border is not None:
            #print("border: {}, roi_size: {}".format(border, roi_size))
            ax.add_patch(patches.Rectangle(border_bounds[0], 
                                           border_bounds[1, 0], 
                                           border_bounds[1, 1], 
                                           fill=False, edgecolor="yellow",
                                           linestyle="dashed", 
                                           linewidth=SEG_LINEWIDTH))
        
    return ax

def plot_roi(roi, segments, channel, show=True, title=""):
    """Plot ROI as sequence of z-planes containing only the ROI itself.
    
    Args:
        roi: The ROI image as a 3D array in (z, y, x) order.
        segments: Numpy array of segments to display in the subplot, which 
            can be None. Segments are generally given as an (n, 4)
            dimension array, where each segment is in (z, y, x, radius).
            All segments are assumed to be within the ROI for display.
        channel: Channel of the image to display.
        show: True if the plot should be displayed to screen; defaults 
            to True.
        title: String used as basename of output file. Defaults to "" 
            and only used if :attr:``savefig`` is set to a file 
            extension.
    """
    fig = plt.figure()
    #fig.suptitle(title)
    # total number of z-planes
    z_planes = roi.shape[0]
    # wrap plots after reaching max, but tolerates additional column
    # if it will fit all the remainder plots from the last row
    zoom_plot_rows = math.ceil(z_planes / ZOOM_COLS)
    col_remainder = z_planes % ZOOM_COLS
    zoom_plot_cols = ZOOM_COLS
    if col_remainder > 0 and col_remainder < zoom_plot_rows:
        zoom_plot_cols += 1
        zoom_plot_rows = math.ceil(z_planes / zoom_plot_cols)
        col_remainder = z_planes % zoom_plot_cols
    roi_size = roi.shape[::-1]
    zoom_offset = [0, 0, 0]
    gs = gridspec.GridSpec(
        zoom_plot_rows, zoom_plot_cols, wspace=0.1, hspace=0.1)
    image5d = importer.roi_to_image5d(roi)
    
    # plot the fully zoomed plots
    for i in range(zoom_plot_rows):
        # adjust columns for last row to number of plots remaining
        cols = zoom_plot_cols
        if i == zoom_plot_rows - 1 and col_remainder > 0:
            cols = col_remainder
        # show zoomed in plots and highlight one at offset z
        for j in range(cols):
            # z relative to the start of the ROI, since segs are relative to ROI
            z = i * zoom_plot_cols + j
            zoom_offset[2] = z
            
            # shows the zoomed subplot with scale bar for the current z-plane 
            # with all segments
            ax_z = show_subplot(
                fig, gs, i, j, image5d, channel, roi_size, zoom_offset, None,
                segments, None, None, 1.0, circles=CIRCLES[0], z_relative=z, 
                roi=roi)
            if i == 0 and j == 0:
                add_scale_bar(ax_z)
    gs.tight_layout(fig, pad=0.5)
    if show:
        plt.show()
    if savefig is not None:
        plt.savefig(title + "." + savefig)
    

def plot_2d_stack(fn_update_seg, title, filename, image5d, channel, roi_size, 
                  offset, segments, mask_in, segs_cmap, fn_close_listener, 
                  border=None, plane="xy", padding_stack=None,
                  zoom_levels=2, single_zoom_row=False, z_level=Z_LEVELS[0], 
                  roi=None, labels=None, blobs_truth=None, circles=None, 
                  mlab_screenshot=None, grid=False, zoom_cols=ZOOM_COLS):
    """Shows a figure of 2D plots to compare with the 3D plot.
    
    Args:
        title: Figure title.
        image5d: Full Numpy array of the image stack.
        channel: Channel of the image to display.
        roi_size: List of x,y,z dimensions of the ROI.
        offset: Tuple of x,y,z coordinates of the ROI.
        segments: Numpy array of segments to display in the subplot, which 
            can be None. Segments are generally given as an (n, 4)
            dimension array, where each segment is in (z, y, x, radius), and 
            coordinates are relative to ``offset``.
            This array can include adjacent segments as well.
        mask_in: Boolean mask of ``segments`` within the ROI.
        segs_cmap: Colormap for segments inside the ROI.
        fn_close_listener: Handle figure close events.
        border: Border dimensions in pixels given as (x, y, z); defaults
            to None.
        plane: The plane to show in each 2D plot, with "xy" to show the 
            XY plane (default) and "xz" to show XZ plane.
        padding_stack: The amount of padding in pixels, defaulting to the 
            padding attribute.
        zoom_levels: Number of zoom levels to include, with n - 1 levels
            included at the overview level, and the last one viewed
            as the series of ROI-sized plots; defaults to 2.
        single_zoom_row: True if the ROI-sized zoomed plots should be
            displayed on a single row; defaults to False.
        z_level: Position of the z-plane shown in the overview plots,
            based on the Z_LEVELS attribute constant; defaults to 
            Z_LEVELS[0].
        roi: A denoised region of interest for display in fully zoomed plots. 
            Defaults to None, in which case image5d will be used instead.
        zoom_cols: Number of columns per row to reserve for zoomed plots; 
            defaults to :attr:``ZOOM_COLS``.
    """
    time_start = time()
    
    fig = plt.figure()
    # black text with transluscent background the color of the figure
    # background in case the title is a 2D plot
    fig.suptitle(title, color="black", 
                 bbox=dict(facecolor=fig.get_facecolor(), edgecolor="none", 
                           alpha=0.5))
    if circles is not None:
        circles = circles.lower()
    
    # adjust array order based on which plane to show
    border_full = np.copy(border)
    border[2] = 0
    if plane == PLANE[1]:
        # "xz" planes; flip y-z to give y-planes instead of z
        roi_size = lib_clrbrain.swap_elements(roi_size, 1, 2)
        offset = lib_clrbrain.swap_elements(offset, 1, 2)
        border = lib_clrbrain.swap_elements(border, 1, 2)
        border_full = lib_clrbrain.swap_elements(border_full, 1, 2)
        if segments is not None and len(segments) > 0:
            segments[:, [0, 1]] = segments[:, [1, 0]]
    elif plane == PLANE[2]:
        # "yz" planes; roll backward to flip x-z and x-y
        roi_size = lib_clrbrain.roll_elements(roi_size, -1)
        offset = lib_clrbrain.roll_elements(offset, -1)
        border = lib_clrbrain.roll_elements(border, -1)
        border_full = lib_clrbrain.roll_elements(border_full, -1)
        print("orig segments:\n{}".format(segments))
        if segments is not None and len(segments) > 0:
            # roll forward since segments in zyx order
            segments[:, [0, 2]] = segments[:, [2, 0]]
            segments[:, [1, 2]] = segments[:, [2, 1]]
            print("rolled segments:\n{}".format(segments))
    print("2D border: {}".format(border))
    
    # total number of z-planes
    z_start = offset[2]
    z_planes = roi_size[2]
    if padding_stack is None:
        padding_stack = padding
    z_planes_padding = padding_stack[2] # additional z's above/below
    print("padding: {}, savefig: {}".format(padding, savefig))
    z_planes = z_planes + z_planes_padding * 2
    z_overview = z_start
    if z_level == Z_LEVELS[1]:
        z_overview = (2 * z_start + z_planes) // 2
    elif z_level == Z_LEVELS[2]:
        z_overview = z_start + z_planes
    print("z_overview: {}".format(z_overview))
    
    # pick image based on chosen orientation
    img2d, aspect, origin = extract_plane(image5d, z_overview, plane)
    
    # plot layout depending on number of z-planes
    if single_zoom_row:
        # show all plots in single row
        zoom_plot_rows = 1
        col_remainder = 0
        zoom_plot_cols = z_planes
    else:
        # wrap plots after reaching max, but tolerates additional column
        # if it will fit all the remainder plots from the last row
        zoom_plot_rows = math.ceil(z_planes / zoom_cols)
        col_remainder = z_planes % zoom_cols
        zoom_plot_cols = zoom_cols
        if col_remainder > 0 and col_remainder < zoom_plot_rows:
            zoom_plot_cols += 1
            zoom_plot_rows = math.ceil(z_planes / zoom_plot_cols)
            col_remainder = z_planes % zoom_plot_cols
    # overview plots is 1 > levels, but last spot is taken by screenshot
    top_cols = zoom_levels
    height_ratios = (3, zoom_plot_rows)
    if mlab_screenshot is None:
        # remove column for screenshot
        top_cols -= 1
        if img2d.shape[1] > 2 * img2d.shape[0]:
            # for wide ROIs, prioritize the fully zoomed plots, especially 
            # if only one overview column
            height_ratios = (1, 1) if top_cols >= 2 else (1, 2)
    gs = gridspec.GridSpec(2, top_cols, wspace=0.7, hspace=0.4,
                           height_ratios=height_ratios)
    
    # overview subplotting
    ax_overviews = [] # overview axes
    
    def set_overview_title(ax, plane, z_overview, zoom, level):
        plane_axis = get_plane_axis(plane)
        if level == 0:
            title = "{}={}".format(plane_axis, z_overview)
        else:
            title = "{}x".format(int(zoom))
        ax.set_title(title)
    
    def show_overview(ax, img2d_ov, level):
        """Show overview image with progressive zooming on the ROI for each 
        zoom level.
        
        Args:
            ax: Subplot axes.
            img2d_ov: Image in which to zoom.
            level: Zoom level, where 0 is the original image.
        
        Returns:
            The zoom amount as by which ``img2d_ov`` was divided.
        """
        patch_offset = offset[0:2]
        zoom = 1
        if level > 0:
            # move origin progressively closer with each zoom level
            zoom_mult = math.pow(level, 3)
            origin = np.floor(np.multiply(
                offset[0:2], zoom_levels + zoom_mult - 1) 
                / (zoom_levels + zoom_mult)).astype(int)
            zoom_shape = np.flipud(img2d_ov.shape[:2])
            # progressively decrease size, zooming in for each level
            zoom = zoom_mult + 3
            size = np.floor(zoom_shape / zoom).astype(int)
            end = np.add(origin, size)
            # keep the zoomed area within the full 2D image
            for j in range(len(origin)):
                if end[j] > zoom_shape[j]:
                    origin[j] -= end[j] - zoom_shape[j]
            # zoom and position ROI patch position
            img2d_ov = img2d_ov[origin[1]:end[1], origin[0]:end[0]]
            #print(img2d_ov_zoom.shape, origin, size)
            patch_offset = np.subtract(patch_offset, origin)
        # show the zoomed 2D image along with rectangle showing ROI, 
        # downsampling by using threshold as mask
        downsample = np.max(
            np.divide(img2d_ov.shape, _DOWNSAMPLE_THRESH)).astype(np.int)
        if downsample < 1: 
            downsample = 1
        min_show = plot_3d.near_min
        max_show = vmax_overview
        #print(img2d_ov.shape, roi_size)
        #print(np.prod(img2d_ov.shape[1:3]), np.prod(roi_size[:2]))
        if np.prod(img2d_ov.shape[1:3]) < 2 * np.prod(roi_size[:2]):
            # remove normalization from overview image if close in size to 
            # zoomed plots to emphasize the raw image
            min_show = None
            max_show = None
        imshow_multichannel(
            ax, img2d_ov[::downsample, ::downsample], channel, colormaps, 
            aspect, 1, min_show, max_show)
        ax.add_patch(patches.Rectangle(
            np.divide(patch_offset, downsample), 
            *np.divide(roi_size[0:2], downsample), 
            fill=False, edgecolor="yellow"))
        add_scale_bar(ax, downsample)
        return zoom
    
    def scroll_overview(event):
        """Scroll through overview images along their orthogonal axis.
        
        Args:
            event: Mouse or key event. For mouse events, scroll step sizes 
                will be used for movements. For key events, up/down arrows 
                will be used.
        """
        nonlocal z_overview
        step = 0
        if isinstance(event, backend_bases.MouseEvent):
            # scroll movements are scaled from 0 for each event
            step += event.step
        elif isinstance(event, backend_bases.KeyEvent):
            # finer-grained movements through keyboard controls since the 
            # finest scroll movements may be > 1
            #print("got key {}".format(event.key))
            if event.key == "up":
                step += 1
            elif event.key == "down":
                step -= 1
        z_overview_new = z_overview + step
        print("scroll step of {} to z {}".format(step, z_overview))
        max_size = max_plane(image5d[0], plane)
        if z_overview_new < 0:
            z_overview_new = 0
        elif z_overview_new >= max_size:
            z_overview_new = max_size - 1
        if step != 0 and z_overview_new != z_overview:
            # move only if step registered and changing position
            z_overview = z_overview_new
            img2d, aspect, origin = extract_plane(
                image5d, z_overview, plane)
            for level in range(zoom_levels - 1):
                ax = ax_overviews[level]
                ax.clear() # prevent performance degradation
                zoom = show_overview(ax, img2d, level)
                set_overview_title(ax, plane, z_overview, zoom, level)
    
    # overview images taken from the bottom plane of the offset, with
    # progressively zoomed overview images if set for additional zoom levels
    overview_cols = zoom_plot_cols // zoom_levels
    colormaps = config.process_settings["channel_colors"]
    for level in range(zoom_levels - 1):
        ax = plt.subplot(gs[0, level])
        ax_overviews.append(ax)
        hide_axes(ax)
        zoom = show_overview(ax, img2d, level)
        set_overview_title(ax, plane, z_overview, zoom, level)
    fig.canvas.mpl_connect("scroll_event", scroll_overview)
    fig.canvas.mpl_connect("key_press_event", scroll_overview)
    
    # zoomed-in views of z-planes spanning from just below to just above ROI
    ax_z_list = []
    segs_in = None
    segs_out = None
    if (circles != CIRCLES[2].lower() and segments is not None 
        and len(segments) > 0):
        # separate segments inside from outside the ROI
        if mask_in is not None:
            segs_in = segments[mask_in]
            segs_out = segments[np.invert(mask_in)]
        # separate out truth blobs
        if segments.shape[1] >= 6:
            if blobs_truth is None:
                blobs_truth = segments[segments[:, 5] >= 0]
            print("blobs_truth:\n{}".format(blobs_truth))
            # non-truth blobs have truth flag unset (-1)
            if segs_in is not None:
                segs_in = segs_in[segs_in[:, 5] == -1]
            if segs_out is not None:
                segs_out = segs_out[segs_out[:, 5] == -1]
            #print("segs_in:\n{}".format(segs_in))
        
    # selected or newly added patches since difficult to get patch from collection,
    # and they don't appear to be individually editable
    seg_patch_dict = {}
    
    # sub-gridspec for fully zoomed plots to allow flexible number of columns
    gs_zoomed = gridspec.GridSpecFromSubplotSpec(zoom_plot_rows, zoom_plot_cols, 
                                                 gs[1, :],
                                                 wspace=0.1, hspace=0.1)
    cmap_labels = None
    if labels is not None:
        # generate discrete colormap for labels
        num_colors = len(np.unique(labels))
        cmap_labels = lib_clrbrain.discrete_colormap(num_colors, alpha=150)
        cmap_labels = LinearSegmentedColormap.from_list(
            "discrete_cmap", cmap_labels / 255.0)
    # plot the fully zoomed plots
    #zoom_plot_rows = 0 # TESTING: show no fully zoomed plots
    for i in range(zoom_plot_rows):
        # adjust columns for last row to number of plots remaining
        cols = zoom_plot_cols
        if i == zoom_plot_rows - 1 and col_remainder > 0:
            cols = col_remainder
        # show zoomed in plots and highlight one at offset z
        for j in range(cols):
            # z relative to the start of the ROI, since segs are relative to ROI
            z_relative = i * zoom_plot_cols + j - z_planes_padding
            # absolute z value, relative to start of image5d
            z = z_start + z_relative
            zoom_offset = (offset[0], offset[1], z)
            
            # fade z-planes outside of ROI and show only image5d
            if z < z_start or z >= z_start + roi_size[2]:
                alpha = 0.5
                roi_show = None
            else:
                alpha = 1
                roi_show = roi
            
            # collects truth blobs within the given z-plane
            blobs_truth_z = None
            if blobs_truth is not None:
                blobs_truth_z = blobs_truth[np.all([
                    blobs_truth[:, 0] == z_relative, 
                    blobs_truth[:, 4] > 0], axis=0)]
            #print("blobs_truth_z:\n{}".format(blobs_truth_z))
            
            # shows border outlining area that will be saved if in verify mode
            show_border = (verify and z_relative >= border[2] 
                           and z_relative < roi_size[2] - border[2])
            
            # shows the zoomed subplot with scale bar for the current z-plane
            ax_z = show_subplot(
                fig, gs_zoomed, i, j, image5d, channel, roi_size, zoom_offset, 
                fn_update_seg,
                segs_in, segs_out, segs_cmap, alpha, z == z_overview, 
                border_full if show_border else None, plane, roi_show, 
                z_relative, labels, blobs_truth_z, circles=circles, 
                aspect=aspect, grid=grid, cmap_labels=cmap_labels)
            if i == 0 and j == 0:
                add_scale_bar(ax_z)
            ax_z_list.append(ax_z)
    
    if not circles == CIRCLES[2].lower():
        # add points that were not segmented by ctrl-clicking on zoom plots 
        # as long as not in "no circles" mode
        def on_btn_release(event):
            ax = event.inaxes
            print("event key: {}".format(event.key))
            if event.key is None:
                # for some reason becomes none with previous event was 
                # ctrl combo and this event is control
                print("Unable to detect key, please try again")
            elif event.key == "control" or event.key.startswith("ctrl"):
                seg_channel = channel
                if channel is None:
                    # specify channel by key combos if displaying multiple 
                    # channels
                    if event.key.endswith("+1"):
                        # ctrl+1
                        seg_channel = 1
                try:
                    axi = ax_z_list.index(ax)
                    if (axi != -1 and axi >= z_planes_padding 
                        and axi < z_planes - z_planes_padding):
                        
                        seg = np.array([[axi - z_planes_padding, 
                                         event.ydata.astype(int), 
                                         event.xdata.astype(int), -5]])
                        seg = detector.format_blobs(seg, seg_channel)
                        detector.shift_blob_abs_coords(seg, offset[::-1])
                        detector.update_blob_confirmed(seg, 1)
                        seg = fn_update_seg(seg[0])
                        # adds a circle to denote the new segment
                        patch = _plot_circle(
                            ax, seg, SEG_LINEWIDTH, "-", fn_update_seg)
                except ValueError as e:
                    print(e)
                    print("not on a plot to select a point")
            elif event.key == "v":
                _circle_last_picked_len = len(_circle_last_picked)
                if _circle_last_picked_len < 1:
                    print("No previously picked circle to paste")
                    return
                moved_item = _circle_last_picked[_circle_last_picked_len - 1]
                circle, move_type = moved_item
                axi = ax_z_list.index(ax)
                dz = axi - z_planes_padding - circle.segment[0]
                seg_old = np.copy(circle.segment)
                seg_new = np.copy(circle.segment)
                seg_new[0] += dz
                if move_type == _CUT:
                    print("Pasting a cut segment")
                    _draggable_circles.remove(circle)
                    _circle_last_picked.remove(moved_item)
                    seg_new = fn_update_seg(seg_new, seg_old)
                else:
                    print("Pasting a copied in segment")
                    detector.shift_blob_abs_coords(seg_new, (dz, 0, 0))
                    seg_new = fn_update_seg(seg_new)
                _plot_circle(
                    ax, seg_new, SEG_LINEWIDTH, ":", fn_update_seg)
           
        fig.canvas.mpl_connect("button_release_event", on_btn_release)
        # reset circles window flag
        fig.canvas.mpl_connect("close_event", fn_close_listener)
    
    # show 3D screenshot if available
    if mlab_screenshot is not None:
        img3d = mlab_screenshot
        ax = plt.subplot(gs[0, zoom_levels - 1])
        # auto to adjust size with less overlap
        ax.imshow(img3d)
        ax.set_aspect(img3d.shape[1] / img3d.shape[0])
        hide_axes(ax)
    gs.tight_layout(fig, pad=0.5)
    #gs_zoomed.tight_layout(fig, pad=0.5)
    plt.ion()
    plt.show()
    fig.set_size_inches(*(fig.get_size_inches() * 1.5), True)
    if savefig is not None:
        name = "{}_offset{}x{}.{}".format(
            os.path.basename(filename), offset, tuple(roi_size), 
            savefig).replace(" ", "")
        print("saving figure as {}".format(name))
        plt.savefig(name)
    print("2D plot time: {}".format(time() - time_start))
    
def hide_axes(ax):
    """Hides x- and y-axes.
    """
    ax.get_xaxis().set_visible(False)
    ax.get_yaxis().set_visible(False)

def extract_plane(image5d, plane_n, plane=None):
    """Extracts a single 2D plane and saves to file.
    
    Args:
        image5d: The full image stack.
        plane_n: Slice of planes to extract, which can be a single index 
            or multiple indices such as would be used for an animation.
        plane: Type of plane to extract, which should be one of 
            :attribute:`PLANES`.
    """
    origin = None
    aspect = None # aspect ratio
    img3d = None
    if image5d.ndim >= 4:
        img3d = image5d[0]
    else:
        img3d = image5d[:]
    # extract a single 2D plane or a stack of planes if plane_n is a slice, 
    # which would be used for animations
    img2d = None
    if plane == PLANE[1]:
        # xz plane
        aspect = detector.resolutions[0, 0] / detector.resolutions[0, 2]
        origin = "lower"
        img2d = img3d[:, plane_n, :]
        #print("img2d.shape: {}".format(img2d.shape))
        if img2d.ndim > 2 and img2d.shape[1] > 1:
            # make y the "z" axis for stack of 2D plots, such as animations
            img2d = np.swapaxes(img2d, 0, 1)
    elif plane == PLANE[2]:
        # yz plane
        aspect = detector.resolutions[0, 0] / detector.resolutions[0, 1]
        origin = "lower"
        img2d = img3d[:, :, plane_n]
        #print("img2d.shape: {}".format(img2d.shape))
        if img2d.ndim > 2 and img2d.shape[2] > 1:
            # make x the "z" axis for stack of 2D plots, such as animations
            img2d = np.swapaxes(img2d, 0, 2)
            img2d = np.swapaxes(img2d, 1, 2)
    else:
        # defaults to "xy"
        aspect = detector.resolutions[0, 1] / detector.resolutions[0, 2]
        img2d = img3d[plane_n, :, :]
    #print("aspect: {}, origin: {}".format(aspect, origin))
    return img2d, aspect, origin

def max_plane(img3d, plane):
    """Get the max plane for the given 3D image.
    
    Args:
        img3d: Image array in (z, y, x) order.
        plane: Plane as a value from :attr:``PLANE``.
    
    Returns:
        Number of elements along ``plane``'s axis.
    """
    shape = img3d.shape
    if plane == PLANE[1]:
        return shape[1]
    elif plane == PLANE[2]:
        return shape[2]
    else:
        return shape[0]

def get_plane_axis(plane):
    """Gets the name of the plane corresponding to the given axis.
    
    Args:
        plane: An element of :attr:``PLANE``.
    
    Returns:
        The axis name orthogonal to :attr:``PLANE``.
    """
    plane_axis = "z"
    if plane == PLANE[1]:
        plane_axis = "y"
    elif plane == PLANE[2]:
        plane_axis = "x"
    return plane_axis

def cycle_colors(i):
    num_colors = len(config.colors)
    cycle = i // num_colors
    colori = i % num_colors
    color = config.colors[colori]
    '''
    print("num_colors: {}, cycle: {}, colori: {}, color: {}"
          .format(num_colors, cycle, colori, color))
    '''
    upper = 255
    if cycle > 0:
        color = np.copy(color)
        color[0] = color[0] + cycle * 5
        if color[0] > upper:
            color[0] -= upper * (color[0] // upper)
    return np.divide(color, upper)

def plot_roc(stats_dict, name):
    """Plot ROC curve.
    
    Args:
        stats_dict: Dictionary of statistics to plot as given by 
            :func:``mlearn.parse_grid_stats``.
        name: String to display as title.
    """
    fig = plt.figure()
    posi = 1 # position of legend
    for group, iterable_dicts in stats_dict.items():
        lines = []
        colori = 0
        for key, value in iterable_dicts.items():
            fdr = value[0]
            sens = value[1]
            params = value[2]
            line, = plt.plot(
                fdr, sens, label=key, lw=2, color=cycle_colors(colori), 
                linestyle="", marker=".")
            lines.append(line)
            colori += 1
            for i, n in enumerate(params):
                annotation = n
                if isinstance(n, float):
                    # limit max decimal points while avoiding trailing zeros
                    annotation = "{:.3g}".format(n)
                plt.annotate(annotation, (fdr[i], sens[i]))
        # iterated legend position to avoid overlap from multiple legends
        legend = plt.legend(
            handles=lines, loc=posi, title=group, fancybox=True, 
            framealpha=0.5)
        plt.gca().add_artist(legend)
        posi += 1
    plt.plot([0, 1], [0, 1], color="navy", lw=2, linestyle="--")
    plt.xlim([0.0, 1.2])
    plt.ylim([0.0, 1.0])
    plt.xlabel("False Discovery Rate")
    plt.ylabel("Sensitivity")
    plt.title("ROC for {}".format(name))
    plt.show()

def _show_overlay(ax, img, plane_i, cmap, out_plane, aspect=1.0, alpha=1.0, 
                  title=None):
    """Shows an image for overlays in the orthogonal plane specified by 
    :attribute:`plane`.
    
    Args:
        ax: Subplot axes.
        img: 3D image.
        plane_i: Plane index of `img` to show.
        cmap: Name of colormap.
        aspect: Aspect ratio; defaults to 1.0.
        alpha: Alpha level; defaults to 1.0.
        title: Subplot title; defaults to None, in which case no title will 
            be shown.
    """
    if out_plane == PLANE[1]:
        # xz plane
        img_2d = img[:, plane_i]
        img_2d = np.flipud(img_2d)
    elif out_plane == PLANE[2]:
        # yz plane, which requires a flip when original orientation is 
        # horizontal section
        # TODO: generalize to other original orientations
        img_2d = img[:, :, plane_i]
        #img_2d = np.swapaxes(img_2d, 1, 0)
        #aspect = 1 / aspect
        img_2d = np.flipud(img_2d)
    else:
        # xy plane (default)
        img_2d = img[plane_i]
    ax.imshow(img_2d, cmap=cmap, aspect=aspect, alpha=alpha)
    hide_axes(ax)
    if title is not None:
        ax.set_title(title)

def plot_overlays(imgs, z, cmaps, title=None, aspect=1.0):
    """Plot images in a single row, with the final subplot showing an 
    overlay of all images.
    
    Args:
        imgs: List of 3D images to show.
        z: Z-plane to view for all images.
        cmaps: List of colormap names, which should be be the same length as 
            `imgs`, with the colormap applied to the corresponding image.
        title: Figure title; if None, will be given default title.
        aspect: Aspect ratio, which will be applied to all images; 
           defaults to 1.0.
    """
    # TODO: deprecated
    fig = plt.figure()
    fig.suptitle(title)
    imgs_len = len(imgs)
    gs = gridspec.GridSpec(1, imgs_len + 1)
    for i in range(imgs_len):
        print("showing img {}".format(i))
        _show_overlay(plt.subplot(gs[0, i]), imgs[i], z, cmaps[i], aspect)
    ax = plt.subplot(gs[0, imgs_len])
    for i in range(imgs_len):
        _show_overlay(ax, imgs[i], z, cmaps[i], aspect, alpha=0.5)
    if title is None:
        title = "Image overlays"
    gs.tight_layout(fig)
    plt.show()

def plot_overlays_reg(exp, atlas, atlas_reg, labels_reg, cmap_exp, 
                      cmap_atlas, cmap_labels, translation=None, title=None, 
                      out_plane=None, show=True):
    """Plot overlays of registered 3D images, showing overlap of atlas and 
    experimental image planes.
    
    Shows the figure on screen. If :attribute:plot_2d:`savefig` is set, 
    the figure will be saved to file with the extensive given by savefig.
    
    Args:
        exp: Experimental image.
        atlas: Atlas image, unregistered.
        atlas_reg: Atlas image, after registration.
        labels_reg: Atlas labels image, also registered.
        cmap_exp: Colormap for the experimental image.
        cmap_atlas: Colormap for the atlas.
        cmap_labels: Colormap for the labels.
        translation: Translation in (z, y, x) order for consistency with 
            operations on Numpy rather than SimpleITK images here; defaults 
            to None, in which case the chosen plane index for the 
            unregistered atlast will be the same fraction of its size as for 
            the registered image.
        title: Figure title; if None, will be given default title.
        out_plane: Output planar orientation.
        show: True if the plot should be displayed on screen; defaults to True.
    """
    fig = plt.figure()
    # give extra space to the first row since the atlas is often larger
    gs = gridspec.GridSpec(2, 3, height_ratios=[3, 2])
    resolution = detector.resolutions[0]
    #size_ratio = np.divide(atlas_reg.shape, exp.shape)
    aspect = 1.0
    z = 0
    atlas_z = 0
    plane_frac = 2#5 / 2
    if out_plane is None:
        out_plane = plane
    if out_plane == PLANE[1]:
        # xz plane
        aspect = resolution[0] / resolution[2]
        z = exp.shape[1] // plane_frac
        if translation is None:
            atlas_z = atlas.shape[1] // plane_frac
        else:
            atlas_z = int(z - translation[1])
    elif out_plane == PLANE[2]:
        # yz plane
        aspect = resolution[0] / resolution[1]
        z = exp.shape[2] // plane_frac
        if translation is None:
            atlas_z = atlas.shape[2] // plane_frac
        else:
            # TODO: not sure why needs to be addition here
            atlas_z = int(z + translation[2])
    else:
        # xy plane (default)
        aspect = resolution[1] / resolution[2]
        z = exp.shape[0] // plane_frac
        if translation is None:
            atlas_z = atlas.shape[0] // plane_frac
        else:
            atlas_z = int(z - translation[0])
    print("z: {}, atlas_z: {}, aspect: {}".format(z, atlas_z, aspect))
    
    # invert any neg values (one hemisphere) to minimize range and match other
    # hemisphere
    labels_reg[labels_reg < 0] = np.multiply(labels_reg[labels_reg < 0], -1)
    vmin, vmax = np.percentile(labels_reg, (5, 95))
    print("vmin: {}, vmax: {}".format(vmin, vmax))
    labels_reg = exposure.rescale_intensity(labels_reg, in_range=(vmin, vmax))
    '''
    labels_reg = labels_reg.astype(np.float)
    lib_clrbrain.normalize(labels_reg, 1, 100, background=15000)
    labels_reg = labels_reg.astype(np.int)
    print(labels_reg[290:300, 20, 190:200])
    '''
    
    # experimental image and atlas
    _show_overlay(plt.subplot(gs[0, 0]), exp, z, cmap_exp, out_plane, aspect, 
                              title="Experiment")
    _show_overlay(plt.subplot(gs[0, 1]), atlas, atlas_z, cmap_atlas, out_plane, 
                  alpha=0.5, title="Atlas")
    
    # atlas overlaid onto experiment
    ax = plt.subplot(gs[0, 2])
    _show_overlay(ax, exp, z, cmap_exp, out_plane, aspect, title="Registered")
    _show_overlay(ax, atlas_reg, z, cmap_atlas, out_plane, aspect, 0.5)
    
    # labels overlaid onto atlas
    ax = plt.subplot(gs[1, 0])
    _show_overlay(ax, atlas_reg, z, cmap_atlas, out_plane, aspect, title="Labeled atlas")
    _show_overlay(ax, labels_reg, z, cmap_labels, out_plane, aspect, 0.5)
    
    # labels overlaid onto exp
    ax = plt.subplot(gs[1, 1])
    _show_overlay(ax, exp, z, cmap_exp, out_plane, aspect, title="Labeled experiment")
    _show_overlay(ax, labels_reg, z, cmap_labels, out_plane, aspect, 0.5)
    
    # all overlaid
    ax = plt.subplot(gs[1, 2])
    _show_overlay(ax, exp, z, cmap_exp, out_plane, aspect, title="All overlaid")
    _show_overlay(ax, atlas_reg, z, cmap_atlas, out_plane, aspect, 0.5)
    _show_overlay(ax, labels_reg, z, cmap_labels, out_plane, aspect, 0.3)
    
    if title is None:
        title = "Image Overlays"
    fig.suptitle(title)
    gs.tight_layout(fig)
    if savefig is not None:
        plt.savefig(title + "." + savefig)
    if show:
        plt.show()

def _bar_plots(ax, lists, errs, list_names, x_labels, colors, width, y_label, 
               title):
    """Generate grouped bar plots from lists, where corresponding elements 
    in the lists are grouped together.
    
    Each list represents an experimental group, such as WT or het. 
    Corresponding elements in each list are grouped together in bar groups, 
    such as WT vs het at time point 0. Bars groups where all values would be 
    below :attr:``config.POS_THRESH`` are not plotted.
    
    Args:
        ax: Axes.
        lists: Tuple of mean lists to display, with each list getting a 
            separate set of bar plots with a legend entry. All lists should 
            be the same size as one another.
        errs: Tuple of variance lists (eg standard deviation or error) to 
            display, with each list getting a separate
            set of bar plots. All lists should be the same size as one 
            another and each list in ``lists``.
        list_names: List of names of each list, where the list size should 
            be the same size as the size of ``lists``.
        x_labels: List of labels for each bar group, where the list size 
            should be equal to the size of each list in ``lists``.
        width: Width of each bar.
        y_label: Y-axis label.
        title: Graph title.
    """
    bars = []
    if len(lists) < 1: return
    
    # convert lists to Numpy arrays to allow fancy indexing
    lists = np.array(lists)
    if errs: errs = np.array(errs)
    x_labels = np.array(x_labels)
    print("lists: {}".format(lists))
    
    # skip bar groups where all bars would be ~0
    mask = np.all(lists > config.POS_THRESH, axis=0)
    print("mask: {}".format(mask))
    if np.all(mask):
        print("skip none")
    else:
        print("skipping {}".format(x_labels[~mask]))
        x_labels = x_labels[mask]
        lists = lists[:, mask]
        # len(errs) may be > 0 when errs.size == 0
        if errs is not None and errs.size > 0:
            errs = errs[:, mask]
    indices = np.arange(len(lists[0]))
    #print("lists: {}".format(lists))
    #print("x_labels: {}".format(x_labels))
    
    # show each list as a set of bar plots so that corresponding elements in 
    # each list will be grouped together as bar groups
    for i in range(len(lists)):
        err = None if errs is None or errs.size < 1 else errs[i]
        #print("lens: {}, {}".format(len(lists[i]), len(x_labels)))
        #print("showing list: {}, err: {}".format(lists[i], err))
        num_bars = len(lists[i])
        err_dict = {"elinewidth": width * 20 / num_bars}
        bars.append(ax.bar(
            indices + width * i, lists[i], width=width, color=colors[i], 
            linewidth=0, yerr=err, error_kw=err_dict))
    ax.set_title(title)
    ax.set_ylabel(y_label)
    ax.set_xticks(indices + width)
    ax.set_xticklabels(x_labels, rotation=80, horizontalalignment="right")
    ax.legend(bars, list_names, loc="best", fancybox=True, framealpha=0.5)

def _volumes_mean_sem(group_dict, key_mean, key_sem, vals, mask):
    """Calculate the mean and standard error of the mean (SEM), storing them 
    in the dictionary.
    
    Values are filtered by ``mask``, and empty (ie near-zero or None) volumes 
    are excluded as well.
    
    Args:
        group_dict: Dictionary where the SEM will be stored.
        key_mean: Key at which the mean will be stored.
        key_sem: Key at which the SEM will be stored.
        vals: Values from which to calculate.
        mask: Boolean array corresponding to ``vals`` of values to keep.
    """
    # convert to Numpy array to filter by make
    vals = np.array(vals)
    if mask is not None:
        vals = vals[mask]
    print("group vals raw: {}, mask: {}, n: {}".format(vals, mask, vals.size))
    
    # further prune to remove None or near-zero values (ie no volume found)
    vals = vals[vals != None] # TODO: check if actually encounter None vals
    vals = vals[vals > config.POS_THRESH]
    mean = np.mean(vals)
    sem = stats.sem(vals)
    print("mean: {}, err: {}, n after pruning: {}".format(mean, sem, vals.size))
    group_dict[key_mean].append(mean)
    group_dict[key_sem].append(sem)

def plot_volumes(volumes_dict, title=None, densities=False, 
                 show=True, groups=None):
    """Plot volumes and densities.
    
    Args:
        volumes_dict: Dictionary of volumes as generated by 
            :func:``register.volumes_by_id``, including values from 
            individual or grouped experiments.
        title: Title to display for the entire figure; defaults to None, in 
            while case a generic title will be given.
        densities: True if densities should be extracted and displayed from 
            the volumes dictionary; defaults to False.
        show: True if plots should be displayed; defaults to True.
        groups: List of groupings for each experiment. List length should be 
            equal to the number of values stored in each label's list in 
            ``volumes_dict``. Defaults to None, in which case each label's 
            value will be assumed to be a scalar rather than a list of values.
    """
    # setup figure layout with single subplot for volumes only or 
    # side-by-side subplots if including densities
    fig = plt.figure()
    subplots_width = 2 if densities else 1
    gs = gridspec.GridSpec(1, subplots_width)
    ax_vols = plt.subplot(gs[0, 0])
    ax_densities = plt.subplot(gs[0, 1]) if densities else None
    
    # measurement units, assuming a base unit of microns
    unit_factor = np.power(1 * 1000.0, 3)
    unit = "mm"
    width = 0.1 # default bar width
    
    # "side" and "mirrored" for opposite side (R/L agnostic)
    SIDE = "side"
    MIR = "mirrored"
    SIDE_SEM = SIDE + "_sem"
    MIR_SEM = MIR + "_sem"
    VOL = "volume"
    DENS = "density"
    multiple = groups is not None
    if groups is None:
        groups = [""]
    print("groups: {}".format(groups))
    groups_unique = np.unique(groups)
    groups_dict = {}
    names = [volumes_dict[key][config.ABA_NAME] for key in volumes_dict.keys() if key >= 0]
    for group in groups_unique:
        print("Finding volumes and densities for group {}".format(group))
        # dictionary of mean and SEM arrays for each side, which will be 
        # populated in same order as experiments in volumes_dict
        vol_group = {SIDE: [], MIR: [], SIDE_SEM: [], MIR_SEM: []}
        dens_group = copy.deepcopy(vol_group)
        groups_dict[group] = {VOL: vol_group, DENS: dens_group}
        group_mask = np.array(groups) == group if multiple else None
        for key in volumes_dict.keys():
            # find negative keys based on the given positive key to show them
            # side-by-side
            if key >= 0:
                # get volumes in the given unit, which are scalar for individual 
                # image, list if multiple images
                vol_side = np.divide(volumes_dict[key][config.VOL_KEY], unit_factor)
                vol_mirrored = np.divide(volumes_dict[-1 * key][config.VOL_KEY], unit_factor)
                # store vol and SEMs in vol_group
                if isinstance(vol_side, np.ndarray):
                    # for multiple experiments, store mean and error
                    _volumes_mean_sem(vol_group, SIDE, SIDE_SEM, vol_side, group_mask)
                    _volumes_mean_sem(
                        vol_group, MIR, MIR_SEM, vol_mirrored, group_mask)
                else:
                    # for single experiment, store only vol
                    vol_group[SIDE].append(vol_side)
                    vol_group[MIR].append(vol_mirrored)
                
                if densities:
                    # calculate densities based on blobs counts and volumes
                    blobs_side = volumes_dict[key][config.BLOBS_KEY]
                    blobs_mirrored = volumes_dict[-1 * key][config.BLOBS_KEY]
                    print("id {}: blobs R {}, L {}".format(
                        key, blobs_side, blobs_mirrored))
                    density_side = np.nan_to_num(np.divide(blobs_side, vol_side))
                    density_mirrored = np.nan_to_num(np.divide(blobs_mirrored, vol_mirrored))
                    if isinstance(density_side, np.ndarray):
                        # density means and SEMs, storing the SEMs
                        _volumes_mean_sem(
                            dens_group, SIDE, SIDE_SEM, density_side, group_mask)
                        _volumes_mean_sem(
                            dens_group, MIR, MIR_SEM, density_mirrored, group_mask)
                    else:
                        dens_group[SIDE].append(density_side)
                        dens_group[MIR].append(density_mirrored)
    
    # generate bar plots
    sides_names = ("Left", "Right")
    means_keys = (MIR, SIDE)
    sem_keys = (MIR_SEM, SIDE_SEM)
    legend_names = []
    vols = []
    dens = []
    errs_vols = []
    errs_dens = []
    bar_colors = []
    i = 0
    for group_name in groups_unique:
        group = groups_dict[group_name]
        for side in sides_names:
            legend_names.append("{} {}".format(group_name, side))
            bar_colors.append("C{}".format(i))
            i += 1
        for means_key in means_keys:
            vols.append(group[VOL][means_key])
            dens.append(group[DENS][means_key])
        for sem_key in sem_keys:
            errs_vols.append(group[VOL][sem_key])
            errs_dens.append(group[DENS][sem_key])
            
    #errs = (vol_group[MIR_SEM], vol_group[SIDE_SEM]) if multiple else None
    _bar_plots(
        ax_vols, vols, errs_vols, legend_names, names, 
        bar_colors, width, "Volume (cubic {})".format(unit), "Volumes")
    if densities:
        #errs = (dens_group[MIR_SEM], dens_group[SIDE_SEM]) if multiple else None
        _bar_plots(
            ax_densities, dens, errs_dens, legend_names, 
            names, bar_colors, width, 
            "Cell density (cells / cubic {})".format(unit), "Densities")
    
    # finalize the image with title and tight layout
    if title is None:
        title = "Regional Volumes"
    fig.suptitle(title)
    gs.tight_layout(fig, rect=[0, 0, 1, 0.97]) # extra padding for title
    if savefig is not None:
        plt.savefig(title + "." + savefig)
    if show:
        plt.show()

if __name__ == "__main__":
    print("Testing plot_2d...")
    stats_dict = { 
        "test1": (np.array([[5, 4, 3], [8, 3, 4]]), [10, 20]),
        "test2": (np.array([[1225, 1200, 95], [235, 93, 230]]), [25, 34])
    }
    plot_roc(stats_dict, "Testing ROC")
    