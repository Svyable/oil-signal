from __future__ import annotations

import argparse
import json
import os

from oilsignal.agent.buyer import BuyerPaymentRequired, OilSignalBuyer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Poll and fetch one OilSignal machine product with digest verification."
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("OILSIGNAL_AGENT_BASE_URL", "http://localhost:8000"),
    )
    parser.add_argument("--sku", default="weekly-petroleum-delta")
    parser.add_argument(
        "--credential-header",
        default=os.getenv("OILSIGNAL_AGENT_CREDENTIAL_HEADER"),
        help="Optional payment/pilot credential header name.",
    )
    parser.add_argument(
        "--credential",
        default=os.getenv("OILSIGNAL_AGENT_CREDENTIAL"),
        help="Optional credential value. Prefer the environment over shell history.",
    )
    parser.add_argument(
        "--etag",
        default=os.getenv("OILSIGNAL_AGENT_STATE_ETAG"),
        help="Optional previous product-state ETag for free revalidation.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    credential_headers: dict[str, str] = {}
    if bool(args.credential_header) != bool(args.credential):
        raise SystemExit("--credential-header and --credential must be supplied together")
    if args.credential_header and args.credential:
        credential_headers[args.credential_header] = args.credential

    with OilSignalBuyer(args.base_url) as buyer:
        state_result = buyer.poll_state(args.sku, etag=args.etag)
        if state_result.not_modified:
            print(json.dumps({"status": "unchanged", "etag": state_result.etag}, indent=2))
            return 0
        if state_result.state is None:
            raise RuntimeError("changed product state did not include a state body")
        state = state_result.state
        print(
            json.dumps(
                {
                    "status": "changed",
                    "sku": state.sku,
                    "as_of": state.as_of,
                    "evidence_sha256": state.evidence_sha256,
                    "state_sha256": state.state_sha256,
                    "state_etag": state_result.etag,
                    "freshness": state.freshness.status.value,
                    "price": state.price.model_dump(mode="json") if state.price else None,
                    "payment_protocols": state.payment_protocols,
                },
                indent=2,
            )
        )

        try:
            result = buyer.fetch_evidence(
                args.sku,
                credential_headers=credential_headers,
                expected_evidence_sha256=state.evidence_sha256,
            )
        except BuyerPaymentRequired as exc:
            print(
                json.dumps(
                    {
                        "status": "payment_required",
                        "problem": exc.problem.model_dump(mode="json"),
                    },
                    indent=2,
                )
            )
            return 2

        if result.evidence is None:
            raise RuntimeError("evidence request returned no evidence body")
        print(
            json.dumps(
                {
                    "status": "fulfilled",
                    "sku": result.evidence.sku,
                    "as_of": result.evidence.as_of,
                    "evidence_sha256": result.evidence.evidence_sha256,
                    "evidence_etag": result.etag,
                    "claims": [claim.model_dump(mode="json") for claim in result.evidence.claims],
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
