# Microscope profile settings
# Author: David Young, 2020
"""Profile settings for processing regions of interests.

These setting typically involve high-resolution such as microscopy images.
"""
from magmap.settings import config
from magmap.settings import profiles


class ProcessSettings(profiles.SettingsDict):

    def __init__(self, *args, **kwargs):
        super().__init__(self)
        self["settings_name"] = "default"

        # visualization and plotting

        self["vis_3d"] = "points"  # "points" or "surface" 3D visualization
        self["points_3d_thresh"] = 0.85  # frac of thresh (changed in v.0.6.6)
        self["channel_colors"] = (
            config.Cmaps.CMAP_GRBK_NAME, config.Cmaps.CMAP_RDBK_NAME)
        self["scale_bar_color"] = "w"
        self["colorbar"] = False
        # num of times to rotate image by 90deg after loading
        self["load_rot90"] = 0
        self["norm"] = None  # (min, max) normalization of image5d

        # image preprocessing before blob detection

        self["clip_vmin"] = 5  # vmin/vmax set contrast stretching, range 0-100
        self["clip_vmax"] = 99.5
        self["clip_min"] = 0.2  # min/max clip after stretching, range 0-1
        self["clip_max"] = 1.0
        # mult by config.near_max for lower threshold of global max
        self["max_thresh_factor"] = 0.5
        self["tot_var_denoise"] = None  # weight (eg skimage default 0.1)
        self["unsharp_strength"] = 0.3  # unsharp filter (sharpens images)
        self["erosion_threshold"] = 0.2  # erode clumped cells

        # 3D blob detection settings

        self["min_sigma_factor"] = 3
        self["max_sigma_factor"] = 5
        self["num_sigma"] = 10
        self["detection_threshold"] = 0.1
        self["overlap"] = 0.5
        self["thresholding"] = None
        self["thresholding_size"] = -1
        # z,y,x px to exclude along border after blob detection
        self["exclude_border"] = None

        # block processing and automated verification

        # multiprocessing start method; if method not available for the given
        # platform, the default method for the platform will be used instead
        self["mp_start"] = "fork"  # fork, spawn, or forkserver
        self["segment_size"] = 500  # detection ROI max size along longest edge
        # max size along longest edge for denoising blocks within
        # segmentation blobs; None turns off preprocessing in stack proc;
        # make much larger than segment_size (eg 2x) to cover the full segment
        # ROI because of additional overlap in segment ROIs
        self["denoise_size"] = 25
        # z,y,x tolerances for pruning duplicates in overlapped regions
        self["prune_tol_factor"] = (1, 1, 1)
        self["verify_tol_factor"] = (1, 1, 1)
        # module level variable will take precedence
        self["sub_stack_max_pixels"] = (1000, 1000, 1000)

        # resizing for anisotropy

        self["isotropic"] = None  # final relative z,y,x scaling after resizing
        self["isotropic_vis"] = None  # z,y,x scaling factor for vis only
        self["resize_blobs"] = None  # z,y,x coord scaling before verification

        self.profiles = {

            # Lightsheet nuclei
            # pre-v01
            # v1 (MagellanMapper v0.6.1)
            # v2 (MagellanMapper v0.6.2): isotropy (no anisotropic detection), dec
            #     clip_max, use default sub_stack_max_pixels
            # v2.1 (MagellanMapper v0.6.4): erosion_threshold
            # v2.2 (MagellanMapper v0.6.6): narrower and taller stack shape
            # v2.3 (MagellanMapper v0.8.7): added prune_tol_factor
            # v2.4 (MagellanMapper v0.8.8): decreased min/max sigma, segment size
            # v2.5 (MagellanMapper v0.8.9): added exclude_border
            # v2.6 (MagellanMapper v0.9.3): slight dec in x/y verify tol for
            #     Hungarian method
            # v2.6.1 (MagellanMapper v0.9.4): scale_factor, segmenting_mean_thresh
            #     had already been turned off and now removed completely
            "lightsheet": {
                "points_3d_thresh": 0.7,
                "clip_vmax": 98.5,
                "clip_min": 0,
                "clip_max": 0.5,
                "unsharp_strength": 0.3,
                "erosion_threshold": 0.3,
                "min_sigma_factor": 2.6,
                "max_sigma_factor": 2.8,
                "num_sigma": 10,
                "overlap": 0.55,
                "segment_size": 150,
                "prune_tol_factor": (1, 0.9, 0.9),
                "verify_tol_factor": (3, 1.2, 1.2),
                "isotropic": (0.96, 1, 1),
                "isotropic_vis": (1.3, 1, 1),
                "sub_stack_max_pixels": (1200, 800, 800),
                "exclude_border": (1, 0, 0),
            },

            # minimal preprocessing
            "minpreproc": {
                "clip_vmin": 0,
                "clip_vmax": 99.99,
                "clip_max": 1,
                "tot_var_denoise": 0.01,
                "unsharp_strength": 0,
                "erosion_threshold": 0,
            },

            # low resolution
            "lowres": {
                "min_sigma_factor": 10,
                "max_sigma_factor": 14,
                "isotropic": None,
                "denoise_size": 2000,  # will use full detection ROI
                "segment_size": 1000,
                "max_thresh_factor": 1.5,
                "exclude_border": (8, 1, 1),
                "verify_tol_factor": (3, 2, 2),
            },

            # 2-photon 20x nuclei
            "2p20x": {
                "vis_3d": "surface",
                "clip_vmax": 97,
                "clip_min": 0,
                "clip_max": 0.7,
                "tot_var_denoise": True,
                "unsharp_strength": 2.5,
                # smaller threshold since total var denoising
                # "points_3d_thresh": 1.1
                "min_sigma_factor": 2.6,
                "max_sigma_factor": 4,
                "num_sigma": 20,
                "overlap": 0.1,
                "thresholding": None,  # "otsu"
                # "thresholding_size": 41,
                "thresholding_size": 64,  # for otsu
                # "thresholding_size": 50.0, # for random_walker
                "denoise_size": 25,
                "segment_size": 100,
                "prune_tol_factor": (1.5, 1.3, 1.3),
            },

            # 2p 20x of zebrafish nuclei
            "zebrafish": {
                "min_sigma_factor": 2.5,
                "max_sigma_factor": 3,
            },

            # higher contrast colormaps
            "contrast": {
                "channel_colors": ("inferno", "inferno"),
                "scale_bar_color": "w",
            },

            # similar colormaps to greyscale but with a cool blue tinge
            "bone": {
                "channel_colors": ("bone", "bone"),
                "scale_bar_color": "w",
            },

            # diverging colormaps for heat maps centered on 0
            "diverging": {
                "channel_colors": ("RdBu", "BrBG"),
                "scale_bar_color": "k",
                "colorbar": True,
            },

            # lightsheet 5x of cytoplasmic markers
            "cytoplasm": {
                "clip_min": 0.3,
                "clip_max": 0.8,
                "points_3d_thresh": 0.7,
                # adjust sigmas based on extent of cyto staining;
                # TODO: consider adding sigma_mult if ratio remains
                # relatively const
                "min_sigma_factor": 4,
                "max_sigma_factor": 10,
                "num_sigma": 10,
                "overlap": 0.2,
            },

            # isotropic image that does not require interpolating visually
            "isotropic": {
                "points_3d_thresh": 0.3,  # used only if not surface
                "isotropic_vis": (1, 1, 1),
            },

            # binary image
            "binary": {
                "denoise_size": None,
                "detection_threshold": 0.001,
            },

            # adjust nuclei size for 4x magnification
            "4xnuc": {
                "min_sigma_factor": 3,
                "max_sigma_factor": 4,
            },

            # fit into ~32GB RAM instance after isotropic interpolation
            "20x": {
                "segment_size": 50,
            },

            # export to deep learning framework with required dimensions
            "exportdl": {
                "isotropic": (0.93, 1, 1),
            },

            # downsample an image previously upsampled for isotropy
            "downiso": {
                "isotropic": None,  # assume already isotropic
                "resize_blobs": (.2, 1, 1),
            },

            # rotate by 180 deg
            # TODO: replace with plot labels config setting?
            "rot180": {
                "load_rot90": 2,  # rotation by 180deg
            },

            # denoise settings when performing registration
            "register": {
                "unsharp_strength": 1.5,
            },

            # color and intensity geared toward histology atlas images
            "atlas": {
                "channel_colors": ("gray",),
                "clip_vmax": 97,
            },

            # colors for each channel based on randomly generated discrete colormaps
            "randomcolors": {
                "channel_colors": [],
            },

            # normalize image5d and associated metadata to intensity values
            # between 0 and 1
            "norm": {
                "norm": (0.0, 1.0),
            },

        }