"""Deprecated: the package is now ironfang_finance.

Importing ironfang_financewolf still works and gives the same objects, so
existing code keeps running. Change imports to ironfang_finance.
"""

import sys
import warnings

warnings.warn(
    "ironfang_financewolf is deprecated; import ironfang_finance instead",
    DeprecationWarning,
    stacklevel=2,
)

import ironfang_finance
from ironfang_finance import *  # noqa: F401,F403
from ironfang_finance import __all__, __version__  # noqa: F401
from ironfang_finance import cli, client, errors, runner, v2

for _name in ("cli", "client", "errors", "runner", "v2"):
    sys.modules[f"{__name__}.{_name}"] = getattr(ironfang_finance, _name)
