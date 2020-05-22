#!/bin/bash
# Sets up the MagellanMapper environment
# Author: David Young 2017, 2020

HELP="
Sets up the initial MagellanMapper environment with Anaconda and all
packages including git repositories.

Downloads and installs Miniconda3 if it is not already present. 
Installs or updates a Conda environment named \"clr\" by 
default in a standard graphical setup or \"clrclu\" for a 
lightweight setup.

Although this installation generally makes use of Conda 
packages, Pip packages are occasionally used instead if the 
package or necessary version is unavailable in Conda. In some 
cases, dependencies that have required updates that are not yet 
fully released but available on Git, in which case shallow Git 
clones will be downloaded and installed through Pip.

Arguments:
  -h: Show help and exit.
  -n [name]: Set the Conda environment name; defaults to CONDA_ENV.
  -s [spec]: Specify the environment specification file; defaults to 
    ENV_CONFIG.
"

# default Conda environment names as found in .yml configs
CONDA_ENV="mag"
env_name="$CONDA_ENV"

# default .yml files
ENV_CONFIG="environment.yml"
config="$ENV_CONFIG"

OPTIND=1
while getopts hn:s: opt; do
  case $opt in
    h)
      echo "$HELP"
      exit 0
      ;;
    n)
      env_name="$OPTARG"
      echo "Set to create the Conda environment $env_name"
      ;;
    s)
      config="$OPTARG"
      echo "Set the environment spec file to $config"
      ;;
    :)
      echo "Option -$OPTARG requires an argument"
      exit 1
      ;;
    *)
      echo "$HELP" >&2
      exit 1
      ;;
  esac
done

# run from script directory
BASE_DIR="$(dirname "$0")/.."
cd "$BASE_DIR" || { echo "Unable to find folder $BASE_DIR, exiting"; exit 1; }
BASE_DIR="$PWD"

# load dependencies
source bin/libmag.sh

# find platform for Anaconda
detect_platform
ext="sh"
if [[ "$os" = "Windows" ]]; then
  ext="ext"
fi

# check for Anaconda installation and download/install if not found
install_conda=""
if ! command -v "conda" &> /dev/null; then
  echo "\"conda\" command from Anaconda/Miniconda not found"
  read -p "Download and install Miniconda (y/n)? " install_conda
  case "${install_conda:0:1}" in
    y|Y )
      echo "Downloading and installing Miniconda..."
    ;;
    * )
      echo "Will not install Miniconda, exiting"
      exit 1
    ;;
  esac
  
  # download Miniconda for OS platform and bit
  PLATFORM="$os-$bit"
  MINICONDA="Miniconda3-latest-$PLATFORM.${ext}"
  CONDA_URL=https://repo.anaconda.com/miniconda/$MINICONDA
  if [[ "$os" == "MacOSX" ]]; then
    curl -O "$CONDA_URL"
  else
    wget "$CONDA_URL"
  fi
  
  # install Miniconda and initialize
  conda_path="$HOME/miniconda3"
  msg="\nDownloaded Miniconda, installing to $conda_path..."
  echo -e "$msg"
  chmod 755 "$MINICONDA"
  ./"$MINICONDA" -b -p "$conda_path"
  eval "$("$conda_path"/bin/conda shell.bash hook)"
  conda init
  conda config --set auto_activate_base false
fi

# create or update Conda environment; warn of apparent hang since no 
# progress monitor displays during installs by environment spec
check_env="$(conda env list | grep -w "$env_name")"
msg="Installing dependencies (may take awhile and appear to hang after the"
msg+="\n  \"Executing transaction\" step because of additional "
msg+="downloads/installs)..."
eval "$(conda shell.bash hook)"
if [[ "$check_env" == "" ]]; then
  # create an new environment
  echo "Creating new Conda environment from $config..."
  echo -e "$msg"
  conda env create -n "$env_name" -f "$config"
else
  # update an existing environment
  echo "$env_name already exists, will update"
  conda activate "$env_name"
  echo -e "$msg"
  conda env update -f "$config"
fi

# check that the environment was created and activate it
echo "Checking and activating conda environment..."
check_env="$(conda env list | grep -w "$env_name")"
if [[ "$check_env" == "" ]]; then
  echo "$env_name could not be found, exiting."
  exit 1
fi

open_shell=""
if [[ "$install_conda" != "" ]]; then
  open_shell="open a new terminal and "
fi
msg="MagellanMapper environment setup complete!\n"
msg+="\n** Please ${open_shell}run \"conda activate $env_name\""
msg+="\n   (or \"source activate $env_name\" in some setups) to enter"
msg+="\n   the MagellanMapper environment **"
echo -e "$msg"
