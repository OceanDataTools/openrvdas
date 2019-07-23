# How to Use the 'local/' Directory

In short, this is where you should put anything/everything specific to
your ship, project and/or organization. Nowhere else.

Below, we propose a directory structure that should prevent file
collisions if you ever hope to share or make use of definitions or
configurations from other organizations:

```
  local/
    devices/             - Definitions for widely-used device types (SeaPath, Garmin, etc.)
    <your org or ship>/  - Subdirectory for device and cruise definitions specific to your org
      devices/             - Device types and physical devices specific to your org
      <cruise id>/         - Directory for files specific to cruise a specific cruise
        devices/                - (optional) Device definitions specific to this particular cruise
        <cruise_id>_cruise.yaml - Cruise definition file for this cruise
        ...                     - Other files for this specific cruise
```
For example, 
```
  local/
    devices/   - Definitions for widely-used device types (SeaPath, Garmin, etc.)
    
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
      
    sikuliaq/
      ...
```
In general, we recommend that any organization or ship using OpenRVDAS
create their own branch or fork of the code to allow them to
selectively merge OpenRVDAS code updates as they see fit. Following
the above structure will simplify the process

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
