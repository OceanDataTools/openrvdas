# NMEA 0183 device types

Parse definitions for standard NMEA 0183 sentences, grouped by kind of device. Each device type has both the standard NMEA sentences and the proprietary (vendor-specific) sentences commonly sent by that kind of device.

`logger/devices/NMEA_0183.yaml` includes every file in this directory, so a `definition_path` or `includes:` entry that names `NMEA_0183.yaml` gets all of them. To load only some, name the individual files instead:

```yaml
includes:
  - logger/devices/nmea_0183/gps.yaml
  - logger/devices/nmea_0183/mru.yaml
```

Use either `NMEA_0183.yaml` or the files here, not both. Loading a device type twice works, but logs `Duplicate device_type definition` for each one. This is also why these files are in a subdirectory: the default definition path, `logger/devices/*.yaml`, matches `NMEA_0183.yaml` but not the files here.

| File | Device types | For |
|---|---|---|
| `gps.yaml` | `NMEA_GPS`, `NMEA_GPS_Signed` | GPS/GNSS receivers |
| `gps_ins.yaml` | `NMEA_GPS_INS`, `NMEA_GPS_INS_Signed` | Integrated GPS/INS systems (Seapath, etc.): position, heading and motion |
| `mru.yaml` | `NMEA_MRU` | Standalone heading sensors, gyrocompasses and MRUs |
| `depth.yaml` | `NMEA_Depth` | Depth sounders, echo sounders, multibeam |
| `speed.yaml` | `NMEA_Speed` | Speed logs, Doppler logs, ADCPs |
| `wind.yaml` | `NMEA_Wind` | Anemometers and wind sensors |
| `meteo.yaml` | `NMEA_Meteo` | Weather stations, TSGs, temperature sensors |
| `autopilot.yaml` | `NMEA_Autopilot`, `NMEA_Autopilot_Signed` | Autopilots and navigation computers |
| `rudder.yaml` | `NMEA_Rudder` | Rudder angle indicators |
| `ais.yaml` | `NMEA_AIS` | AIS receivers |
| `radar.yaml` | `NMEA_Radar`, `NMEA_Radar_Signed` | Radar and ARPA target tracking |
| `usbl.yaml` | `NMEA_USBL` | USBL/SSBL underwater positioning |
| `winch.yaml` | `NMEA_Winch` | Winch and wire monitoring systems |

## Signed positions

The `*_Signed` device types (#718) are the device types they're named after, except that positions are parsed with `nlat_dir`. So latitude and longitude come out in signed decimal degrees, negative for South and West, and there are no separate `NorS`/`EorW` (or `DestNorS`/`DestEorW`) fields. Use one when anything downstream needs a real position, such as a geofence, a map or a distance, so that it doesn't have to recombine each value with its hemisphere first. Without a position fix, latitude and longitude are None.

They're built with YAML merge keys (`<<: *NMEA_GPS_format`): every sentence is the original device type's, and only the sentences that carry a position are overridden. So a change to any other sentence needs making only once, in the original. Two consequences:

- **Each `*_Signed` type must stay in the same file as its original.** YAML anchors only work within one file.
- **The merged `fields` lists still describe `NorS` and `EorW`,** which these device types never produce, because merge keys can't remove keys.

## Format types

These come from `logger/utils/record_parser_formats.py` and the [parse](https://pypi.org/project/parse/) library:

| Type | Matches |
|---|---|
| `d` | integer |
| `f` | float |
| `g` | generalized number (int or float) |
| `w` | word (letters, numbers, underscore) |
| `x` | hexadecimal |
| `od` | optional integer |
| `of` | optional float |
| `og` | optional generalized number |
| `ow` | optional word |
| `os` | optional string (matches everything) |
| `nlat` | NMEA latitude or longitude (DDDMM.MMMM), converted to decimal degrees; the hemisphere is a separate field |
| `nlat_dir` | NMEA latitude or longitude together with its hemisphere field (`4317.0146,S`), converted to signed decimal degrees |
| `nc` | any text that is not a comma |
| `ns` | any text that is not an asterisk |

**Talker IDs:** the `{:2l}` pattern matches any 2-letter talker ID (GP, GN, GL, etc.).

**Proprietary sentence prefixes:** `$Pxxx` sentences are vendor-specific (ASH = Ashtech, GRM = Garmin, KEL = Knudsen, etc.).
