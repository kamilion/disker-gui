#!/bin/bash
## This shellscript is executed by a rqworker to fork off a long running task and return immediately.
## It is assumed this task can communicate with the database and keep up to date status by itself.

LOG_DIR="/var/log/diskaction/"
MY_DIR="/home/git/disker-gui/"
MY_TASK="diskaction.py -f"

########################################################################################################################

# Make sure we're in the right current directory so the executable can find it's imports.
cd ${MY_DIR}

# Make sure we have somewhere to log
mkdir -p ${LOG_DIR}

# Generate a unique filename-friendly timestamp
dt=$(date --utc +%FT%H%M%SZ)

LOG_FILE="${LOG_DIR}${dt}.trigger.log"

## Completely detach from the file descriptors.
## Shamelessly stolen from http://stackoverflow.com/a/20564208
# Close STDOUT file descriptor
exec 1<&-
# Close STDERR FD
exec 2<&-
# Open STDOUT as ${LOG_FILE} file for read and write.
exec 1<>${LOG_FILE}
# Redirect STDERR to STDOUT ( The ${LOG_FILE} )
exec 2>&1
# Further echos now only appear in the ${LOG_FILE} and no output will be returned to our parent process.

echo "Starting " "${MY_TASK}" "${@}"

# NOHangUP a task with arguments, redirect it's stdout and stderr
nohup python -u ${MY_DIR}${MY_TASK} "${@}" > ${LOG_DIR}${dt}.out.log 2>&1 < /dev/null &

echo "Forked " "${MY_TASK}" "${@}"