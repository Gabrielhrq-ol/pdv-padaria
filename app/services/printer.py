"""
Interface de impressao + factory configuravel por setting.

Fase 1: so Dummy existia.
Fase 5 (preparatoria): adiciona Win32RawPrinter e factory que le o
setting `printer_backend`. Admin troca de backend pela UI; o codigo
nao precisa saber qual impressora e.

python-escpos e pywin32 sao importados PREGUICOSAMENTE: so quando
backend != dummy. Isso significa que `DummyPrinter` continua funcionando
mesmo em ambiente onde a lib nao esta instalada (CI, Linux, etc.).

Backends suportados agora:
    - dummy   : grava jobs em memoria (default)
    - win32raw: fala com driver do Windows via python-escpos

Backends previstos (nao implementados):
    - network : via socket 9100
    - serial  : via porta serial
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Setting


# ---------- erros ----------


class PrinterUnavailableError(Exception):
    """Backend configurado nao consegue imprimir no momento."""


# ---------- modelo basico ----------


@dataclass
class PrintJob:
    """
    Trabalho de impressao. `lines` sao strings prontas (ja em
    N colunas, vindas de app/services/receipt.py).
    """

    lines: list[str] = field(default_factory=list)
    cut_at_end: bool = False


class Printer(ABC):
    """Interface comum. Implementacao real na Fase 5 (ou nao - decisao do admin)."""

    @abstractmethod
    def print_job(self, job: PrintJob) -> None:
        """Executa o trabalho. Pode lancar PrinterUnavailableError."""

    @abstractmethod
    def is_available(self) -> bool:
        """Diz se a impressora esta acessivel. Nao lanca."""

    def label(self) -> str:
        """Nome legivel do backend (para logs/UI)."""
        return type(self).__name__


class DummyPrinter(Printer):
    """
    Impressora sem hardware. Guarda jobs em memoria para inspecao
    (desenvolvimento, testes). Nunca falha.
    """

    def __init__(self) -> None:
        self.jobs: list[PrintJob] = []

    def print_job(self, job: PrintJob) -> None:
        self.jobs.append(job)

    def is_available(self) -> bool:
        return True

    def label(self) -> str:
        return "Dummy"

    def last_output(self) -> str:
        if not self.jobs:
            return ""
        return "\n".join(self.jobs[-1].lines)


class Win32RawPrinter(Printer):
    """
    Fala com impressora via driver do Windows (python-escpos.Win32Raw).

    Nao e singleton - cria conexao por job e fecha logo depois. Simples
    e mais tolerante a desconexoes do USB.

    Decisao 10 do cliente: `cut_at_end` do PrintJob vence o setting
    `auto_cut`. Operador pode forcar corte em um job especifico.
    """

    def __init__(
        self,
        printer_name: str,
        codepage: str = "",
        auto_cut: bool = False,
    ) -> None:
        if not isinstance(printer_name, str) or not printer_name.strip():
            raise PrinterUnavailableError(
                "Nome da impressora nao configurado (setting printer_name)."
            )
        self._printer_name = printer_name.strip()
        self._codepage = (codepage or "").strip()
        self._auto_cut = bool(auto_cut)

    def _open_raw(self):  # type: ignore[no-untyped-def]
        """Lazy import; so chama python-escpos quando usado de verdade."""
        try:
            from escpos.printer import Win32Raw  # type: ignore[import-not-found]
        except ImportError as exc:
            raise PrinterUnavailableError(
                "python-escpos nao esta instalado. "
                "Rode: pip install python-escpos==3.1 pywin32==308"
            ) from exc
        try:
            p = Win32Raw(printer_name=self._printer_name)
            p.open()
        except Exception as exc:
            raise PrinterUnavailableError(
                f"Falha ao abrir impressora '{self._printer_name}': {exc}"
            ) from exc
        if self._codepage:
            try:
                p.charcode(self._codepage)
            except Exception:  # codepage invalido nao impede impressao
                pass
        return p

    def print_job(self, job: PrintJob) -> None:
        p = self._open_raw()
        try:
            for line in job.lines:
                p.text(line + "\n")
            should_cut = job.cut_at_end or self._auto_cut
            if should_cut:
                try:
                    p.cut()
                except Exception:
                    # Muitos POS-58xx nao tem guilhotina; ignora silenciosamente
                    pass
        finally:
            try:
                p.close()
            except Exception:
                pass

    def is_available(self) -> bool:
        try:
            p = self._open_raw()
        except PrinterUnavailableError:
            return False
        try:
            return True
        finally:
            try:
                p.close()
            except Exception:
                pass

    def label(self) -> str:
        return f"Win32Raw ({self._printer_name})"


# ---------- settings helpers ----------


def _setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(Setting, key)
    if row is None or row.value is None:
        return default
    return str(row.value)


def _bool_setting(db: Session, key: str, default: bool = False) -> bool:
    raw = _setting(db, key, "true" if default else "false").strip().lower()
    return raw in {"true", "1", "sim", "yes", "s", "y"}


# ---------- factory ----------


def get_printer(db: Session) -> Printer:
    """
    Devolve a impressora ativa segundo o setting `printer_backend`.
    Sem cache: le o banco a cada chamada. Simples e previsivel.
    """
    backend = _setting(db, "printer_backend", "dummy").strip().lower() or "dummy"
    if backend == "dummy":
        return DummyPrinter()
    if backend == "win32raw":
        name = _setting(db, "printer_name", "")
        codepage = _setting(db, "printer_codepage", "")
        auto_cut = _bool_setting(db, "printer_auto_cut", False)
        return Win32RawPrinter(
            printer_name=name,
            codepage=codepage,
            auto_cut=auto_cut,
        )
    raise PrinterUnavailableError(
        f"Backend de impressora desconhecido: {backend!r}. "
        "Valores aceitos: dummy, win32raw."
    )
