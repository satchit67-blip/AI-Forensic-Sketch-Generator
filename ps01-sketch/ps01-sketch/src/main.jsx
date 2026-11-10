import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App.jsx';
import ErrorBoundary from './components/ErrorBoundary.jsx';
import './index.css';

createRoot(document.getElementById('root')).render(
  <ErrorBoundary variant="page">
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </ErrorBoundary>
);
