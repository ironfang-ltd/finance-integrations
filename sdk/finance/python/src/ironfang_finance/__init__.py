from .client import IronfangFinance
from .errors import VERSION as __version__
from .errors import IronfangFinanceError

# Deprecated names from ironfang-financewolf, kept so existing code runs unchanged.
Financewolf = IronfangFinance
FinancewolfError = IronfangFinanceError

__all__ = ["IronfangFinance", "IronfangFinanceError", "Financewolf", "FinancewolfError"]
