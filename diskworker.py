#!/usr/bin/env python
import sys
from rq import Queue, Connection, Worker

# Preload libraries
from time import sleep

# Provide queue names to listen to as arguments to this script,
# similar to rqworker
with Connection():
    qs = map(rq.Queue, sys.argv[1:]) or [rq.Queue()]

    w = rq.Worker(qs)
    sleep(1)
    w.work()
