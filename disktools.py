# RQ Worker functions
# These are called by rqworker, and so there is no held state.
# Beware; new workhorses are immediately forked and never reused!


# System imports
import string
import sh
import re

# RethinkDB imports
from datetime import datetime
import rethinkdb as r
from rethinkdb.errors import RqlRuntimeError, RqlDriverError

from diskerbasedb import connect_db, find_machine_state, verify_db_machine_state, verify_db_table

conn = None
conn = connect_db(conn)

machine_state_uuid = find_machine_state(conn)  # Verifies DB Automatically.
print("LocalDB: DiskTools found a machine state: {}".format(machine_state_uuid))

### Local functions
def verify_db_tables(conn):
    try:
        verify_db_machine_state(conn)
        verify_db_table(conn, 'disk_results')
        verify_db_table(conn, 'job_results')
    except RqlRuntimeError:
        print("LocalDB: wanwipe database verified.")


### Remote commands

#  This will end up in the failed queue
def broken_mirror(device):
    raise NotImplementedError("A Million Shades of Light")


def start_shutdown(hostname):
    verify_db_tables(conn)  # Verify DB and tables exist
    run = sh.Command("/home/git/zurfa-deploy/tools/zurfa-shutdown.sh")
    result = run("all", str(hostname), _bg=True)  # Short circuit, using 'all' as the first param instead of hostname.
    return str(result)


def start_reboot(hostname):
    verify_db_tables(conn)  # Verify DB and tables exist
    run = sh.Command("/home/git/zurfa-deploy/tools/zurfa-reboot.sh")
    result = run("all", str(hostname), _bg=True)  # Short circuit, using 'all' as the first param instead of hostname.
    return str(result)


def start_wipe(device):
    verify_db_tables(conn)  # Verify DB and tables exist
    run = sh.Command("./start_wipe.sh")
    result = run("-d", str(device), _bg=True)
    return str(result)
    #return str(device)


def get_disk_info(device):
    verify_db_tables(conn)  # Verify DB and tables exist
    # Insert Data
    inserted = r.db('wanwipe').table('disk_results').insert({
        'serial': get_disk_sdinfo(device), 'throughput': get_disk_throughput(device),
        'updated_at': r.now()
    }).run(conn)
    return inserted['generated_keys'][0]

# noinspection PyUnresolvedReferences
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


# noinspection PyUnresolvedReferences
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


# noinspection PyUnresolvedReferences
def read_values(device):
    num_exit_status = 0
    disk_record = {}
    smart_values = {}
    #try:
    print('Reading S.M.A.R.T values for '+device)
    # Just accept any return code as a success from smartctl.
    ok_codes = range(255)  #  [0,1,2,3,4,5,6,7,8,9,10,11,12,64,192]
    smart_output = sh.smartctl('-a','-A', '-i', device, _err_to_out=True, _ok_code=ok_codes)
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

    # Begin packing up the disk_record

    if smart_values == {}:
        print("Can't find any S.M.A.R.T value to capture!")
        disk_record["smart_values"] = "Unable to query SMART"
    else:
        print(smart_values)
        disk_record["smart_values"] = smart_values

    disk_record["smartctl_exit_status"] = { "value":str(num_exit_status), "threshold":"1" }

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
    disk_record["created_at"] = r.now()
    disk_record["updated_at"] = r.now()

    verify_db_tables(conn)  # Verify DB and Tables exist
    disk_inserted = r.db('wanwipe').table('disk_results').insert(disk_record).run(conn)
    record_id = disk_inserted['generated_keys'][0]
    print("Inserted disk information as record UUID: {}".format(record_id))
    return record_id

    #return "Done"  # for debugging
