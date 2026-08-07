export default function CostHUD({ metrics }) {
  const hitRate = Math.round((metrics?.cache_hit_rate || 0) * 100);
  return (
    <aside className="cost-hud">
      <strong className="cost-hud__title">❄️ Cost HUD</strong>
      <p>Session cost <b>${(metrics?.session_usd || 0).toFixed(4)}</b></p>
      <p>Cache hit rate <b>{hitRate}%</b></p>
      <p>LLM calls avoided <b>{metrics?.llm_calls_avoided || 0}</b></p>
      <p className="cost-hud__note">Savings vs. Naive — measuring</p>
    </aside>
  );
}
