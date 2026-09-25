"""Gerador genérico de modelos XML a partir de schemas XSD 1.0."""

from .generator import GenerationOptions, GenerationResult, XsdModelGenerator
from .schema import SchemaCandidate, XsdCatalog, discover_schemas
from .conformance import ConformanceCase, ConformanceReport, run_conformance
from .validator import validate_xml

__all__ = [
    "GenerationOptions",
    "GenerationResult",
    "ConformanceCase",
    "ConformanceReport",
    "SchemaCandidate",
    "XsdCatalog",
    "XsdModelGenerator",
    "discover_schemas",
    "run_conformance",
    "validate_xml",
]
