from fastapi import FastAPI


def register_routes(app: FastAPI) -> None:
    """Wire all routers."""
    # Routers are registered in later tasks (auth, clients, filings, collect, dashboard).
    # Importing here so adding new routers is a one-line edit.
    from app.api import admin, auth, clients, collect, filings, imports, public_collect, webhooks

    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(clients.router, prefix="/api/v1/clients", tags=["clients"])
    app.include_router(imports.router, prefix="/api/v1/clients", tags=["imports"])
    app.include_router(filings.router, prefix="/api/v1/filings", tags=["filings"])
    app.include_router(collect.router, prefix="/api/v1/collect", tags=["collect"])
    app.include_router(public_collect.router, prefix="/api/v1/public", tags=["public"])
    app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["webhooks"])
