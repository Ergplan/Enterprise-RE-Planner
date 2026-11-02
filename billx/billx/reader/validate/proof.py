"""`decide`, the verification rule of build prompt 5.2, at the path the prompt names.

The implementation is `billx.core.proof` (core cannot import the engines, and the core
schema's validator needs the rule); this module re-exports it so `from
billx.reader.validate.proof import decide` is the one name every caller uses.
"""

from billx.core.proof import PROOF_RULE_VERSION, Decision, ReadingView, decide, independent

__all__ = ["PROOF_RULE_VERSION", "Decision", "ReadingView", "decide", "independent"]
