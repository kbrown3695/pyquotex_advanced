"""Site customization for QuotexChart — suppress noisy but harmless warnings."""

import warnings

# Suppress sklearn joblib warnings at startup (before any modules load)
warnings.filterwarnings("ignore", message=".*sklearn.utils.parallel.*")
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn.utils.parallel")

# Also suppress these at the simplefilter level for maximum coverage
import sys
if 'sklearn' in sys.modules or 'joblib' in sys.modules:
    warnings.filterwarnings("ignore", message=".*sklearn.utils.parallel.*")
