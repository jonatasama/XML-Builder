class XsdModelError(Exception):
    """Erro controlado apresentado pela CLI ou pela interface gráfica."""


class SchemaLoadError(XsdModelError):
    """O conjunto de schemas não pôde ser carregado."""


class GenerationError(XsdModelError):
    """O modelo XML não pôde ser gerado."""


class GeneratedXmlValidationError(XsdModelError):
    """O XML sintetizado não passou pela validação XSD."""

