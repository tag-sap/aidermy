"""Evaluation v2 — pure, deterministic per-parameter scoring.

The package does not import any legacy scoring module (scoring_engine,
decision_engine, phase1, profile_matrix). It can be tested without a database.
"""
from .contracts import (
    ENGINE_VERSION,
    STATUS_CONTRADICTORY,
    STATUS_EVALUATED,
    STATUS_INSUFFICIENT,
    STATUS_NOT_RESEARCHED,
    STATUS_STALE,
    ContractError,
    EngineResult,
    Parameter,
    ParameterEvaluation,
    RuleSet,
)
from .assessment import EVIDENCE_RULE_VERSION, assess, net_score, value_for_net
from .engine import evaluate
from .evidence import (
    Evidence,
    EvidenceCandidate,
    EvidenceError,
    Source,
    normalize_text,
    validate_candidate,
    validate_candidates,
)
from .freshness import is_current, select_current, stale_reason
from .parameters import PARAMETERS, collect_signals, resolve_relevance, validate_registry
from .rules import DEFAULT_RULE_VERSION, RULE_SETS, describe_rules, get_rules
from .research import (
    FakeResearchProvider,
    ResearchOutcome,
    ResearchProvider,
    ResearchRequest,
    candidate,
    insufficient,
    ok,
    provider_error,
    source_unavailable,
)
from .research_service import ResearchPlan, ResearchRunReport, ResearchService
from .snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    build_snapshot,
    profile_fingerprint,
    snapshot_summary,
    verify_snapshot,
)

__all__ = [
    "ENGINE_VERSION",
    "EVIDENCE_RULE_VERSION",
    "SNAPSHOT_SCHEMA_VERSION",
    "STATUS_EVALUATED",
    "STATUS_INSUFFICIENT",
    "STATUS_CONTRADICTORY",
    "STATUS_NOT_RESEARCHED",
    "STATUS_STALE",
    "ContractError",
    "EngineResult",
    "Evidence",
    "EvidenceCandidate",
    "EvidenceError",
    "FakeResearchProvider",
    "Parameter",
    "ParameterEvaluation",
    "ResearchOutcome",
    "ResearchPlan",
    "ResearchProvider",
    "ResearchRequest",
    "ResearchRunReport",
    "ResearchService",
    "RuleSet",
    "Source",
    "assess",
    "candidate",
    "insufficient",
    "net_score",
    "ok",
    "provider_error",
    "source_unavailable",
    "value_for_net",
    "normalize_text",
    "validate_candidate",
    "validate_candidates",
    "PARAMETERS",
    "RULE_SETS",
    "DEFAULT_RULE_VERSION",
    "build_snapshot",
    "collect_signals",
    "describe_rules",
    "evaluate",
    "get_rules",
    "is_current",
    "profile_fingerprint",
    "resolve_relevance",
    "select_current",
    "snapshot_summary",
    "stale_reason",
    "validate_registry",
    "verify_snapshot",
]
