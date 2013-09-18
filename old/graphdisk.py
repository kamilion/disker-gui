#!/usr/bin/env python

import sys
import commands
import re
import csv
from optparse import OptionParser

def get_disk_throughput(device, blocksize):
    blocksize = str(blocksize) + 'k'
    #cmd = "dd if=/dev/zero of=%s bs=%s" % (device, blocksize)  # Write Test
    cmd = "dd if=%s of=/dev/zero bs=%s" % (device, blocksize)  # Read Test
    output = commands.getoutput(cmd)
    throughput = 0
    unit = ""
    for line in output.split('\n'):
        s = re.search(' copied,.*, (\S+) (\S+)$', line)
        if s:
            throughput = s.group(1)
            unit = s.group(2)
            break
    return (throughput, unit)

if __name__ == "__main__":

    usage = "usage: %prog options"
    parser = OptionParser(usage=usage)
    parser.add_option("-d", "--device", dest="device",
            help="Disk device to operate on (NOTE: any data on that device will be lost)")
    (options, args) = parser.parse_args()
    device = options.device
    if not device:
        parser.print_help()
        sys.exit(1)

    try:
        f = open('disk_throughput.csv', 'w')
        writer = csv.writer(f)
        writer.writerow( ('Block size (KB)', 'Throughput') )
        blocksizes = [128, 256, 512, 1024]
        gchart_url = "http://chart.apis.google.com/chart?"
        gchart_type = "cht=bvs"
        gchart_title = "&chtt=Disk%20throughput"
        gchart_size = "&chs=400x250"
        gchart_axis_labels = "&chxt=x,y"
        gchart_data = "&chd=t:"
        gchart_labels = "&chl="
        max_t = 0.0
        for blocksize in blocksizes:
            (t, u) = get_disk_throughput(device, blocksize)
            if float(t) > max_t:
                max_t = float(t)
            writer.writerow( (blocksize, t) )
            print 'Block Size: %sk Throughput: %s %s' % (blocksize, t, u)
            gchart_data += t + ","
            gchart_labels += str(blocksize) + "k" + "|"
        gchart_data = gchart_data.rstrip(',')
        gchart_labels = gchart_labels.rstrip('|')
        gchart_axis_range = "&chxr=1,0," + str(max_t+10.0)
        gchart_scaling = "&chds=0," + str(max_t+10.0)
        gchart_url += gchart_type + gchart_title + gchart_size + gchart_data + gchart_labels
        gchart_url += gchart_axis_labels + gchart_axis_range + gchart_scaling
        print "Google Chart URL (just paste in a browser):", gchart_url
    finally:
        f.close()
