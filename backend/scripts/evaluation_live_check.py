"""One-off live check of the V2 research path (single paid request).

What it does:
  1. downloads ONE page with the real fetcher (SSRF-protected httpx);
  2. sends ONE DeepSeek request for ONE parameter over that page text;
  3. validates quotes against the stored page text (deterministic layer);
  4. prints the outcome, tokens and cost estimate.

Guards:
  * refuses to run without ``--yes``;
  * refuses without ``DEEPSEEK_API_KEY``;
  * makes exactly one provider call (no batch research, no DB writes);
  * optional ``--store-dsn`` must be an isolated local test database.

Usage:
    DEEPSEEK_API_KEY=... python backend/scripts/evaluation_live_check.py \\
        --url https://brand.example/product --parameter problem:dryness --yes
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.evaluation.documents import DocumentUnavailable, HttpDocumentFetcher  # noqa: E402
from app.evaluation.evidence import validate_candidates  # noqa: E402
from app.evaluation.llm_research import LlmResearchProvider  # noqa: E402
from app.evaluation.parameters import PARAMETERS  # noqa: E402
from app.evaluation.research import ResearchRequest  # noqa: E402
from app.evaluation.research_service import DEFAULT_METHOD_VERSION  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--parameter", default="problem:dryness")
    parser.add_argument("--product-name", default="Live check product")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--store-dsn", default="")
    args = parser.parse_args()

    if not args.yes:
        print("REFUSED: pass --yes to make a real (paid) provider call")
        return 2
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("BLOCKED: DEEPSEEK_API_KEY is not set in this environment")
        return 3
    if args.store_dsn:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        from evaluation_test_env import guard_local_test_dsn

        guard_local_test_dsn(args.store_dsn)

    parameter = PARAMETERS.get(args.parameter)
    if parameter is None:
        print(f"unknown parameter: {args.parameter}")
        return 2

    print("fetching:", args.url)
    try:
        document = HttpDocumentFetcher().fetch(args.url)
    except DocumentUnavailable as exc:
        print("FETCH FAILED:", exc.reason)
        return 4
    print(
        "fetched :",
        document.url,
        "chars=", len(document.text),
        "hash=", document.content_hash[:12],
        "provenance=", document.provenance,
    )

    request = ResearchRequest(
        product_id=0,
        product_name=args.product_name,
        composition_hash="live-check",
        ingredients=(),
        parameter_id=parameter.id,
        parameter_label=parameter.label,
        method_version=DEFAULT_METHOD_VERSION,
        scale_anchors=tuple(parameter.anchors),
        parameter_question=parameter.question,
        parameter_definition=parameter.definition,
        documents=(document,),
    )
    print("provider:", "deepseek (single request)")
    outcome = LlmResearchProvider(api_key=api_key).research(request)
    print(
        "outcome :",
        outcome.status,
        "candidates=", len(outcome.candidates),
        "tokens=", (outcome.tokens_in, outcome.tokens_out),
        "cost_usd=", outcome.cost_usd,
        "error=", outcome.error or "-",
    )
    if outcome.proposal is not None:
        print(
            "proposal:",
            outcome.proposal.applicability,
            "sufficient=", outcome.proposal.sufficient,
            "score=", outcome.proposal.score,
        )
        print("rationale:", outcome.proposal.rationale[:400])
    if outcome.candidates:
        evidence = validate_candidates(
            outcome.candidates,
            product_id=0,
            composition_hash="live-check",
            parameter_id=parameter.id,
            documents=(document,),
        )
        for item in evidence:
            print(
                "evidence:",
                item.verification,
                item.source.url,
                (item.rejection_reason or "quote confirmed")[:160],
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
