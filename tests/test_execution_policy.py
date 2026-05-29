from pathlib import Path

from pymercator.execution_policy import (
    load_execution_policy,
    validate_execution_policy,
    write_execution_policy_template,
)


def test_execution_policy_template_is_safe(tmp_path: Path):
    output = tmp_path / "execution_policy.json"

    write_execution_policy_template(output)

    policy = load_execution_policy(output)
    validation = validate_execution_policy(output)

    assert policy["execution_mode"] == "ANALYSIS_ONLY"
    assert policy["allow_order_routing"] is False
    assert policy["require_human_confirmation"] is True
    assert validation["valid"] is True


def test_execution_policy_rejects_order_routing(tmp_path: Path):
    output = tmp_path / "execution_policy.json"

    output.write_text(
        '''
{
  "execution_mode": "ANALYSIS_ONLY",
  "allow_order_routing": true,
  "require_human_confirmation": true
}
''',
        encoding="utf-8",
    )

    validation = validate_execution_policy(output)

    assert validation["valid"] is False
    assert validation["errors"]
