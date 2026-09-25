from __future__ import annotations

import re
from collections.abc import MutableMapping

from .errors import InputError


def _required(mapping: MutableMapping[str, object], key: str, path: str) -> str:
    value = mapping.get(key)
    if value is None or str(value) == "":
        raise InputError(f"Campo obrigatório ausente: {path}/{key}")
    return str(value)


def _access_key_character_value(character: str) -> int:
    """Valor usado pelo cálculo DF-e compatível com CNPJ alfanumérico.

    Dígitos mantêm seu valor decimal. Letras usam o valor ASCII menos 48,
    conforme a convenção do CNPJ alfanumérico.
    """

    if not re.fullmatch(r"[A-Z0-9]", character):
        raise InputError(f"Caractere inválido na chave de acesso: {character!r}")
    return ord(character) - 48


def calculate_mod11_digit(base: str) -> str:
    if len(base) != 43:
        raise InputError(
            f"A base da chave deve possuir 43 posições antes do DV; recebidas {len(base)}."
        )

    total = 0
    weight = 2
    for character in reversed(base):
        total += _access_key_character_value(character) * weight
        weight = 2 if weight == 9 else weight + 1

    digit = 11 - (total % 11)
    return "0" if digit >= 10 else str(digit)


def prepare_access_key(document: MutableMapping[str, object]) -> str:
    """Calcula chave, cDV e Id diretamente no documento JSON mutável."""

    root = document.get("NFeABI")
    if not isinstance(root, MutableMapping):
        raise InputError("O JSON deve possuir um objeto raiz chamado 'NFeABI'.")

    inf = root.get("infNFeABI")
    if not isinstance(inf, MutableMapping):
        raise InputError("Objeto obrigatório ausente: NFeABI/infNFeABI")

    ide = inf.get("ide")
    emit = inf.get("emit")
    if not isinstance(ide, MutableMapping) or not isinstance(emit, MutableMapping):
        raise InputError("Objetos obrigatórios ausentes: infNFeABI/ide ou infNFeABI/emit")

    c_uf = _required(ide, "cUF", "infNFeABI/ide")
    emission = _required(ide, "dhEmi", "infNFeABI/ide")
    model = _required(ide, "mod", "infNFeABI/ide")
    series = _required(ide, "serie", "infNFeABI/ide")
    number = _required(ide, "nNF", "infNFeABI/ide")
    emission_type = _required(ide, "tpEmis", "infNFeABI/ide")
    authorization_site = _required(ide, "nSiteAutoriz", "infNFeABI/ide")
    numeric_code = _required(ide, "cNF", "infNFeABI/ide")

    if not re.match(r"^\d{4}-\d{2}-\d{2}T", emission):
        raise InputError("dhEmi deve começar no formato AAAA-MM-DDT.")

    if "CNPJ" in emit:
        issuer = str(emit["CNPJ"]).upper()
        if not re.fullmatch(r"[A-Z0-9]{12}[0-9]{2}", issuer):
            raise InputError("CNPJ do emitente deve possuir 12 posições alfanuméricas e 2 DVs.")
    elif "CPF" in emit:
        cpf = str(emit["CPF"])
        if not re.fullmatch(r"\d{11}", cpf):
            raise InputError("CPF do emitente deve possuir 11 dígitos.")
        issuer = cpf.zfill(14)
    else:
        raise InputError("O emitente deve possuir CNPJ ou CPF.")

    if not re.fullmatch(r"\d{2}", c_uf):
        raise InputError("cUF deve possuir 2 dígitos.")
    if model != "77":
        raise InputError("O modelo da NF-e ABI deve ser 77.")
    if not re.fullmatch(r"\d{7}", numeric_code):
        raise InputError("cNF deve possuir exatamente 7 dígitos.")
    if not re.fullmatch(r"[19]", emission_type):
        raise InputError("tpEmis deve ser 1 ou 9.")
    if not re.fullmatch(r"\d", authorization_site):
        raise InputError("nSiteAutoriz deve possuir um dígito.")

    year_month = emission[2:4] + emission[5:7]
    base = "".join(
        [
            c_uf,
            year_month,
            issuer,
            model,
            series.zfill(3),
            number.zfill(9),
            emission_type,
            authorization_site,
            numeric_code,
        ]
    )
    digit = calculate_mod11_digit(base)
    key = base + digit

    provided_digit = ide.get("cDV")
    if provided_digit is not None and str(provided_digit) != digit:
        raise InputError(
            f"cDV informado ({provided_digit}) diverge do calculado ({digit})."
        )
    ide["cDV"] = digit

    expected_id = "NFeABI" + key
    provided_id = inf.get("@Id")
    if provided_id is not None and str(provided_id) != expected_id:
        raise InputError("infNFeABI/@Id diverge da chave de acesso calculada.")
    inf["@Id"] = expected_id
    inf.setdefault("@versao", "1.00")
    return key

