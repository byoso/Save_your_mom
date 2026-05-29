#! /bin/bash

# call pre_uninstall.py with absolute path
python3 "$(dirname "$(realpath "$0")")/pre_uninstall.py"