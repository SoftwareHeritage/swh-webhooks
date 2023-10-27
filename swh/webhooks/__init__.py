from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)


# hack for Python 3.7 to fix import of svix module
import sys

if sys.version_info < (3, 8):
    import typing

    from typing_extensions import Literal

    typing.Literal = Literal
