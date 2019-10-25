#! /usr/bin/env python3

import logging
from collections import OrderedDict

VARS = {
  '%UDP_INTERFACE%': '157.132.129.255', # broadcast for nbp-dast-02-t
  '%RAW_UDP%': '6224',
  '%CACHE_UDP%': '6225',
  '%WEBSOCKET%': '8766',
  '%BACK_SECONDS%': '640',
  '%FILEBASE%': '/data/logger'
}

LOGGERS = [
  'adcp',
  'ctdd',
  'eng1',
  'gp02',
  'grv1',
  'gyr1',
  'hdas',
  'knud',
  'mbdp',
  'mwx1',
  'ndfl',
  'pco2',
  'PCOD',
  'pguv',
  'rtmp',
  's330',
  'seap',
  'sp1b',
  'svp1',
  'tsg1',
  'tsg2',

  'bwnc',
  'cwnc',
  'twnc',
  'true_wind',
  'network_timeout'
  ]

LOGGER_TIMEOUTS = {
  'adcp': 10,
  'ctdd': 10,
  'eng1': 10,
  'gp02': 10,
  'grv1': 10,
  'gyr1': 10,
  'hdas': 10,
  'knud': 10,
  'mbdp': 10,
  'mwx1': 10,
  'ndfl': 10,
  'pco2': 200,
  'PCOD': 10,
  'pguv': 10,
  'rtmp': 10,
  's330': 10,
  'seap': 10,
  'sp1b': 10,
  'svp1': 10,
  'tsg1': 10,
  'tsg2': 10,

  'bwnc': 10,
  'cwnc': 10,
  'twnc': 10,
  'true_wind': 10,
}


# The port.tab from challenger.nbp.usap.gov
#
##########################################################################
#
#   NOTE:  IT IS EASY FOR THIS FILE TO GET OUT OF DATE AND CONFUSING.
#     PLEASE TAKE THE TIME TO KEEP IT NEAT AND UP TO DATE.  THE NEXT
#     PERSON WON'T KNOW WHERE THE MYSTERY CABLE YOU INSTALLED GOES TO
#     UNLESS YOU KEEP IT DOCUMENTED HERE.
#
#########################################################################
#
#	Serial Port Table - RVDAS 
#
#	$Id: port.tab,v 1.862 2019/07/21 13:30:58 rvdas Exp $
#	@(#) port.tab 1.6 2/14/94 R/V Ewing Logging System
#
#
#	baud rate: 0, 150, 300, 1200, 2400, 4800, 9600, 19200, 38400
#	data bits: 5, 6, 7, 8. 
#	stop bits: 1 or 2. 
#	parity:	   1 = odd, 2 = even, 0 = none  
#	igncr:	   1 = ignore CR
#	icrnl:	   1 = map CR to NL on input, 0 = do not map (depends upon 
#                      igncr setting)
#	eol:	   additional EOL char
#	onlcr:	   1 = map NL to CRNL on output, 0 = do not map
#	ocrnl:	   1 = map CR to NL on output, 0 = do not map
#	icanon:	   1 = canonical, 0 = non-canonical mode
#	vmin:	   # of chars to read (non-canonical mode)
#	vtime:	   # time (non-canonical mode)
#	vintr	   0 = disable INTR special input char, 1 = enable
#	vquit	   0 = disable QUIT special input char, 1 = enable
#	opost	   0 = disable output post-processing; 1 = enable
#
#
# instrument	serial port	baud  datab stopb parity igncr icrnl eol onlcr ocrnl icanon vmin vtime vintr vquit opost
# ----------    -----------     ----- ----- ----- ------ ----- ----- --- ----- ----- ------ ---- ----- ----- ----- -----
# SAMPLE  	/dev/ttyy00 	9600  8	    1     0      1     0     0   1     0     1      1    0     0     0     0
#
#	TRAX1	  = Trax Systems GPS time of day clock
#	TRUETIME2 = TrueTime GOES clock
#	ADU	  = ADU GPS receiver
#	GPS2      = GPS Receiver #2	
#	GPS3      = GPS Receiver #3
#	GPS4      = GPS Receiver #4
#	TRANSIT1  = Magnavox 1107 Transit Satellite Receiver (lab)
#	TRANSIT2  = Magnavox 1107 Transit Satellite Receiver (bridge)
#	INTERNAV  = INTERNAV LORAN C Receiver
#	NORTHSTAR = NorthStar LORAN C Receiver
#	FURUNO    = Furuno /CI-30 doppller water speed log
#	MAG       = Magnetics
#	BGM       = Bell Aerospace BGM-3 Gravity Meter
#	KSS       = Boedensework KSS-30 Gravity Meter
#	DSS240    = DSS-240 console
#	DSSNAV    = DSS-240 "nav" data io
#	SHOTTIME  = seismic shot time tagger 
#	GUNDEPTH  = seismic gun depths
#	PCO2	  = CO2 data 
#	CTEMP	  = seawater temperature
#	JOES_DATA = selected data output by program "collect" 
#                       to a PC (for display) 
#	ADCP_OUT  = GPS data output to ADCP by progam "l_4200"
#	WIRE	  = core/ctd winch wire out and rate
#	PITCH-ROLL= pitch and roll
#	WX_IN	  = meteorological station data
#	SeaPath   = Center of gravity location from seapath 1 
#	SeaPath2A = Center of gravity location from seapath 2
#	SeaPath2B = moon pool location from seapath 2 
#
#
#    *** NOTE: ALL FIELDS SHOULD HAVE ENTRIES ***
#
# History

# Revision 1.1  1995/05/16  20:42:27  brockda
# Initial revision
#
#
# instrument	serial port	baud  datab stopb parity igncr icrnl eol onlcr ocrnl icanon vmin vtime vintr vquit opost
# ----------    -----------     ----- ----- ----- ------ ----- ----- --- ----- ----- ------ ---- ----- ----- ----- -----
#SAMPLE  	/dev/ttyy00 	9600  8     1     0      1     0     0   1     0     1      1    0     0     0     0
#
MOXA = {
  # Moxa box 1     10.1.1.50
  'PCOD': 'PcodeGPS  /dev/ttyr00  4800  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'cwnc': 'WatFallWinch  /dev/ttyr01  19200  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': 'OXYG  /dev/ttyr02  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'gp02': 'FurunoGPS  /dev/ttyr03  4800  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'gyr1': 'Gyroscope  /dev/ttyr04  4800  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'adcp': 'ADCP  /dev/ttyr05  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'eng1': 'EngDAS  /dev/ttyr06  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'svp1': 'SVPadcp  /dev/ttyr07  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': 'PortTrawlW  /dev/ttyr08  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': 'StbdTrawlW  /dev/ttyr09  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'bwnc': 'BalticWinch  /dev/ttyr0a  19200  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'twnc': 'TrawlWinch  /dev/ttyr0b  19200  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': 'MBTSG  /dev/ttyr0c  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': 'AIS  /dev/ttyr0d  38400  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': '# not working 2/5/2015 kag  /dev/ttyr0e  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'mbdp': 'MBdepth  /dev/ttyr0f  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',

  # Moxa box 2     10.1.1.51
  #'': '#  /dev/ttyr10  9600  8  2  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': 'SimEK500  /dev/ttyr11  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'knud': 'Knudsen  /dev/ttyr12  19200  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': 'Magnetics  /dev/ttyr13  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'grv1': 'Gravity  /dev/ttyr14  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': '#  /dev/ttyr15  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'mwx1': 'MastWx  /dev/ttyr16  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'ndfl': 'Fluorometer  /dev/ttyr17  19200  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'pco2': 'PCO2  /dev/ttyr18  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': 'OYO  /dev/ttyr19  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': 'Bird  /dev/ttyr1a  9600  8  1  0  0  1  0  1  0  1  1  0  0  0  0',
  #'': 'rawS330  /dev/ttyr1b  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': 'SeisTimeC  /dev/ttyr1c  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': '#  /dev/ttyr1d  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'pguv': 'PUVGUV  /dev/ttyr1e  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': '#  /dev/ttyr1f  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',

  # Moxa box 3     10.1.1.52
  #'': 'StarFix1  /dev/ttyr20  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': 'StarFix2  /dev/ttyr21  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  's330': 'SeaPath330  /dev/ttyr22  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'sp1b': 'SeaPath1B  /dev/ttyr23  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'ctdd': 'CTDdepth  /dev/ttyr24  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'tsg1': 'TSG1  /dev/ttyr25  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'rtmp': 'RmtTemp  /dev/ttyr26  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'hdas': 'HydroDAS  /dev/ttyr27  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': '#  /dev/ttyr28  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'tsg2': 'TSG2  /dev/ttyr29  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  'seap': 'SeaPath200  /dev/ttyr2a  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': 'GEN2  /dev/ttyr2b  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': 'GEN3  /dev/ttyr2c  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': 'GEN4  /dev/ttyr2d  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': 'VOSIMET  /dev/ttyr2e  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
  #'': 'CTDpar  /dev/ttyr2f  9600  8  1  0  1  1  0  1  0  1  1  0  0  0  0',
}


HEADER_TEMPLATE = """##########
# Sample YAML cruise definition file for NBP openrvdas, created by hacked-up
# script at local/nbp/create_MOXA_cruise_definition.py.

# Note that the one hack necessary is that YAML interprets 'off' (when not
# quoted) as the literal 'False'. So YAML needs to quote 'off'.

########################################
cruise:
  id: NBPxxxx
  start: '2019-07-30'
  end: '2019-12-31'
"""

TRUE_WIND_TEMPLATE = """
  true_wind->net:
    name: true_wind->net
    readers:
      class: CachedDataReader
      kwargs:
        data_server: localhost:%WEBSOCKET%
        subscription:
          fields:
            S330CourseTrue:
              seconds: 0
            S330HeadingTrue:
              seconds: 0
            S330SpeedKt:
              seconds: 0
            MwxPortRelWindDir:
              seconds: 0
            MwxPortRelWindSpeed:
              seconds: 0
            MwxStbdRelWindDir:
              seconds: 0
            MwxStbdRelWindSpeed:
              seconds: 0
    transforms:
    - class: ComposedDerivedDataTransform
      kwargs:
        transforms:
        - class: TrueWindsTransform
          kwargs:
            apparent_dir_name: PortApparentWindDir
            convert_wind_factor: 1.94384
            course_field: S330CourseTrue
            heading_field: S330HeadingTrue
            speed_field: S330SpeedKt
            true_dir_name: PortTrueWindDir
            true_speed_name: PortTrueWindSpeed
            update_on_fields:
            - MwxPortRelWindDir
            wind_dir_field: MwxPortRelWindDir
            wind_speed_field: MwxPortRelWindSpeed
        - class: TrueWindsTransform
          kwargs:
            apparent_dir_name: StbdApparentWindDir
            convert_wind_factor: 1.94384
            course_field: S330CourseTrue
            heading_field: S330HeadingTrue
            speed_field: S330SpeedKt
            true_dir_name: StbdTrueWindDir
            true_speed_name: StbdTrueWindSpeed
            update_on_fields:
            - MwxStbdRelWindDir
            wind_dir_field: MwxStbdRelWindDir
            wind_speed_field: MwxStbdRelWindSpeed
    writers:
    - class: CachedDataWriter
      kwargs:
        data_server: localhost:%WEBSOCKET%
    stderr_writers:          # Turn stderr into DASRecord, broadcast to cache
    - class: ComposedWriter  # UDP port for CachedDataServer to pick up.
      kwargs:
        transforms:
        - class: ToDASRecordTransform
          kwargs:
            field_name: 'stderr:logger:true_wind'
        writers:
        - class: CachedDataWriter
          kwargs:
            data_server: localhost:%WEBSOCKET%

  true_wind->file/net:
    name: true_wind->file/net
    readers:
      class: CachedDataReader
      kwargs:
        data_server: localhost:%WEBSOCKET%
        subscription:
          fields:
            S330CourseTrue:
              seconds: 0
            S330HeadingTrue:
              seconds: 0
            S330SpeedKt:
              seconds: 0
            MwxPortRelWindDir:
              seconds: 0
            MwxPortRelWindSpeed:
              seconds: 0
            MwxStbdRelWindDir:
              seconds: 0
            MwxStbdRelWindSpeed:
              seconds: 0
    transforms:
    - class: ComposedDerivedDataTransform
      kwargs:
        transforms:
        - class: TrueWindsTransform
          kwargs:
            apparent_dir_name: PortApparentWindDir
            convert_wind_factor: 1.94384
            course_field: S330CourseTrue
            heading_field: S330HeadingTrue
            speed_field: S330SpeedKt
            true_dir_name: PortTrueWindDir
            true_speed_name: PortTrueWindSpeed
            update_on_fields:
            - MwxPortRelWindDir
            wind_dir_field: MwxPortRelWindDir
            wind_speed_field: MwxPortRelWindSpeed
        - class: TrueWindsTransform
          kwargs:
            apparent_dir_name: StbdApparentWindDir
            convert_wind_factor: 1.94384
            course_field: S330CourseTrue
            heading_field: S330HeadingTrue
            speed_field: S330SpeedKt
            true_dir_name: StbdTrueWindDir
            true_speed_name: StbdTrueWindSpeed
            update_on_fields:
            - MwxStbdRelWindDir
            wind_dir_field: MwxStbdRelWindDir
            wind_speed_field: MwxStbdRelWindSpeed
    writers:
    - class: CachedDataWriter
      kwargs:
        data_server: localhost:%WEBSOCKET%
    stderr_writers:          # Turn stderr into DASRecord, broadcast to cache
    - class: ComposedWriter  # UDP port for CachedDataServer to pick up.
      kwargs:
        transforms:
        - class: ToDASRecordTransform
          kwargs:
            field_name: 'stderr:logger:true_wind'
        writers:
        - class: CachedDataWriter
          kwargs:
            data_server: localhost:%WEBSOCKET%

  true_wind->file/net/db:
    name: true_wind->file/net/db
    readers:
      class: CachedDataReader
      kwargs:
        data_server: localhost:%WEBSOCKET%
        subscription:
          fields:
            S330CourseTrue:
              seconds: 0
            S330HeadingTrue:
              seconds: 0
            S330SpeedKt:
              seconds: 0
            MwxPortRelWindDir:
              seconds: 0
            MwxPortRelWindSpeed:
              seconds: 0
            MwxStbdRelWindDir:
              seconds: 0
            MwxStbdRelWindSpeed:
              seconds: 0
    transforms:
    - class: ComposedDerivedDataTransform
      kwargs:
        transforms:
        - class: TrueWindsTransform
          kwargs:
            apparent_dir_name: PortApparentWindDir
            convert_wind_factor: 1.94384
            course_field: S330CourseTrue
            heading_field: S330HeadingTrue
            speed_field: S330SpeedKt
            true_dir_name: PortTrueWindDir
            true_speed_name: PortTrueWindSpeed
            update_on_fields:
            - MwxPortRelWindDir
            wind_dir_field: MwxPortRelWindDir
            wind_speed_field: MwxPortRelWindSpeed
        - class: TrueWindsTransform
          kwargs:
            apparent_dir_name: StbdApparentWindDir
            convert_wind_factor: 1.94384
            course_field: S330CourseTrue
            heading_field: S330HeadingTrue
            speed_field: S330SpeedKt
            true_dir_name: StbdTrueWindDir
            true_speed_name: StbdTrueWindSpeed
            update_on_fields:
            - MwxStbdRelWindDir
            wind_dir_field: MwxStbdRelWindDir
            wind_speed_field: MwxStbdRelWindSpeed
    writers:
    - class: CachedDataWriter
      kwargs:
        data_server: localhost:%WEBSOCKET%
    stderr_writers:          # Turn stderr into DASRecord, broadcast to cache
    - class: ComposedWriter  # UDP port for CachedDataServer to pick up.
      kwargs:
        transforms:
        - class: ToDASRecordTransform
          kwargs:
            field_name: 'stderr:logger:true_wind'
        writers:
        - class: CachedDataWriter
          kwargs:
            data_server: localhost:%WEBSOCKET%
"""

OFF_TEMPLATE="""
  %LOGGER%->off:
    name: %LOGGER%->off
"""

NET_WRITER_TEMPLATE="""
  %LOGGER%->net:
    name: %LOGGER%->net
    readers:                    # Read from simulated serial port
      class: SerialReader
      kwargs:
        baudrate: %BAUD%
        port: %TTY%
    transforms:                 # Add timestamp and logger label
    - class: TimestampTransform
    - class: PrefixTransform
      kwargs:
        prefix: %LOGGER%
    writers:
    - class: UDPWriter
      kwargs:
        port: %RAW_UDP%
        interface: %UDP_INTERFACE%
    - class: ComposedWriter     # Also parse to fields and send to CACHE UDP
      kwargs:                   # port for CachedDataServer to pick up
        transforms:
        - class: ParseTransform
          kwargs:
            definition_path: local/devices/*.yaml,local/usap/devices/*.yaml,local/usap/nbp/devices/*.yaml
        writers:
        - class: CachedDataWriter
          kwargs:
            data_server: localhost:%WEBSOCKET%
    stderr_writers:          # Turn stderr into DASRecord, broadcast to cache
    - class: ComposedWriter  # UDP port for CachedDataServer to pick up.
      kwargs:
        transforms:
        - class: ToDASRecordTransform
          kwargs:
            field_name: 'stderr:logger:%LOGGER%'
        writers:
        - class: CachedDataWriter
          kwargs:
            data_server: localhost:%WEBSOCKET%
"""

FILE_NET_WRITER_TEMPLATE="""
  %LOGGER%->file/net:
    name: %LOGGER%->file/net
    readers:                    # Read from simulated serial port
      class: SerialReader
      kwargs:
        baudrate: %BAUD%
        port: %TTY%
    transforms:                 # Add timestamp
    - class: TimestampTransform
    writers:
    - class: LogfileWriter      # Write to logfile
      kwargs:
        filebase: %FILEBASE%/%LOGGER%/raw/%LOGGER%
    - class: ComposedWriter     # Also prefix with logger name and broadcast
      kwargs:                   # raw NMEA on UDP
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: %LOGGER%
        writers:
        - class: UDPWriter
          kwargs:
            port: %RAW_UDP%
            interface: %UDP_INTERFACE%
    - class: ComposedWriter     # Also parse to fields and send to CACHE UDP
      kwargs:                   # port for CachedDataServer to pick up
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: %LOGGER%
        - class: ParseTransform
          kwargs:
            definition_path: local/devices/*.yaml,local/usap/devices/*.yaml,local/usap/nbp/devices/*.yaml
        writers:
        - class: CachedDataWriter
          kwargs:
            data_server: localhost:%WEBSOCKET%
    stderr_writers:          # Turn stderr into DASRecord, broadcast to cache
    - class: ComposedWriter  # UDP port for CachedDataServer to pick up.
      kwargs:
        transforms:
        - class: ToDASRecordTransform
          kwargs:
            field_name: 'stderr:logger:%LOGGER%'
        writers:
        - class: CachedDataWriter
          kwargs:
            data_server: localhost:%WEBSOCKET%
"""

FULL_WRITER_TEMPLATE="""
  %LOGGER%->file/net/db:
    name: %LOGGER%->file/net/db
    readers:                    # Read from simulated serial port
      class: SerialReader
      kwargs:
        baudrate: %BAUD%
        port: %TTY%
    transforms:                 # Add timestamp
    - class: TimestampTransform
    writers:
    - class: LogfileWriter      # Write to logfile
      kwargs:
        filebase: %FILEBASE%/%LOGGER%/raw/%LOGGER%
    - class: ComposedWriter     # Also prefix with logger name and broadcast
      kwargs:                   # raw NMEA on UDP
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: %LOGGER%
        writers:
        - class: UDPWriter
          kwargs:
            port: %RAW_UDP%
            interface: %UDP_INTERFACE% 
    - class: ComposedWriter     # Also parse to fields and send to CACHE UDP
      kwargs:                   # port for CachedDataServer to pick up
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: %LOGGER%
        - class: ParseTransform
          kwargs:
            definition_path: local/devices/*.yaml,local/usap/devices/*.yaml,local/usap/nbp/devices/*.yaml
        writers:
        - class: CachedDataWriter
          kwargs:
            data_server: localhost:%WEBSOCKET%
    - class: ComposedWriter     # Also write parsed data to database
      kwargs:
        transforms:
        - class: PrefixTransform
          kwargs:
            prefix: %LOGGER%
        - class: ParseTransform
          kwargs:
            definition_path: local/devices/*.yaml,local/usap/devices/*.yaml,local/usap/nbp/devices/*.yaml
        writers:
        - class: DatabaseWriter
    stderr_writers:          # Turn stderr into DASRecord, broadcast to cache
    - class: ComposedWriter  # UDP port for CachedDataServer to pick up.
      kwargs:
        transforms:
        - class: ToDASRecordTransform
          kwargs:
            field_name: 'stderr:logger:%LOGGER%'
        writers:
        - class: CachedDataWriter
          kwargs:
            data_server: localhost:%WEBSOCKET%
"""

NET_TIMEOUT_TEMPLATE = """
  network_timeout->off:
    name: network_timeout->off

  network_timeout->on:
    name: network_timeout->on
    readers:                   # Read from raw UDP
    - class: UDPReader
      kwargs:
        port: %RAW_UDP%
    stderr_writers:
    - class: TextFileWriter
    writers:""" # Append list of actual timeout writers to this stub

###############################
def assemble_timeout_writer():
  timeout_logger = fill_vars(NET_TIMEOUT_TEMPLATE, VARS)
  for logger in LOGGER_TIMEOUTS:
    writer_string = """
    - class: ComposedWriter
      kwargs:
        transforms:
        - class: RegexFilterTransform
          kwargs:
            pattern: "^%LOGGER%"
        writers:
        - class: TimeoutWriter
          kwargs:
            timeout: %TIMEOUT%
            message: %LOGGER% logged no data on port %RAW_UDP% in %TIMEOUT% seconds
            resume_message: %LOGGER% logged new data on port %RAW_UDP%
            writer:
              class: ComposedWriter
              kwargs:
                transforms:
                - class: TimestampTransform
                - class: ToDASRecordTransform
                  kwargs:
                    field_name: stderr:logger:%LOGGER%
                writers:
                - class: CachedDataWriter
                  kwargs:
                    data_server: localhost:%WEBSOCKET%"""
    writer_string = fill_vars(writer_string, VARS)
    writer_string = fill_vars(writer_string,
                              {'%LOGGER%': logger,
                               '%TIMEOUT%': str(LOGGER_TIMEOUTS[logger])})
    timeout_logger += writer_string
  return timeout_logger

###############################
def fill_vars(template, vars):
  output = template
  for src, dest in vars.items():
    output = output.replace(src, dest)
  return output

################################################################################
################################################################################

output = HEADER_TEMPLATE

################################################################################
# Fill in the logger definitions
output += """
########################################
loggers:
"""

LOGGER_DEF = """  %LOGGER%:
    configs:
    - %LOGGER%->off
    - %LOGGER%->net
    - %LOGGER%->file/net
    - %LOGGER%->file/net/db
"""
for logger in LOGGERS:
  if logger == 'network_timeout':
    output += """  network_timeout:
    configs:
    - network_timeout->off
    - network_timeout->on
"""
    continue

  output += fill_vars(LOGGER_DEF, VARS).replace('%LOGGER%', logger)

################################################################################
# Fill in mode definitions
output += """
########################################
modes:
  'off':
"""
for logger in LOGGERS:
  output += '    %LOGGER%: %LOGGER%->off\n'.replace('%LOGGER%', logger)
#### monitor
output += """
  monitor:
"""
for logger in LOGGERS:
  if logger == 'network_timeout':
    output += '    network_timeout: network_timeout->on'
    continue
  output += '    %LOGGER%: %LOGGER%->net\n'.replace('%LOGGER%', logger)
#### log
output += """
  log:
"""
for logger in LOGGERS:
  if logger == 'network_timeout':
    output += '    network_timeout: network_timeout->on'
    continue
  output += '    %LOGGER%: %LOGGER%->file/net\n'.replace('%LOGGER%', logger)
#### log+db
output += """
  'log+db':
"""
for logger in LOGGERS:
  if logger == 'network_timeout':
    output += '    network_timeout: network_timeout->on'
    continue
  output += '    %LOGGER%: %LOGGER%->file/net/db\n'.replace('%LOGGER%', logger)

output += """
########################################
default_mode: 'off'
"""

################################################################################
# Now output configs
output += """
########################################
configs:
"""
for logger in LOGGERS:
  output += """  ########"""
  output += fill_vars(OFF_TEMPLATE, VARS).replace('%LOGGER%', logger)
  # Special case for true winds, which is a derived logger
  if logger == 'true_wind':
    output += fill_vars(TRUE_WIND_TEMPLATE, VARS)
    continue
  if logger == 'network_timeout':
    output += assemble_timeout_writer()
    continue

  # Look up port.tab values for this logger
  if not logger in MOXA:
    logging.warning('No port.tab entry found for %s; skipping...', logger)
    continue

  (inst, tty, baud, datab, stopb, parity, igncr, icrnl, eol, onlcr,
   ocrnl, icanon, vmin, vtime, vintr, vquit, opost) = MOXA[logger].split()
  net_writer = fill_vars(NET_WRITER_TEMPLATE, VARS)
  net_writer = net_writer.replace('%LOGGER%', logger)
  net_writer = net_writer.replace('%TTY%', tty)
  net_writer = net_writer.replace('%BAUD%', baud)
  output += net_writer

  file_net_writer = fill_vars(FILE_NET_WRITER_TEMPLATE, VARS)
  file_net_writer = file_net_writer.replace('%LOGGER%', logger)
  file_net_writer = file_net_writer.replace('%TTY%', tty)
  file_net_writer = file_net_writer.replace('%BAUD%', baud)
  output += file_net_writer

  full_writer = fill_vars(FULL_WRITER_TEMPLATE, VARS)
  full_writer = full_writer.replace('%LOGGER%', logger)
  full_writer = full_writer.replace('%TTY%', tty)
  full_writer = full_writer.replace('%BAUD%', baud)
  output += full_writer

  output += assemble_timeout_writer()

print(output)
