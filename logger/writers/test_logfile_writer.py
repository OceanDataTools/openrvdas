#!/usr/bin/env python3

import logging
import sys
import tempfile
import time
import unittest
import warnings

sys.path.append('.')

from logger.writers.logfile_writer import LogfileWriter
from logger.utils import formats

SAMPLE_DATA = """2017-11-03:17:23:04.832875 Nel mezzo del cammin di nostra vita
2017-11-03:17:23:04.833188 mi ritrovai per una selva oscura,
2017-11-03:17:23:04.833243 ché la diritta via era smarrita.
2017-11-04:17:23:04.833274 Ahi quanto a dir qual era è cosa dura
2017-11-04:17:23:04.833303 esta selva selvaggia e aspra e forte
2017-11-04:17:23:04.833330 che nel pensier rinova la paura!
2017-11-05:17:23:04.833356 Tant' è amara che poco è più morte;
2017-11-05:17:23:04.833391 ma per trattar del ben ch'i' vi trovai,
2017-11-05:17:23:04.833418 dirò de l'altre cose ch'i' v'ho scorte.
2017-11-06:17:23:04.833445 Io non so ben ridir com' i' v'intrai,
2017-11-06:17:23:04.833471 tant' era pien di sonno a quel punto
2017-11-06:17:23:04.833498 che la verace via abbandonai.
2017-11-07:17:23:04.833525 Ma poi ch'i' fui al piè d'un colle giunto,
2017-11-07:17:23:04.833551 là dove terminava quella valle
2017-11-07:17:23:04.833578 che m'avea di paura il cor compunto,
2017-11-08:17:23:04.833604 guardai in alto e vidi le sue spalle
2017-11-08:17:23:04.833630 vestite già de' raggi del pianeta
2017-11-08:17:23:04.833657 che mena dritto altrui per ogne calle.
2017-11-09:17:23:04.833683 Allor fu la paura un poco queta,
2017-11-09:17:23:04.833710 che nel lago del cor m'era durata
2017-11-09:17:23:04.833736 la notte ch'i' passai con tanta pieta.
"""
class TestLogfileWriter(unittest.TestCase):

  ############################
  def test_write(self):
    with tempfile.TemporaryDirectory() as tmpdirname:
      lines = SAMPLE_DATA.split('\n')

      filebase = tmpdirname + '/logfile'
      
      writer = LogfileWriter(filebase)

      with self.assertLogs(logging.getLogger(), logging.ERROR):
        writer.write('there is no timestamp here')

      r = range(0,3)
      for i in r:
        writer.write(lines[i])

      outfile = open(filebase + '-2017-11-03', 'r')
      for i in r:
        self.assertEqual(lines[i], outfile.readline().rstrip())

      r = range(3,6)
      for i in r:
        writer.write(lines[i])

      outfile = open(filebase + '-2017-11-04', 'r')
      for i in r:
        self.assertEqual(lines[i], outfile.readline().rstrip())

      r = range(6,9)
      for i in r:
        writer.write(lines[i])

      outfile = open(filebase + '-2017-11-05', 'r')
      for i in r:
        self.assertEqual(lines[i], outfile.readline().rstrip())
      
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
