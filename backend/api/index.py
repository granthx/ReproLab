import sys
from pathlib import Path

# Ensure the backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from reprolab.main import app as fastapi_app  # ASGI FastAPI application

async def app(scope, receive, send):
    if scope["type"] == "http":
        headers = dict(scope.get("headers", []))
        for header_name in (b"x-matched-path", b"x-forwarded-uri", b"x-original-uri", b"x-vercel-matched-path"):
            val = headers.get(header_name)
            if val:
                decoded = val.decode("utf-8")
                path_part = decoded.split("?")[0]
                if path_part and path_part not in ("/api/index.py", "/api/index"):
                    scope["path"] = path_part
                    if "?" in decoded and not scope.get("query_string"):
                        scope["query_string"] = decoded.split("?", 1)[1].encode("utf-8")
                    break
        if scope.get("path") in ("/api/index.py", "/api/index", ""):
            scope["path"] = "/"
    await fastapi_app(scope, receive, send)
