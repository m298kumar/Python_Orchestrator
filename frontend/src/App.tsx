import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import NotificationProvider from './components/NotificationProvider';
import ProtectedRoute from './components/ProtectedRoute';
import { AuthProvider } from './context/AuthContext';
import Dashboard from './pages/Dashboard';
import Requirements from './pages/Requirements';
import TestCases from './pages/TestCases';
import BddCode from './pages/BddCode';
import Crawler from './pages/Crawler';
import ApiTests from './pages/ApiTests';
import Config from './pages/Config';
import History from './pages/History';
import Metrics from './pages/Metrics';
import Login from './pages/Login';
import NotFound from './pages/NotFound';

export default function App() {
  return (
    <AuthProvider>
      <NotificationProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="*"
            element={
              <ProtectedRoute>
                <Layout>
                  <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/requirements" element={<Requirements />} />
                    <Route path="/test-cases" element={<TestCases />} />
                    <Route path="/bdd" element={<BddCode />} />
                    <Route path="/crawler" element={<Crawler />} />
                    <Route path="/api-tests" element={<ApiTests />} />
                    <Route path="/config" element={<Config />} />
                    <Route path="/history" element={<History />} />
                    <Route path="/metrics" element={<Metrics />} />
                    <Route path="*" element={<NotFound />} />
                  </Routes>
                </Layout>
              </ProtectedRoute>
            }
          />
        </Routes>
      </NotificationProvider>
    </AuthProvider>
  );
}
