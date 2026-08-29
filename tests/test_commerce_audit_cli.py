import json
from decimal import Decimal
from pathlib import Path

from oilsignal.agent.commerce import VerifiedPayment, build_payment_requirement
from oilsignal.cli import main
from oilsignal.storage.commerce import record_paid_fulfillment


def test_commerce_audit_cli_filters_by_gateway_reference(tmp_path: Path, capsys) -> None:
    requirement = build_payment_requirement(
        sku="weekly-petroleum-evidence",
        amount=Decimal("0.05"),
        currency="USD",
        evidence_sha256="a" * 64,
        description="Weekly petroleum evidence",
    )
    record_paid_fulfillment(
        tmp_path / "metadata.sqlite",
        requirement=requirement,
        verified=VerifiedPayment(
            protocol="mpp",
            response_headers={"Payment-Receipt": "secret-receipt"},
            external_id=requirement.external_id,
            reference="settlement-123",
            payer="agent:buyer",
        ),
    )

    exit_code = main(
        [
            "commerce-audit",
            "--data-dir",
            str(tmp_path),
            "--gateway-reference",
            "settlement-123",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert len(payload) == 1
    assert payload[0]["external_id"] == requirement.external_id
    assert payload[0]["gateway_reference"] == "settlement-123"
    assert payload[0]["payer"] == "agent:buyer"
    assert "response_headers" not in payload[0]
    assert "secret-receipt" not in str(payload)
