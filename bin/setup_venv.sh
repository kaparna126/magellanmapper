#!/bin/bash
# Sets up the MagellanMapper environment using venv
# Author: David Young 2019

HELP="
Sets up the initial MagellanMapper environment using the built-in
venv environment manager.

Arguments:
  -h: Show help and exit.
  -e [path]: Path to folder where the new venv directory will be placed. 
    Defaults to \"../venvs\".
  -n [name]: Set the virtual environment name; defaults to CLR_ENV.
"

CLR_ENV="mag"
env_name="$CLR_ENV"
venv_dir="../venvs"

OPTIND=1
while getopts hn:e: opt; do
  case $opt in
    h)
      echo "$HELP"
      exit 0
      ;;
    n)
      env_name="$OPTARG"
      echo "Set to create the venv environment $env_name"
      ;;
    e)
      venv_dir="$OPTARG"
      echo "Set the venv directory to $venv_dir"
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

# run from script's parent directory
BASE_DIR="$(dirname "$0")/.."
cd "$BASE_DIR" || { echo "Unable to find folder $BASE_DIR, exiting"; exit 1; }
BASE_DIR="$PWD"

# load dependencies
source bin/libmag.sh

# find platform for Anaconda
detect_platform
ext="sh"
if [[ "$OS_NAME" = "Windows" ]]; then
  ext="ext"
fi

# check for Python availability and version requirement
py_ver_majmin="" # found Python version in x.y format
py_ver_min=(3 6) # minimum supported Python version
py_vers=(3.6 3.7 3.8) # range of versions currently supported
py_vers_prebuilt_deps=(3.6) # vers for which custom prebuilt deps are avail
for ver in "${py_vers[@]}"; do
  # prioritize specific versions in case "python" points to lower version
  if command -v "python$ver" &> /dev/null; then
    python=python$ver
    py_ver_majmin="$ver"
    break
  fi
done
if [[ -z "$python" ]]; then
  # fallback to checking version number output by "python"
  if command -v python &> /dev/null; then
    if check_python python "${py_ver_min[@]}"; then
      python=python
      py_ver_majmin="$PY_VER"
    fi
  fi
  if [[ -z "$python" ]]; then
    echo "Please install Python >= version ${py_ver_min[0]}.${py_ver_min[1]}"
    exit 1
  fi
fi
echo "Found $python"

# Compiler and Java dependency checks
check_java # assume if java is not available, javac is not either
warn_prebuilt=true
for ver in "${py_vers_prebuilt_deps[@]}"; do
  if [[ "$ver" = "$py_ver_majmin" ]]; then
    warn_prebuilt=false
    break
  fi
done
if $warn_prebuilt; then
  # custom precompiled dependencies may not be available, in which case
  # compilers are required
  check_clt
  check_gcc
  #check_git # only necessary if deps req git
fi

# create new virtual environment
env_path="${venv_dir}/${env_name}"
if [[ -e "$env_path" ]]; then
  # prevent environment directory conflict
  echo "$env_path already exists. Please give a different venv directory name."
  exit 1
fi
if [[ ! -d "$venv_dir" ]]; then
  # create directory structure to hold new environment folder
  mkdir -p "$venv_dir"
fi
"$python" -m venv "$env_path"
env_act="${env_path}/bin/activate"
if [[ ! -e "$env_act" ]]; then
  # env generated in Windows does not contain bin folder; will need to 
  # change line endings if running in Cygwin (works as-is in MSYS2)
  env_act="${env_path}/Scripts/activate"
  if [[ ! -e "$env_act" ]]; then
    # check to ensure that the environment was actually created
    echo "Could not create new venv environment at $env_path"
    exit 1
  fi
fi
source "$env_act"

# update pip and install MagellanMapper including required dependencies
"$python" -m pip install -U pip
pip install -e .[all] --extra-index-url https://pypi.fury.io/dd8/

echo "MagellanMapper environment setup complete!"
echo "** Please run \"source $env_act\" to enter your new environment **"
