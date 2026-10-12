"""
Interface de impressao e implementacao Dummy.

Fase 1: apenas a interface e a Dummy. Implementacao real entra na Fase 5,
depois do teste real da impressora (ver CLAUDE.md secao Hardware).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class PrintJob:
    """
    Representa um trabalho de impressao.

    `lines` sao strings prontas (como viriam de app/services/receipt.py na
    Fase 5). A classe Printer e burra: apenas armazena / escreve. A
    formatacao em colunas e feita antes.
    """

    lines: list[str] = field(default_factory=list)
    cut_at_end: bool = False


class Printer(ABC):
    """Interface de impressora. Implementacao real na Fase 5."""

    @abstractmethod
    def print_job(self, job: PrintJob) -> None:
        """Executa o trabalho de impressao. Pode falhar."""

    @abstractmethod
    def is_available(self) -> bool:
        """Diz se a impressora esta acessivel."""


class DummyPrinter(Printer):
    """
    Implementacao sem hardware. Guarda os jobs em memoria para inspecao.
    Usado em desenvolvimento e em TODOS os testes.
    """

    def __init__(self) -> None:
        self.jobs: list[PrintJob] = []

    def print_job(self, job: PrintJob) -> None:
        self.jobs.append(job)

    def is_available(self) -> bool:
        return True

    def last_output(self) -> str:
        if not self.jobs:
            return ""
        return "\n".join(self.jobs[-1].lines)


_default_printer: Printer | None = None


def get_printer() -> Printer:
    """
    Retorna a impressora ativa. Fase 1: sempre DummyPrinter.
    Fase 5: le a configuracao em settings e devolve Win32Raw / Dummy.
    """
    global _default_printer
    if _default_printer is None:
        _default_printer = DummyPrinter()
    return _default_printer


def set_printer_for_tests(printer: Printer) -> None:
    """Permite testes substituirem a impressora global."""
    global _default_printer
    _default_printer = printer


def reset_printer() -> None:
    """Volta para a DummyPrinter padrao."""
    global _default_printer
    _default_printer = None
