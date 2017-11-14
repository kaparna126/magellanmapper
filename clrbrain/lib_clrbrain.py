#!/bin/bash
# Library functions shared within Clrbrain
# Author: David Young, 2017
"""Shared functions with the Clrbrain package.
"""

import numpy as np

from clrbrain import config

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

def insert_before_ext(name, insert):
    """Inserts a string before an extension.
    
    Args:
        name: Path.
        insert: String to insert before the extension in the name.
    
    Returns:
        Modified path.
    """
    return "{0}{2}.{1}".format(*name.rsplit(".", 1) + [insert])

def normalize(array, minimum, maximum, background=None):
    """Normalizes an array to fall within the given min and max.
    
    Args:
        min: Minimum value for the array.
        max: Maximum value for the array.
    
    Returns:
        The normalized array, operated on in-place.
    """
    #print(array)
    if len(array) <= 0:
        return array
    foreground = array
    if background is not None:
        foreground = foreground[foreground > background]
    array -= np.min(foreground)
    print("min: {}".format(np.min(foreground)))
    array /= np.max(array) / (maximum - minimum)
    array += minimum
    if background is not None:
        array[array < minimum] = minimum
    return array

def printv(s):
    if config.verbose:
        print(s)

if __name__ == "__main__":
    print(insert_before_ext("test.name01.jpg", "_modifier"))
    a = np.arange(2 * 3).reshape(2, 3).astype(np.float)
    a = np.ones(3 * 4).reshape(3, 4).astype(np.float)
    a *= 100
    a[0, 0] = 0
    a[1, 1] = 50
    print("a:\n{}".format(a))
    a_norm = normalize(np.copy(a), 1, 2)
    print("a_norm without background:\n{}".format(a_norm))
    a_norm = normalize(np.copy(a), 1, 2, background=0)
    print("a_norm with background:\n{}".format(a_norm))
