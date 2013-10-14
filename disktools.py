# RQ Worker functions
# These are called by rqworker, and so there is no held state.
# Beware; new workhorses are immediately forked and never reused!


# System imports
import os, string, sh, re, json

# RethinkDB imports
import rethinkdb as r
from rethinkdb.errors import RqlRuntimeError, RqlDriverError
try:
    #conn = r.connect(db='wanwipe')
    conn = r.connect()
except RqlDriverError:
    print("Failed to connect to rethinkdb. Check the daemon status and try again.")

### Local functions
def verify_db_tables():
    try:
        result = r.db_create('wanwipe').run(conn)
        print("DB: wanwipe database created: {}".format(result))
    except RqlRuntimeError:
        print("DB: wanwipe database found.")
    try:
        result = r.db('wanwipe').table_create('disk_results').run(conn)
        print("DB: disk_results table created: {}".format(result))
    except RqlRuntimeError:
        print("DB: disk_results table found.")
    try:
        result = r.db('wanwipe').table_create('job_results').run(conn)
        print("DB: job_results table created: {}".format(result))
    except RqlRuntimeError:
        print("DB: job_results table found.")

### Remote commands

#  This will end up in the failed queue
def broken_mirror(device):
    raise Filesystem.GenericError("A Million Shades of Light")
    return None


def get_disk_info(device):
    verify_db_tables()  # Verify DB and tables exist
    # Insert Data
    inserted = r.db('wanwipe').table('disk_results').insert({'serial': get_disk_sdinfo(device), 'throughput': get_disk_throughput(device)}).run(conn)
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

disk_record = {}
smart_values = {}

def read_values(device):
    num_exit_status=0
    #try:
    print('Reading S.M.A.R.T values for '+device)
    smart_output = sh.smartctl('-a','-A', '-i', device, _err_to_out=True, _ok_code=[0,1,2,3,4,5,6,7,8,9,10,11,12,64])
    read_values = 0
    print(smart_output)
    for l in smart_output:
        print('parsing: '+l)
        if l[:-1] == '':
            read_values = 0
        elif l[:13]=='Device Model:' or l[:7]=='Device:' or l[:8]=='Product:':
            model_list = string.split(string.split(l,':')[1])
            try: model_list.remove('Version')
            except: None
            model = string.join(model_list)
            print('captured a model description: {}'.format(model))
        elif l[:14]=='Serial Number:' or l[:6]=='Serial':
            serial_list = string.split(string.split(l,':')[1])
            serial_no = string.join(serial_list)
            print('captured a serial number: {}'.format(serial_no))
        elif l[:7]=='Vendor:':
            vendor_list = string.split(string.split(l,':')[1])
            vendor = string.join(vendor_list)
            print('captured a vendor name: {}'.format(vendor))
        elif l[:14]=='User Capacity:':
            capacity_list = string.split(string.split(l,':')[1])
            capacity = string.join(capacity_list)
            print('captured a capacity: {}'.format(capacity))
        if read_values == 1:
            smart_attribute=string.split(l)
            smart_values[string.replace(smart_attribute[1],'-','_')] = {"smart_id":smart_attribute[0], "flag":smart_attribute[2], "value":smart_attribute[3], "worst":smart_attribute[4], "threshold":smart_attribute[5], "raw_value":smart_attribute[9]}
            print('captured a smart attribute: {}',format(smart_attribute))
        elif l[:18] == "ID# ATTRIBUTE_NAME":
            # Start reading the Attributes block
            read_values = 1
            print('found the Attributes block')
    exit_status = smart_output.exit_code
    if exit_status is not None:
        # smartctl exit code is a bitmask, check man page.
        print(exit_status)
        num_exit_status = int(exit_status/256)
        print(num_exit_status)
        if num_exit_status <= 2:
            print('smartctl cannot access S.M.A.R.T values on drive '+device+'. Command exited with code '+str(num_exit_status)+' ('+str(exit_status/256)+')')
        else:
            print('smartctl exited with code '+str(num_exit_status)+'. '+device+' may be FAILING RIGHT NOW !')

    if smart_values == {}:
        print("Can't find any S.M.A.R.T value to capture!")

    smart_values["smartctl_exit_status"] = { "value":str(num_exit_status), "threshold":"1" }

    # Begin packing up the disk_record

    # For some reason we may have no value for "smart_values"
    try:
        disk_record["smart_values"] = smart_values
    except:
        disk_record["smart_values"] = "Unable to query SMART"

    print(smart_values)

    # For some reason we may have no value for "model"
    try:
        disk_record["model"] = model
    except:
        disk_record["model"] = "Unknown Model"

    # For some reason we may have no value for "serial"
    try:
        disk_record["serial_no"] = serial_no
    except:
        disk_record["serial_no"] = "Unknown Serial Number"

    # For some reason we may have no value for "vendor"
    try:
        disk_record["vendor"] = vendor
    except:
        disk_record["vendor"] = "Unknown Vendor"

    # For some reason we may have no value for "capacity"
    try:
        disk_record["capacity"] = capacity
    except:
        disk_record["capacity"] = "Unknown Capacity"

    print("Running sdparm query...")
    # For some reason we may have no value for "identifier"
    try:
        sdinfo = get_disk_sdinfo(device)
        print("sdparm result: {}".format(sdinfo))
        disk_record["identifier"] = sdinfo
    except:
        disk_record["identifier"] = "Generic"

    print("Running throughput test...")
    # For some reason we may have no value for "throughput"
    try:
        disk_throughput = get_disk_throughput(device)
        print("throughput result: {}".format(disk_throughput))
        disk_record["throughput"] = disk_throughput
    except:
        disk_record["throughput"] = "Failed"

    disk_record["last_known_as"] = device

    verify_db_tables()  # Verify DB and Tables exist
    disk_inserted = r.db('wanwipe').table('disk_results').insert(disk_record).run(conn)
    record_id = disk_inserted['generated_keys'][0]
    print("Inserted disk information as record UUID: {}".format(record_id))
    return record_id

    #return "Done"  # for debugging
