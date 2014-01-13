#!/bin/bash
# Make sure we're in the right directory.
cd /home/git/disker-gui/
echo "Starting diskaction.py -f" "${@}"
# -n will disable the password prompt, -s will create a shelled session.
sudo -ns /home/git/disker-gui/diskaction.py -f "${@}" &
echo "Backgrounded diskaction.py"
