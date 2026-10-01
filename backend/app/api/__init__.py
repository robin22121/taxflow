from fastapi import FastAPI


def register_routes(app: FastAPI) -> None:
    """Wire all routers."""
    # Routers are registered in later tasks (auth, clients, filings, collect, dashboard).
    # Importing here so adding new routers is a one-line edit.
    from app.api import (
        access_log,
        admin,
        auth,
        beta_signup,
        certificates,
        clients,
        collect,
        employee_changes,
        fast_path,
        filings,
        imports,
        kakao_inbox,
        messages,
        public_collect,
        qa,
        rpa,
        rpa_import,
        staff,
        webhooks,
    )

    app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(access_log.router, prefix="/api/v1/access-log", tags=["access-log"])
    app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
    app.include_router(beta_signup.router, prefix="/api/v1/beta-signup", tags=["beta-signup"])
    app.include_router(clients.router, prefix="/api/v1/clients", tags=["clients"])
    app.include_router(imports.router, prefix="/api/v1/clients", tags=["imports"])
    app.include_router(filings.router, prefix="/api/v1/filings", tags=["filings"])
    app.include_router(fast_path.router, prefix="/api/v1/filings", tags=["fast-path"])
    app.include_router(messages.router, prefix="/api/v1/messages", tags=["messages"])
    app.include_router(kakao_inbox.router, prefix="/api/v1/kakao-inbox", tags=["kakao-inbox"])
    app.include_router(collect.router, prefix="/api/v1/collect", tags=["collect"])
    app.include_router(
        employee_changes.router,
        prefix="/api/v1/employee-changes",
        tags=["employee-changes"],
    )
    app.include_router(public_collect.router, prefix="/api/v1/public", tags=["public"])
    app.include_router(qa.router, prefix="/api/v1/qa", tags=["qa"])
    app.include_router(rpa.router, prefix="/api/v1/rpa", tags=["rpa"])
    app.include_router(rpa_import.router, prefix="/api/v1/rpa", tags=["rpa"])
    app.include_router(staff.router, prefix="/api/v1/staff", tags=["staff"])
    app.include_router(certificates.router, prefix="/api/v1/certificates", tags=["certificates"])
    app.include_router(certificates.public_router, prefix="/api/v1/public", tags=["public"])
    app.include_router(webhooks.router, prefix="/api/v1/webhooks", tags=["webhooks"])
