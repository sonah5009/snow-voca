# SnowVoca

대화형 영어 학습 데모이자, Naive 대비 추론 비용 절감률을 실시간으로 보여주는 Track 1 프로젝트입니다.
현재 구현은 Cortex REST API + 비용 계측을 사용하고, EverOS/MCP/SPCS는 발표의 Next Steps 확장안으로 남겨둡니다.
상세 기준은 [CLAUDE.md](./CLAUDE.md)를 참고하세요.

```bash
# 의존성: .venv/bin/python, FastAPI, httpx, python-dotenv
# 기본값은 로컬 리허설 응답입니다. Cortex 호출은 SNOWVOCA_OFFLINE=0일 때만 활성화됩니다.
.venv/bin/python -m measure.baseline_naive
.venv/bin/python -m batch.generate_exercises
.venv/bin/python -m measure.report

# API + CostHUD 데모
uvicorn gateway.main:app --reload --port 8000

# Cortex 권한이 복구된 뒤에만 온라인 모드로 전환
SNOWVOCA_OFFLINE=0 SNOWVOCA_USE_SNOWFLAKE=1 uvicorn gateway.main:app --reload --port 8000

# frontend
cd frontend && npm install && npm run dev
```

프론트엔드가 아직 설치되지 않은 환경에서는 먼저 `npm install`을 실행하세요. 발표에서는 `measure.report`의
`비용 절감률` 한 줄과 브라우저 우측 Cost HUD를 함께 보여주면 됩니다.
