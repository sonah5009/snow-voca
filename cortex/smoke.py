import os, json
from llm.client import messages, text_of
from dotenv import load_dotenv
load_dotenv()

resp = messages(os.environ["MODEL_CHEAP"],
                [{"type": "text", "text": "Reply with exactly: OK"}], max_tokens=16)
print("TEXT :", text_of(resp))
print("USAGE:", json.dumps(resp.get("usage", {}), indent=2))  # ← 필드명 여기서 확정
