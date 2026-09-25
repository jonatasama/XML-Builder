class NFeAbiError(Exception):
    """Erro esperado e apresentável pela CLI."""


class InputError(NFeAbiError):
    """Entrada JSON ausente, ambígua ou incompatível com o schema."""


class SchemaValidationError(NFeAbiError):
    """XML não atende ao XSD selecionado."""


class BusinessValidationError(NFeAbiError):
    """Dados violam regras de negócio implementadas localmente."""


class SignatureError(NFeAbiError):
    """Falha ao produzir ou conferir a assinatura XMLDSig."""

