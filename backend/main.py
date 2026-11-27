import os
import uvicorn
from src.main import app  # noqa: F401  (uvicorn 문자열 경로 사용)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "3000"))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"Starting server on http://{host}:{port}")
    uvicorn.run("src.main:app", host=host, port=port, reload=True)
