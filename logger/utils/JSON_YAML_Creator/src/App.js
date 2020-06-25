import React from 'react';
import './App.css';
import Menu from './components/Menu';
import './components/index.css';

// Main component that brings subcomponents
function App() {
  return (
    <div className='App'>
      <h1 className='test'>YAML/JSON Creator</h1>
      <Menu></Menu>
    </div>
  );
}

export default App;
