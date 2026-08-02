"""Turn a pile of postmortems into a triage decision tree and candidate SLIs.

The pipeline is deliberately deterministic and explainable end to end:

    markdown -> Incident (parser) -> Signal tokens (signals)
             -> Patterns (patterns) -> decision tree (decision_tree) -> report

No embeddings, no model calls. During an incident you need an answer you can
argue with, not a similarity score you have to trust.
"""

from postmortem_miner.models import Incident, Pattern, Signal, SignalKind

__all__ = ["Incident", "Pattern", "Signal", "SignalKind", "__version__"]
__version__ = "0.2.0"
