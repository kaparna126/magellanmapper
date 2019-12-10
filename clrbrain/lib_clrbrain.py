#!/bin/bash
# Library functions shared within Clrbrain
# Author: David Young, 2017, 2019
"""Shared functions with the Clrbrain package.
"""

import os
import shutil
import warnings

import numpy as np
from skimage import exposure

from clrbrain import config

# file types that are associated with other types
_FILE_TYPE_GROUPS = {
    "obj": "mtl", 
    "mhd": "raw", 
}

# Numpy numerical dtypes with various ranges
_DTYPES = {
    "uint": [np.uint8, np.uint16, np.uint32, np.uint64], 
    "int": [np.int8, np.int16, np.int32, np.int64], 
    "float": [np.float16, np.float32, np.float64]
}

# the start of extensions that may have multiple periods
_EXTENSIONS_MULTIPLE = (".tar", ".nii")


def swap_elements(arr, axis0, axis1, offset=0):
    """Swap elements within an list or tuple.
    
    Args:
        arr: List or tuple in which to swap elements.
        axis0: Index of first element to swap.
        axis1: Index of second element to swap.
        offset: Offsets for indices; defaults to 0.
    
    Returns:
        The array with elements swapped. If the original array is actually
            a tuple, a new tuple with the elements swapped will be returned,
            so the return object may be different from the passed one.
    """
    axis0 += offset
    axis1 += offset
    check_tuple = isinstance(arr, tuple)
    if check_tuple:
        arr = list(arr)
    arr[axis0], arr[axis1] = arr[axis1], arr[axis0]
    if check_tuple:
        arr = tuple(arr)
    return arr


def transpose_1d(arr, plane):
    transposed = arr
    if plane == config.PLANE[1]:
        # make y the "z" axis
        transposed = swap_elements(arr, 0, 1)
    elif plane == config.PLANE[2]:
        # yz plane
        transposed = swap_elements(arr, 0, 2)
        transposed = swap_elements(arr, 1, 2)
    return transposed


def transpose_1d_rev(arr, plane):
    transposed = arr
    if plane == config.PLANE[1]:
        # make y the "z" axis
        transposed = swap_elements(arr, 1, 0)
    elif plane == config.PLANE[2]:
        # yz plane
        transposed = swap_elements(arr, 2, 1)
        transposed = swap_elements(arr, 2, 0)
    return transposed


def roll_elements(arr, shift, axis=None):
    """Roll elements in a tuple safe manner.
    
    Essentially calls Numpy.roll, but checks for tuple beforehand and converts 
    it to a Numpy array beforehand and back to a new tuple afterward.
    
    Args:
        arr: Array, which can be a tuple, list, or Numpy array. 
    
    Returns:
        The array with elements rolled. If arr is a tuple, the returned value 
            will be a new tuple. If arr is a Numpy array, a view of the array 
            will be turned.
    """
    #print("orig: {}".format(arr))
    check_tuple = isinstance(arr, tuple)
    if check_tuple:
        arr = np.array(arr)
    arr = np.roll(arr, shift, axis)
    if check_tuple:
        arr = tuple(arr)
    #print("after moving: {}".format(arr))
    return arr


def pad_seq(seq, n, pad=None):
    """Pad a sequence with a given value or truncate the sequence to fit 
    a given length.
    
    Args:
        seq: Sequence to fill in-place.
        n: Target length.
        pad: Value with which to fill; defaults to None.
    
    Returns:
        A truncated view of ``seq`` if the sequence is longer than ``n`` 
        or ``seq`` as a List with ``pad`` appended to reach a length of ``n``.
    """
    len_seq = len(seq)
    if len_seq >= n:
        # truncate if seq is longer than n is
        seq = seq[:n]
    else:
        # pad with the given value
        if isinstance(seq, np.ndarray):
            # convert to list if ndarray to allow mixing with None values
            seq = seq.tolist()
        seq += [pad] * (n - len_seq)
    return seq


def insert_before_ext(name, insert, sep=""):
    """Merge two paths by splicing in ``insert`` just before the extention 
    in ``base_path``.
    
    Args:
        name (str): Path; if no dot is present, it will be appended.
        insert (str): String to insert before the extension in the name.
        sep (str): Separator between ``name`` and ``insert``; default to an 
           empty string.
    
    Returns:
        Modified path.
    
    See Also:
        :func:``combine_paths`` to use the extension from ``insert``.
    """
    if name.find(".") == -1: name += "."
    return "{0}{2}{3}.{1}".format(*name.rsplit(".", 1), sep, insert)


def splitext(path):
    """Split a path at its extension in a way that supports extensions 
    with multiple periods as identified in :const:``_EXTENSIONS_MULTIPLE``.
    
    Args:
        path: Path to split.
    
    Returns:
        Tuple of path prior to extension and the extension, including 
        leading period. If an extension start is not found in 
        :const:``_EXTENSIONS_MULTIPLE``, the path will simply be split 
        by :meth:``os.path.splitext``.
    """
    i = -1
    for ext in _EXTENSIONS_MULTIPLE:
        i = path.rfind(ext)
        if i != -1: break
    if i == -1:
        path_split = os.path.splitext(path)
    else:
        path_split = (path[:i], path[i:])
    return path_split


def match_ext(path, path_to_match):
    """Match extensions for two paths.
    
    Args:
        path: Path with extension that will be kept; will be ignored if only 
            an extension with dot.
        path_to_match: Path whose extension will be replaced with that of 
            ``path``.
    
    Returns:
        ``path_to_match`` with extension replaced by that of ``path`` if 
        it has an extension; otherwise, ``path_to_match`` is simply returned.
    """
    path_split = splitext(path)
    if path_split[1] and not path_to_match.endswith(path_split[1]):
        path_to_match = os.path.splitext(path_to_match)[0] + path_split[1]
    return path_to_match


def get_filename_without_ext(path):
    """Get filename without extension.
    
    Args:
        path: Full path.
    
    Returns:
        Filename alone without extension; simply returns the filename if 
        no extension exists.
    """
    name = os.path.basename(path)
    name_split = os.path.splitext(name)
    if len(name_split) > 1: return name_split[0]
    return name


def combine_paths(base_path, suffix, sep="_", ext=None):
    """Merge two paths by appending ``suffix``, replacing the extention 
    in ``base_path``.
    
    Args:
        base_path: Path whose dot-extension will be replaced by ``suffix``. 
            If None, ``suffix`` will be returned. If a directory, will 
            be simply joined with ``suffix``.
        suffix: Replacement including new extension.
        sep: Separator between ``base_path`` and ``suffix``.
        ext: Extension to add or substitute; defaults to None to use 
            the extension in ``suffix``.
    
    Returns:
        Merged path.
    
    See Also:
        :func:``insert_before_ext`` to splice in ``suffix`` instead.
    """
    if not base_path: return suffix
    if os.path.isdir(base_path):
        path = os.path.join(base_path, suffix)
    else:
        path = os.path.splitext(base_path)[0] + sep + suffix
    if ext: path = "{}.{}".format(os.path.splitext(path)[0], ext)
    return path


def normalize(array, minimum, maximum, in_range="image"):
    """Normalizes an array to fall within the given min and max.
    
    Args:
        array (:obj:`np.ndarray`): Array to normalize.
        minimum (int): Minimum value for the array.
        maximum (int): Maximum value for the array. Assumed to be greater 
            than ``min``.
        in_range(str, List[int, float]): Range within ``array`` to rescale; 
            defaults to "image" to use the range from ``array`` itself.
    
    Returns:
        :obj:`np.ndarray`: The normalized array. 
    """
    if len(array) <= 0:
        return array
    
    if not isinstance(array, np.ndarray):
        # rescale_intensity requires Numpy arrays
        array = np.array(array)
    if isinstance(array.flat[0], (int, np.integer)) and (
            isinstance(minimum, float) or isinstance(maximum, float)):
        # convert to float if min/max are float but array is not
        array = 1.0 * array
    
    array = exposure.rescale_intensity(
        array, out_range=(minimum, maximum), in_range=in_range)
    
    return array


def printv(*s):
    """Print to console only if verbose.
    
    Args:
        s: Variable number of strings to be printed 
            if :attr:``config.verbose`` is true.
    """
    if config.verbose:
        print(*s)


def printv_format(s, form):
    """Print a formatted string to console only if verbose.
    
    Args:
        s: String to be formatted and printed if :attr:``config.verbose`` 
            is true.
        form: String by which to format ``s``.
    """
    if config.verbose:
        print(s.format(*form))


def warn(msg, category=UserWarning, stacklevel=2):
    """Print a warning message.
    
    Args:
        msg (str): Message to print.
        category (Exception): Warning category class.
        stacklevel: Warning message level.

    """
    warnings.warn(msg, category, stacklevel=stacklevel)


def series_as_str(series):
    """Get the series as a string for Clrbrain filenames, ensuring 5 
    characters to allow for a large number of series.
    
    Args:
        series: Series number, to be padded to 5 characters.
    
    Returns:
        Padded series.
    """
    return str(series).zfill(5)


def splice_before(base, search, splice, post_splice="_"):
    """Splice in a string before a given substring.
    
    Args:
        base: String in which to splice.
        search: Splice before this substring.
        splice: Splice in this string; falls back to a "." if not found.
        post_splice: String to add after the spliced string if found. If 
            only a "." is found, ``post_splice`` will be added before 
            ``splice`` instead. Defaults to "_".
    
    Returns:
        ``base`` with ``splice`` spliced in before ``search`` if found, 
        separated by ``post_splice``, falling back to splicing before 
        the first "." with ``post_splice`` placed in front of ``splice`` 
        instead. If neither ``search`` nor ``.`` are found, simply 
        returns ``base``.
    """
    i = base.rfind(search)
    if i == -1:
        # fallback to splicing before extension
        i = base.rfind(".")
        if i == -1:
            return base
        else:
            # turn post-splice into pre-splice delimiter, assuming that the 
            # absence of search string means delimiter is not before the ext
            splice = post_splice + splice
            post_splice = ""
    return base[0:i] + splice + post_splice + base[i:]


def str_to_disp(s):
    """Convert a string to a user-friendly, displayable string by replacing 
    underscores with spaces and trimming outer whitespace.
    
    Args:
        s: String to make displayable.
    
    Returns:
        New, converted string.
    """
    return s.replace("_", " ").strip()


def get_int(val):
    """Cast a value as an integer or a float if not an integer, if possible.
    
    Args:
        val: Value to cast. If a tuple or list, each entry will be casted 
            recursively.
    
    Returns:
        Value casted to int, falling back to a float, None if ``none``
        (case-insensitive), or the original value if any error occurs during
        casting.
    """
    if isinstance(val, (tuple, list)):
        return [get_int(elt) for elt in val]
    try:
        # prioritize casting to int before float if possible
        return int(val)
    except ValueError:
        try:
            # strings of floating point numbers will give an error when casting 
            # to int, so try casting to float
            return float(val)
        except ValueError:
            if isinstance(val, str) and val.lower() == "none":
                # convert to None if string is "none" (case-insensitive)
                return None
            return val


def is_int(val):
    """Check if a value is an integer, with support for alternate integer
    types such as Numpy integers.
    
    Args:
        val: Value to check.

    Returns:
        True if ``val`` is castable to an int.

    """
    return val == int(val)


def is_number(val):
    """Check if a value is a number by attempting to cast to ``float``.
    
    Args:
        val: Value to check.
    
    Returns:
        True if the value was successfully cast to ``float``; False otherwise.
    """
    try:
        float(val)
        return True
    except (ValueError, TypeError):
        return False


def format_num(val, digits=1):
    """Format a value to a given number of digits if the value is a number.
    
    Args:
        val: The value to format.
        digits: Maximum number of digits to keep; defaults to 3.
    
    Returns:
        A formatted string with the number of digits reduced to ``digits`` 
        if ``val`` is a number, or otherwise simply ``val``.
    """
    formatted = val
    if is_number(val):
        if isinstance(val, str): val = float(val)
        formatted = ("{:." + str(digits) + "g}").format(float(val))
    return formatted


def convert_indices_to_int(dict_to_convert):
    """Convert indices of a dictionary to int if possible, including nested 
    indices.
    
    Args:
        dict_to_convert: Dictionary whose indices will be converted.
    
    Returns:
        The converted dictionary.
    """
    dict_converted = {
        get_int(k): [get_int(i) for i in v] if isinstance(v, list) else v 
        for k, v in dict_to_convert.items()
    }
    return dict_converted


def npstr_to_array(s, shape=None):
    """Convert a string representation of a Numpy array back to an array.

    Args:
        s: String representation of a Numpy array such as from a ``print``
            command.
        shape: Tuple of ints by which to reshape the Numpy array. Defaults
            to None, in which case the output will be a 1-D array even
            if the input is multi-dimensional.

    Returns:
        A numpy array, or None if the string could not be converted.

    """
    arr = None
    if isinstance(s, str):
        try:
            # outputs 1-D array
            arr = np.fromstring(s.replace("[", "").replace("]", ""), sep=" ")
            if shape is not None:
                arr = arr.reshape(shape)
        except ValueError:
            pass
    return arr


def show_full_arrays(on=True):
    """Show full Numpy arrays, except for particularly large arrays.
    
    Args:
        on: True if full printing should be turned on; False to reset
            all settings.
    """
    if on:
        np.set_printoptions(linewidth=500, threshold=10000000)
    else:
        np.set_printoptions()


def print_compact(arr, msg=None, mid=False):
    """Print a Numpy array in a compact form to visual comparison with 
    other arrays.
    
    The array will be rounded, converted to integer, and optionally 
    reduced to a single plane to maximize chance of printing a 
    non-truncated array (or plane) to compare more easily with modified 
    versions of the array or other arrays.
    
    Args:
        arr: Numpy array.
        msg: Message to print on separate line before the array; defaults to 
            None, in which case the message will not be printed.
        mid: True to only print the middle element of the array.
    
    Returns:
        The compact array as a new array.
    """
    compact = np.around(arr).astype(int)
    if msg: print(msg)
    if mid:
        i = len(compact) // 2
        print(compact[i])
    else:
        print(compact)
    return compact


def compact_float(n, max_decimals=None):
    """Reduce a float to a more compact value.
    
    Args:
        n: Floating point number.
        max_decimals: Maximum decimals to keep; defaults to None.
    
    Returns:
        An integer if `n` is essentially an integer, or a string 
        representation of `n` reduced to `max_decimals` numbers after 
        the decimal point. Otherwise, simply returns `n`.
    """
    compact = n
    if float(n).is_integer():
        compact = int(n)
    elif max_decimals is not None:
        compact = "{0:.{1}f}".format(n, max_decimals)
    return compact


def backup_file(path, modifier="", i=None):
    """Backup a file to the next given available path with an index number 
    before the extension.
    
    The backed up path will be in the format 
    ``path-before-ext[modifier](i).ext``, where ``[modifier]`` is an optional 
    additional string, and ``i`` is the index number, which will be 
    incremented to avoid overwriting an existing file. Will also backup 
    any associated files as given by :const:``_FILE_TYPE_GROUPS``.
    
    Args:
        path: Path of file to backup.
        modifier: Modifier string to place before the index number.
        i: Index to use; typically use default of None to iniate recursivie 
            backup calls.
    """
    if not i:
        if not os.path.exists(path):
            # original path does not exist, so no need to back up
            return
        i = 0
    while True:
        if i == 0 and modifier != "":
            # check modifier directly first
            backup_path = insert_before_ext(path, modifier)
        else:
            # start incrementing from 1
            if i == 0: i = 1
            backup_path = insert_before_ext(path, "{}({})".format(modifier, i))
        if not os.path.exists(backup_path):
            # backup file to currently non-existent path
            shutil.move(path, backup_path)
            print("Backed up {} to {}".format(path, backup_path))
            path_split = os.path.splitext(path)
            if len(path_split) > 1:
                # remove ".", which should exist if path was split, and get 
                # any associated file to backup as well
                ext_associated = _FILE_TYPE_GROUPS.get(path_split[1][1:])
                if ext_associated:
                    # back up associated file with i
                    backup_file(
                        "{}.{}".format(path_split[0], ext_associated), 
                        modifier, i)
            break
        i += 1


def is_binary(img):
    """Check if image is binary.
    
    Args:
        img: Image array.
    
    Returns:
        True if the image is composed of only 0 and 1 values.
    """
    return ((img == 0) | (img == 1)).all()


def last_lines(path, n):
    """Get the last lines of a file by simply loading the entire file and 
    returning only the last specified lines, without depending on any 
    underlying system commands.
    
    Args:
        path: Path to file.
        n: Number of lines at the end of the file to extract; if the file is 
            shorter than this number, all lines are returned.
    
    Returns:
        The last ``n`` lines as a list, or all lines if ``n`` is greater than 
        the number of lines in the file.
    """
    lines = None
    with open(path, "r") as f:
        lines = f.read().splitlines()
        num_lines = len(lines)
        if n > num_lines:
            return lines
    return lines[-1*n:]


def coords_for_indexing(coords):
    """Convert array of coordinates to array for fancy indexing in a 
    Numpy array.
    
    Args:
        coords: Array of shape (n, m), where n = number of coordinate sets, 
            and m = number of coordinate dimensions.
    
    Returns:
        Array of coordinates split into axes, such as 
        `nd.array(rows_array, columns_array)`). This array can then be used 
        to index another array through `arr[tuple(indices)]`.
    """
    coordsi = np.transpose(coords)
    coordsi = np.split(coordsi, coordsi.shape[0])
    return coordsi


def dtype_within_range(min_val, max_val, integer=None, signed=None):
    """Get a dtype that will contain the given range.
    
    :const:``_DTYPES`` will be used to specify the possible dtypes.
    
    Args:
        min_val: Minimum required value, inclusive.
        max_val: Maximim required value, inclusive.
        integer: True to get an int type, False for float. Defaults to None
            to determine automatically based on ``max_val``.
        signed: True for a signed int, False for unsigned; ignored for float. 
            Defaults to None to determine automatically based on ``min_val``.
    
    Returns:
        The dtype fitting the range specifications.
    
    Raise:
        TypeError if a dtype with the appropriate range cannot be found.
    """
    if signed is None:
        # determine automatically based on whether min val is neg
        signed = min_val < 0
    if integer is None:
        integer = is_int(max_val)
    if integer:
        type_group = "int" if signed else "uint"
        fn_info = np.iinfo
    else:
        type_group = "float"
        fn_info = np.finfo
    types = _DTYPES[type_group]
    for dtype in types:
        if fn_info(dtype).min <= min_val and fn_info(dtype).max >= max_val:
            return dtype
    raise TypeError(
        "unable to find numerical type (integer {}, signed {}) containing "
        "range {} through {}".format(integer, signed, min_val, max_val))


def is_seq(val):
    """Check if a value is a non-string sequence.
    
    Arg:
        val: Value to check.
    
    Returns:
        True if the value is a list, tuple, or Numpy array.
    """
    # Numpy rec instead of isscalar to handle more cases such as 0d Numpy
    # arrays and third-party objects
    return np.ndim(val) != 0


def to_seq(val):
    """Convert a value to a sequence if not already a sequence.
    
    Args:
        val: Value to convert.

    Returns:
        A sequence of the value if it is not already a sequence, or
        otherwise the sequence itself.

    """
    if not is_seq(val):
        val = [val]
    return val


def enum_dict_aslist(d):
    """Summarize a dictionary with enums as keys as a shortened 
    list with only the names of each enum member.
    
    Args:
        d: Dictionary with enums as keys.
    
    Returns:
        List of tuples for all dictionary key-value pairs, with each 
        tuple containing the enum member name in place of the full 
        enum as the key.
    """
    return [(key.name, val) for key, val in d.items()]


def get_enum(s, enum_class):
    """Get an enum from a string where the enum class is assumed to have 
    all upper-case keys, returning None if the key is not found.
    
    Args:
        s (str): Key of enum to find, case-insensitive.
        enum_class (:class:`Enum`): Enum class to search.

    Returns:
        The enum if found, otherwise None.

    """
    enum = None
    if s:
        s_upper = s.upper()
        try:
            enum = enum_class[s_upper]
        except KeyError:
            pass
    return enum


def scale_slice(sl, scale, size):
    """Scale slice values by a given factor.
    
    Args:
        sl (slice): Slice object to scale.
        scale (int, float): Scaling factor.
        size (int): Size of the full range, used if ``sl.stop`` is None 
            and generating a sequence of indices.

    Returns:
        Either a new slice object after scaling if ``scale`` is >= 1, or
        a :obj:`np.ndarray` of scaled indices with the same number of elements
        as would be in the original `sl` range.

    """
    scaled = [sl.start, sl.stop, sl.step]
    scaled = [s if s is None else int(s * scale) for s in scaled]
    if scale >= 1:
        # should produce the same number of elements
        return slice(*scaled)
    # interval would be < 1 if scaling down, so need to construct a sequence
    # of indices including repeated indices to get the same total number of
    # elements
    start = 0 if scaled[0] is None else scaled[0]
    end = size if scaled[1] is None else scaled[1]
    return np.linspace(start, end, sl.stop - sl.start, dtype=int)


if __name__ == "__main__":
    print("Initializing Clrbrain general library module")
