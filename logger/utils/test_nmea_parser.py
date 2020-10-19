#!/usr/bin/env python3

# flake8: noqa E501 - ignore long lines

import logging
import pprint
import sys
import time
import unittest
import warnings

from os.path import dirname, realpath
sys.path.append(dirname(dirname(dirname(realpath(__file__)))))
from logger.utils.nmea_parser import NMEAParser  # noqa: E402

GYR1_RECORDS = """gyr1 2017-11-10T01:00:06.739Z $HEHDT,143.7,T*2E
gyr1 2017-11-10T01:00:06.739Z $HEROT,-0000.8,A*3E
gyr1 2017-11-10T01:00:07.737Z $HEHDT,143.8,T*21
gyr1 2017-11-10T01:00:07.737Z $HEROT,0002.9,A*10
gyr1 2017-11-10T01:00:08.737Z $HEHDT,143.9,T*20""".split('\n')

GRV1_RECORDS = """grv1 2017-11-10T01:00:06.572Z 01:024557 00
grv1 2017-11-10T01:00:07.569Z 01:024106 00
grv1 2017-11-10T01:00:08.572Z 01:024303 00
grv1 2017-11-10T01:00:09.568Z 01:024858 00
grv1 2017-11-10T01:00:10.570Z 01:025187 00
grv1 2017-11-10T01:00:11.571Z 01:025013 00""".split('\n')

SEAP_RECORDS = """seap 2017-11-04T07:00:39.291859Z $PSXN,20,1,0,0,0*3A
seap 2017-11-04T07:00:39.547251Z $PSXN,22,0.44,0.74*3A
seap 2017-11-04T07:00:39.802690Z $PSXN,23,-1.47,0.01,235.77,-0.38*34
seap 2017-11-04T07:00:41.081670Z $PSXN,20,1,0,0,0*3A
seap 2017-11-04T07:00:41.335040Z $PSXN,22,0.44,0.74*3A
seap 2017-11-04T07:00:41.590413Z $PSXN,23,-1.52,0.05,235.99,-0.39*35
seap 2017-11-04T07:00:31.383319Z $GPGGA,002705.69,3938.136133,S,03732.635753,W,1,09,1.0,-5.24,M,,M,,*64
seap 2017-11-04T07:00:33.174207Z $GPGGA,002706.69,3938.138360,S,03732.638933,W,1,09,1.0,-4.90,M,,M,,*66
seap 2017-11-04T07:00:34.950267Z $GPGGA,002707.69,3938.140620,S,03732.642016,W,1,09,1.0,-4.47,M,,M,,*60
seap 2017-11-04T07:00:36.738001Z $GPGGA,002708.69,3938.142856,S,03732.645094,W,1,09,1.0,-4.20,M,,M,,*6E
seap 2017-11-04T07:00:38.525747Z $GPGGA,002709.69,3938.144967,S,03732.648274,W,1,09,1.0,-4.14,M,,M,,*6C
seap 2017-11-04T07:00:40.313598Z $GPGGA,002710.69,3938.146908,S,03732.651523,W,1,09,1.0,-4.11,M,,M,,*67
seap 2017-11-04T07:00:42.097605Z $GPGGA,002711.69,3938.148700,S,03732.654753,W,1,10,0.9,-4.34,M,,M,,*69
seap 2017-11-04T07:00:12.255629Z $GPHDT,236.08,T*0A
seap 2017-11-04T07:00:14.043307Z $GPHDT,236.17,T*04
seap 2017-11-04T07:00:15.831022Z $GPHDT,236.00,T*02
seap 2017-11-04T07:00:17.618759Z $GPHDT,235.83,T*0A
seap 2017-11-04T07:00:19.402391Z $GPHDT,235.88,T*01
seap 2017-11-04T07:00:21.188320Z $GPHDT,236.04,T*06
seap 2017-11-04T07:00:17.363424Z $GPVTG,229.08,T,,M,12.2,N,,K,A*23
seap 2017-11-04T07:00:19.151129Z $GPVTG,228.96,T,,M,11.8,N,,K,A*2C
seap 2017-11-04T07:00:20.933065Z $GPVTG,228.71,T,,M,11.4,N,,K,A*29
seap 2017-11-04T07:00:22.720805Z $GPVTG,228.53,T,,M,11.1,N,,K,A*2C
seap 2017-11-04T07:00:24.508455Z $GPVTG,228.75,T,,M,11.0,N,,K,A*29
seap 2017-11-04T07:00:32.918751Z $GPZDA,002706.69,07,08,2014,,*62
seap 2017-11-04T07:00:34.696982Z $GPZDA,002707.69,07,08,2014,,*63
seap 2017-11-04T07:00:36.482615Z $GPZDA,002708.69,07,08,2014,,*6C
seap 2017-11-04T07:00:38.270328Z $GPZDA,002709.69,07,08,2014,,*6D
seap 2017-11-04T07:00:40.058070Z $GPZDA,002710.69,07,08,2014,,*65
seap 2017-11-04T07:00:41.845780Z $GPZDA,002711.69,07,08,2014,,*64""".split('\n')

S330_RECORDS = """s330 2017-11-04T05:12:21.511263Z $INZDA,000001.17,07,08,2014,,*79
s330 2017-11-04T05:12:21.765827Z $INGGA,000001.16,3934.833674,S,03727.698164,W,1,12,0.7,0.03,M,-3.04,M,,*6D
s330 2017-11-04T05:12:22.016470Z $INVTG,230.21,T,248.66,M,10.8,N,20.0,K,A*34
s330 2017-11-04T05:12:22.267012Z $INRMC,000001.16,A,3934.833674,S,03727.698164,W,10.8,230.21,070814,18.5,W,A*06
s330 2017-11-04T05:12:22.520671Z $INHDT,235.50,T*14
s330 2017-11-04T05:12:22.770997Z $PSXN,20,1,0,0,0*3A
s330 2017-11-04T05:12:23.022713Z $PSXN,22,-0.05,-0.68*32
s330 2017-11-04T05:12:23.274388Z $PSXN,23,-2.68,-2.25,235.50,-0.88*1D""".split('\n')

PCOD_RECORDS = """PCOD 2017-11-04T05:12:23.264356Z $GPGLL,3934.8363,S,03727.7011,W,000002.125,A*3A
PCOD 2017-11-04T05:12:23.518240Z $GPVTG,232.5,T,250.4,M,011.1,N,020.5,K*4D
PCOD 2017-11-04T05:12:23.768523Z $GPRMC,000002.125,A,3934.8363,S,03727.7011,W,011.1,232.5,221294,17.8,W*43
PCOD 2017-11-04T05:12:24.018771Z $GPZDA,000003.00,22,12,1994,00,00,*4F
PCOD 2017-11-04T05:12:24.274063Z $GPZDA,000004.00,22,12,1994,00,00,*48
PCOD 2017-11-04T05:12:24.529377Z $GPGGA,000003.125,3934.8376,S,03727.7041,W,1,06,1.4,031.1,M,004.1,M,,*67
PCOD 2017-11-04T05:12:24.782562Z $GPGLL,3934.8376,S,03727.7041,W,000003.125,A*3A
PCOD 2017-11-04T05:12:25.034354Z $GPVTG,235.4,T,253.2,M,008.8,N,016.2,K*4D
PCOD 2017-11-04T05:12:25.286072Z $GPRMC,000003.125,A,3934.8376,S,03727.7041,W,008.8,235.4,221294,17.8,W*44""".split('\n')

GP02_RECORDS = """gp02 2017-11-04T05:12:21.662148Z $GPZDA,000003,07,08,2014,7
gp02 2017-11-04T05:12:21.917365Z $GPGLL,3934.820,S,03727.675,W
gp02 2017-11-04T05:12:22.168517Z $GPVTG,229.9,T,,M,012.1,N,022.4,K
gp02 2017-11-04T05:12:22.422504Z $GPZDA,000004,07,08,2014,7
gp02 2017-11-04T05:12:22.675236Z $GPGLL,3934.822,S,03727.678,W
gp02 2017-11-04T05:12:22.927688Z $GPVTG,229.5,T,,M,012.3,N,022.8,K
gp02 2017-11-04T05:12:23.180968Z $GPZDA,000005,07,08,2014,7
gp02 2017-11-04T05:12:23.432572Z $GPGLL,3934.822,S,03727.678,W
gp02 2017-11-04T05:12:23.686738Z $GPVTG,229.5,T,,M,012.3,N,022.8,K
gp02 2017-11-04T05:12:23.939352Z $GPZDA,000006,07,08,2014,7
gp02 2017-11-04T05:12:24.192983Z $GPGLL,3934.827,S,03727.686,W
gp02 2017-11-04T05:12:24.448264Z $GPVTG,229.8,T,,M,011.9,N,022.1,K
gp02 2017-11-04T05:12:24.702250Z $GPZDA,000007,07,08,2014,7
gp02 2017-11-04T05:12:24.953273Z $GPGLL,3934.829,S,03727.690,W
gp02 2017-11-04T05:12:25.208551Z $GPVTG,230.2,T,,M,011.7,N,021.7,K
gp02 2017-11-04T05:12:25.458579Z $GPZDA,000008,07,08,2014,7
gp02 2017-11-04T05:12:25.713710Z $GPGLL,3934.831,S,03727.694,W
gp02 2017-11-04T05:12:25.968944Z $GPVTG,230.0,T,,M,011.8,N,021.9,K""".split('\n')

ADCP_RECORDS = """adcp 2017-11-04T05:12:21.270191Z $PUHAW,UVH,-7.44,-5.15,236.3
adcp 2017-11-04T05:12:21.521661Z $PUHAW,UVH,-7.38,-5.27,236.2
adcp 2017-11-04T05:12:21.772433Z $PUHAW,UVH,-7.16,-5.40,236.2
adcp 2017-11-04T05:12:22.022646Z $PUHAW,UVH,-7.10,-5.36,236.5
adcp 2017-11-04T05:12:22.272873Z $PUHAW,UVH,-7.07,-5.27,236.8
adcp 2017-11-04T05:12:22.526512Z $PUHAW,UVH,-7.14,-5.25,236.6
adcp 2017-11-04T05:12:22.779671Z $PUHAW,UVH,-7.45,-5.35,236.8""".split('\n')

ENG1_RECORDS = """eng1 2017-11-04T05:12:25.553228Z 12.25 19.70 507.5 569.0 240.5 -751.9 0 0 NAN NAN -11.5 -7.4
eng1 2017-11-04T05:12:25.806867Z 12.25 19.70 507.5 570.6 240.1 -751.9 0 0 NAN NAN -11.5 -7.4
eng1 2017-11-04T05:12:26.061740Z 12.25 19.70 507.5 573.8 239.1 -751.9 0 0 NAN NAN -11.5 -7.4
eng1 2017-11-04T05:12:26.314885Z 12.26 19.70 507.5 566.8 238.4 -751.9 0 0 NAN NAN -11.5 -7.4
eng1 2017-11-04T05:12:26.567011Z 12.25 19.70 507.5 572.8 239.1 -751.9 0 0 NAN NAN -11.5 -7.4
eng1 2017-11-04T05:12:26.819316Z 12.25 19.70 507.5 573.8 240.1 -751.9 0 0 NAN NAN -11.5 -7.4
eng1 2017-11-04T05:12:27.072111Z 12.25 19.70 507.5 571.4 240.2 -751.9 0 0 NAN NAN -11.5 -7.4
eng1 2017-11-04T05:12:27.832683Z 12.25 19.70 507.5 574.1 239.7 -751.9 0 0 NAN NAN -11.5 -7.4
eng1 2017-11-04T05:12:28.085470Z 12.25 19.70 287.1 567.3 239.6 -751.9 0 0 NAN NAN -11.5 -7.4
eng1 2017-11-04T05:12:28.335733Z 12.25 19.70 507.5 566.0 239.5 -751.9 0 0 NAN NAN -11.5 -7.4""".split('\n')

KNUD_RECORDS = """knud 2017-11-04T05:15:42.994693Z 3.5kHz,5188.29,0,,,,1500,-39.836439,-37.847002
knud 2017-11-04T05:15:43.250057Z 3.5kHz,5188.69,0,,,,1500,-39.836743,-37.847468
knud 2017-11-04T05:15:43.500259Z 3.5kHz,5189.04,0,,,,1500,-39.837049,-37.847935
knud 2017-11-04T05:15:43.753747Z 3.5kHz,5200.02,0,,,,1500,-39.837358,-37.848386
knud 2017-11-04T05:15:44.005004Z 3.5kHz,5187.60,0,,,,1500,-39.837664,-37.848836
knud 2017-11-04T05:15:44.260347Z 3.5kHz,5196.97,1,,,,1500,-39.837938,-37.849228
knud 2017-11-04T05:15:47.058222Z 3.5kHz,5185.91,0,,,,1500,-39.841175,-37.854183""".split('\n')

CWNC_RECORDS = """cwnc 2017-11-04T05:12:19.207411Z 01RD,2014-08-07T00:26:52.402,UPPER WF,-104.,-0000000,-05689.4,3323
cwnc 2017-11-04T05:12:19.457563Z 01RD,2014-08-07T00:26:52.453,UPPER WF,-104.,-0000000,-05689.4,3329
cwnc 2017-11-04T05:12:19.712122Z 01RD,2014-08-07T00:26:52.503,UPPER WF,-104.,-0000000,-05689.4,3325
cwnc 2017-11-04T05:12:19.967423Z 01RD,2014-08-07T00:26:52.553,UPPER WF,-104.,-0000000,-05689.4,3330
cwnc 2017-11-04T05:12:20.219647Z 01RD,2014-08-07T00:26:52.603,UPPER WF,-104.,-0000000,-05689.4,3326
cwnc 2017-11-04T05:12:20.472403Z 01RD,2014-08-07T00:26:52.654,UPPER WF,-104.,-0000000,-05689.4,3332
cwnc 2017-11-04T05:12:20.725199Z 01RD,2014-08-07T00:26:52.704,UPPER WF,-105.,-0000000,-05689.4,3329
cwnc 2017-11-04T05:12:20.977554Z 01RD,2014-08-07T00:26:52.754,UPPER WF,-105.,-0000000,-05689.4,3334""".split('\n')

PGUV_RECORDS = """pguv 2017-11-04T05:12:19.420136Z 080614 165956 .00024 3.576E-4 6.554E-4 -1.517E-3 1.099E-2 -5.338E-4 6.442E-8 5.456E-4 46.561 17.924
pguv 2017-11-04T05:12:19.671521Z 080614 170002 .00024 4.004E-4 6.677E-4 -1.522E-3 1.132E-2 -3.735E-4 6.365E-8 5.533E-4 46.584 17.924
pguv 2017-11-04T05:12:19.926825Z 080614 170003 .000238 3.843E-4 7.217E-4 -1.523E-3 1.086E-2 -4.86E-4 6.303E-8 5.53E-4 46.587 17.924
pguv 2017-11-04T05:12:20.177497Z 080614 170005 .00024 3.903E-4 7.116E-4 -1.501E-3 1.109E-2 -3.606E-4 6.337E-8 5.629E-4 46.591 17.924
pguv 2017-11-04T05:12:20.431905Z 080614 170006 .000238 4.234E-4 6.854E-4 -1.537E-3 1.103E-2 -3.102E-4 6.331E-8 5.596E-4 46.598 17.924
pguv 2017-11-04T05:12:20.687152Z 080614 170008 .00024 3.949E-4 7.126E-4 -1.556E-3 1.127E-2 -3.994E-4 6.285E-8 5.67E-4 46.6 17.924""".split('\n')

SVP1_RECORDS = """svp1 2017-11-04T05:12:20.245906Z  1611.31
svp1 2017-11-04T05:12:20.501188Z  1611.44
svp1 2017-11-04T05:12:20.754590Z  1611.44
svp1 2017-11-04T05:12:21.006557Z  1611.31
svp1 2017-11-04T05:12:21.261809Z  1611.31
svp1 2017-11-04T05:12:21.517091Z  1611.31
svp1 2017-11-04T05:12:21.772475Z  1611.44
svp1 2017-11-04T05:12:22.022673Z  1611.31""".split('\n')

TSG1_RECORDS = """tsg1 2017-11-04T05:12:19.511621Z  14.7989,  4.30728,  35.3236, 1506.416
tsg1 2017-11-04T05:12:19.764312Z  14.7996,  4.30722,  35.3225, 1506.417
tsg1 2017-11-04T05:12:20.018848Z  14.7987,  4.30718,  35.3229, 1506.414
tsg1 2017-11-04T05:12:20.269114Z  14.7989,  4.30714,  35.3223, 1506.414
tsg1 2017-11-04T05:12:20.524465Z  14.7986,  4.30709,  35.3222, 1506.413""".split('\n')

HDAS_RECORDS = """hdas 2017-11-04T05:12:19.747736Z 12.16954 16.81086 198.6207 3877.931 -1 30.5 47 34.5 40
hdas 2017-11-04T05:12:20.002331Z 12.16395 16.81086 182.069 3877.242 -1 30.5 47 34.5 40
hdas 2017-11-04T05:12:20.257642Z 12.16954 16.81086 189.6552 3875.862 -1 30.5 46.5 34.5 40""".split('\n')

MBDP_RECORDS = """mbdp 2017-11-04T05:12:26.085076Z $KIDPT,5130.92,7.10,12000.0*79
mbdp 2017-11-04T05:12:26.340356Z $KIDPT,5138.18,6.91,12000.0*7b
mbdp 2017-11-04T05:12:26.593493Z $KIDPT,5154.69,7.04,12000.0*7a
mbdp 2017-11-04T05:12:26.845608Z $KIDPT,5131.65,6.91,12000.0*78
mbdp 2017-11-04T05:12:27.098566Z $KIDPT,5126.80,7.32,12000.0*7d""".split('\n')

PCO2_RECORDS = """pco2 2017-11-04T05:12:20.269115Z 2014218.99930	 2579.13	   33.99	 1018.14	   45.93	  349.65	  345.74	   14.69	   14.73	    0.00	  Equil
pco2 2017-11-04T05:12:20.524470Z 2014219.00188	 2822.79	   34.02	 1018.13	   59.47	  397.63	  393.14	   14.79	   14.84	    1.00	  Atmos
pco2 2017-11-04T05:12:20.779866Z 2014219.00447	 2824.64	   34.04	 1018.52	   59.39	  398.00	  393.65	   14.83	   14.86	    1.00	  Atmos""".split('\n')

RTMP_RECORDS = """rtmp 2017-11-04T05:12:22.023266Z 14.6480
rtmp 2017-11-04T05:12:22.273528Z 14.6472
rtmp 2017-11-04T05:12:22.526939Z 14.6459
rtmp 2017-11-04T05:12:22.780126Z 14.6453""".split('\n')


def create_file(filename, lines, interval=0, pre_sleep_interval=0):
    time.sleep(pre_sleep_interval)
    logging.info('creating file "%s"', filename)
    f = open(filename, 'w')
    for line in lines:
        time.sleep(interval)
        f.write(line + '\n')
        f.flush()
    f.close()


@unittest.skip('The NMEAParser class is deprecated')
class TestNMEAParser(unittest.TestCase):

    ############################
    # To suppress resource warnings about unclosed files
    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)

    ############################
    def test_default_parser(self):

        p = NMEAParser()
        logging.debug('\n\nMessages: %s', pprint.pformat(p.messages))
        logging.debug('\n\nSensor Models: %s', pprint.pformat(p.sensor_models))
        logging.debug('\n\nMessages: %s', pprint.pformat(p.sensors))

        for records in [
            GYR1_RECORDS,
            GRV1_RECORDS,
            SEAP_RECORDS,
            S330_RECORDS,
            PCOD_RECORDS,
            GP02_RECORDS,
            ADCP_RECORDS,
            ENG1_RECORDS,
            KNUD_RECORDS,
            CWNC_RECORDS,
            PGUV_RECORDS,
            SVP1_RECORDS,
            TSG1_RECORDS,
            HDAS_RECORDS,
            MBDP_RECORDS,
            PCO2_RECORDS,
            RTMP_RECORDS,
        ]:
            for line in records:
                logging.info('line: %s', line)
                record = p.parse_record(line)
                logging.info('record: %s', str(record))

    ############################
    def test_parse_records(self):
        p = NMEAParser()

        r = p.parse_record(GYR1_RECORDS[0])
        self.assertEqual(r.data_id, 'gyr1')
        self.assertEqual(r.message_type, '$HEHDT')
        self.assertAlmostEqual(r.timestamp, 1510275606.739)
        self.assertDictEqual(r.fields, {'Gyro1HeadingTrue': 143.7})

        r = p.parse_record(GRV1_RECORDS[0])
        self.assertEqual(r.data_id, 'grv1')
        self.assertEqual(r.message_type, '')
        self.assertAlmostEqual(r.timestamp, 1510275606.572)
        self.assertDictEqual(r.fields, {'Grav1Error': 0, 'Grav1ValueMg': 24557})

        r = p.parse_record(SEAP_RECORDS[0])
        self.assertEqual(r.data_id, 'seap')
        self.assertEqual(r.message_type, '$PSXN-20')
        self.assertAlmostEqual(r.timestamp, 1509778839.291859)
        self.assertEqual(r.fields, {'Seap200HeightQual': 0,
                                    'Seap200RollPitchQual': 0,
                                    'Seap200HorizQual': 1,
                                    'Seap200HeadingQual': 0})

        r = p.parse_record(SEAP_RECORDS[1])
        self.assertEqual(r.data_id, 'seap')
        self.assertEqual(r.message_type, '$PSXN-22')
        self.assertAlmostEqual(r.timestamp, 1509778839.547251)
        self.assertEqual(r.fields, {'Seap200GyroOffset': 0.74,
                                    'Seap200GyroCal': 0.44})

        r = p.parse_record(SEAP_RECORDS[2])
        self.assertEqual(r.data_id, 'seap')
        self.assertEqual(r.message_type, '$PSXN-23')
        self.assertAlmostEqual(r.timestamp, 1509778839.802690)
        self.assertEqual(r.fields, {'Seap200Roll': -1.47,
                                    'Seap200HeadingTrue': 235.77,
                                    'Seap200Pitch': 0.01})

    ############################
    def test_parse_nmea(self):
        p = NMEAParser()

        (nmea, msg_type) = p.parse_nmea('Gyroscope', GYR1_RECORDS[0].split(' ')[2])
        logging.info('NMEA: %s: %s', msg_type, nmea)
        self.assertEqual(msg_type, '$HEHDT')
        self.assertDictEqual(nmea, {'HeadingTrue': 143.7, 'TrueConst': 'T'})

        (nmea, msg_type) = p.parse_nmea('Gravimeter',
                                        GRV1_RECORDS[0].split(' ', maxsplit=2)[2])
        self.assertEqual(msg_type, '')
        self.assertDictEqual(nmea, {'CounterUnits': 1, 'GravityError': 0,
                                    'GravityValueMg': 24557})

        (nmea, msg_type) = p.parse_nmea('Seapath200', SEAP_RECORDS[0].split(' ')[2])
        logging.info('NMEA: %s: %s', msg_type, nmea)
        self.assertEqual(msg_type, '$PSXN-20')
        self.assertDictEqual(nmea, {'HeightQual': 0, 'RollPitchQual': 0,
                                    'HorizQual': 1, 'HeadingQual': 0})

        (nmea, msg_type) = p.parse_nmea('Seapath200', SEAP_RECORDS[1].split(' ')[2])
        logging.info('NMEA: %s: %s', msg_type, nmea)
        self.assertEqual(msg_type, '$PSXN-22')
        self.assertDictEqual(nmea, {'GyroCal': 0.44, 'GyroOffset': 0.74})

        (nmea, msg_type) = p.parse_nmea('Seapath200', SEAP_RECORDS[2].split(' ')[2])
        logging.info('NMEA: %s: %s', msg_type, nmea)
        self.assertEqual(msg_type, '$PSXN-23')
        self.assertDictEqual(nmea, {'Roll': -1.47, 'HeadingTrue': 235.77,
                                    'Pitch': 0.01, 'Heave': -0.38})


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

    LOG_LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    args.verbosity = min(args.verbosity, max(LOG_LEVELS))
    logging.getLogger().setLevel(LOG_LEVELS[args.verbosity])

    # logging.getLogger().setLevel(logging.DEBUG)
    unittest.main(warnings='ignore')
