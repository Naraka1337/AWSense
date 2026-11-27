import json
import logging
from urllib.error import HTTPError, URLError

import pytest

from app.services import ai_explainer
from app.services.ml_detector import score_metrics
from app.services.risk_scorer import score_risk


def test_metric_scores_rank_anomaly_above_normal():
    baseline = [
        {
            "event_id": f"baseline-{index}",
            "resource_id": "test-resource",
            "cpu_utilization": 30 + index / 10,
            "network_in_bytes": 10000 + index * 10,
            "network_out_bytes": 15000 + index * 20,
            "request_count": 400 + index,
        }
        for index in range(40)
    ]
    normal = {**baseline[20], "event_id": "normal-check"}
    anomaly = {
        **normal,
        "event_id": "anomaly-check",
        "cpu_utilization": 99,
        "network_in_bytes": 500000,
        "network_out_bytes": 900000,
        "request_count": 85000,
    }
    normal_score, anomaly_score = score_metrics(baseline, [normal, anomaly])
    assert 0 <= normal_score < anomaly_score <= 1
    assert score_metrics(baseline, []) == []


def test_risk_weights_and_levels():
    assert score_risk(1, 100, 100, 100, 100) == {
        "risk_score": 100.0, "severity": "critical"
    }
    assert score_risk(0.8, 60, 50, 40, 20) == {
        "risk_score": 57.0, "severity": "medium"
    }
    assert score_risk(1, 100, 50, 0, 0)["severity"] == "high"
    assert score_risk(0, 0, 0, 0, 0)["severity"] == "low"


@pytest.mark.parametrize("provider", ["fallback", "openai", "gemini"])
def test_incident_explainer(monkeypatch, provider):
    for key in ("LLM_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    calls = []
    incident = {
        "title": "Cost spike",
        "resource_ids": ["test-resource"],
        "signals": [{"type": "cost_delta"}],
        "cost_delta_usd": 125,
    }
    llm_output = json.dumps({
        "summary": "Unexpected cost on test-resource.",
        "recommended_actions": ["Review recent billing records."],
    })

    def fake_post(url, headers, payload):
        calls.append(url)
        assert "Cost spike" in json.dumps(payload)
        if provider == "openai":
            assert headers["Authorization"] == "Bearer test-key"
            return {"choices": [{"message": {"content": llm_output}}]}
        if provider == "gemini":
            assert headers["x-goog-api-key"] == "test-key"
            return {"candidates": [{"content": {"parts": [{"text": llm_output}]}}]}
        raise AssertionError("Fallback should not call an API.")

    monkeypatch.setattr(ai_explainer, "_post_json", fake_post)
    if provider == "openai":
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    elif provider == "gemini":
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    result = ai_explainer.explain_incident(incident)
    assert "test-resource" in result["summary"]
    assert result["recommended_actions"][0].startswith("1. ")
    assert len(calls) == int(provider != "fallback")
    if provider == "fallback":
        assert "125" in result["summary"]
        assert result == ai_explainer.explain_incident(incident)
    else:
        assert result == {
            "summary": "Unexpected cost on test-resource.",
            "recommended_actions": ["1. Review recent billing records."],
        }


@pytest.mark.parametrize("provider", ["openai", "gemini"])
@pytest.mark.parametrize(
    ("failure", "error_type"),
    [
        ("network", "URLError"),
        ("http", "HTTPError"),
        ("timeout", "TimeoutError"),
        ("invalid_json", "JSONDecodeError"),
        ("missing_fields", "KeyError"),
        ("empty_results", "IndexError"),
        ("wrong_shape", "TypeError"),
        ("invalid_actions", "ValueError"),
    ],
)
def test_explainer_falls_back_on_provider_failure(
    monkeypatch, caplog, provider, failure, error_type,
):
    for key in ("LLM_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    incident = {
        "title": "Cost spike",
        "resource_ids": ["test-resource"],
        "signals": [{"type": "cost_delta"}],
        "cost_delta_usd": 125,
    }
    expected = ai_explainer.explain_incident(incident)
    monkeypatch.setenv(f"{provider.upper()}_API_KEY", "test-key")

    def fake_post(url, headers, payload):
        if failure == "network":
            raise URLError("provider-only details")
        if failure == "http":
            raise HTTPError(url, 503, "provider-only details", {}, None)
        if failure == "timeout":
            raise TimeoutError("provider-only details")
        if failure == "empty_results":
            return {"choices": []} if provider == "openai" else {"candidates": []}
        if failure == "wrong_shape":
            return None

        content = "invalid JSON"
        if failure == "missing_fields":
            content = '{"summary": "Partial provider reply"}'
        if failure == "invalid_actions":
            content = '{"summary": "Partial provider reply", "recommended_actions": []}'
        if provider == "openai":
            return {"choices": [{"message": {"content": content}}]}
        return {"candidates": [{"content": {"parts": [{"text": content}]}}]}

    monkeypatch.setattr(ai_explainer, "_post_json", fake_post)
    with caplog.at_level(logging.WARNING, logger=ai_explainer.__name__):
        assert ai_explainer.explain_incident(incident) == expected

    assert len(caplog.records) == 1
    assert error_type in caplog.text
    assert "deterministic template" in caplog.text
    assert "provider-only details" not in caplog.text
    assert "test-key" not in caplog.text
