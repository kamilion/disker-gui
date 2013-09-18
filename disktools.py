
# System imports
import os, string, sh, re

# RethinkDB imports
import rethinkdb as r
conn = r.connect(db='wanwipe')

### Remote commands

def broken_mirror(device):
    raise Filesystem.GenericError("A Million Shades of Light")
    return None


def get_disk_info(device):
    # Insert Data
    inserted = r.table('disk_results').insert({'serial': get_disk_sdinfo(device), 'throughput': get_disk_throughput(device)}).run(conn)
    return inserted['generated_keys'][0]

def get_disk_sdinfo(device):
    vendor = ""
    model = ""
    for line in sh.sdparm("-i", device, _err_to_out=True, _ok_code=[0,2,3,5,9,11,33,97,98,99]):
        needle = '    {}: (\S+)\s+(\S+.*)$'.format(device)
        s = re.search(needle, line)
        if s:
            vendor = s.group(1)
            model = s.group(2)
            break
    return "{} {}".format(vendor, model)


def get_disk_throughput(device):
    throughput = 0
    unit = ""
    for line in sh.dd("if={}".format(device),"of=/dev/zero","bs=1M", "count=1000", _err_to_out=True):
        s = re.search(' copied,.*, (\S+) (\S+)$', line)
        if s:
            throughput = s.group(1)
            unit = s.group(2)
            break
    return "{} {}".format(throughput, unit)

smart_values = {}

def read_values(device):
    num_exit_status=0
    #try:
    print('Reading S.M.A.R.T values for '+device)
    #os.putenv('LC_ALL','C')
    smart_output=sh.smartctl('-a','-A', '-i', device, _err_to_out=True, _ok_code=[0,1,2,3,4,5,6,7,8,9,10,11,12,64])
    read_values=0
    print(smart_output)
    for l in smart_output:
        print('parsing: '+l)
        if l[:-1] == '':
            read_values = 0
            print('found empty line')
        elif l[:13]=='Device Model:' or l[:7]=='Device:':
            print('found a model description')
            model_list = string.split(string.split(l,':')[1])
            try: model_list.remove('Version')
            except: None
            model = string.join(model_list)
            print('captured a model description: {}'.format(model))
        elif l[:14]=='Serial Number:' or l[:6]=='Serial':
            print('found a serial number')
            serial_list = string.split(string.split(l,':')[1])
            serial_no = string.join(serial_list)
            print('captured a serial number: {}'.format(serial_no))
        if read_values == 1:
            smart_attribute=string.split(l)
            smart_values[string.replace(smart_attribute[1],'-','_')] = {"value":smart_attribute[3],"threshold":smart_attribute[5]}
            print('found a smart attribute')
        elif l[:18] == "ID# ATTRIBUTE_NAME":
            # Start reading the Attributes block
            read_values = 1
            print('# Start reading the Attributes block')
    exit_status = smart_output.exit_code
    if exit_status != None:
        # smartctl exit code is a bitmask, check man page.
        print(exit_status)
        num_exit_status = int(exit_status/256)
        print(num_exit_status)
        if num_exit_status <= 2:
            print('smartctl cannot access S.M.A.R.T values on drive '+device+'. Command exited with code '+str(num_exit_status)+' ('+str(exit_status/256)+')')
        else:
            print('smartctl exited with code '+str(num_exit_status)+'. '+device+' may be FAILING RIGHT NOW !')
    #except:
    #    print('Cannot access S.M.A.R.T values ! Check user rights or proper smartmontools installation. Quitting...')

    if smart_values == {}:
        print('Can\'t find any S.M.A.R.T value to plot ! Quitting...')

    smart_values["smartctl_exit_status"] = { "value":str(num_exit_status), "threshold":"1" }

    # For some reason we may have no value for "model"
    try:
        smart_values["model"] = model
    except:
        smart_values["model"] = "unknown"


    print(smart_values)

    return "Done"
