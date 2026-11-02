"""Exception hierarchy for the data_export package.

Callers can catch ``ExportError`` to handle any failure raised by this module,
or catch a specific subclass when they need to react to one failure mode.
Low-level exceptions (``TypeError`` from ``json``, ``csv.Error`` and so on)
are never leaked directly: they are wrapped and chained with ``raise ... from``
so the original cause stays visible in tracebacks.
"""


class ExportError(Exception):
    """Base class for every error raised by data_export."""


class UnsupportedFormatError(ExportError, ValueError):
    """Raised when an export is requested in a format we don't support.

    Also subclasses ``ValueError`` because an unknown format is, semantically,
    a bad argument value. Existing ``except ValueError`` handlers still work.
    """


class SerializationError(ExportError):
    """Raised when the data cannot be converted into the requested format.

    Typical causes: a value of a type we don't know how to serialise
    (e.g. a custom object), or a nested structure in a CSV export.
    """
