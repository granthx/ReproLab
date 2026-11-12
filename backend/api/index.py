import sys
import urllib.parse
from pathlib import Path

# Ensure the backend directory is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from reprolab.main import app as fastapi_app  # ASGI FastAPI application

async def app(scope, receive, send):
    if scope["type"] == "http":
        # 1. First check if rewritten path was passed via query parameter (__path)
        qs_bytes = scope.get("query_string", b"")
        resolved_path = None
        if b"__path=" in qs_bytes:
            try:
                qs_str = qs_bytes.decode("utf-8")
                parsed = urllib.parse.parse_qs(qs_str, keep_blank_values=True)
                if "__path" in parsed:
                    p = parsed.pop("__path")[0]
                    if p:
                        if not p.startswith("/"):
                            p = "/" + p
                        resolved_path = p
                    new_qs = urllib.parse.urlencode([(k, v) for k, vs in parsed.items() for v in vs])
                    scope["query_string"] = new_qs.encode("utf-8")
            except Exception:
                pass

        # 2. Check Vercel proxy headers as fallback
        if not resolved_path:
            headers = dict(scope.get("headers", []))
            for header_name in (b"x-matched-path", b"x-forwarded-uri", b"x-original-uri", b"x-vercel-matched-path"):
                val = headers.get(header_name)
                if val:
                    decoded = val.decode("utf-8").split("?")[0]
                    if decoded and decoded not in ("/api/index.py", "/api/index"):
                        resolved_path = decoded
                        break

        if resolved_path:
            scope["path"] = resolved_path
        elif scope.get("path") in ("/api/index.py", "/api/index", ""):
            scope["path"] = "/"

    await fastapi_app(scope, receive, send)
