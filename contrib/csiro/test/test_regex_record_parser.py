import logging
import unittest


from contrib.csiro.logger.utils.regex_parser import RegexRecordParser


class TestRegexRecordParser(unittest.TestCase):
    device_path = 'contrib/csiro/test/CSIRO_device_catalogue.yaml'
    regex_record_parser = RegexRecordParser(definition_path=device_path)

    def assert_record_with_regex_parser(self, test_records, expected_results, func_assert_equal=None):
        func_assert_equal = func_assert_equal or self.assertEqual

        def parse_and_assert(record, expected):
            result = self.regex_record_parser.parse_record(record)
            func_assert_equal(result, expected)

        # Test each record as a subtest if both test_records and expected_results are lists
        if isinstance(test_records, list) and isinstance(expected_results, list):
            if len(test_records) != len(expected_results):
                raise ValueError("The number of test records must match the number of expected results")

            for test_record, expected_result in zip(test_records, expected_results):
                with self.subTest(f'Testing with input: {str(test_record)[:50]}...'):
                    parse_and_assert(test_record, expected_result)
        else:
            parse_and_assert(test_records, expected_results)


class TestSeapathDevicesRegexParser(TestRegexRecordParser):
    def test_GGA(self):
        test_record = 'seap 2022-08-17T01:39:42.459365Z $GPGGA,143357.30,4856.189306,S,10227.213911,E,2,12,1.0,-0.31,M,-6.40,M,9.0,1007*60'
        expected_result = {
            'data_id': 'seap',
            'timestamp': 1660700382.459365,
            'fields': {
                'TalkerID': 'GP',
                'GPSTime': 143357.30,
                'Latitude': 4856.189306,
                'NorS': 'S',
                'Longitude': 10227.213911,
                'EorW': 'E',
                'FixQuality': 2,
                'NumSats': 12,
                'HDOP': 1.0,
                'AntennaHeight': -0.31,
                'GeoidHeight': -6.40,
                'LastDGPSUpdate': 9.0,
                'DGPSStationID': 1007
            },
            'message_type': 'GGA'
        }
        super().assert_record_with_regex_parser(test_record, expected_result)

    def test_HDT(self):
        test_record = 'seap 2022-08-17T01:39:42.459365Z $GPHDT,213.02,T*07'
        expected_result = {
            'data_id': 'seap',
            'timestamp': 1660700382.459365,
            'fields': {
                'TalkerID': 'GP',
                'HeadingTrue': 213.02
            },
            'message_type': 'HDT'
        }
        super().assert_record_with_regex_parser(test_record, expected_result)

    def test_VTG(self):
        test_record = 'seap 2022-08-17T01:39:42.459365Z $GPVTG,207.27,T,,M,8.7,N,16.2,K,D*02'
        expected_result = {
            'data_id': 'seap',
            'timestamp': 1660700382.459365,
            'fields': {
                'TalkerID': 'GP',
                'CourseTrue': 207.27,
                'CourseMag': None,
                'SpeedOverGround': 8.7,
                'SpeedKm': 16.2,
                'Mode': 'D'
            },
            'message_type': 'VTG'
        }
        super().assert_record_with_regex_parser(test_record, expected_result)

    def test_ZDA(self):
        test_record = 'seap 2022-08-17T01:39:42.459365Z $GPZDA,143357.30,30,01,2023,,*63'
        expected_result = {
            'data_id': 'seap',
            'timestamp': 1660700382.459365,
            'fields': {
                'TalkerID': 'GP',
                'GPSTime': 143357.30,
                'GPSDay': 30,
                'GPSMonth': 1,
                'GPSYear': 2023,
                'LocalZoneHours': None,
                'LocalZoneMinutes': None
            },
            'message_type': 'ZDA'
        }
        super().assert_record_with_regex_parser(test_record, expected_result)

    def test_RMC(self):
        test_record = 'seap 2022-08-17T01:39:42.459365Z $GPRMC,143357.30,A,4856.189306,S,10227.213911,E,8.7,207.27,300123,,,D*7B'
        expected_result = {
            'data_id': 'seap',
            'timestamp': 1660700382.459365,
            'fields': {
                'TalkerID': 'GP',
                'GPSTime': 143357.30,
                'GPSStatus': 'A',
                'Latitude': 4856.189306,
                'NorS': 'S',
                'Longitude': 10227.213911,
                'EorW': 'E',
                'SpeedOverGround': 8.7,
                'CourseTrue': 207.27,
                'GPSDate': 300123,
                'MagneticVar': None,
                'MagneticVarEorW': '',
                'Mode': 'D'
            },
            'message_type': 'RMC'
        }
        super().assert_record_with_regex_parser(test_record, expected_result)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbosity', dest='verbosity',
                        default=0, action='count',
                        help='Increase output verbosity')
    args = parser.parse_args()

    LOGGING_FORMAT = '%(asctime)-15s %(message)s'
    logging.basicConfig(format=LOGGING_FORMAT)

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    # unittest.main(warnings='ignore')
    unittest.main()