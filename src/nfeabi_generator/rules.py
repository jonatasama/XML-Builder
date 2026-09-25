from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .access_key import _access_key_character_value
from .constants import HOMOLOGATION_NAME


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    path: str
    message: str
    severity: str = "error"

    def __str__(self) -> str:
        return f"[{self.severity.upper()} {self.code}] {self.path}: {self.message}"


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _decimal(value: object, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("NaN")


def _different(left: Decimal, right: Decimal, tolerance: str = "0.01") -> bool:
    if left.is_nan() or right.is_nan():
        return True
    return abs(left - right) > Decimal(tolerance)


def _cpf_is_valid(value: str) -> bool:
    if len(value) != 11 or not value.isdigit() or len(set(value)) == 1:
        return False
    numbers = [int(char) for char in value]
    for size in (9, 10):
        total = sum(numbers[index] * (size + 1 - index) for index in range(size))
        digit = (total * 10) % 11
        if digit == 10:
            digit = 0
        if numbers[size] != digit:
            return False
    return True


def _cnpj_digit(base: str, weights: Iterable[int]) -> str:
    total = sum(
        _access_key_character_value(character) * weight
        for character, weight in zip(base, weights, strict=True)
    )
    digit = 11 - (total % 11)
    return "0" if digit >= 10 else str(digit)


def _cnpj_is_valid(value: str) -> bool:
    value = value.upper()
    if len(value) != 14 or not value[-2:].isdigit():
        return False
    if not all(char.isdigit() or "A" <= char <= "Z" for char in value[:12]):
        return False
    if len(set(value)) == 1:
        return False
    first = _cnpj_digit(value[:12], (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))
    second = _cnpj_digit(
        value[:12] + first, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    )
    return value[-2:] == first + second


def _walk_documents(value: object, path: str = "NFeABI") -> Iterable[tuple[str, str, str]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}/{key}"
            if key in {"CNPJ", "CPF"} and child is not None:
                yield key, str(child), child_path
            yield from _walk_documents(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value, start=1):
            yield from _walk_documents(child, f"{path}[{index}]")


def validate_business(document: Mapping[str, object], access_key: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    root = document.get("NFeABI")
    if not isinstance(root, Mapping):
        return [ValidationIssue("INPUT", "NFeABI", "Objeto raiz ausente.")]
    inf = root.get("infNFeABI")
    if not isinstance(inf, Mapping):
        return [ValidationIssue("INPUT", "NFeABI/infNFeABI", "Grupo ausente.")]

    ide = inf.get("ide") if isinstance(inf.get("ide"), Mapping) else {}
    operation = inf.get("infOper") if isinstance(inf.get("infOper"), Mapping) else {}
    tax_info = inf.get("gInfTrib") if isinstance(inf.get("gInfTrib"), Mapping) else {}
    ibscbs = tax_info.get("IBSCBS") if isinstance(tax_info.get("IBSCBS"), Mapping) else {}
    tax = ibscbs.get("gIBSCBS") if isinstance(ibscbs.get("gIBSCBS"), Mapping) else {}

    for kind, value, path in _walk_documents(root):
        valid = _cnpj_is_valid(value) if kind == "CNPJ" else _cpf_is_valid(value)
        if not valid:
            issues.append(ValidationIssue(kind, path, f"{kind} inválido."))

    tp_amb = str(ide.get("tpAmb", ""))
    if tp_amb == "2":
        named_groups: list[tuple[str, object]] = [("emit", inf.get("emit"))]
        named_groups.extend(("transmit", item) for item in _as_list(inf.get("transmit")))
        named_groups.extend(
            ("adquirente", item) for item in _as_list(inf.get("adquirente"))
        )
        for group_name, group in named_groups:
            if isinstance(group, Mapping) and group.get("xNome") != HOMOLOGATION_NAME:
                issues.append(
                    ValidationIssue(
                        "HOMOLOG",
                        f"infNFeABI/{group_name}/xNome",
                        f"Em homologação, xNome deve ser '{HOMOLOGATION_NAME}'.",
                    )
                )

    c_nf = str(ide.get("cNF", ""))
    if len(c_nf) == 7 and len(set(c_nf)) == 1:
        issues.append(
            ValidationIssue("B03-10", "infNFeABI/ide/cNF", "Código numérico repetitivo.")
        )
    try:
        if c_nf and int(c_nf) == int(str(ide.get("nNF", "-1"))):
            issues.append(
                ValidationIssue("B03-10", "infNFeABI/ide/cNF", "cNF não pode ser igual a nNF.")
            )
    except ValueError:
        pass

    tp_emis = str(ide.get("tpEmis", ""))
    has_contingency = isinstance(ide.get("gCont"), Mapping)
    if tp_emis == "1" and has_contingency:
        issues.append(ValidationIssue("B28-10", "infNFeABI/ide/gCont", "Proibido na emissão normal."))
    if tp_emis == "9" and not has_contingency:
        issues.append(ValidationIssue("B28-20", "infNFeABI/ide/gCont", "Obrigatório em contingência."))

    references = _as_list(inf.get("NFref"))
    if str(ide.get("finNFe", "")) == "2" and len(references) != 1:
        issues.append(
            ValidationIssue(
                "B25",
                "infNFeABI/NFref",
                "NF-e ABI de substituição deve possuir exatamente uma referência.",
            )
        )

    mod_oper = str(
        (ide.get("gModNat") or {}).get("modOper", "")
        if isinstance(ide.get("gModNat"), Mapping)
        else ""
    )
    nat_oper = str(
        (ide.get("gModNat") or {}).get("natOper", "")
        if isinstance(ide.get("gModNat"), Mapping)
        else ""
    )
    tp_nf = str(ide.get("tpNF", ""))
    transmitters = _as_list(inf.get("transmit"))
    buyers = _as_list(inf.get("adquirente"))

    _validate_sequence(transmitters, "@nTransmit", "E01a-10", "transmit", issues)
    _validate_sequence(buyers, "@nAdquir", "F01a-10", "adquirente", issues)
    _validate_participants(transmitters, buyers, mod_oper, tp_nf, issues)

    p_transmitted = operation.get("pTransImovel")
    if tp_nf == "0" and p_transmitted is not None:
        issues.append(ValidationIssue("H02-10", "infNFeABI/infOper/pTransImovel", "Proibido para tpNF=0."))
    if tp_nf == "1" and p_transmitted is None:
        issues.append(ValidationIssue("H02-20", "infNFeABI/infOper/pTransImovel", "Obrigatório para tpNF=1."))

    incorporation = operation.get("gIncorpLote")
    if mod_oper == "01" and not isinstance(incorporation, Mapping):
        issues.append(ValidationIssue("H08-10", "infNFeABI/infOper/gIncorpLote", "Obrigatório para modOper=01."))
    if mod_oper != "01" and isinstance(incorporation, Mapping):
        issues.append(ValidationIssue("H08-20", "infNFeABI/infOper/gIncorpLote", "Proibido para esta modalidade."))

    incorporation_flag = (
        str(incorporation.get("indIncorpLote", ""))
        if isinstance(incorporation, Mapping)
        else "0"
    )
    total = inf.get("total")
    if incorporation_flag == "1" and total is not None:
        issues.append(ValidationIssue("W01-10", "infNFeABI/total", "Proibido quando indIncorpLote=1."))
    if incorporation_flag != "1" and not isinstance(total, Mapping):
        issues.append(ValidationIssue("W01-20", "infNFeABI/total", "Obrigatório quando indIncorpLote não é 1."))

    if tax:
        _validate_calculated_values(
            inf, operation, tax, total, mod_oper, nat_oper, tp_nf, transmitters, buyers, issues
        )

    if inf.get("@Id") != "NFeABI" + access_key:
        issues.append(ValidationIssue("A03-10", "infNFeABI/@Id", "Id diverge da chave calculada."))

    issues.append(
        ValidationIssue(
            "EXT-TABLES",
            "infNFeABI/gInfTrib/IBSCBS",
            "CST, cClassTrib e seus indicadores ainda dependem das tabelas oficiais externas.",
            "warning",
        )
    )
    issues.append(
        ValidationIssue(
            "QR-PENDING",
            "NFeABI/infNFeSupl/qrCode",
            "Conteúdo e assinatura do QR Code não são recalculados: faltam URLs e especificação oficial no pacote.",
            "warning",
        )
    )
    return issues


def _validate_sequence(
    groups: list[object], attribute: str, code: str, group_name: str, issues: list[ValidationIssue]
) -> None:
    for index, group in enumerate(groups, start=1):
        if not isinstance(group, Mapping) or str(group.get(attribute, "")) != str(index):
            issues.append(
                ValidationIssue(
                    code,
                    f"infNFeABI/{group_name}[{index}]/{attribute}",
                    f"Sequencial esperado: {index}.",
                )
            )


def _validate_participants(
    transmitters: list[object],
    buyers: list[object],
    mod_oper: str,
    tp_nf: str,
    issues: list[ValidationIssue],
) -> None:
    for index, item in enumerate(transmitters, start=1):
        if not isinstance(item, Mapping):
            continue
        path = f"infNFeABI/transmit[{index}]"
        if tp_nf == "0" and item.get("pTransIndiv") is not None:
            issues.append(ValidationIssue("E18-10", path + "/pTransIndiv", "Proibido para tpNF=0."))
        if tp_nf == "1" and item.get("pTransIndiv") is None:
            issues.append(ValidationIssue("E18-20", path + "/pTransIndiv", "Obrigatório para tpNF=1."))
        if (tp_nf == "0" or mod_oper == "02") and item.get("indDeclarante") is not None:
            issues.append(ValidationIssue("E02-10", path + "/indDeclarante", "Indicador proibido."))
        if mod_oper == "02" and item.get("indContrib") is not None:
            issues.append(ValidationIssue("E19-10", path + "/indContrib", "Indicador proibido nesta modalidade."))
        if mod_oper != "02" and item.get("indContrib") is None:
            issues.append(ValidationIssue("E19-20", path + "/indContrib", "Indicador obrigatório."))

    if tp_nf == "1" and mod_oper != "02":
        declarants = [item for item in transmitters if isinstance(item, Mapping) and str(item.get("indDeclarante")) == "1"]
        if len(declarants) != 1:
            issues.append(ValidationIssue("E02-40", "infNFeABI/transmit", "Deve existir exatamente um declarante."))
        elif str(declarants[0].get("@nTransmit")) != "1":
            issues.append(ValidationIssue("E02", "infNFeABI/transmit", "O declarante deve ser nTransmit=1."))

    for index, item in enumerate(buyers, start=1):
        if not isinstance(item, Mapping):
            continue
        path = f"infNFeABI/adquirente[{index}]"
        p_acquisition = item.get("pAquisicao")
        if tp_nf == "0" or mod_oper != "02":
            if p_acquisition is not None:
                issues.append(ValidationIssue("F18-10", path + "/pAquisicao", "Percentual proibido."))
        elif p_acquisition is None:
            issues.append(ValidationIssue("F18-30", path + "/pAquisicao", "Percentual obrigatório."))
        if (tp_nf == "0" or mod_oper != "02") and item.get("indDeclarante") is not None:
            issues.append(ValidationIssue("F02-10", path + "/indDeclarante", "Indicador proibido."))
        if mod_oper != "02" and item.get("indContrib") is not None:
            issues.append(ValidationIssue("F19", path + "/indContrib", "Indicador só é previsto para modOper=02."))

    if tp_nf == "1" and mod_oper == "02":
        declarants = [item for item in buyers if isinstance(item, Mapping) and str(item.get("indDeclarante")) == "1"]
        if len(declarants) != 1:
            issues.append(ValidationIssue("F02-40", "infNFeABI/adquirente", "Deve existir exatamente um declarante."))
        elif str(declarants[0].get("@nAdquir")) != "1":
            issues.append(ValidationIssue("F02", "infNFeABI/adquirente", "O declarante deve ser nAdquir=1."))


def _validate_calculated_values(
    inf: Mapping[str, object],
    operation: Mapping[str, object],
    tax: Mapping[str, object],
    total: object,
    mod_oper: str,
    nat_oper: str,
    tp_nf: str,
    transmitters: list[object],
    buyers: list[object],
    issues: list[ValidationIssue],
) -> None:
    operation_total = _decimal(operation.get("vTotalOperacao"))
    individual = _decimal(tax.get("vOperacIndiv"))
    expected_individual = operation_total
    p_total = _decimal(operation.get("pTransImovel"), "100")
    if tp_nf == "1" and p_total != 0:
        participants = buyers if mod_oper == "02" else transmitters
        first = participants[0] if participants and isinstance(participants[0], Mapping) else {}
        percentage_name = "pAquisicao" if mod_oper == "02" else "pTransIndiv"
        expected_individual = operation_total * _decimal(first.get(percentage_name)) / p_total
    if _different(individual, expected_individual):
        issues.append(ValidationIssue("U10", "infNFeABI/gInfTrib/IBSCBS/gIBSCBS/vOperacIndiv", f"Esperado {expected_individual:.2f}."))

    red_adjustment = _decimal(tax.get("vRedAjusteIndiv"))
    red_social = _decimal(tax.get("vRedSocialIndiv"))
    expected_base: Decimal | None = None
    if mod_oper == "01":
        expected_base = max(individual - red_adjustment - red_social, Decimal("0"))
    elif mod_oper == "02":
        group = operation.get("gRedAjusteImovel")
        property_reducer = _decimal(group.get("vRedAjusteImovel")) if isinstance(group, Mapping) else Decimal("0")
        expected_base = Decimal("0") if property_reducer == 0 else max(individual - red_adjustment - red_social, Decimal("0"))
    elif mod_oper == "03":
        expected_base = individual
    elif mod_oper == "04" and nat_oper in {"13", "14"} and str(operation.get("indTorna")) == "1":
        expected_base = _decimal(tax.get("vTornaIndiv"))
    elif mod_oper == "04" and nat_oper == "15":
        expected_base = max(individual - red_adjustment - red_social, Decimal("0"))

    base = _decimal(tax.get("vBC"))
    if expected_base is not None and _different(base, expected_base):
        issues.append(ValidationIssue("U14", "infNFeABI/gInfTrib/IBSCBS/gIBSCBS/vBC", f"Esperado {expected_base:.2f}."))

    if not isinstance(total, Mapping):
        return
    trib_total = total.get("tribTot") if isinstance(total.get("tribTot"), Mapping) else {}
    comparisons = [
        ("vTotalOperacao", operation_total, _decimal(total.get("vTotalOperacao")), "W03"),
        ("vOperacIndiv", individual, _decimal(total.get("vOperacIndiv")), "W04"),
        ("vBC", base, _decimal(trib_total.get("vBC")), "W07-10"),
        ("vIBSUF", _decimal((tax.get("gIBSUF") or {}).get("vIBSUF") if isinstance(tax.get("gIBSUF"), Mapping) else None), _decimal(trib_total.get("vIBSUF")), "W08-10"),
        ("vIBSMun", _decimal((tax.get("gIBSMun") or {}).get("vIBSMun") if isinstance(tax.get("gIBSMun"), Mapping) else None), _decimal(trib_total.get("vIBSMun")), "W09"),
        ("vCBS", _decimal((tax.get("gCBS") or {}).get("vCBS") if isinstance(tax.get("gCBS"), Mapping) else None), _decimal(trib_total.get("vCBS")), "W10"),
    ]
    for name, expected, actual, code in comparisons:
        if _different(actual, expected):
            issues.append(ValidationIssue(code, f"infNFeABI/total/{name}", f"Esperado {expected:.2f}."))

    expected_invoice = (
        _decimal(total.get("vOperacIndiv"))
        + _decimal(trib_total.get("vIBSUF"))
        + _decimal(trib_total.get("vIBSMun"))
        + _decimal(trib_total.get("vCBS"))
    )
    if _different(_decimal(total.get("vNF")), expected_invoice):
        issues.append(ValidationIssue("W11-10", "infNFeABI/total/vNF", f"Esperado {expected_invoice:.2f}."))

