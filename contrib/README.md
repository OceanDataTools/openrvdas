# How to Use the 'contrib/' Directory

__NOTE:__ This directory and the current instructions are maintained for compatibility reasons, but as of 2024-10-01, the preferred way to contribute code to OpenRVDAS is to open pull requests to the [openrvdas_contrib](https://github.com/OceanDataTools/openrvdas_contrib) repository.
----

In short, this is where you should put code that you wish to
contribute to the OpenRVDAS project.

This differs from the 'local/' directory in that local/ is for
definitions, configurations and code specific to a particular ship,
project and/or organization. The contrib/ directory is intended for
code that the author believes may be of use outside their specific
project. Code from contrib/ that proves especially useful may be
incorporated into the core OpenRVDAS structure.

Below, we propose a directory structure that should prevent file
collisions:

```
  contrib/
    my_project/          - Project/individual/organization, e.g. coriolix, pablo68, etc.
      database/          - Mimic the structure of top-level OpenRVDAS with your code
      logger/            - "   "
      utils/             - "   "
```

Note that Reader/TransformWriter code placed in the contrib/ directory may be incorporated at runtime by a listener by using the ``module`` declaration in the logger configuration:

```
    readers:
      # Code in contrib/my_project/readers/custom_reader.py
      class: MyCustomReader
      module: contrib.my_project.readers.custom_reader
      kwargs:
        host_port: 'host_port:8174'
        interval: 5
        
    writers:
      # Code in contrib/my_project/writers/custom_writer.py
      class: MyCustomWriter
      module: contrib.my_project.writers.custom_writer
      kwargs:
        base_path: '/var/tmp/log/custom_writer'
```

In general, we recommend that any organization or ship using OpenRVDAS
create their own branch or fork of the code to allow them to
selectively merge OpenRVDAS code updates as they see fit. Following
the above structure will simplify the process.

