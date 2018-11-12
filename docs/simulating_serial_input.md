# Simulating Serial Input  
© 2018 David Pablo Cohn


See [OpenRVDAS Introduction to Loggers](intro_to_loggers.md) for system
overview.

It can be very useful, during development or testing, to run using saved
log files as synthetic input, and some sample synthetic data are
included in the test/ subdirectory for that purpose. For systems that
expect their data to arrive via UDP, simulation can be set up using the
listen.py script to connect a LogfileReader to a NetworkWriter, e.g.

```
logger/listener/listen.py \
    --logfile test/nmea/NBP1700/gyr1/raw/NBP1700_gyr1-2017-11-04 \
    --transform_timestamp \
    --transform_prefix gyr1 \
    --write_network :6224
```
Simulating a system that uses serial ports for its input is more
involved. We provide a rudimentary serial port simulation in
`logger/utils/simulate_serial.py`. The file defines a SimSerial class and a
command line script that invokes it:

```
logger/utils/simulate_serial.py \
    --port /dev/ttyr15 \
    --logfile test/nmea/NBP1700/gyr1/raw/NBP1700_gyr1-2017-11-04 \
    --loop
```
tries to create virtual serial port /dev/ttyr15 and feeds it with data
from the specified logfile, timing the records to arrive at the same
intervals indicated between timestamps in the logfile.

Note that if you wish to actually create virtual serial ports in /dev
(perhaps corresponding to some port.tab definition), you will need to
run the script as root, and if those ports actually exist, the script
*WILL WIPE THEM OUT.*

Because of this, it is recommended that you specify a different location
for your simulated ports, such as /tmp/ttyr15, etc.

To simplify the creation/testing, simulate\_serial.py can also take a
JSON-format[^1] configuration file such as the one in
test/serial\_sim.json, specifying a complete set of virtual serial
port-log file pairings:

```
logger/utils/simulate_serial.py --config test/serial_sim.json --loop
```
[^1]: Throughout the system, we use a slightly expanded form of JSON
    that allows Javascript-style "//-prefixed" comments for
    readability. The code for stripping comments and reading in this
    format is in utils/read\_json.py
