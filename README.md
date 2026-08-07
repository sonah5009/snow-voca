# snow-voca

말해보카 스타일 영어 학습 데모. 상세 스펙은 [CLAUDE.md](./CLAUDE.md) 참고.

```bash
# backend
cd backend && pip install fastapi uvicorn snowflake-connector-python --break-system-packages
# .env 또는 환경변수에 SNOWFLAKE_ACCOUNT / USER / PASSWORD / WAREHOUSE 설정 필요
python generate_exercises.py   # 초기 문제 배치 생성 (1회)
uvicorn main:app --reload --port 8000

# frontend
cd frontend && npm install && npm run dev
```
