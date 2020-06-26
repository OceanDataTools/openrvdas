import React from 'react';
import YAML from 'yaml';
import './index.css';
import { CopyToClipboard } from 'react-copy-to-clipboard';

export default function YAMLOutput(props) {
  const divStyle = {
    display: 'flex',
    alignItems: 'center',
  };

  const combined = {
    readers: props.readers.map((element) => element),
    transforms: props.transforms.map((element) => element),
    writers: props.writers.map((element) => element),
  };

  return (
    <div>
      <div className='container p-3 my-3 bg-light text-white border'>
        <div className='row'>
          <div className='text-left col-10'>
            <pre style={divStyle}>
              {JSON.stringify(
                combined,
                function (key, val) {
                  if (key !== 'kwargClass') return val;
                },
                2
              )}
            </pre>
          </div>
          <div className='col-2'>
            <CopyToClipboard
              className='copyButton'
              text={JSON.stringify(
                combined,
                function (key, val) {
                  if (key !== 'kwargClass') return val;
                },
                2
              )}
            >
              <button>Copy JSON</button>
            </CopyToClipboard>
          </div>
        </div>
      </div>
      <div className='container p-3 my-3 bg-light text-white border'>
        <div className='row'>
          <div className='text-left col-10'>
            <pre>
              {YAML.stringify(
                JSON.parse(
                  JSON.stringify(
                    combined,
                    function (key, val) {
                      if (key !== 'kwargClass') return val;
                    },
                    2
                  )
                )
              )}
            </pre>
          </div>
          <div className='col-2'>
            <CopyToClipboard
              className='copyButton'
              text={YAML.stringify(
                JSON.parse(
                  JSON.stringify(
                    combined,
                    function (key, val) {
                      if (key !== 'kwargClass') return val;
                    },
                    2
                  )
                )
              )}
            >
              <button>Copy YAML</button>
            </CopyToClipboard>
          </div>
        </div>
      </div>
    </div>
  );
}
