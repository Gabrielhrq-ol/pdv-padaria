"""Testes da factory de impressora e dos adapters."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models import Setting
from app.services.printer import (
    DummyPrinter,
    PrintJob,
    Printer,
    PrinterUnavailableError,
    Win32RawPrinter,
    get_printer,
)


class TestFactory:
    def test_default_e_dummy(self, session) -> None:
        p = get_printer(session)
        assert isinstance(p, DummyPrinter)

    def test_setting_dummy_explicito(self, session) -> None:
        session.add(Setting(key="printer_backend", value="dummy"))
        session.commit()
        p = get_printer(session)
        assert isinstance(p, DummyPrinter)

    def test_setting_win32raw(self, session) -> None:
        session.add(Setting(key="printer_backend", value="win32raw"))
        session.add(Setting(key="printer_name", value="POS-58"))
        session.add(Setting(key="printer_codepage", value="CP850"))
        session.add(Setting(key="printer_auto_cut", value="true"))
        session.commit()
        p = get_printer(session)
        assert isinstance(p, Win32RawPrinter)
        assert p._printer_name == "POS-58"
        assert p._codepage == "CP850"
        assert p._auto_cut is True

    def test_backend_desconhecido_lanca(self, session) -> None:
        session.add(Setting(key="printer_backend", value="invalido"))
        session.commit()
        with pytest.raises(PrinterUnavailableError):
            get_printer(session)

    def test_win32raw_sem_nome_lanca(self, session) -> None:
        session.add(Setting(key="printer_backend", value="win32raw"))
        session.add(Setting(key="printer_name", value=""))
        session.commit()
        with pytest.raises(PrinterUnavailableError):
            get_printer(session)


class TestDummy:
    def test_grava_jobs(self) -> None:
        p = DummyPrinter()
        p.print_job(PrintJob(lines=["abc", "def"]))
        assert len(p.jobs) == 1
        assert p.last_output() == "abc\ndef"

    def test_sempre_disponivel(self) -> None:
        assert DummyPrinter().is_available() is True

    def test_label(self) -> None:
        assert DummyPrinter().label() == "Dummy"


class TestWin32RawMock:
    """Testa Win32RawPrinter sem hardware, via mock do python-escpos."""

    def test_print_job_chama_text_e_cut(self) -> None:
        p = Win32RawPrinter(printer_name="FAKE", codepage="CP850", auto_cut=True)

        fake_raw = MagicMock()
        with patch.object(p, "_open_raw", return_value=fake_raw):
            p.print_job(PrintJob(lines=["linha 1", "linha 2"]))

        # Cada linha + \n
        assert fake_raw.text.call_count == 2
        fake_raw.text.assert_any_call("linha 1\n")
        fake_raw.text.assert_any_call("linha 2\n")
        fake_raw.cut.assert_called_once()
        fake_raw.close.assert_called_once()

    def test_cut_desligado_nao_chama_cut(self) -> None:
        p = Win32RawPrinter(printer_name="FAKE", auto_cut=False)
        fake_raw = MagicMock()
        with patch.object(p, "_open_raw", return_value=fake_raw):
            p.print_job(PrintJob(lines=["x"], cut_at_end=False))
        fake_raw.cut.assert_not_called()

    def test_cut_falhou_nao_quebra(self) -> None:
        p = Win32RawPrinter(printer_name="FAKE", auto_cut=True)
        fake_raw = MagicMock()
        fake_raw.cut.side_effect = RuntimeError("sem guilhotina")
        with patch.object(p, "_open_raw", return_value=fake_raw):
            # Nao deve lancar
            p.print_job(PrintJob(lines=["x"]))

    def test_falha_ao_abrir_lanca_printer_unavailable(self) -> None:
        p = Win32RawPrinter(printer_name="NAOEXISTE")
        with patch.object(
            p, "_open_raw", side_effect=PrinterUnavailableError("sem driver")
        ):
            with pytest.raises(PrinterUnavailableError):
                p.print_job(PrintJob(lines=["x"]))

    def test_is_available_true_quando_abre(self) -> None:
        p = Win32RawPrinter(printer_name="FAKE")
        fake_raw = MagicMock()
        with patch.object(p, "_open_raw", return_value=fake_raw):
            assert p.is_available() is True

    def test_is_available_false_quando_erro(self) -> None:
        p = Win32RawPrinter(printer_name="NAOEXISTE")
        with patch.object(
            p, "_open_raw", side_effect=PrinterUnavailableError("x")
        ):
            assert p.is_available() is False

    def test_label_inclui_nome(self) -> None:
        p = Win32RawPrinter(printer_name="EPSON TM-T20X")
        assert "EPSON TM-T20X" in p.label()


class TestNomeInvalido:
    def test_rejeita_nome_vazio_na_construcao(self) -> None:
        with pytest.raises(PrinterUnavailableError):
            Win32RawPrinter(printer_name="")

    def test_rejeita_nome_so_espaco(self) -> None:
        with pytest.raises(PrinterUnavailableError):
            Win32RawPrinter(printer_name="   ")
