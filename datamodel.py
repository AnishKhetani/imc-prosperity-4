# Bridge module: re-exports prosperity4bt's datamodel so that
# `from datamodel import ...` works when running under prosperity4btx.
# On the real Prosperity platform, `datamodel` is provided natively.
try:
    from prosperity3bt.datamodel import *  # noqa: F401,F403
except ImportError:
    from prosperity4bt.datamodel import *  # noqa: F401,F403

