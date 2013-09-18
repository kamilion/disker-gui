#!/usr/bin/env python
import sys
import rq
from rq import Queue, Connection, Worker

# Preload libraries
from my_module import count_words_at_url

# Provide queue names to listen to as arguments to this script,
# similar to rqworker
with Connection():
    qs = map(rq.Queue, sys.argv[1:]) or [rq.Queue()]

    w = rq.Worker(qs)
    w.work()