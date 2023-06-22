#!/usr/bin/env python3

"""
    pty_hack.py

    So I call it a hack, and it really needs some serious code
    cleanup, but it's a pretty decent data simulator.  Uses
    pty pairs (totally portable) instead of `socat`, and synchronizes
    the data from the data files based on their timestamps so that sensors
    that output 5 times a second still have their data line up
    (chronologically) with sensors that only output once every 2 minutes.

    Lining up data like this can be important for observing things like
    how changes in wind correlate with pCO2 concentrations.
"""

import argparse
import datetime
import glob
import grp
# import logging
import os
import pty
import pwd
import re
import setproctitle
# import sys
import threading
import time
import yaml

# FIXME: at exit, if we had to create the ports_dir, remove it
#        either way, remove all the symlinks we created.


class Simulator:
    def init():
        pass


global config
config = {}


def drop_privs(uid_name='rvdas', gid_name='rvdas'):
    """
    On my laptop at home, I don't have MOXA drivers (and thus don't have a
    bunch of serial ports).  But I can run this script with the sim.conf
    tweaked to simulate the ship serial ports so the actual ship cruise
    config can be used to simulate data.  Handy, but a hack.  Only problem
    is that to create symlinks in the /dev directory, you need privs.
    I suppose the right way to do this is to acquire CAP_FOWNER via
    a setcap(8) wrapper, but
    A) That's a lot of work,
    B) Most people understand how that works... NOT, and
    C) I don't think that's portable to Darwin.

    To actually get the UDP stuff in an un-edited ship's cruise config
    file to work (in LMG's case, sent to 157.132.133.255) I'll have to
    do a little sysctl and iptables voodoo.  When that's worked out, 
    it can get shared with the class.
    """

    if os.getuid() != 0:
        # We're not root so, like, whatever dude
        return

    username = config.get('user', uid_name)
    grpname = config.get('group', gid_name)
    # Get the uid/gid from the name
    running_uid = pwd.getpwnam(username).pw_uid
    running_gid = grp.getgrnam(grpname).gr_gid

    # Remove group privileges
    os.setgroups([])

    # Try setting the new uid/gid
    os.setgid(running_gid)
    os.setuid(running_uid)

    # Ensure a very conservative umask
    os.umask(0o077)


def create_ptys(config):
    """
    Since we don't have any control over what file descriptors or device
    paths get created when we create a pty pair, we create symlinks between
    the pty slave and the device we actually want.  That way we have the
    illusion of complete control over the device path we want to use.
    """

    pty_pairs = {}
    ports_dir = config.get('ports_dir', None)
    sims = config.get('Simulate', None)

    username = config.get('user', 'rvdas')
    use_uid = pwd.getpwnam(username).pw_uid
    groupname = config.get('group', 'rvdas')
    use_gid = grp.getgrnam(groupname).gr_gid

    # Create ports_dir if necessary.  And remember if it was necessary.
    if not os.path.exists(ports_dir):
        os.makedirs(ports_dir)
        os.chown(ports_dir, use_uid, use_gid)
        # So we can (eventually) clean it when we want to quit
        config['made_ports_dir'] = True

    for key in sims:
        sim_logger = sims[key]
        # Port is in config because we sanity checked.
        port = sim_logger.get('port', None)
        (master, slave) = pty.openpty()
        symlink = os.path.join(ports_dir, port)
        try:
            os.remove(symlink)
        except FileNotFoundError:
            pass
        os.symlink(os.ttyname(slave), symlink)
        os.chmod(symlink, 0o777)
        # try:  # Try setting the new uid/gid
        #    os.chown(os.ttyname(slave), use_uid, use_gid)
        # except OSError:
        #    pass  # Whatever, dude

        pair = {
            'master': master,
            'slave': slave
        }
        pty_pairs[key] = pair

    return pty_pairs


# FIXME:  Pass stop event and key.  I mean, we have that big
#         dict with all our information....
def reader_thread(stop_event, key):
    """ Read from file (derived from patten) and direct it to (fake) serial
        port "port".  Keep playing until EOF or the stop event is raised
        We use the first datafile that matches the pattern.  May or may
        not be exactly what we want.  Maybe we'll add a date option, and
        maybe we'll extend this to keep simulating over midnight boundaries.
        But probably not.
    """

    def sleep_until(when, ts_delta):
        """ Sleep until the (adjusted) timestamp is reached """
        while True:
            now = time.time() - ts_delta
            diff = when - now
            if (diff <= 0):
                break
            if stop_event.is_set():
                break
            stop_event.wait(diff/2)

    # Unfortunately there's a bit of setup for this.
    # Get file pattern from config
    pattern = config['Simulate'][key]['pattern']
    # Get pty master from config
    port = config['ptys'][key]['master']
    sport = open(port, 'w')
    # Set up regex for <iso8601> <data string>
    re_iso8601 = r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.?\d*)Z?\s+(.*)$'
    re_logged_data = re.compile(re_iso8601)
    # Open first matching data file
    datafile = glob.glob(os.path.join(config['data_dir'], pattern))[0]
    # Set process name for monitoring purposes
    setproctitle.setthreadtitle("Simulated: %s" % key)
    # Get timestamp delta between now and the first data item
    # FIXME:  We can move this calc to get_start_times and do it only once.
    dt = config.get('start_time', 0)
    ts_delta = time.time() - dt

    # And finally, (read;sleep;write)*
    f = open(datafile, 'r')
    for line in f:
        if stop_event.is_set():
            print("Reader for %s received stop signal" % pattern)
            break
        m = re.match(re_logged_data, line)
        if not m:
            # log no recex match
            continue
        isotime = m.group(1)
        data_to_send = m.group(2)
        ts = datetime.datetime.fromisoformat(isotime).timestamp()
        sleep_until(ts, ts_delta)
        print("%s: %s" % (key, data_to_send))
        sport.write(data_to_send)
        sport.write('\n')   # Toss in an EOL, 'for line' stripped it.

    sport.close()
    f.close()


def get_start_time():
    """
        To synchronize the data from all the provided files. we need to find
        the chronologically earliest piece of data.  This is how we do
        that.

        Once again, I'll mention I find it ironic that 'fromisoformat'
        will not actually process our compliant iso8601 string.  Turns out
        the function only exists as a complement to .isoformat(), not as
        a fully functional parser of iso8601 compliant date-time strings.
    """

    # This matches the LMG's timestrings.  I forget if this is configable
    stimes = []
    sims = config.get('Simulate', None)
    data_dir = config.get('data_dir', None)
    dead_keys = []
    for key in sims:
        logger = sims[key]
        pattern = logger.get('pattern', '*%s*' % key)
        files = glob.glob(os.path.join(data_dir, pattern))
        if not files:
            print('Key %s has no matching files.  Removing' % key)
            dead_keys.append(key)
            continue
        datafile = files[0]
        f = open(datafile, 'r')
        first_line = f.readline()
        f.close()
        start_time = first_line.split(' ')[0]
        stimes.append(start_time)
    for key in dead_keys:
        config['Simulate'].pop(key)
    stimes.sort()
    st = stimes[0]
    st = st[:-1]
    ts = datetime.datetime.fromisoformat(st).timestamp()
    config['start_time'] = ts
    return ts


def start_reader_threads(our_pty_pairs):
    sims = config.get('Simulate', None)
    my_threads = {}
    stop_event = threading.Event()
    config['start_time'] = get_start_time()
    for key in sims:
        print("starting sim for %s" % key)
        t = threading.Thread(target=reader_thread,
                             args=(stop_event, key))
        # log('starting whatver')
        t.start()
        my_threads[key] = t
    config['threads'] = my_threads
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_event.set()

    for t in my_threads:
        my_threads[t].join()


def do_main():
    our_pty_pairs = create_ptys(config)
    config['ptys'] = our_pty_pairs
    drop_privs()
    start_reader_threads(our_pty_pairs)
    pass


# 'configr' needs to be global so at_exit can see it.
# That or we make this a class.
if __name__ == "__main__":
    setproctitle.setproctitle("Simulated data pump")
    # Would be nice to make the thing a class, so everyone can play.
    parser = argparse.ArgumentParser(
                 prog='Data Sim',
                 description='Sends data to virtual serial ports')
    parser.add_argument('-c', '-config',
                        action='store',
                        help="Configuration file")
    args = parser.parse_args()
    # FIXME:  args.c or die.  Can argparse do this for us ?
    if not args.c:
        raise ValueError("You need a config file:  -c <config>")
    f = open(str(args.c), 'r')
    config = yaml.load(f, Loader=yaml.FullLoader)

    # Sanity checks, since everything relies on the config dict.
    data_dir = config.get('data_dir', None)
    if not data_dir:
        raise ValueError("No data_dir in config file")
    sims = config.get('Simulate', None)
    if not sims:
        raise ValueError("No 'Simulate' in config file")
    ports_dir = config.get('ports_dir', None)
    if not ports_dir:
        raise ValueError('No "ports_dir" in config file')
    for key in sims:
        sim_logger = sims[key]
        port = sim_logger.get('port', None)
        if not port:
            raise ValueError('No port for simulated %s' % key)
    do_main()
    # log (all done)

"""
# A way to immediately realize we caught a quit signal
from threading import Event

exit = Event()

def main():
    while not exit.is_set():
      do_my_thing()
      exit.wait(60)

    print("All done!")
    # perform any cleanup here

def quit(signo, _frame):
    print("Interrupted by %d, shutting down" % signo)
    exit.set()

if __name__ == '__main__':

    import signal
    for sig in ('TERM', 'HUP', 'INT'):
        signal.signal(getattr(signal, 'SIG'+sig), quit);

    main()
"""
