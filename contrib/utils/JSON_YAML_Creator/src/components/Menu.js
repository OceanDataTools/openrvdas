import React, { useState } from 'react';
import '../App.css';
import './index.css';
import { Dropdown, Button } from 'react-bootstrap';
import JSONYAMLOutput from './JSONYAMLOutput';
import KWArgs from './KWArgs';

function YAML() {
  // Chosen reader in the main dropdown menu
  const [reader, setReader] = useState('');

  // Chosen transform in the main dropdown menu
  const [transform, setTransform] = useState('');

  // Chosen writer in the main dropdown menu
  const [writer, setWriter] = useState('');

  // Array of readers
  const [allReaders, setAllReaders] = useState([]);
  // Array of transforms
  const [allTransforms, setAllTransforms] = useState([]);
  // Array of writers
  const [allWriters, setAllWriters] = useState([]);

  // Reader KWargs
  const [allReaderKwargs, setReaderAllKwargs] = useState([]);
  const [allTransformKwargs, setTransformAllKwargs] = useState([]);
  const [allWriterKwargs, setWriterAllKwargs] = useState([]);

  // Triggers when a kwarg is added for any reader
  const readerKwargCallback = (val) => {
    let obj = allReaders.find((o) => o.class === reader.replace(/\s/g, ''));
    let kw = {};
    kw[val[1]] = val[2];
    kw.kwargClass = val[0];
    const arrayCopy = allReaderKwargs.filter((ob) => ob.kwargClass === val[0]);

    if (obj.hasOwnProperty('kwargs')) {
      let exists = false;
      for (let i = 0; i < arrayCopy.length; i++) {
        console.log(JSON.stringify(arrayCopy[i]));
        if (
          arrayCopy[i].hasOwnProperty(val[1]) &&
          arrayCopy[i].kwargClass === val[0]
        ) {
          exists = true;
        }
      }
      if (!exists) {
        arrayCopy.push(kw);
      }
    } else {
      arrayCopy.push(kw);
    }
    obj.kwargs = arrayCopy;
    setReaderAllKwargs(arrayCopy);
  };

  // Triggers when a kwarg is added for any transform
  const transformKwargCallback = (val) => {
    let obj = allTransforms.find(
      (o) => o.class === transform.replace(/\s/g, '')
    );
    let kw = {};
    kw[val[1]] = val[2];
    kw.kwargClass = val[0];
    const arrayCopy = allTransformKwargs.filter(
      (ob) => ob.kwargClass === val[0]
    );
    if (obj.hasOwnProperty('kwargs')) {
      let exists = false;
      for (let i = 0; i < arrayCopy.length; i++) {
        console.log(JSON.stringify(arrayCopy[i]));
        if (
          arrayCopy[i].hasOwnProperty(val[1]) &&
          arrayCopy[i].kwargClass === val[0]
        ) {
          exists = true;
        }
      }
      if (!exists) {
        arrayCopy.push(kw);
      }
    } else {
      arrayCopy.push(kw);
    }
    obj.kwargs = arrayCopy;
    setTransformAllKwargs(arrayCopy);
  };

  // Triggers when a kwarg is added for any writer EXCEPT Composed Writer
  const writerKwargCallback = (val) => {
    let obj = allWriters.find((o) => o.class === writer.replace(/\s/g, ''));
    let kw = {};
    kw[val[1]] = val[2];
    kw.kwargClass = val[0];
    const arrayCopy = allWriterKwargs.filter((ob) => ob.kwargClass === val[0]);

    if (obj.hasOwnProperty('kwargs')) {
      let exists = false;
      for (let i = 0; i < arrayCopy.length; i++) {
        console.log(JSON.stringify(arrayCopy[i]));
        if (
          arrayCopy[i].hasOwnProperty(val[1]) &&
          arrayCopy[i].kwargClass === val[0]
        ) {
          exists = true;
        }
      }
      if (!exists) {
        arrayCopy.push(kw);
      }
    } else {
      arrayCopy.push(kw);
    }
    obj.kwargs = arrayCopy;
    setWriterAllKwargs(arrayCopy);
  };

  const readerChange = (e) => {
    setReader(e.target.innerHTML);
  };

  const transformChange = (e) => {
    setTransform(e.target.innerHTML);
  };

  const writerChange = (e) => {
    setWriter(e.target.innerHTML);
  };

  const generateJSONXML = async (e) => {
    e.preventDefault();
  };

  const handleClickReader = (e) => {
    let r = { class: reader.replace(/\s/g, '') };
    setAllReaders((arr) => [...arr, r]);
  };
  const handleClickTransform = (e) => {
    let r = { class: transform.replace(/\s/g, '') };
    setAllTransforms((arr) => [...arr, r]);
  };
  const handleClickWriter = (e) => {
    let r = { class: writer.replace(/\s/g, '') };
    setAllWriters((arr) => [...arr, r]);
  };

  const divStyle = {
    display: 'flex',
    alignItems: 'center',
  };
  return (
    <div className='blue-container p-3 my-3 text-white border'>
      <div className='blue-container-text'>
        <form onSubmit={(e) => generateJSONXML(e)}>
          <div className='container'>
            <div className='row'>
              <div className='col-sm'>
                <h1 style={divStyle}>Readers</h1>
                <div className='form-group' id='reader' style={divStyle}>
                  <Dropdown>
                    <Dropdown.Toggle variant='success' id='dropdown-basic'>
                      {reader.length > 0 ? reader : 'Please Select a Reader'}
                    </Dropdown.Toggle>

                    <Dropdown.Menu>
                      <Dropdown.Item href='#/action-1' onClick={readerChange}>
                        Cached Data Reader
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-2' onClick={readerChange}>
                        Composed Reader
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-3' onClick={readerChange}>
                        Database Reader
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-4' onClick={readerChange}>
                        Logfile Reader
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-5' onClick={readerChange}>
                        MQTT Reader
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-6' onClick={readerChange}>
                        Network Reader
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-7' onClick={readerChange}>
                        Polled Serial Reader
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-8' onClick={readerChange}>
                        Redis Reader
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-9' onClick={readerChange}>
                        Serial Reader
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-10' onClick={readerChange}>
                        Timeout Reader
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-11' onClick={readerChange}>
                        UDP Reader
                      </Dropdown.Item>
                    </Dropdown.Menu>
                  </Dropdown>
                  <Button
                    className='addButton'
                    variant='outline-primary'
                    onClick={handleClickReader}
                  >
                    Add
                  </Button>{' '}
                </div>
                {allReaders.some((e) => e.class === 'CachedDataReader') &&
                reader === 'Cached Data Reader' ? (
                  <KWArgs
                    kwargCallback={readerKwargCallback}
                    items={['data_server', 'subscription']}
                    kwClass={'CachedDataReader'}
                  />
                ) : null}
                {allReaders.some((e) => e.class === 'LogfileReader') &&
                reader === 'Logfile Reader' ? (
                  <KWArgs
                    kwargCallback={readerKwargCallback}
                    items={[
                      'filebase',
                      'tail',
                      'refresh_file_spec',
                      'retry_interval',
                      'interval',
                    ]}
                    kwClass={'LogfileReader'}
                  />
                ) : null}
                {allReaders.some((e) => e.class === 'MQTTReader') &&
                reader === 'MQTT Reader' ? (
                  <KWArgs
                    kwargCallback={readerKwargCallback}
                    items={['channel']}
                    kwClass={'MQTTReader'}
                  />
                ) : null}
                {allReaders.some((e) => e.class === 'ComposedReader') &&
                reader === 'Composed Reader' ? (
                  <KWArgs
                    kwargCallback={readerKwargCallback}
                    items={['reader', 'readers', 'transforms', 'check_format']}
                    kwClass={'ComposedReader'}
                  />
                ) : null}
                {allReaders.some((e) => e.class === 'PolledSerialReader') &&
                reader === 'Polled Serial Reader' ? (
                  <KWArgs
                    kwargCallback={readerKwargCallback}
                    items={[
                      'port',
                      'baudrate',
                      'bytesize',
                      'parity',
                      'stopbits',
                      'timeout',
                      'xonxoff',
                      'rtscts',
                      'write_timeout',
                      'dsrdtr',
                      'inter_byte_timeout',
                      'exclusive',
                      'max_bytes',
                      'eol',
                      'start_cmd',
                      'pre_read_cmd',
                      'stop_cmd',
                    ]}
                    kwclass={'PolledSerialReader'}
                  />
                ) : null}
                {allReaders.some((e) => e.class === 'RedisReader') &&
                reader === 'Redis Reader' ? (
                  <KWArgs
                    kwargCallback={readerKwargCallback}
                    items={['channel']}
                    kwClass={'RedisReader'}
                  />
                ) : null}
                {allReaders.some((e) => e.class === 'SerialReader') &&
                reader === 'Serial Reader' ? (
                  <KWArgs
                    kwargCallback={readerKwargCallback}
                    items={['baudrate', 'port', 'eol']}
                    kwClass={'SerialReader'}
                  />
                ) : null}
                {allReaders.some((e) => e.class === 'TimeoutReader') &&
                reader === 'Timeout Reader' ? (
                  <KWArgs
                    kwargCallback={readerKwargCallback}
                    items={[
                      'reader',
                      'timeout',
                      'message',
                      'resume_message',
                      'empty_is_okay',
                      'none_is_okay',
                    ]}
                    kwClass={'TimeoutReader'}
                  />
                ) : null}
                {allReaders.some((e) => e.class === 'UDPReader') &&
                reader === 'UDP Reader' ? (
                  <KWArgs
                    kwargCallback={readerKwargCallback}
                    items={['port', 'source', 'eol']}
                    kwClass={'UDPReader'}
                  />
                ) : null}
                <h1 style={divStyle}>Transforms</h1>
                <div className='form-group' style={divStyle}>
                  <Dropdown>
                    <Dropdown.Toggle variant='success' id='dropdown-basic'>
                      {transform.length > 0
                        ? transform
                        : 'Please Select a Transform'}
                    </Dropdown.Toggle>

                    <Dropdown.Menu>
                      <Dropdown.Item
                        href='#/action-1'
                        onClick={transformChange}
                      >
                        Count Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-2'
                        onClick={transformChange}
                      >
                        Derived Data Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-3'
                        onClick={transformChange}
                      >
                        Extract Field Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-4'
                        onClick={transformChange}
                      >
                        Format Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-5'
                        onClick={transformChange}
                      >
                        From Json Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-6'
                        onClick={transformChange}
                      >
                        Interpolation Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-7'
                        onClick={transformChange}
                      >
                        MaxMin Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-8'
                        onClick={transformChange}
                      >
                        NMEA Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-9'
                        onClick={transformChange}
                      >
                        Parse NMEA Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-10'
                        onClick={transformChange}
                      >
                        Parse Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-11'
                        onClick={transformChange}
                      >
                        Prefix Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-12'
                        onClick={transformChange}
                      >
                        QC Filter Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-13'
                        onClick={transformChange}
                      >
                        Regex Filter Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-14'
                        onClick={transformChange}
                      >
                        Select Fields Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-15'
                        onClick={transformChange}
                      >
                        Slice Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-16'
                        onClick={transformChange}
                      >
                        Subsample Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-17'
                        onClick={transformChange}
                      >
                        Timestamp Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-18'
                        onClick={transformChange}
                      >
                        ToDASRecord Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-19'
                        onClick={transformChange}
                      >
                        ToJSON Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-20'
                        onClick={transformChange}
                      >
                        True Winds Transform
                      </Dropdown.Item>
                      <Dropdown.Item
                        href='#/action-21'
                        onClick={transformChange}
                      >
                        XMLAggregator Transform
                      </Dropdown.Item>
                    </Dropdown.Menu>
                  </Dropdown>
                  <Button
                    className='addButton'
                    variant='outline-primary'
                    onClick={handleClickTransform}
                  >
                    Add
                  </Button>{' '}
                </div>

                {allTransforms.some(
                  (e) => e.class === 'ExtractFieldTransform'
                ) && transform === 'Extract Field Transform' ? (
                  <KWArgs
                    kwargCallback={transformKwargCallback}
                    items={['field_name']}
                    kwClass={'ExtractFieldTransform'}
                  />
                ) : null}

                {allTransforms.some((e) => e.class === 'FormatTransform') &&
                transform === 'Format Transform' ? (
                  <KWArgs
                    kwargCallback={transformKwargCallback}
                    items={['format_str', 'defaults']}
                    kwClass={'FormatTransform'}
                  />
                ) : null}

                {allTransforms.some((e) => e.class === 'FromJsonTransform') &&
                transform === 'From Json Transform' ? (
                  <KWArgs
                    kwargCallback={transformKwargCallback}
                    items={['das_record']}
                    kwClass={'FromJsonTransform'}
                  />
                ) : null}

                {allTransforms.some(
                  (e) => e.class === 'InterpolationTransform'
                ) && transform === 'Interpolation Transform' ? (
                  <KWArgs
                    kwargCallback={transformKwargCallback}
                    items={[
                      'field_spec',
                      'interval',
                      'window',
                      'metadata_interval',
                    ]}
                    kwClass={'InterpolationTransform'}
                  />
                ) : null}

                {allTransforms.some((e) => e.class === 'ParseNMEATransform') &&
                transform === 'Parse NMEA Transform' ? (
                  <KWArgs
                    kwargCallback={transformKwargCallback}
                    items={[
                      'json',
                      'message_path',
                      'sensor_path',
                      'sensor_model_path',
                      'time_format',
                    ]}
                    kwClass={'ParseNMEATransform'}
                  />
                ) : null}

                {allTransforms.some((e) => e.class === 'ParseTransform') &&
                transform === 'Parse Transform' ? (
                  <KWArgs
                    kwargCallback={transformKwargCallback}
                    items={[
                      'record_format',
                      'field_patterns',
                      'metadata',
                      'definition_path',
                      'return_json',
                      'return_das_record',
                      'metadata_interval',
                      'quiet',
                    ]}
                    kwClass={'ParseTransform'}
                  />
                ) : null}

                {allTransforms.some((e) => e.class === 'PrefixTransform') &&
                transform === 'Prefix Transform' ? (
                  <KWArgs
                    kwargCallback={transformKwargCallback}
                    items={['prefix', 'sep']}
                    kwClass={'PrefixTransform'}
                  />
                ) : null}

                {allTransforms.some((e) => e.class === 'QCFilterTransform') &&
                transform === 'QC Filter Transform' ? (
                  <KWArgs
                    kwargCallback={transformKwargCallback}
                    items={['bounds', 'message']}
                    kwClass={'QCFilterTransform'}
                  />
                ) : null}

                {allTransforms.some(
                  (e) => e.class === 'RegexFilterTransform'
                ) && transform === 'Regex Filter Transform' ? (
                  <KWArgs
                    kwargCallback={transformKwargCallback}
                    items={['pattern', 'flags', 'negate']}
                    kwClass={'RegexFilterTransform'}
                  />
                ) : null}

                {allTransforms.some(
                  (e) => e.class === 'SelectFieldsTransform'
                ) && transform === 'Select Fields Transform' ? (
                  <KWArgs
                    kwargCallback={transformKwargCallback}
                    items={['keep', 'delete']}
                    kwClass={'SelectFieldsTransform'}
                  />
                ) : null}

                {allTransforms.some((e) => e.class === 'SliceTransform') &&
                transform === 'Slice Transform' ? (
                  <KWArgs
                    kwargCallback={transformKwargCallback}
                    items={['fields', 'sep']}
                    kwClass={'SliceTransform'}
                  />
                ) : null}

                {allTransforms.some((e) => e.class === 'SubsampleTransform') &&
                transform === 'Subsample Transform' ? (
                  <KWArgs
                    kwargCallback={transformKwargCallback}
                    items={['field_spec', 'back_seconds', 'metadata_interval']}
                    kwClass={'SubsampleTransform'}
                  />
                ) : null}

                {allTransforms.some((e) => e.class === 'TimestampTransform') &&
                transform === 'Timestamp Transform' ? (
                  <KWArgs
                    kwargCallback={transformKwargCallback}
                    items={['time_format', 'sep']}
                    kwClass={'TimestampTransform'}
                  />
                ) : null}

                {allTransforms.some(
                  (e) => e.class === 'ToDASRecordTransform'
                ) && transform === 'ToDASRecord Transform' ? (
                  <KWArgs
                    kwargCallback={transformKwargCallback}
                    items={['data_id', 'field_name']}
                    kwClass={'ToDASRecordTransform'}
                  />
                ) : null}

                {allTransforms.some((e) => e.class === 'ToJSONTransform') &&
                transform === 'ToJSON Transform' ? (
                  <KWArgs
                    kwargCallback={transformKwargCallback}
                    items={['pretty']}
                    kwClass={'ToJSONTransform'}
                  />
                ) : null}

                {allTransforms.some((e) => e.class === 'TrueWindsTransform') &&
                transform === 'True Winds Transform' ? (
                  <KWArgs
                    kwargCallback={transformKwargCallback}
                    items={[
                      'course_field',
                      'speed_field',
                      'heading_field',
                      'wind_dir_field',
                      'wind_speed_field',
                      'true_dir_name',
                      'true_speed_name',
                      'apparent_dir_name',
                      'update_on_fields',
                      'zero_line_reference',
                      'convert_wind_factor',
                      'convert_speed_factor',
                      'metadata_interval',
                    ]}
                    kwClass={'TrueWindsTransform'}
                  />
                ) : null}

                {allTransforms.some(
                  (e) => e.class === 'XMLAggregatorTransform'
                ) && transform === 'XMLAggregator Transform' ? (
                  <KWArgs
                    kwargCallback={transformKwargCallback}
                    items={['input_format', 'output_format']}
                    kwClass={'XMLAggregatorTransform'}
                  />
                ) : null}

                <h1 style={divStyle}>Writers</h1>
                <div className='form-group' style={divStyle}>
                  <Dropdown>
                    <Dropdown.Toggle variant='success' id='dropdown-basic'>
                      {writer.length > 0 ? writer : 'Please Select a Writer'}
                    </Dropdown.Toggle>

                    <Dropdown.Menu>
                      <Dropdown.Item href='#/action-1' onClick={writerChange}>
                        Cached Data Writer
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-2' onClick={writerChange}>
                        Composed Writer
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-3' onClick={writerChange}>
                        Database Writer
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-4' onClick={writerChange}>
                        Email Writer
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-5' onClick={writerChange}>
                        Influxdb Writer
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-6' onClick={writerChange}>
                        Logfile Writer
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-7' onClick={writerChange}>
                        Network Writer
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-8' onClick={writerChange}>
                        Record Screen Writer
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-9' onClick={writerChange}>
                        Redis Writer
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-10' onClick={writerChange}>
                        Text File Writer
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-11' onClick={writerChange}>
                        Timeout Writer
                      </Dropdown.Item>
                      <Dropdown.Item href='#/action-12' onClick={writerChange}>
                        UDP Writer
                      </Dropdown.Item>
                    </Dropdown.Menu>
                  </Dropdown>
                  <Button
                    className='addButton'
                    variant='outline-primary'
                    onClick={handleClickWriter}
                  >
                    Add
                  </Button>{' '}
                </div>

                {allWriters.some((e) => e.class === 'CachedDataWriter') &&
                writer === 'Cached Data Writer' ? (
                  <KWArgs
                    kwargCallback={writerKwargCallback}
                    items={[
                      'data_server',
                      'start_server',
                      'back_seconds',
                      'cleanup_interval',
                      'update_interval',
                      'max_backup',
                    ]}
                    kwClass={'CachedDataWriter'}
                  />
                ) : null}

                {allWriters.some((e) => e.class === 'ComposedWriter') &&
                writer === 'Composed Writer' ? (
                  <KWArgs
                    kwargCallback={writerKwargCallback}
                    items={['transforms', 'writers', 'check_format']}
                    kwClass={'ComposedWriter'}
                  />
                ) : null}

                {allWriters.some((e) => e.class === 'DatabaseWriter') &&
                writer === 'Database Writer' ? (
                  <KWArgs
                    kwargCallback={writerKwargCallback}
                    items={[
                      'database',
                      'host',
                      'user',
                      'password',
                      'save_source',
                    ]}
                    kwClass={'DatabaseWriter'}
                  />
                ) : null}

                {allWriters.some((e) => e.class === 'EmailWriter') &&
                writer === 'Email Writer' ? (
                  <KWArgs
                    kwargCallback={writerKwargCallback}
                    items={['to', 'sender', 'subject', 'max_freq']}
                    kwClass={'EmailWriter'}
                  />
                ) : null}

                {allWriters.some((e) => e.class === 'InfluxdbWriter') &&
                writer === 'Influxdb Writer' ? (
                  <KWArgs
                    kwargCallback={writerKwargCallback}
                    items={['bucket_name']}
                    kwClass={'InfluxdbWriter'}
                  />
                ) : null}

                {allWriters.some((e) => e.class === 'LogfileWriter') &&
                writer === 'Logfile Writer' ? (
                  <KWArgs
                    kwargCallback={writerKwargCallback}
                    items={[
                      'filebase',
                      'flush',
                      'time_format',
                      'date_format',
                      'suffix',
                      'rollover_hourly',
                    ]}
                    kwClass={'LogfileWriter'}
                  />
                ) : null}
                {allWriters.some((e) => e.class === 'NetworkWriter') &&
                writer === 'Network Writer' ? (
                  <KWArgs
                    kwargCallback={writerKwargCallback}
                    items={['network', 'num_retry', 'eol']}
                    kwClass={'NetworkWriter'}
                  />
                ) : null}

                {allWriters.some((e) => e.class === 'TimeoutWriter') &&
                writer === 'Timeout Writer' ? (
                  <KWArgs
                    kwargCallback={writerKwargCallback}
                    items={[
                      'writer',
                      'timeout',
                      'message',
                      'resume_message',
                      'empty_is_okay',
                      'none_is_okay',
                    ]}
                    kwClass={'TimeoutWriter'}
                  />
                ) : null}

                {allWriters.some((e) => e.class === 'UDPWriter') &&
                writer === 'UDP Writer' ? (
                  <KWArgs
                    kwargCallback={writerKwargCallback}
                    items={[
                      'port',
                      'destination',
                      'interface',
                      'ttl',
                      'num_retry',
                      'eol',
                    ]}
                    kwClass={'UDPWriter'}
                  />
                ) : null}

                {allWriters.some((e) => e.class === 'RedisWriter') &&
                writer === 'Redis Writer' ? (
                  <KWArgs
                    kwargCallback={writerKwargCallback}
                    items={['channel', 'password']}
                    kwClass={'RedisWriter'}
                  />
                ) : null}
              </div>

              <div className='col-sm'>
                <JSONYAMLOutput
                  readers={allReaders}
                  transforms={allTransforms}
                  writers={allWriters}
                />
              </div>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

export default YAML;
