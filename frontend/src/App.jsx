import QuizScreen from "./QuizScreen.jsx";
import CostHUD from "./CostHUD.jsx";
import { useEffect, useState } from "react";
import { fetchMetrics } from "./api.js";

export default function App() {
  const [metrics, setMetrics] = useState({});
  useEffect(() => {
    const load = () => fetchMetrics().then(setMetrics).catch(() => {});
    load();
    const timer = setInterval(load, 1500);
    return () => clearInterval(timer);
  }, []);
  return (
    <div>
      <h1 style={{ textAlign: "center" }}>SnowVoca</h1>
      <QuizScreen />
      <CostHUD metrics={metrics} />
    </div>
  );
}
