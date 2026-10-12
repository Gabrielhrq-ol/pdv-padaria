"""
Teste de impressora termica para o PDV Padaria.

Uso:
    python scripts/test_printer.py "NOME_DA_IMPRESSORA" [--columns 32] [--codepage CP850] [--cut]

Argumentos:
    printer_name      Nome EXATO da impressora como aparece em
                      "Impressoras e scanners" do Windows.
    --columns N       Largura do cupom em colunas (default: 32 para 58 mm).
    --codepage CP     Codepage para acentos (ex.: CP850, CP858, CP860).
                      Sem este flag, imprime no codepage padrao da impressora.
    --cut             Tenta cortar o papel ao final (muitos POS-58xx nao
                      tem guilhotina; deixe desligado se nao tiver certeza).

Dependencias (NAO estao no requirements.txt da Fase 1):
    pip install python-escpos==3.1 pywin32

Impressora alvo (nao confirmada ainda):
    POS-5890U-L, 58 mm, USB + Bluetooth.
    Compatibilidade com ESC/POS NAO foi confirmada pela fonte do cliente.

O que este script faz:
    1. Conecta via Win32Raw (usa o driver do Windows, nao precisa trocar
       driver USB por WinUSB).
    2. Imprime um cupom de teste com texto normal, negrito, uma linha
       simulando venda, acentos com e sem.
    3. Se --cut, envia o comando de corte ao final.

O que fazer com o resultado:
    - Imprimiu e saiu legivel: a impressora fala ESC/POS. Anote
      resultado dos acentos.
    - Imprimiu com acentos errados: ajuste --codepage e repita.
    - Imprimiu lixo ou simbolos: a impressora provavelmente NAO fala
      ESC/POS. Pare e revise a estrategia (ver secao 0.1 do guia).
    - Nao imprimiu nada: nome errado, driver nao instalado, ou offline.

NOTA DE INCERTEZA:
    - A classe Win32Raw do python-escpos aceita o parametro `printer_name`
      (confirmado na doc oficial de python-escpos 3.1).
    - O metodo `open()` precisa ser chamado explicitamente antes de usar.
    - A sintaxe `set(align=..., bold=...)` esta documentada mas pode variar
      em futuras versoes.
    - O codepage exato para a POS-5890U-L nao esta documentado em fonte
      publica confiavel. Vamos descobrir no teste real.
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Teste de impressora termica para PDV Padaria.",
    )
    parser.add_argument(
        "printer_name",
        help='Nome da impressora como aparece em "Impressoras e scanners".',
    )
    parser.add_argument(
        "--columns",
        type=int,
        default=32,
        help="Largura do cupom em colunas (default: 32 para 58 mm).",
    )
    parser.add_argument(
        "--codepage",
        default=None,
        help="Codepage opcional (CP850, CP858, CP860...).",
    )
    parser.add_argument(
        "--cut",
        action="store_true",
        help="Tenta cortar o papel ao final (default: NAO corta).",
    )
    args = parser.parse_args()

    try:
        from escpos.printer import Win32Raw  # type: ignore[import-not-found]
    except ImportError:
        print(
            "ERRO: python-escpos nao esta instalado.\n"
            "Instale com: pip install python-escpos==3.1 pywin32",
            file=sys.stderr,
        )
        return 2

    width = args.columns
    divider = "-" * width

    printer = Win32Raw(printer_name=args.printer_name)
    try:
        printer.open()
    except Exception as exc:
        print(
            f"ERRO ao abrir a impressora '{args.printer_name}': {exc}\n"
            "Verifique:\n"
            "  - Nome exato em 'Impressoras e scanners' (copie e cole).\n"
            "  - Driver instalado.\n"
            "  - Impressora ligada e com papel.",
            file=sys.stderr,
        )
        return 1

    try:
        if args.codepage:
            try:
                printer.charcode(args.codepage)
                print(f"Codepage definido: {args.codepage}")
            except Exception as exc:
                print(
                    f"AVISO: nao consegui definir codepage {args.codepage}: {exc}",
                    file=sys.stderr,
                )

        # Cabecalho
        printer.set(align="center", bold=True, double_height=True)
        printer.text("PADARIA TESTE\n")
        printer.set(align="center", bold=False, double_height=False)
        printer.text("CUPOM NAO FISCAL\n")
        printer.text("SEM VALOR FISCAL - CONTROLE INTERNO\n")
        printer.text(divider + "\n")

        # Dados da venda simulada
        printer.set(align="left")
        printer.text(f"Venda: 000001 (teste)\n")
        printer.text("Operador: TESTE\n")
        printer.text(divider + "\n")

        # Item com unidade por peso (centavos + milesimos)
        # 0,350 kg x R$ 18,00 = R$ 6,30
        line_item = "Pao frances"
        line_qty = "0,350 kg x 18,00"
        line_total = "6,30"
        printer.text(line_item + "\n")
        # Formata quantidade a esquerda e total a direita
        padding = max(1, width - len(line_qty) - len(line_total))
        printer.text(line_qty + (" " * padding) + line_total + "\n")

        # Item unitario
        line_item2 = "Refrigerante 2L"
        line_qty2 = "1 UN x 9,50"
        line_total2 = "9,50"
        printer.text(line_item2 + "\n")
        padding2 = max(1, width - len(line_qty2) - len(line_total2))
        printer.text(line_qty2 + (" " * padding2) + line_total2 + "\n")

        printer.text(divider + "\n")

        # Total
        total_label = "TOTAL"
        total_value = "15,80"
        padding_total = max(1, width - len(total_label) - len(total_value))
        printer.set(bold=True)
        printer.text(total_label + (" " * padding_total) + total_value + "\n")
        printer.set(bold=False)

        printer.text(divider + "\n")

        # Teste de acentos
        printer.text("Com acento : acao, coracao, pao, cafe\n")
        printer.text("Com acentos: acao, coracao, pao, cafe\n")
        printer.text("Com acentos: " + "ação, coração, pão, café" + "\n")
        printer.text(divider + "\n")

        # Rodape
        printer.set(align="center")
        printer.text("Obrigado e volte sempre!\n")
        printer.text("\n\n")

        # Corte opcional
        if args.cut:
            try:
                printer.cut()
                print("Comando de corte enviado.")
            except Exception as exc:
                print(
                    f"AVISO: comando de corte falhou: {exc}\n"
                    "A impressora provavelmente nao tem guilhotina.",
                    file=sys.stderr,
                )
    finally:
        try:
            printer.close()
        except Exception:
            pass

    print(
        "OK: enviei o cupom para a impressora.\n"
        "Confira o papel. Resultados possiveis:\n"
        "  - Legivel + acentos ok: ESC/POS funciona. Anote o codepage.\n"
        "  - Acentos errados: teste outro --codepage (CP850, CP858, CP860).\n"
        "  - Lixo ou simbolos: provavel que a impressora NAO fale ESC/POS.\n"
        "  - Vazio: impressora offline ou nome errado."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
