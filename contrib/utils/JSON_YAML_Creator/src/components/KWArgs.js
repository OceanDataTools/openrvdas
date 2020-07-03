import React, { useState } from 'react';
import { Dropdown, Button } from 'react-bootstrap';

export default function KWArgs(props) {
  const [kwargs, setKwargs] = useState('');
  const [value, setValue] = useState('');

  const kwargsChange = (e) => {
    setKwargs(e.target.innerHTML);
  };

  const divStyle = {
    display: 'flex',
    alignItems: 'center',
  };
  const handleTextChange = (e) => {
    setValue(e.target.value);
  };

  return (
    <div>
      <h1 style={divStyle}>Kwargs</h1>
      <div className='form-group' id='reader' style={divStyle}>
        <Dropdown>
          <Dropdown.Toggle variant='success' id='dropdown-basic'>
            {kwargs.length > 0 ? kwargs : 'Select keyword argument'}
          </Dropdown.Toggle>

          <Dropdown.Menu>
            {props.items.map((item) => (
              <Dropdown.Item onClick={kwargsChange}>{item}</Dropdown.Item>
            ))}
          </Dropdown.Menu>
        </Dropdown>
        <input type='text' placeholder='Value' onChange={handleTextChange} />
        <Button
          className='addButton'
          variant='outline-primary'
          onClick={() => {
            let arr = [props.kwClass, kwargs, value];
            console.log(props.kwClass, kwargs, value);
            props.kwargCallback(arr);
          }}
        >
          Add
        </Button>{' '}
      </div>
    </div>
  );
}
