# Stats for Clrbrain
# Author: David Young, 2018
"""Stats calculations and text output for Clrbrain.

Attributes:
"""

import copy
import csv
from collections import OrderedDict
from enum import Enum
import os
import numpy as np
import pandas as pd
from scipy import stats

from clrbrain import config
from clrbrain import lib_clrbrain

def _volumes_mean_err(group_dict, key_mean, key_sem, vals, mask, ci=None):
    """Calculate the mean and error values, storing them in the given group 
    dictionary.
    
    Values are filtered by ``mask``, and empty (ie near-zero or None) volumes 
    are excluded as well. By default, SEM is used as the error measurement. 
    If a confidence interval argument is given, the size of the CI will be 
    used instead of SEM.
    
    Args:
        group_dict: Dictionary where the SEM will be stored.
        key_mean: Key at which the mean will be stored.
        key_sem: Key at which the SEM will be stored.
        vals: Values from which to calculate.
        mask: Boolean array corresponding to ``vals`` of values to keep.
        ci: Confidence interval alpha level; if None, CI will not be calculated.
    """
    # convert to Numpy array to filter by make
    vals = np.array(vals)
    if mask is not None:
        vals = vals[mask]
    #print("group vals raw: {}, mask: {}, n: {}".format(vals, mask, vals.size))
    
    # further prune to remove None or near-zero values (ie no volume found)
    vals = vals[vals != None] # TODO: check if actually encounter None vals
    vals = vals[vals > config.POS_THRESH]
    mean = np.mean(vals)
    sem = stats.sem(vals)
    err = sem
    if ci:
        # use confidence interval instead of SEM if CI percentage given
        confidence = stats.t.interval(ci, len(vals) - 1, loc=mean, scale=sem)
        err = confidence[1] - mean
        '''
        # alternative method, which appears to give same result
        confidence = stats.t.ppf((1 + ci)/2., len(vals) - 1)
        err = sem * confidence
        '''
    #print("mean: {}, err: {}, n after pruning: {}".format(mean, err, vals.size))
    group_dict[key_mean].append(mean)
    group_dict[key_sem].append(err)

def volume_stats(volumes_dict, densities, groups=[""], unit_factor=1.0, 
                 ci=0.95):
    """Generate stats for volumes and densities by region and groups.
    
    Args:
        volumes_dict: Dictionary of volumes as generated by 
            :func:``register.volumes_by_id`` or 
            :func:``register.group_volumes``, including values from 
            individual or grouped experiments, respectively.
        densities: True if densities should be extracted and displayed from 
            the volumes dictionary; defaults to False.
        groups: List of groupings for each experiment. List length should be 
            equal to the number of values stored in each label's list in 
            ``volumes_dict``. Defaults to a list with an empty string, in 
            which case each label's value will be assumed to be a scalar 
            rather than a list of values.
        unit_factor: Factor by which volumes will be divided to adjust units; 
            defaults to 1.0.
        ci: Confidence intervale alpha level, which can be None to ignore.
    
    Returns:
        Tuple of ``group_dict``, ``names``, ``mean_keys``, ``err_keys``, and 
        ``measurement_keys``, ``measurement_units``.
        ``group_dict`` is a dictionary with group names as keys. Each value is 
        another dictionary with ``meausurement_keys`` as keys, such as 
        "volumes" or "densities", and the corresponding ``measurement_units``, 
        such as "cubic mm". Values are in turn additional dictionaries 
        with ``mean_keys`` as keys for sub-groups  such as "right" or "left" 
        that could be means or simple counts,
        and ``err_keys`` as keys for error values, such "SEM_of_the_right" 
        or "SEM_of_the_left". These values are 2-dimensional lists in the 
        format, 
        ``[[name0_val0, name0_val2, ...], [name1_val0, name2_val1, ...], ...]``,
        where ``names`` correspond to these values. If only one sub-list is 
        given, such as for individual experiments rather than a group of 
        experiments, error values are assumed to be None or empty lists.
    """
    # "side" and "mirrored" for opposite side (R/L agnostic)
    SIDE = "side"
    MIR = "mirrored"
    SIDE_ERR = SIDE + "_err"
    MIR_ERR = MIR + "_err"
    VOL = "volume"
    BLOBS = "nuclei"
    DENS = "density"
    multiple = groups is not None
    groups_unique = np.unique(groups)
    groups_dict = {}
    for group in groups_unique:
        print("Finding volumes and densities for group {}".format(group))
        # dictionary of mean and SEM arrays for each side, which will be 
        # populated in same order as experiments in volumes_dict
        vol_group = {SIDE: [], MIR: [], SIDE_ERR: [], MIR_ERR: []}
        blobs_group = copy.deepcopy(vol_group)
        dens_group = copy.deepcopy(vol_group)
        groups_dict[group] = {
            VOL: vol_group, BLOBS: blobs_group, DENS: dens_group}
        group_mask = np.array(groups) == group if multiple else None
        for key in volumes_dict.keys():
            # find negative keys based on the given positive key to show them
            # side-by-side
            if key >= 0:
                # get volumes in the given unit, which are scalar for 
                # individual image, list if multiple images
                vol_side = np.divide(
                    volumes_dict[key][config.VOL_KEY], unit_factor)
                vol_mirrored = np.divide(
                    volumes_dict[-1 * key][config.VOL_KEY], unit_factor)
                # store vol and SEMs in vol_group
                if isinstance(vol_side, np.ndarray):
                    # for multiple experiments, store mean and error
                    _volumes_mean_err(
                        vol_group, SIDE, SIDE_ERR, vol_side, group_mask, ci=ci)
                    _volumes_mean_err(
                        vol_group, MIR, MIR_ERR, vol_mirrored, group_mask, 
                        ci=ci)
                else:
                    # for single experiment, store only vol
                    vol_group[SIDE].append(vol_side)
                    vol_group[MIR].append(vol_mirrored)
                
                if densities:
                    # calculate densities based on blobs counts and volumes
                    blobs_side = volumes_dict[key][config.BLOBS_KEY]
                    blobs_mirrored = volumes_dict[-1 * key][config.BLOBS_KEY]
                    '''
                    print("id {}: blobs R {}, L {}".format(
                        key, blobs_side, blobs_mirrored))
                    '''
                    density_side = np.nan_to_num(
                        np.divide(blobs_side, vol_side))
                    density_mirrored = np.nan_to_num(
                        np.divide(blobs_mirrored, vol_mirrored))
                    if isinstance(density_side, np.ndarray):
                        # density means and SEMs, storing the SEMs
                        _volumes_mean_err(
                            blobs_group, SIDE, SIDE_ERR, blobs_side, 
                            group_mask, ci=ci)
                        _volumes_mean_err(
                            blobs_group, MIR, MIR_ERR, blobs_mirrored, 
                            group_mask, ci=ci)
                        _volumes_mean_err(
                            dens_group, SIDE, SIDE_ERR, density_side, 
                            group_mask, ci=ci)
                        _volumes_mean_err(
                            dens_group, MIR, MIR_ERR, density_mirrored, 
                            group_mask, ci=ci)
                    else:
                        blobs_group[SIDE].append(blobs_side)
                        blobs_group[MIR].append(blobs_mirrored)
                        dens_group[SIDE].append(density_side)
                        dens_group[MIR].append(density_mirrored)
    names = [volumes_dict[key][config.ABAKeys.NAME.value] 
             for key in volumes_dict.keys() if key >= 0]
    return groups_dict, names, (MIR, SIDE), (MIR_ERR, SIDE_ERR), \
           (VOL, BLOBS, DENS), \
           ("cubic \u00b5m", "nuclei", "nuclei / cubic \u00b5m")

def vol_group_to_meas_dict(vol_stats, groups):
    groups_dict, names, means_keys, sem_keys, meas_keys, meas_units = vol_stats
    # group stats into a list for each set of bars
    meas_dict = {}
    stats_keys = (means_keys, sem_keys)
    num_stats = len(stats_keys)
    for meas in meas_keys:
        # nested dict for each meas to contain stats types (eg mean, err)
        meas_dict[meas] = {}
        for i in range(num_stats):
            meas_dict[meas][i] = []
    groups_unique = np.unique(groups)
    for group_name in groups_unique:
        group = groups_dict[group_name]
        for meas in meas_keys:
            for j in range(num_stats):
                for stat_key in stats_keys[j]:
                    # append val from stat type for each measurement
                    meas_dict[meas][j].append(group[meas][stat_key])
    return meas_dict

def volume_stats_to_csv(vol_stats, path, groups=[""]):
    """Export volume mean stats to CSV file.
    
    Args:
        vol_stats: Dictionary of volume mean/error stats as given by 
            :func:``volume_stats``.
        path: Path to output CSV file. If the filename does not end with .csv, 
            this extension will be appended.
        groups: List of groups; defaults to a list with an empty string, which 
            is the default for ``vol_stats`` with no group, including an 
            individual sample.
    
    Returns:
        Volumes stats in a Pandas data frame with separate sets of columns 
        for each measurement given in ``vol_stats``. Each column set 
        in turn has another set of columns for each group in ``groups``, 
        which are further divided by side based on pos/neg keys in 
        ``vol_stats``. Each of these sets includes mean and errors.
    """
    # unpack volume stats
    groups_dict, names, means_keys, sem_keys, meas_keys, meas_units = vol_stats
    ext = ".csv"
    if not path.endswith(ext): path += ext
    
    meas_stats = vol_group_to_meas_dict(vol_stats, groups)
    
    data = OrderedDict()
    sides = ("L", "R")
    groups_unique = np.unique(groups)
    header = ["Region"]
    for meas in meas_keys:
        for group_name in groups_unique:
            for side in sides:
                header.extend("{0}_{1}_{2},{0}_{1}_err_{2}"
                              .format(group_name, meas, side).split(","))
    for h in header:
        data[h] = []
    
    data[header[0]] = names
    j = 1
    # generate bar plots
    for i in range(len(meas_keys)):
        meas = meas_keys[i]
        # assume that meas_group 0 is means/count, 1 is errs
        meas_group = meas_stats[meas]
        for means, errs in zip(meas_group[0], meas_group[1]):
            data[header[j]].extend(means)
            data[header[j + 1]].extend(errs)
            j += 2
    
    data_frame = pd.DataFrame(data=data, columns=header)
    data_frame.to_csv(path, index=False)
    print("exported volume data per group to CSV file: \"{}\"".format(path))
    return data_frame

def volumes_to_csv(volumes_dict, path, groups=[""], unit_factor=1.0):
    """Export volumes from each sample to Pandas format and CSV file with 
    a separate column for each region.
    
    Args:
        volumes_dict: Dictionary of volumes as generated by 
            :func:``register.volumes_by_id`` or 
            :func:``register.group_volumes``, including values from 
            individual or grouped experiments, respectively.
        path: Path to output CSV file. If the filename does not end with .csv, 
            this extension will be appended.
        groups: List of groupings for each experiment. List length should be 
            equal to the number of values stored in each label's list in 
            ``volumes_dict``. Defaults to a list with an empty string, in 
            which case each label's value will be assumed to be a scalar 
            rather than a list of values.
        unit_factor: Factor by which volumes will be divided to adjust units; 
            defaults to 1.0.
    
    Returns:
        Pandas ``DataFrame`` with volume and density as separate columns for 
        each region, with one line per sample per side. Eg: 
        ```
        Sample, Geno, Side, Vol_01, Dens_01, Vol_02, Dens_02, ...
        0, 0, L, 1.1, 0.3, 1.2, 0.2, ...
        0, 0, R, 0.9, 0.2, 1.1, 0.2, ...
        1, 0, L, 1.0, 0.3, 1.1, 0.3, ...
        ```
    """
    # TODO: no longer used; consider deprecating
    
    header = ["Sample", "Geno", "Side"]
    num_samples = len(groups)
    samples = list(range(num_samples)) * 2
    genos = groups * 2
    sides = ["L"] * num_samples
    sides.extend(["R"] * num_samples)
    vol_dens = []
    for key in volumes_dict.keys():
        # find negative keys based on the given positive key to group them
        if key >= 0:
            header.append("Vol_{}".format(key))
            header.append("Dens_{}".format(key))
            # get volumes in the given unit, which are scalar for 
            # individual image, list if multiple images
            vol_side = np.divide(
                volumes_dict[key][config.VOL_KEY], unit_factor)
            vol_mirrored = np.divide(
                volumes_dict[-1 * key][config.VOL_KEY], unit_factor)
            # calculate densities based on blobs counts and volumes
            blobs_side = volumes_dict[key][config.BLOBS_KEY]
            blobs_mirrored = volumes_dict[-1 * key][config.BLOBS_KEY]
            density_side = np.nan_to_num(np.divide(blobs_side, vol_side))
            density_mirrored = np.nan_to_num(
                np.divide(blobs_mirrored, vol_mirrored))
            
            # concatenate vol/dens from each side into 1d list and interleave 
            # in master list
            vols = vol_side.tolist()
            vols.extend(vol_mirrored.tolist())
            vol_dens.append(vols)
            density = density_side.tolist()
            density.extend(density_mirrored.tolist())
            vol_dens.append(density)
    
    # pool lists and add to Pandas data frame
    volumes_dataset = list(zip(samples, genos, sides, *vol_dens))
    data_frame = pd.DataFrame(data=volumes_dataset, columns=header)
    ext = ".csv"
    if not path.endswith(ext): path += ext
    data_frame.to_csv(path, index=False)
    print("exported volume data per sample to CSV at {}".format(path))
    return data_frame

def regions_to_pandas(volumes_dict, level, groups=[""], unit_factor=1.0, 
                      condition=None):
    """Export volumes from each sample to Pandas format, with 
    measurements for each region on a separate line.
    
    Args:
        volumes_dict: Dictionary of volumes as generated by 
            :func:``register.volumes_by_id`` or 
            :func:``register.group_volumes``, including values from 
            individual or grouped experiments, respectively.
        level: Ontology level at which to show volumes and densities.
        path: Path to output CSV file. If the filename does not end with .csv, 
            this extension will be appended.
        groups: List of groupings for each experiment. List length should be 
            equal to the number of values stored in each label's list in 
            ``volumes_dict``. Defaults to a list with an empty string, in 
            which case each label's value will be assumed to be a scalar 
            rather than a list of values.
        unit_factor: Factor by which volumes will be divided to adjust units; 
            defaults to 1.0.
        condition: Single condition string for all samples; defaults to None, 
            in which case an empty string will be used.
    
    Returns:
        Pandas ``DataFrame`` with regional measurements given as one region 
        per line.
    """
    if condition is None:
        condition = ""
    header = [
        "Sample", "Geno", "Side", "Condition", "Region", "Level", "Volume", 
        "Density", "Nuclei", "VarNuclei", "VarIntensity"]
    num_samples = len(groups)
    #data = {k: [] for k in header} # retains order for Python 3.6 but not <
    data = OrderedDict()
    for h in header:
        data[h] = []
    for key in volumes_dict.keys():
        # find negative keys based on the given positive key to group them
        if key >= 0:
            
            # concatenate vol/dens from each side into 1d list
            data[header[0]].extend(list(range(num_samples)) * 2)
            data[header[1]].extend(groups * 2)
            data[header[2]].extend(["L"] * num_samples)
            data[header[2]].extend(["R"] * num_samples)
            data[header[3]].extend([condition] * num_samples * 2)
            data[header[4]].extend([key] * num_samples * 2)
            data[header[5]].extend([level] * num_samples * 2)
            n = 6
            
            for key_signed in (key, -1 * key):
                # gather metrics, which are scalar for individual images, 
                # list for multiple (grouped) images
                
                # convert volumes to the given unit and use to calc density
                vol = np.divide(
                    volumes_dict[key_signed][config.VOL_KEY], unit_factor)
                blobs = volumes_dict[key_signed][config.BLOBS_KEY]
                density = np.nan_to_num(np.divide(blobs, vol))
                data[header[n]].extend(vol.tolist())
                data[header[n + 1]].extend(density.tolist())
                data[header[n + 2]].extend(blobs)
                data[header[n + 3]].extend(
                    volumes_dict[key_signed][config.VARIATION_BLOBS_KEY])
                data[header[n + 4]].extend(
                    volumes_dict[key_signed][config.VARIATION_EXP_KEY])
            
    # pool lists and add to Pandas data frame
    data_frame = pd.DataFrame(data=data, columns=header)
    return data_frame

def exps_by_regions(path, filter_zeros=True, sample_delim="-"):
    """Transform volumes by regions data frame to experiments-condition 
    as columns and regions as rows.
    
    Multiple measurements for each experiment-condition combination such 
    measurements from separate sides of each sample will 
    be summed. A separate data frame will be generated for each 
    measurement.
    
    Args:
        path: Path to data frame generated from :func:``regions_to_pandas`` 
            or an aggregate of these data frames.
        filter_zero: True to remove rows that contain only zeros.
        sample_delim: Split samples column by this delimiter, taking only 
            the first split element. Defaults to "-"; if None, will 
            not split the samples.
    
    Returns:
        Dictionary of transformed dataframes with measurements as keys.
    """
    df = pd.read_csv(path)
    measurements = ("Volume", "Nuclei") # raw measurements
    
    # combine sample name with condition
    samples = df["Sample"]
    if sample_delim is not None:
        # use truncated sample names, eg for sample ID
        samples = samples.str.split(sample_delim, n=1).str[0]
    df["SampleCond"] = df["Condition"] + "_" + samples
    
    dfs = {}
    for meas in measurements:
        # combines values from each side by summing
        df_pivoted = df.pivot_table(
            values=meas, index=["Region"], columns=["SampleCond"], 
            aggfunc=np.sum)
        if filter_zeros:
            # remove rows that contain all zeros and replace remaining zeros 
            # with NaNs since 0 is used for volumes that could not be found, 
            # not necessarily those without any nuclei
            df_pivoted = df_pivoted[(df_pivoted != 0).any(axis=1)]
            df_pivoted[df_pivoted == 0] = np.nan
        dfs[meas] = df_pivoted
    
    # calculate densities directly from values since simple averaging of 
    # density columns would not weight appropriately
    df_dens = dfs[measurements[1]] / dfs[measurements[0]]
    dfs["Dens"] = df_dens
    base_path = os.path.splitext(path)[0]
    
    # export data frames to separate files
    for key in dfs.keys():
        df_pivoted = dfs[key]
        print("df_{}:\n{}".format(key, df_pivoted))
        df_path = "{}_{}.csv".format(base_path, key)
        df_pivoted.to_csv(df_path, na_rep="NaN")
    return dfs

def dict_to_data_frame(dict_import, path=None, sort_cols=None, show=False):
    """Import dictionary to data frame, with option to export to CSV.
    
    Args:
        dict_import: Dictionary to import. If dictionary keys are enums, 
            their names will be used instead to shorten column names.
        path: Output path to export data frame to CSV file; defaults to 
            None for no export.
        sort_cols: Column as a string of list of columns by which to sort; 
            defaults to None for no sorting.
        show: True to print the data frame; defaults to False.
    
    Returns:
        The imported data frame.
    """
    df = pd.DataFrame(dict_import)
    
    keys = dict_import.keys()
    if len(keys) > 0 and isinstance(next(iter(keys)), Enum):
        # convert enum keys to names of enums
        cols = {}
        for key in keys: cols[key] = key.value
        df.rename(dict_import, columns=cols, inplace=True)
    
    if sort_cols is not None:
        df = df.sort_values(sort_cols)
    
    if show:
        print(df.to_csv(sep="\t", index=False, na_rep="NaN"))
    
    if path:
        # backup and export to CSV
        lib_clrbrain.backup_file(path)
        df.to_csv(path, index=False, na_rep="NaN")
        print("data frame saved to {}".format(path))
    return df

def data_frames_to_csv(data_frames, path, sort_cols=None):
    """Combine and export multiple data frames to CSV file.
    
    Args:
        data_frames: List of data frames to concatenate.
        path: Output path.
        sort_cols: Column as a string of list of columns by which to sort; 
            defaults to None for no sorting.
    
    Returns:
        The combined data frame.
    """
    ext = ".csv"
    if not path.endswith(ext): path += ext
    combined = pd.concat(data_frames)
    if sort_cols is not None:
        combined = combined.sort_values(sort_cols)
    lib_clrbrain.backup_file(path)
    combined.to_csv(path, index=False, na_rep="NaN")
    print("exported volume data per sample to CSV file: \"{}\"".format(path))
    return combined

def merge_csvs(in_paths, out_path):
    """Combine and export multiple CSV files to a single CSV file.
    
    Args:
        in_paths: List of paths to CSV files to import as data frames 
            and concatenate.
        path: Output path.
    """
    dfs = [pd.read_csv(path) for path in in_paths]
    data_frames_to_csv(dfs, out_path)

if __name__ == "__main__":
    print("Starting Clrbrain stats...")
    from clrbrain import cli
    cli.main(True)
    
    # process stats based on command-line argument
    
    if config.stats_type == config.STATS_TYPES[0]:
        # merge multiple CSV files into single CSV file
        merge_csvs(config.filenames, config.prefix)
    
    elif config.stats_type == config.STATS_TYPES[1]:
        # convert volume stats data frame to experiments by region
        exps_by_regions(config.filename)
