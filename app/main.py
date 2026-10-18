"""
Bootstrap do FastAPI com todas as regras de seguranca da Fase 1.

Checklist (ver CLAUDE.md secao Seguranca):
- TrustedHostMiddleware aceita so 127.0.0.1 e localhost.
- Headers injetados: CSP self, nosniff, DENY, no-referrer.
- /docs, /redoc, /openapi.json desligados fora de ENVIRONMENT=development.
- Exception handler nunca retorna stack trace; loga internamente.
- Jinja2 com autoescape ligado.
- Nenhum CORS liberado.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import HTMLResponse, Response

from fastapi.responses import RedirectResponse

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.dependencies import get_optional_user
from app.models import User
from app.routers import admin as admin_router
from app.routers import auth as auth_router
from app.routers import backup as backup_router
from app.routers import cash as cash_router
from app.routers import products as products_router
from app.routers import reports as reports_router
from app.routers import sales as sales_router
from app.routers import users as users_router

# ---------- logging interno ----------

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "pdv.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("app")


# ---------- app ----------

settings = get_settings()

app = FastAPI(
    title="PDV Padaria",
    version="0.1.0",
    # /docs, /redoc e /openapi.json somente em development.
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    openapi_url="/openapi.json" if settings.is_development else None,
)

# ---------- middlewares ----------

# Protege contra DNS rebinding e requisicoes com Host arbitrario.
# Starlette compara so o nome do host (ignora porta), entao basta listar os nomes.
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injeta cabecalhos de seguranca em TODAS as respostas."""

    _CSP = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self'; "
        "script-src 'self'; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'"
    )

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        response: Response = await call_next(request)
        response.headers["Content-Security-Policy"] = self._CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=()"
        )
        return response


app.add_middleware(SecurityHeadersMiddleware)


# ---------- handlers de erro ----------


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    # HTTPExceptions tem detalhe legivel e sao esperadas (404, 409, etc.).
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # 422: entrada invalida. Log minimo, resposta estruturada mas sem vazar.
    logger.info("Validation error em %s: %s", request.url.path, exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Dados invalidos.", "errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Nunca vaza stack trace. Loga internamente com stack completo.
    logger.exception("Erro nao tratado em %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Erro interno. Verifique os logs."},
    )


# ---------- static e templates ----------

BASE_DIR = Path(__file__).resolve().parent
app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
# Jinja2Templates ja vem com autoescape ativado para html/xml por padrao.


# ---------- rotas de UI ----------


def _home_for(user: User) -> str:
    """Rota default por papel (Fase 11): admin -> painel, caixa -> PDV."""
    return "/admin" if user.role == "admin" else "/pdv"


@app.get("/", include_in_schema=False)
async def root(user: User | None = Depends(get_optional_user)) -> RedirectResponse:
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    return RedirectResponse(url=_home_for(user), status_code=302)


@app.get("/login", include_in_schema=False, response_model=None)
async def login_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
) -> HTMLResponse | RedirectResponse:
    # Se ja esta logado, nao mostra o form.
    if user is not None:
        return RedirectResponse(url=_home_for(user), status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"env": settings.ENVIRONMENT},
    )


@app.get("/products", include_in_schema=False, response_model=None)
async def products_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
) -> HTMLResponse | RedirectResponse:
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="products.html",
        context={
            "env": settings.ENVIRONMENT,
            "user": {"name": user.name, "username": user.username, "role": user.role},
        },
    )


@app.get("/pdv", include_in_schema=False, response_model=None)
async def pdv_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    # Guard: se cash required e nao ha caixa aberto, manda pra /caixa
    from app.services.cash_service import get_open_session, is_cash_required

    if is_cash_required(db) and get_open_session(db) is None:
        return RedirectResponse(url="/caixa?msg=abra", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="pdv.html",
        context={
            "env": settings.ENVIRONMENT,
            "user": {"name": user.name, "username": user.username, "role": user.role},
        },
    )


@app.get("/caixa", include_in_schema=False, response_model=None)
async def caixa_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
) -> HTMLResponse | RedirectResponse:
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="caixa.html",
        context={
            "env": settings.ENVIRONMENT,
            "user": {"name": user.name, "username": user.username, "role": user.role},
        },
    )


@app.get("/admin/printer", include_in_schema=False, response_model=None)
async def admin_printer_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
) -> HTMLResponse | RedirectResponse:
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    if user.role != "admin":
        return RedirectResponse(url="/products", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="admin_printer.html",
        context={
            "env": settings.ENVIRONMENT,
            "user": {"name": user.name, "username": user.username, "role": user.role},
        },
    )


@app.get("/admin", include_in_schema=False, response_model=None)
async def admin_dashboard_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
) -> HTMLResponse | RedirectResponse:
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    if user.role != "admin":
        return RedirectResponse(url="/pdv", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="admin_dashboard.html",
        context={
            "env": settings.ENVIRONMENT,
            "user": {"name": user.name, "username": user.username, "role": user.role},
        },
    )


@app.get("/admin/stock", include_in_schema=False, response_model=None)
async def admin_stock_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
) -> HTMLResponse | RedirectResponse:
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    if user.role != "admin":
        return RedirectResponse(url="/products", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="admin_stock.html",
        context={
            "env": settings.ENVIRONMENT,
            "user": {"name": user.name, "username": user.username, "role": user.role},
        },
    )


@app.get("/admin/reports", include_in_schema=False, response_model=None)
async def admin_reports_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
) -> HTMLResponse | RedirectResponse:
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    if user.role != "admin":
        return RedirectResponse(url="/products", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="admin_reports.html",
        context={
            "env": settings.ENVIRONMENT,
            "user": {"name": user.name, "username": user.username, "role": user.role},
        },
    )


@app.get("/admin/vendas", include_in_schema=False, response_model=None)
async def admin_vendas_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
) -> HTMLResponse | RedirectResponse:
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    if user.role != "admin":
        return RedirectResponse(url="/pdv", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="admin_vendas.html",
        context={
            "env": settings.ENVIRONMENT,
            "user": {"name": user.name, "username": user.username, "role": user.role},
        },
    )


@app.get("/admin/usuarios", include_in_schema=False, response_model=None)
async def admin_usuarios_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
) -> HTMLResponse | RedirectResponse:
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    if user.role != "admin":
        return RedirectResponse(url="/pdv", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="admin_usuarios.html",
        context={
            "env": settings.ENVIRONMENT,
            "user": {"name": user.name, "username": user.username, "role": user.role},
        },
    )


@app.get("/admin/backup", include_in_schema=False, response_model=None)
async def admin_backup_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
) -> HTMLResponse | RedirectResponse:
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    if user.role != "admin":
        return RedirectResponse(url="/products", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="admin_backup.html",
        context={
            "env": settings.ENVIRONMENT,
            "user": {"name": user.name, "username": user.username, "role": user.role},
        },
    )


@app.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------- API ----------

app.include_router(auth_router.router)
app.include_router(products_router.router)
app.include_router(sales_router.router)
app.include_router(admin_router.router)
app.include_router(cash_router.router)
app.include_router(cash_router.admin_router)
app.include_router(reports_router.router)
app.include_router(backup_router.router)
app.include_router(users_router.router)
