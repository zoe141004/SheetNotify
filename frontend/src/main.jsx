import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { AuthProvider } from './context/AuthContext'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              background: '#25262b',
              color: '#c1c2c5',
              border: '1px solid rgba(55, 58, 64, 0.5)',
              borderRadius: '12px',
            },
            success: { iconTheme: { primary: '#22b8cf', secondary: '#25262b' } },
            error: { iconTheme: { primary: '#ff6b6b', secondary: '#25262b' } },
          }}
        />
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
