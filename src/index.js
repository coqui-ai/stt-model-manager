import React from 'react';
import ReactDOM from 'react-dom';
import './index.css';
import App from './App';

window.startReactUI = function(modelName) {
    ReactDOM.render(<App modelName={modelName}/>, document.getElementById('react-root'));
}
