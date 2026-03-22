import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Requirements from "./pages/Requirements";
import TestCases from "./pages/TestCases";
import BddCode from "./pages/BddCode";

function Placeholder({ title }: { title: string }) {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold">{title}</h1>
      <p className="text-gray-500 mt-2">Coming in Phase 3</p>
    </div>
  );
}

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/requirements" element={<Requirements />} />
        <Route path="/test-cases" element={<TestCases />} />
        <Route path="/bdd" element={<BddCode />} />
        <Route path="/crawler" element={<Placeholder title="Crawler" />} />
        <Route path="/api-tests" element={<Placeholder title="API Tests" />} />
        <Route path="/config" element={<Placeholder title="Config" />} />
        <Route path="/history" element={<Placeholder title="History" />} />
      </Routes>
    </Layout>
  );
}
