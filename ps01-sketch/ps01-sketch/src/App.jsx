import { Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Splash from './pages/Splash';
import Studio from './pages/Studio';
import DisguisePage from './pages/DisguisePage';
import AuditPage from './pages/AuditPage';
import DashboardLayout from './layouts/DashboardLayout';

// Redirects to the login gateway when no officer session exists.
const Guard = ({ children }) => (sessionStorage.getItem('nexus_badge') ? children : <Navigate to="/" replace />);

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Login />} />
      <Route path="/splash" element={<Guard><Splash /></Guard>} />
      <Route element={<Guard><DashboardLayout /></Guard>}>
        <Route path="/studio" element={<Studio />} />
        <Route path="/disguise-toolkit" element={<DisguisePage />} />
        <Route path="/audit-trail" element={<AuditPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
