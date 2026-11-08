import os
from fastapi.testclient import TestClient

# Set test environment variables before importing app
os.environ["MODEL_VERSION"] = "v1-test"
os.environ["HOSTNAME"] = "test-pod-0"

from service.main import app, validate_output

client = TestClient(app)


def test_healthz():
    """Liveness probe must return HTTP 200 while process is alive."""
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "alive"}


def test_readyz_before_model_loads():
    """Readiness probe must return HTTP 503 until the model is loaded."""
    # Since background thread has not loaded a real model in test, should return 503
    from service import main as svc
    svc.MODEL_READY = False
    res = client.get("/readyz")
    assert res.status_code == 503
    assert res.json() == {"status": "loading"}


def test_validate_output_valid():
    """Validation must accept correct 4-key JSON with valid intent."""
    valid_raw = '{"intent": "alarm_set", "date": "tomorrow", "time": "seven am", "place": null}'
    parsed = validate_output(valid_raw)
    assert parsed is not None
    assert parsed["intent"] == "alarm_set"
    assert parsed["date"] == "tomorrow"
    assert parsed["time"] == "seven am"
    assert parsed["place"] is None


def test_validate_output_invalid_keys():
    """Validation must reject JSON with missing or extra keys."""
    # Extra key
    bad_extra = '{"intent": "alarm_set", "date": null, "time": null, "place": null, "extra": 123}'
    assert validate_output(bad_extra) is None

    # Missing key
    bad_missing = '{"intent": "alarm_set", "date": null, "time": null}'
    assert validate_output(bad_missing) is None


def test_validate_output_invalid_intent():
    """Validation must reject unknown intents."""
    bad_intent = '{"intent": "unknown_action", "date": null, "time": null, "place": null}'
    assert validate_output(bad_intent) is None


def test_validate_output_broken_json():
    """Validation must reject non-JSON strings."""
    assert validate_output("not json at all") is None
    assert validate_output("{broken: json,") is None


def test_fault_inject():
    """When FAULT_INJECT=1, /parse must return HTTP 500 with exact error body."""
    from service import main as svc
    svc.MODEL_READY = True

    # Mock model and tokenizer
    class DummyTokenizer:
        pad_token_id = 0
        eos_token_id = 0

        def __call__(self, text, return_tensors="pt"):
            return {"input_ids": [[1, 2]]}

        def decode(self, tokens, skip_special_tokens=True):
            return '{"intent": "alarm_set", "date": null, "time": null, "place": null}'

    class DummyModel:
        def generate(self, **kwargs):
            return [[1, 2, 3, 4]]

    svc.TOKENIZER = DummyTokenizer()
    svc.MODEL = DummyModel()

    os.environ["FAULT_INJECT"] = "1"
    try:
        res = client.post("/parse", json={"text": "set an alarm for seven am"})
        assert res.status_code == 500
        assert res.json() == {"error": "invalid_model_output"}
        assert res.headers.get("X-Model-Version") == "v1-test"
        assert res.headers.get("X-Served-By") == "test-pod-0"
    finally:
        os.environ["FAULT_INJECT"] = "0"
        svc.MODEL_READY = False
