# Notes for RCRV-specific code
__DRAFT 2020-07-23__

RCRV-specific code consists of two primary components:

 1. A project-specific CORIOLIXWriter module in
 ``local/rcrv/modules/coriolix-writer.py``
 
 2. A script (``build_cruise_definition.py``) that connects to a
 CORIOLIX database to retrieve sensor and parameter definitions and
 reads a local template file (such as the sample at
 ``config_template.yaml``) and creates an OpenRVDAS cruise definition
 file that can be loaded and run by the OpenRVDAS Logger Manager.

There are ancillary pieces of code, such as a ``setup.sh`` script that
configures ``supervisord`` to run the ``build_cruise_definition.py``
script when cued and allows it to be invoked via an HTTP call. There
is also a ``settings.py.dist`` file that serves as a template for the
settings that the CORIOLIXWriter will need in order to read/write the
database.

## Prior to running a cruise definition

The file ``settings.py.dist`` in this directory must be copied over to
``settings.py`` prior to running anything that depends on a
CORIOLIXWriter.  Modify the variables declared in ``settings.py`` to
refect the desired setup.

## Prior to creating a cruise definition

The file ``config_template.yaml.dist`` in this directory must be
copied over to ``config_template.yaml`` prior to creating an OpenRVDAS
configuration file using the ``build_cruise_definition.py`` script.

## Manually creating a new cruise definition file

The script for creating a cruise definition may be invoked as follows:

```
  venv/bin/python local/rcrv/build_cruise_definition.py \
    --template local/rcrv/config_template.yaml \
    --host_path http://157.245.173.52:8000/api/ \
    --destination /opt/openrvdas/local/rcrv/cruise.yaml \
    -v
```

The script will read templates and variables from
``local/rcrv/config_template.yaml`` to figure out what configs and
modes to create and attempt to connect to a CORIOLIX database at
``http://157.245.173.52:8000/api/``.

## Creating a new cruise definition whenever anything changes

If you wish the script to periodically check the CORIOLIX database and
generate a new cruise definition when it detects changes or when the
``config_template.yaml`` file changes, add the ``--interval``
argument, e.g. ``--interval 10`` to check every ten seconds:

```
  venv/bin/python local/rcrv/build_cruise_definition.py \
    --template local/rcrv/config_template.yaml \
    --host_path http://157.245.173.52:8000/api/ \
    --destination /opt/openrvdas/local/rcrv/cruise.yaml \
    --interval 10 \
    -v
```

## Updating via HTTP call

If you wish to be able to generate/update the cruise definition via an
http call, you should run ``setup.sh`` in this directory after
OpenRVDAS has been fully installed and set up. This will create an entry in the OpenRVDAS-specific supervisord config file\* that will allow running the build script either directly through the supervisorctl command line interface or via HTTP.

\* (This file is locate in ``/etc/supervisor/conf.d/openrvdas.conf`` in Ubuntu, ``/etc/supervisord.d/openrvdas.ini`` in CentOS/RedHat and ``/usr/local/etc/supervisor.d/openrvdas.ini`` in MacOS).


Once the setup script has been run, you can trigger the script from the command line via

```
supervisorctl start build_cruise_definition
```

You can also trigger it via HTTP using a call to supervisord's web interface:

```
wget -O - 'http://localhost:9001/index.html?processname=build_cruise_definition&action=start' > /dev/null
```

## What happens next

The Logger Manager periodically checks the file modification time of
the cruise definition file that it has most recently loaded.

If you have an OpenRVDAS logger console open in a browser when the
cruise definition file is updated, the Logger Manager will raise an
alert next to the 'Load new definition' button saying the loaded file
has been changed, and asking if you want to reload it. Note that
reloading will only restart those loggers whose current configuration
definition has changed. Other loggers will continue to run
uninterrupted.

If you are interacting with the Logger Manager via the command line
interface, there will be no alert when a cruise definition file
changes, but you can still manually reload the file (with the same
behavior that only changed loggers will be restarted) via the
``reload_configuration`` command.

## Customizing the config_template.yaml file

The ``config_template.yaml.dist`` file, when copied over into
``config_template.yaml``, will produce what - as of this writing - is
a fully-functional cruise definition.

As specifications change or special cases need to be added, this file
may be modified as needed. Documentation for modifying the template
components may be found inside the file itself.