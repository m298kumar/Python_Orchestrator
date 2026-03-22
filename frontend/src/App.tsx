import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import NotificationProvider from "./components/NotificationProvider";
import Dashboard from "./pages/Dashboard";
import Requirements from "./pages/Requirements";
import TestCases from "./pages/TestCases";
import BddCode from "./pages/BddCode";
import Crawler from "./pages/Crawler";
import ApiTests from "./pages/ApiTests";
import Config from "./pages/Config";
import History from "./pages/History";

export default function App() {
  return (
    <NotificationProvider>
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
        </Routes>
      </Layout>
    </NotificationProvider>
  );
}
