"""
Modulo central de dinheiro e quantidade.

Regra inegociavel (CLAUDE.md):
- Dinheiro SEMPRE em centavos (int). Nunca float.
- Quantidade SEMPRE em milesimos (int). Nunca float.
- Todo calculo de total passa por `line_total_cents` (unica funcao de arredondamento).
"""

from __future__ import annotations

from typing import Literal

Unit = Literal["UN", "KG", "L"]
VALID_UNITS: tuple[Unit, ...] = ("UN", "KG", "L")

# Teto de seguranca contra overflow / entrada maliciosa.
# R$ 1.000.000,00 em centavos = 100_000_000
MAX_CENTS: int = 100_000_000
# 1.000.000 unidades em milesimos = 1_000_000_000
MAX_MILLI: int = 1_000_000_000


def line_total_cents(price_cents: int, qty_milli: int) -> int:
    """
    Calcula o total de uma linha de venda em centavos.

    Arredondamento para cima na meia casa (banker's half-up).
    Formula:  (price_cents * qty_milli + 500) // 1000

    Exemplos:
        0,350 kg x R$ 18,00 ->  line_total_cents(1800, 350) == 630
        3 x R$ 3,33         ->  line_total_cents(333, 3000) == 999
        1 x R$ 10,00        ->  line_total_cents(1000, 1000) == 1000

    Rejeita float na entrada (vide CLAUDE.md). bool e subclasse de int em
    Python, entao e explicitamente rejeitado para evitar bool virar 0/1
    silenciosamente.
    """
    if type(price_cents) is not int:
        raise TypeError(
            f"price_cents precisa ser int (recebi {type(price_cents).__name__})"
        )
    if type(qty_milli) is not int:
        raise TypeError(
            f"qty_milli precisa ser int (recebi {type(qty_milli).__name__})"
        )
    if price_cents < 0:
        raise ValueError("price_cents nao pode ser negativo")
    if qty_milli < 0:
        raise ValueError("qty_milli nao pode ser negativo")
    if price_cents > MAX_CENTS:
        raise ValueError(f"price_cents acima do teto ({MAX_CENTS})")
    if qty_milli > MAX_MILLI:
        raise ValueError(f"qty_milli acima do teto ({MAX_MILLI})")

    return (price_cents * qty_milli + 500) // 1000


def format_brl(cents: int) -> str:
    """
    Formata centavos como string no padrao brasileiro: "R$ 1.234,56".

    Exemplos:
        format_brl(1800)      -> "R$ 18,00"
        format_brl(0)         -> "R$ 0,00"
        format_brl(100000)    -> "R$ 1.000,00"
        format_brl(10000000)  -> "R$ 100.000,00"
    """
    if type(cents) is not int:
        raise TypeError(f"cents precisa ser int (recebi {type(cents).__name__})")

    negative = cents < 0
    abs_cents = -cents if negative else cents

    reais, resto = divmod(abs_cents, 100)
    # Formata parte inteira com separador de milhar brasileiro (ponto).
    # Trick: usa format {:,} do Python (que usa virgula) e troca por ponto.
    reais_str = f"{reais:,}".replace(",", ".")
    resultado = f"R$ {reais_str},{resto:02d}"
    return f"R$ -{resultado[3:]}" if negative else resultado


def parse_brl(text: str) -> int:
    """
    Converte texto no formato brasileiro em centavos.

    Aceita:
        "18,00"       -> 1800
        "18.00"       -> 1800  (formato americano, para conveniencia)
        "R$ 18,00"    -> 1800
        "1.234,56"    -> 123456 (separador de milhar brasileiro)
        "1,000.50"    -> 100050 (separador de milhar americano)

    Rejeita texto vazio, valor negativo, mais de 2 casas decimais.
    """
    if type(text) is not str:
        raise TypeError(f"text precisa ser str (recebi {type(text).__name__})")

    cleaned = text.strip()
    if not cleaned:
        raise ValueError("valor vazio")

    # Remove prefixo R$ e espacos
    if cleaned.upper().startswith("R$"):
        cleaned = cleaned[2:].strip()

    if cleaned.startswith("-"):
        raise ValueError("valor negativo nao e aceito")

    # Detecta separador decimal: o ULTIMO entre '.' e ',' e o decimal.
    last_comma = cleaned.rfind(",")
    last_dot = cleaned.rfind(".")

    if last_comma == -1 and last_dot == -1:
        # Numero inteiro de reais, ex.: "18"
        if not cleaned.isdigit():
            raise ValueError(f"formato invalido: {text!r}")
        return int(cleaned) * 100

    if last_comma > last_dot:
        # Virgula e decimal, ponto e milhar
        decimal_sep = ","
        thousand_sep = "."
    else:
        # Ponto e decimal, virgula e milhar
        decimal_sep = "."
        thousand_sep = ","

    integer_part, _, decimal_part = cleaned.rpartition(decimal_sep)
    integer_part = integer_part.replace(thousand_sep, "")

    if not integer_part.isdigit():
        raise ValueError(f"parte inteira invalida: {text!r}")
    if not decimal_part.isdigit():
        raise ValueError(f"parte decimal invalida: {text!r}")
    if len(decimal_part) > 2:
        raise ValueError(f"mais de 2 casas decimais: {text!r}")

    # Normaliza decimal para exatamente 2 digitos
    decimal_part = decimal_part.ljust(2, "0")
    return int(integer_part) * 100 + int(decimal_part)


def format_qty(qty_milli: int, unit: Unit) -> str:
    """
    Formata quantidade conforme a unidade.

    UN -> inteiro, sem casas:        format_qty(3000, "UN") -> "3"
    KG -> 3 casas decimais:          format_qty(350, "KG")  -> "0,350"
    L  -> 3 casas decimais:          format_qty(1500, "L")  -> "1,500"
    """
    if type(qty_milli) is not int:
        raise TypeError(
            f"qty_milli precisa ser int (recebi {type(qty_milli).__name__})"
        )
    if unit not in VALID_UNITS:
        raise ValueError(f"unidade invalida: {unit!r}. Use UN, KG ou L.")

    if unit == "UN":
        if qty_milli % 1000 != 0:
            # Permitimos para nao falhar silenciosamente, mas mostra fracao.
            inteiro, resto = divmod(qty_milli, 1000)
            return f"{inteiro},{resto:03d}"
        return str(qty_milli // 1000)

    # KG ou L: sempre 3 casas
    inteiro, resto = divmod(qty_milli, 1000)
    return f"{inteiro},{resto:03d}"


def parse_qty(text: str, unit: Unit) -> int:
    """
    Converte texto de quantidade em milesimos conforme a unidade.

    UN aceita: "3", "3,000"            -> 3000
    KG aceita: "0,350", "0.350", "1"   -> 350, 350, 1000
    L  aceita: idem KG.

    Rejeita negativo, mais de 3 casas decimais, teto excedido.
    """
    if type(text) is not str:
        raise TypeError(f"text precisa ser str (recebi {type(text).__name__})")
    if unit not in VALID_UNITS:
        raise ValueError(f"unidade invalida: {unit!r}. Use UN, KG ou L.")

    cleaned = text.strip().replace(".", ",")
    if not cleaned:
        raise ValueError("quantidade vazia")
    if cleaned.startswith("-"):
        raise ValueError("quantidade negativa nao e aceita")

    if "," in cleaned:
        integer_part, _, decimal_part = cleaned.partition(",")
        if not integer_part:
            integer_part = "0"
    else:
        integer_part = cleaned
        decimal_part = ""

    if not integer_part.isdigit():
        raise ValueError(f"parte inteira invalida: {text!r}")
    if decimal_part and not decimal_part.isdigit():
        raise ValueError(f"parte decimal invalida: {text!r}")
    if len(decimal_part) > 3:
        raise ValueError(f"mais de 3 casas decimais: {text!r}")

    decimal_part = decimal_part.ljust(3, "0") if decimal_part else "000"
    milli = int(integer_part) * 1000 + int(decimal_part)

    if milli > MAX_MILLI:
        raise ValueError(f"quantidade acima do teto ({MAX_MILLI})")

    return milli
