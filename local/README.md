# Where did all the code go?

Initially, we encouraged OpenRVDAS users to put their institution and
vessel-specific code and configurations in this directory. We now encourage
users instead to put their code into a separate repository and link it into
this directory, as described below.

All of the files that were formerly stored in this directory can now be
found in separate repositories at https://github.com/OceanDataTools. If
you wish to use some of those files, please check them out and link them
in as described below.

# How to Use the 'local/' Directory

In short, this is where you should put symbolic links to the code specific
to your project. There should be little, if any, actual code in this directory.

For example, if you work for University of Upper Windsock and have code for
your ship, the M/V Plunger, you would probably create a UUW repository with
university-wide code and definitions and a 'mvp' subdirectory for ship-specific
code and definitions (see below for suggested structure).

Assuming OpenRVDAS is checked out into `/opt/openrvdas`, you might then check
your repository out into `/opt/oceandatatools_local/uww`, creating a symbolic
link as follows:
```
ln -s /opt/oceandatatools_local/uww /opt/openrvdas/local
```
This will allow you to reference your institution's and ship's configurations
and data as though they were subdirectories under `local`, without clogging
the original repository with institution/ship-specific files.

The effective file structure should look something like:
```
  local/
    <your org or ship>/  - Subdirectory for device and cruise definitions specific to your org
      devices/             - Device types and physical devices specific to your org
      modules/             - Readers, transforms and writers specific to your org
      <cruise id>/         - Directory for files specific to cruise a specific cruise
        devices/                - (optional) Device definitions specific to this particular cruise
        <cruise_id>_cruise.yaml - Cruise definition file for this cruise
        ...                     - Other files for this specific cruise
```
For example, 
```
  local/
    devices/   - Definitions for widely-used device types (SeaPath, Garmin, etc.)
    usap/
      nbp/       - Subdirectory for device and cruise definitions for the NB Palmer
        devices/   - Device types and physical devices specific to the NB Palmer
        NBP1906/   - Files specific to cruise NBP1406
          devices/   - If there are any devices specific to cruise NBP1906
          NBP1906_cruise.yaml - Cruise definition file for NBP1906
          NBP1906_winch.yaml  - If you want to have a separate instance for monitoring winches
        NBP1907/   - Files specific to cruise NBP1907
          ...
            
      lmg/       - Subdirectory for the Lawrence M. Gould
        devices/   -  Device types and physical devices specific to the LM Gould
        LMG1903/   - Files specific to cruise LMG1903
          LMG_1903_cruise.yaml - Cruise definition file for LMG1903
      ...

```

## Local Device/Device Type Definitions

By default, the parser transform (class ``ParseTransform``) will look
for device and device type definitions in ``local/devices/*.yaml``. If
you wish to also use devices/device types defined in any other
directories, you can specify the path in the config file in which you
specify the parser:
```
   readers:
     class: UDPReader
     kwargs:
       port: 6224
   transforms:
     class: ParseTransform
     kwargs:
       definition_path: local/devices/*.yaml,local/devices/nbp/devices/*.yaml
   writers:
     class: UDPWriter
     kwargs:
       port: 6225
```
If invoked from the command line with the ``listen.py`` script, use
the ``--parse_definition_path`` argument (lexically __before__ the
parser transform) on the command line:
```
  logger/listener/listen.py \
      --udp 6224 \
      --parse_definition_path "local/devices/*.yaml,local/devices/nbp/devices/*.yaml" \
      --transform_parse \
      --write_udp 6225
```
