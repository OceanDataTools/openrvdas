#!/usr/bin/env python3

import logging
import sys
import unittest
import warnings

sys.path.append('.')

from logger.transforms.xml_aggregator_transform import XMLAggregatorTransform

SAMPLE_DATA = """<?xml version="1.0" encoding="UTF-8"?>
<OSU_DAS_Record Type="Data" Version="2.0">
		<Data Type="Serial" Status="Good">
		<Raw Type="HexBin">0A2448454844542C392E382C542A32450D</Raw>
		<Calibration>
			<Date>None</Date>
		</Calibration>
		<Signal Units="ASCII">
$HEHDT,9.8,T*2E
</Signal>
		<Physical Units="NMEA0183"/>
	</Data>
</OSU_DAS_Record>
<?xml version="1.0" encoding="UTF-8"?>
<OSU_DAS_Record Type="Data" Version="2.0">
		<Data Type="Serial" Status="Good">
		<Raw Type="HexBin">0A2448454844542C31302E312C542A31460D</Raw>
		<Calibration>
			<Date>None</Date>
		</Calibration>
		<Signal Units="ASCII">
$HEHDT,10.1,T*1F
</Signal>
		<Physical Units="NMEA0183"/>
	</Data>
</OSU_DAS_Record>
<?xml version="1.0" encoding="UTF-8"?>
<OSU_DAS_Record Type="Data" Version="2.0">
	<Data Type="Serial" Status="Good">
		<Raw Type="HexBin">0A2448454844542C31302E342C542A31410D</Raw>
		<Calibration>
			<Date>None</Date>
		</Calibration>
		<Signal Units="ASCII">
$HEHDT,10.4,T*1A
</Signal>
		<Physical Units="NMEA0183"/>
	</Data>
</OSU_DAS_Record>
<?xml version="1.0" encoding="UTF-8"?>
"""

xml_recs = [
 """<?xml version="1.0" encoding="UTF-8"?><OSU_DAS_Record Type="Data" Version="2.0">
		<Data Type="Serial" Status="Good">
		<Raw Type="HexBin">0A2448454844542C392E382C542A32450D</Raw>
		<Calibration>
			<Date>None</Date>
		</Calibration>
		<Signal Units="ASCII">
$HEHDT,9.8,T*2E
</Signal>
		<Physical Units="NMEA0183"/>
	</Data>
</OSU_DAS_Record>
""",
  """<?xml version="1.0" encoding="UTF-8"?><OSU_DAS_Record Type="Data" Version="2.0">
		<Data Type="Serial" Status="Good">
		<Raw Type="HexBin">0A2448454844542C31302E312C542A31460D</Raw>
		<Calibration>
			<Date>None</Date>
		</Calibration>
		<Signal Units="ASCII">
$HEHDT,10.1,T*1F
</Signal>
		<Physical Units="NMEA0183"/>
	</Data>
</OSU_DAS_Record>
""",
  """<?xml version="1.0" encoding="UTF-8"?><OSU_DAS_Record Type="Data" Version="2.0">
	<Data Type="Serial" Status="Good">
		<Raw Type="HexBin">0A2448454844542C31302E342C542A31410D</Raw>
		<Calibration>
			<Date>None</Date>
		</Calibration>
		<Signal Units="ASCII">
$HEHDT,10.4,T*1A
</Signal>
		<Physical Units="NMEA0183"/>
	</Data>
</OSU_DAS_Record>
"""]

################################################################################
class TestXMLAggregatorTransform(unittest.TestCase):
  ############################
  def test_default(self):
    transform = XMLAggregatorTransform()

    record_num = 0
    for line in SAMPLE_DATA.split('\n'):
      #logging.debug('transforming line: %s', line)
      record = transform.transform(line)
      if record:
        logging.info('received completed XML record: "%s..."',
                     record[0:15])
        self.assertEqual([r.strip() for r in record.split('\n')],
                         [x.strip() for x in xml_recs[record_num].split('\n')])
        record_num += 1
                         
################################################################################
if __name__ == '__main__':
  import argparse
  parser = argparse.ArgumentParser()
  parser.add_argument('-v', '--verbosity', dest='verbosity',
                      default=0, action='count',
                      help='Increase output verbosity')
  args = parser.parse_args()

  LOGGING_FORMAT = '%(asctime)-15s %(message)s'
  logging.basicConfig(format=LOGGING_FORMAT)

  LOG_LEVELS ={0:logging.WARNING, 1:logging.INFO, 2:logging.DEBUG}
  args.verbosity = min(args.verbosity, max(LOG_LEVELS))
  logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])
  
  unittest.main(warnings='ignore')
