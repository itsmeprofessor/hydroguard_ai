# auth_router is imported directly in app.main to avoid circular imports:
#   app.auth → router → user_repo → app.auth.models → (app.auth not yet initialized)
# Use: from app.auth.router import router as auth_router
