
def get_disk_throughput_ugly(device):
    raw_device = "if={}".format(device)
    output = sh.dd(raw_device,"of=/dev/zero","bs=1M", _err_to_out=True)
    throughput = 0
    unit = ""
    for line in output.split('\n'):
        s = re.search(' copied,.*, (\S+) (\S+)$', line)
        if s:
            throughput = s.group(1)
            unit = s.group(2)
            break
    return "{} {}".format(throughput, unit)



# Debugging stuff

import requests

from time import sleep

def count_words_at_url(url):
    resp = requests.get(url)
    return len(resp.text.split())

def do_nothing():
    return None

def do_something():
    toolresult = sh.echo("Hello World")
    sleep(0.3)
    return "{}".format(toolresult)

def do_something_else(that):
    toolresult = sh.echo(that)
    sleep(0.3)
    return "{}".format(toolresult)

def do_something_new(that):
    toolresult = sh.echo(that)
    sleep(0.3)
    return "{}".format(toolresult)
