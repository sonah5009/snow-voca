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
    <div className="app-shell">
      <header className="app-header">
        <h1>❄️ SnowVoca</h1>
        <p className="app-subtitle">One word from your conversation — say it out loud</p>
      </header>
      <QuizScreen />
      <CostHUD metrics={metrics} />
    </div>
  );
}
