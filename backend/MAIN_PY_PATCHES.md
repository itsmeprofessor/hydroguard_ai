# HydroGuard-AI — main.py patches
# ─────────────────────────────────────────────────────────────────────────────
# Two surgical edits to backend/app/main.py. Do NOT replace your existing
# main.py — merge these two snippets into it.
#
# 1.  Add CORS middleware so the Flutter mobile app (any IP/origin) and the
#     HTML dashboard (file:// or localhost:port) can hit the API.
#
#     import added:
#         from fastapi.middleware.cors import CORSMiddleware
#
#     after `app = FastAPI(...)` in your main.py, insert:
#
#         app.add_middleware(
#             CORSMiddleware,
#             allow_origins=["*"],              # demo-wide open; tighten later
#             allow_credentials=False,          # must be False when using "*"
#             allow_methods=["*"],
#             allow_headers=["*"],
#             expose_headers=["*"],
#         )
#
#     Production note: once you're past the FYP demo, replace "*" with a
#     concrete list like:
#         allow_origins=[
#             "https://hydroguard-dashboard.web.app",
#             "http://localhost:8080",
#             "http://192.168.1.100:8080",
#         ]
#     and set allow_credentials=True if you need cookies/auth headers.
#
# 2.  Register the new analytics-alias router.
#
#     import added:
#         from app.api.routes import analytics_aliases
#
#     where you include your other routers (near api_router.include_router(...)
#     or app.include_router(...)):
#
#         app.include_router(analytics_aliases.router)
#
# That is the entire backend change. No ML code, no schema changes.
# ─────────────────────────────────────────────────────────────────────────────
