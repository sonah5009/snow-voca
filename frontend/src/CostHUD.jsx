export default function CostHUD({ metrics }) {
  const hitRate = Math.round((metrics?.cache_hit_rate || 0) * 100);
  return (
    <aside style={{ position: "fixed", right: 24, top: 24, padding: 18, borderRadius: 16, background: "#111827", color: "white", minWidth: 190, boxShadow: "0 12px 30px #0003" }}>
      <strong>Cost HUD</strong>
      <p>세션 비용 <b>${(metrics?.session_usd || 0).toFixed(4)}</b></p>
      <p>캐시 히트율 <b>{hitRate}%</b></p>
      <p>LLM 회피 <b>{metrics?.llm_calls_avoided || 0}회</b></p>
      <p style={{ color: "#86efac" }}>Naive 대비 비용 절감 계측 중</p>
    </aside>
  );
}
