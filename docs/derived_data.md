# Derived Data Loggers

A typical logger will receive its raw data via a serial port, or a network attached sensor. But many ships rely on derived values as well, e.g. combining relative wind speed and direction with vessel heading, course and speed to compute a true wind speed and direction.

The recommended way of achieving this with OpenRVDAS is with derived data loggers. Typically, a derived data logger will take values from, say, a cached data server, compute new values, and output them back to the same cached data server. To implement the true wind example above, we retrieve the desired values and feed them into a [TrueWindsTransform](../logger/transforms/true_winds_transform.py), a subclass of the generic [DerivedDataTransform](../logger/transforms/derived_data_transform.py):

```
  true_wind->on:
    name: true_wind->on
    # Get values we need from cached data server
    readers:
      class: CachedDataReader
      kwargs:
        data_server: localhost:8766
        subscription:
          fields:
            S330CourseTrue:
              seconds: 0
            S330HeadingTrue:
              seconds: 0
            S330SpeedKt:
              seconds: 0
            MwxPortRelWindDir:
              seconds: 0
            MwxPortRelWindSpeed:
              seconds: 0
            
    transforms:
    - class: TrueWindsTransform
      kwargs:
        wind_dir_field: MwxPortRelWindDir     # What field to use for wind dir
        wind_speed_field: MwxPortRelWindSpeed # "       "       "     wind speed
        course_field: S330CourseTrue          # "       "       "     ship course
        heading_field: S330HeadingTrue        # "       "       "     ship heading
        speed_field: S330SpeedKt              # "       "       "     ship speed

        convert_speed_factor: 0.5144          # Convert ship speed from kt to m/s
        update_on_fields:                     # Output new value when we get an
        - MwxPortRelWindDir                   # update from one of these fields

        apparent_dir_name: PortApparentWindDir  # What to call the apparent wind output
        true_dir_name: PortTrueWindDir          # "       "     "  true wind dir output
        true_speed_name: PortTrueWindSpeed      # "       "     "  true wind speed output

    # Send output back to cached data server
    writers:
    - class: CachedDataWriter
      kwargs:
        data_server: localhost:8766
```

The other widely-useful derived data transform that is available is the SubsampleTransform. One may want to plot a smoothed version of a noisy data stream, or save a compact 10-minute snapshot average. The SubsampleTransform is designed specifically for this.

```
  subsample->on:
    name: subsample->on
    
    # Request the fields we want from cached data server
    readers:
      class: CachedDataReader
      kwargs:
        data_server: localhost:8766
        subscription:
          fields:
            PortTrueWindDir:
              seconds: 0
            PortTrueWindSpeed:
              seconds: 0
            StbdTrueWindDir:
              seconds: 0
            StbdTrueWindSpeed:
              seconds: 0

    # For each field we're subsampling, key on name of field to subsample
    # and specify what the subsampled output should be called, and what 
    # algorithm to apply to subsample it.
    transforms:
    - class: SubsampleTransform
      kwargs:
        back_seconds: 3600     # Retain this many seconds of back data
        metadata_interval: 20  # Send metadata every 20 seconds
        field_spec:
          PortTrueWindDir:              # What field to subsample
            output: AvgPortTrueWindDir  # What to call the subsampled output
            subsample:
              type: boxcar_average      # Use 'boxcar' averaging
              window: 10                # Use a window 10 seconds wide
              interval: 10              # Output an average every 10 seconds
          PortTrueWindSpeed:
            output: AvgPortTrueWindSpeed
            subsample:
              type: boxcar_average
              window: 10
              interval: 10
          StbdTrueWindDir:
            output: AvgStbdTrueWindDir
            subsample:
              type: boxcar_average
              window: 10
              interval: 10
          StbdTrueWindSpeed:
            output: AvgStbdTrueWindSpeed
            subsample:
              type: boxcar_average
              window: 10
              interval: 10

    # Write results back to the cached data server
    writers:
    - class: CachedDataWriter
      kwargs:
        data_server: localhost:8766        
```

The value associated with the 'subsample' key should be a dict that will be passed to [logger/utils/subsample.py](./logger/utils/subsample.py). At present, only 'boxcar_average' is defined, but the subsampling code is designed to make it easy to add other algorithms, such as Gaussian smoothing and linear and higher-order interpolations. Contributions to this code base would be very welcome.
