#!/usr/bin/env python3
"""
Outputs text for a subsample logger of all variables defined in whatever
device definition file it's handed. Reads from CDS (CachedDataServer), 
writes averages back to CDS and specified logfile.
"""

import pprint
import sys
import yaml

DATA_SERVER = 'localhost:8766'
WINDOW = 60  # Number of seconds to average
LOGFILE_BASE = '/var/data/openrvdas/proc/snapshot_%d' % WINDOW 

# Whether variable should be numerical average or nearest neighbor;
# commented out to omit variable entirely.
FIELDS = {
  'AirTemp': 'boxcar_average',
  'AvgWindDir': 'boxcar_average',
  'AvgWindSpeed': 'boxcar_average',
  #'BeamC': 'boxcar_average',
  'CNAVAntennaHeight': 'nearest',
  'CNAVCourseMag': 'boxcar_average',
  'CNAVCourseTrue': 'boxcar_average',
  #'CNAVDGPSStationID': 'nearest',
  'CNAVEorW': 'nearest',
  'CNAVFixQuality': 'nearest',
  'CNAVGPSDay': 'nearest',
  'CNAVGPSMonth': 'nearest',
  'CNAVGPSTime': 'nearest',
  'CNAVGPSTime': 'nearest',
  'CNAVGPSYear': 'nearest',
  #'CNAVGeoidHeight': 'nearest',
  'CNAVGyroCal': 'nearest',
  'CNAVGyroOffset': 'nearest',
  #'CNAVHDOP': 'nearest',
  'CNAVHeadingQual': 'nearest',
  'CNAVHeadingTrue': 'boxcar_average',
  'CNAVHeave': 'boxcar_average',
  'CNAVHeightQual': 'nearest',
  'CNAVHorizQual': 'nearest',
  #'CNAVLastDGPSUpdate': 'nearest',
  'CNAVLatitude': 'boxcar_average',
  'CNAVLocalHours': 'nearest',
  'CNAVLocalZone': 'nearest',
  'CNAVLongitude': 'boxcar_average',
  'CNAVMode': 'nearest',
  'CNAVNorS': 'nearest',
  'CNAVNumSats': 'boxcar_average',
  'CNAVPitch': 'boxcar_average',
  'CNAVRoll': 'boxcar_average',
  'CNAVRollPitchQual': 'nearest',
  'CNAVSpeedKm': 'boxcar_average',
  'CNAVSpeedKt': 'boxcar_average',
  'Conductivity': 'boxcar_average',
  'CorrectedRawCounts': 'boxcar_average',
  'FlowthroughTemp': 'boxcar_average',
  'FluorometerSignalCounts': 'boxcar_average',
  'GyroHeadingTrue': 'boxcar_average',
  'GyroRateOfTurn': 'boxcar_average',
  'KnudDepthHF': 'boxcar_average',
  'KnudDepthLF': 'boxcar_average',
  #'KnudHF': 'nearest',
  #'KnudLF': 'nearest',
  'KnudLatitude': 'boxcar_average',
  'KnudLongitude': 'boxcar_average',
  'KnudSoundSpeed': 'boxcar_average',
  'KnudValidHF': 'nearest',
  'KnudValidLF': 'nearest',
  'MaxWindSpeed': 'boxcar_average',
  'POSMVAntennaHeight': 'nearest',
  'POSMVCourseMag': 'boxcar_average',
  'POSMVCourseTrue': 'boxcar_average',
  #'POSMVDGPSStationID': 'nearest',
  'POSMVEorW': 'nearest',
  'POSMVFixQuality': 'nearest',
  'POSMVGPSDay': 'nearest',
  'POSMVGPSMonth': 'nearest',
  'POSMVGPSTime': 'nearest',
  'POSMVGPSYear': 'nearest',
  'POSMVGPSYear2': 'nearest',
  #'POSMVGeoidHeight': 'nearest',
  #'POSMVGyroCal': 'nearest',
  #'POSMVGyroOffset': 'nearest',
  #'POSMVHDOP': 'nearest',
  'POSMVHeadingQual': 'nearest',
  'POSMVHeadingTrue': 'boxcar_average',
  'POSMVHeave': 'boxcar_average',
  'POSMVHeightQual': 'nearest',
  'POSMVHorizQual': 'nearest',
  'POSMVLastDGPSUpdate': 'nearest',
  'POSMVLatitude': 'boxcar_average',
  'POSMVLocalHours': 'nearest',
  'POSMVLocalZone': 'nearest',
  'POSMVLongitude': 'boxcar_average',
  #'POSMVMode': 'nearest',
  'POSMVNorS': 'nearest',
  'POSMVNumSats': 'nearest',
  'POSMVPitch': 'boxcar_average',
  'POSMVRoll': 'boxcar_average',
  'POSMVRollPitchQual': 'nearest',
  'POSMVSpeedKm': 'boxcar_average',
  'POSMVSpeedKt': 'boxcar_average',
  'Pressure': 'boxcar_average',
  'RH': 'boxcar_average',
  'RainAccumulation': 'boxcar_average',
  'RainIntensity': 'boxcar_average',
  'ReferenceCounts': 'boxcar_average',
  'SBE48Date': 'nearest',
  'SBE48Temp': 'boxcar_average',
  'SBE48Time': 'nearest',
  'Salinity': 'boxcar_average',
  #'SerialNumber': 'nearest',
  'SignalCounts': 'boxcar_average',
  'SoundVelocity': 'boxcar_average',
  'ThermisterCounts': 'boxcar_average',
  'UnderwayFlowRate': 'boxcar_average',
  'UnderwayFlowVolume': 'boxcar_average',
}

field_spec = {}
for field, method in FIELDS.items():
  dest = 'Avg' + field
  field_spec[dest] = {
    'source': field,
    'algorithm': { 'type': method }
  }
  if method == 'boxcar_average':
    field_spec[dest]['algorithm']['window'] = WINDOW

snapshot_logger = {
  'snapshot->off': {
    'name': 'snapshot->off',
  },
  'snapshot->on': {
    'name': 'snapshot->on',
    'readers': [{
      'class': 'CachedDataReader',
      'kwargs': {
        'data_server': DATA_SERVER,
        'subscription': {
          'fields': {f:{'seconds': 0} for f in FIELDS}
        }
      }
    }],
    'transforms': [{
      'class': 'InterpolationTransform',
      'module': 'local.alucia.modules.interpolation_transform',
      'kwargs': {
        'interval': WINDOW,
        'window': WINDOW,
        'metadata_interval': 6 * WINDOW,
        'field_spec': field_spec
      }
    }],
    'writers': [{
      'class': 'CachedDataWriter',
      'kwargs': {
        'data_server': DATA_SERVER,
      }
    },
                
    {
      'class': 'TextFileWriter',
      'kwargs': {
        'filename': LOGFILE_BASE,
        'split_by_date': 'true'
      }
    }
    ],
  }
}


print(yaml.dump(snapshot_logger))
  
#pprint.pprint(snapshot_logger)
