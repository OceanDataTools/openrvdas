#!/usr/bin/env python3

import logging
import sys
import pytest
import unittest
from contrib.niwa.logger.transforms.regex_replace_function_transform import RegexReplaceFunctionTransform

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))


test_data = {
    "$INGGA,020726.45,4151.821322,N,01124.225123,W,2,10,0.9,-4.89,M,52.68,M,2.0,0136*66\r": "$INGGA,020726.45,41.863688,N,-11.403752,W,2,10,0.9,-4.89,M,52.68,M,2.0,0136*66\r",
    "$INRMC,033617.45,A,4149.969671,N,01139.989334,W,8.1,258.15,020424,2.2,W,D*1B\r": "$INRMC,033617.45,A,41.832827,N,-11.666488,W,8.1,258.15,020424,2.2,W,D*1B\r"
}


@pytest.mark.parametrize('input_string', test_data.keys())
def test_degrees_decimal(input_string):
    # this represents a conversion from decimal degrees to degrees minutes 
    transform = RegexReplaceFunctionTransform(patterns={
               "(\\-?\\d{5}\\.\\d*),([EW])": "str(round(float(match[0][:3]) + (float(match[0][3:10]) / 60), 6) * (1 if match[1] == 'E' else -1)) + \",\" + match[1]",
               "(\\-?\\d{4}\\.\\d*),([NS])": "str(round(float(match[0][:2]) + (float(match[0][2:9]) / 60), 6) * (1 if match[1] == 'N' else -1)) + \",\" + match[1]",
            })
    
    assert transform.transform(input_string) == test_data[input_string]

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(filename)s:%(lineno)d %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    unittest.main(warnings='ignore')
