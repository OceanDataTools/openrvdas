#!/usr/bin/env python3
"""NOTE: THIS ISN'T ACTUALLY A UNITTEST!

It can be run manually to visually verify that the ScreenWriter is
doing what we think it should be doing, but it only causes a mess if
run as part of the test suite.

"""
import logging
import sys
import time
import unittest
import warnings

sys.path.append('.')

from logger.utils.nmea_parser import NMEAParser
from logger.writers.record_screen_writer import RecordScreenWriter

RECORDS = """
seap 2017-11-04:05:12:19.481328 $GPZDA,235959.92,06,08,2014,,*65
seap 2017-11-04:05:12:19.735342 $GPGGA,235959.92,3934.831152,S,03727.694551,W,1,11,0.9,-5.30,M,,M,,*6F
seap 2017-11-04:05:12:19.990659 $GPVTG,226.69,T,,M,10.8,N,,K,A*23
seap 2017-11-04:05:12:20.245888 $GPHDT,236.03,T*01
seap 2017-11-04:05:12:20.501188 $PSXN,20,1,0,0,0*3A
seap 2017-11-04:05:12:20.754583 $PSXN,22,0.44,0.81*30
seap 2017-11-04:05:12:21.006515 $PSXN,23,-2.54,1.82,236.03,-1.67*34
seap 2017-11-04:05:12:21.261835 $GPZDA,000000.92,07,08,2014,,*65
seap 2017-11-04:05:12:21.517092 $GPGGA,000000.92,3934.833175,S,03727.697459,W,1,11,0.9,-5.89,M,,M,,*61
seap 2017-11-04:05:12:21.772426 $GPVTG,229.63,T,,M,10.8,N,,K,A*26
seap 2017-11-04:05:12:22.022646 $GPHDT,236.28,T*08
seap 2017-11-04:05:12:22.272874 $PSXN,20,1,0,0,0*3A
seap 2017-11-04:05:12:22.526512 $PSXN,22,0.44,0.81*30
seap 2017-11-04:05:12:22.779671 $PSXN,23,-2.50,-1.48,236.28,-1.06*15
seap 2017-11-04:05:12:23.030096 $GPZDA,000001.92,07,08,2014,,*64
seap 2017-11-04:05:12:23.281760 $GPGGA,000001.92,3934.835118,S,03727.700517,W,1,11,0.9,-7.07,M,,M,,*6D
seap 2017-11-04:05:12:23.532669 $GPVTG,231.79,T,,M,11.1,N,,K,A*2C
seap 2017-11-04:05:12:23.783004 $GPHDT,236.56,T*01
seap 2017-11-04:05:12:24.035708 $PSXN,20,1,0,0,0*3A
seap 2017-11-04:05:12:24.287940 $PSXN,22,0.44,0.81*30
seap 2017-11-04:05:12:24.540765 $PSXN,23,-2.19,-3.26,236.56,0.13*33
seap 2017-11-04:05:12:24.790998 $GPZDA,000002.92,07,08,2014,,*67
seap 2017-11-04:05:12:25.046195 $GPGGA,000002.92,3934.837038,S,03727.703725,W,1,11,0.9,-7.98,M,,M,,*69
seap 2017-11-04:05:12:25.301541 $GPVTG,232.31,T,,M,11.5,N,,K,A*27
seap 2017-11-04:05:12:25.553129 $GPHDT,236.47,T*01
seap 2017-11-04:05:12:25.806433 $PSXN,20,1,0,0,0*3A
seap 2017-11-04:05:12:26.061721 $PSXN,22,0.44,0.81*30
seap 2017-11-04:05:12:26.314857 $PSXN,23,-1.63,-2.22,236.47,1.04*3F
seap 2017-11-04:05:12:26.567007 $GPZDA,000003.92,07,08,2014,,*66
seap 2017-11-04:05:12:26.819311 $GPGGA,000003.92,3934.839023,S,03727.706977,W,1,11,0.9,-7.98,M,,M,,*60
seap 2017-11-04:05:12:27.071958 $GPVTG,230.75,T,,M,11.7,N,,K,A*27
seap 2017-11-04:05:12:27.327301 $GPHDT,235.98,T*00
seap 2017-11-04:05:12:27.581758 $PSXN,20,1,0,0,0*3A
seap 2017-11-04:05:12:27.832511 $PSXN,22,0.44,0.81*30
seap 2017-11-04:05:12:28.085464 $PSXN,23,-1.03,0.41,235.98,1.04*12
seap 2017-11-04:05:12:28.335724 $GPZDA,000004.91,07,08,2014,,*62
seap 2017-11-04:05:12:28.586228 $GPGGA,000004.91,3934.841042,S,03727.710114,W,1,10,0.9,-7.22,M,,M,,*66
seap 2017-11-04:05:12:28.837839 $GPVTG,229.21,T,,M,11.4,N,,K,A*2D
seap 2017-11-04:05:12:29.091909 $GPHDT,235.63,T*04
seap 2017-11-04:05:12:29.347263 $PSXN,20,1,0,0,0*3A
seap 2017-11-04:05:12:29.602303 $PSXN,22,0.44,0.81*30
seap 2017-11-04:05:12:29.852553 $PSXN,23,-0.84,2.47,235.63,0.22*19
seap 2017-11-04:05:12:30.107463 $GPZDA,000005.91,07,08,2014,,*63
seap 2017-11-04:05:12:30.362874 $GPGGA,000005.91,3934.843045,S,03727.713132,W,1,11,0.9,-6.32,M,,M,,*64""".split('\n')


class TestRecordScreenWriter(unittest.TestCase):
  ############################
  def test_default_parser(self):
    p = NMEAParser()
    t = RecordScreenWriter()

    for line in RECORDS:
      record = p.parse_record(line)
      t.write(record)
      time.sleep(0.1)
      
################################################################################
if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  args = parser.parse_args()

  LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
  logging.basicConfig(format=LOGGING_FORMAT)

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])
  
  unittest.main(warnings='ignore')
    
