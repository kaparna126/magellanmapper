#!/usr/bin/env bash
# Sample settings for MagellanMapper tasks
# Author: David Young, 2020

# Copy this file to your own file and update with your own settings.

# choose file paths (relative to magellanmapper directory), channels, etc
PREFIXES=(. ../data) # add additional data folders
BASE=sample # replace with your sample file (without extension)
CHL=1
SERIES=0
ABA_DIR=ABA-CCFv3 # replace with atlas of choice
ABA_SPEC=ontology1.json # replace with atlas label map file

# profiles and theme
MIC=lightsheet # add/replace additional microscope profiles, separated by "_"
REG=finer_abaccfv3 # add/replace register/atlas profiles
THEME=(--theme dark) # GUI theme

# Annotation building
SIZE=1000,100,50 # z: 50-6*2 for ROI, -3*2 for border = 32; x/y: 42-5*2 for border
ROI_OFFSET=50,25,13 # get z from [50 (tot size) - 18 (ROI size)] / 2 - 3 (border)
ROI_SIZE=50,50,18

# offsets for ground truth ROIs within a thin, long sub-image
# - increment each ROI in x by 70 (small gap between each ROI)
# - view in "wide region" layout
OFFSETS=(
  "800,1150,250"
)

# subsets of OFFSETS that have been completed for testing
OFFSETS_DONE=("${OFFSETS[@]:0:20}")
offsets_test=($OFFSET)

# current offset
OFFSET="${OFFSETS[0]}"
