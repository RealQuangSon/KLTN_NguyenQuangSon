"""Token usage accounting: input/output split and per-model accumulation (AG-03).

Fake clients only (no network): the Responses API shape (input_tokens/output_tokens)
and the Chat Completions shape (prompt_tokens/completion_tokens) must both feed the
metrics, and a provider reply without usage keeps counting calls without usage.
"""
from types import SimpleNamespace

from backend.app.interpreter import OpenAIInterpreter, reported_tokens, split_usage
from backend.app.models import Extraction
from backend.app.operations import Metrics
from backend.app.semantic import OpenAIEmbeddings

MODEL = "gpt-4o-2024-08-06"

RESPONSES_USAGE = SimpleNamespace(total_tokens=150, input_tokens=100, output_tokens=50)
CHAT_COMPLETIONS_USAGE = SimpleNamespace(total_tokens=150, prompt_tokens=100, completion_tokens=50)
SPLIT = {"input_tokens": 100, "output_tokens": 50}


def extraction():
    return Extraction(intent="find_room", city="TP.HCM", area=None, people=2,
                      preferences=[], needs_destination=False)


def interpreter_client(usage):
    def parse(**kwargs):
        response = SimpleNamespace(status="completed", output_parsed=extraction())
        if usage is not None:
            response.usage = usage
        return response

    return SimpleNamespace(responses=SimpleNamespace(parse=parse))


def test_split_usage_supports_both_provider_shapes():
    assert split_usage(RESPONSES_USAGE) == SPLIT
    assert split_usage(CHAT_COMPLETIONS_USAGE) == SPLIT
    assert split_usage(None) == {"input_tokens": None, "output_tokens": None}


def test_reported_tokens_never_estimates_a_missing_total():
    assert reported_tokens(RESPONSES_USAGE) == 150
    # Total missing but both sides reported: the sum of the reported split, not a guess.
    assert reported_tokens(SimpleNamespace(input_tokens=10, output_tokens=5)) == 15
    assert reported_tokens(None) is None
    assert reported_tokens(SimpleNamespace(input_tokens=10)) is None


def test_message_usage_split_reaches_metrics_and_reply(service, renter):
    service.interpreter = OpenAIInterpreter(client=interpreter_client(RESPONSES_USAGE), model=MODEL)
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "Tìm phòng TP.HCM cho 2 người")
    assert reply["usage"]["tokens"] == 150
    assert reply["usage"]["input_tokens"] == 100 and reply["usage"]["output_tokens"] == 50
    assert service.metrics.snapshot()["provider_usage"] == {
        "logical_calls": 1, "reported_tokens": 150, "calls_without_token_usage": 0,
        "input_tokens": 100, "output_tokens": 50,
        "by_model": {MODEL: {"logical_calls": 1, "reported_tokens": 150,
                             "input_tokens": 100, "output_tokens": 50}}}


def test_chat_completions_usage_shape_maps_to_the_same_split(service, renter):
    service.interpreter = OpenAIInterpreter(client=interpreter_client(CHAT_COMPLETIONS_USAGE), model=MODEL)
    sid = service.create_session(renter)["session_id"]
    reply = service.message(sid, renter, "Tìm phòng TP.HCM cho 2 người")
    assert reply["usage"]["input_tokens"] == 100 and reply["usage"]["output_tokens"] == 50
    usage = service.metrics.snapshot()["provider_usage"]
    assert usage["reported_tokens"] == 150 and usage["input_tokens"] == 100 and usage["output_tokens"] == 50


def test_missing_usage_keeps_legacy_payload_and_counts_the_call(service, renter):
    service.interpreter = OpenAIInterpreter(client=interpreter_client(None), model=MODEL)
    sid = service.create_session(renter)["session_id"]
    service.message(sid, renter, "Tìm phòng TP.HCM cho 2 người")
    usage = service.metrics.snapshot()["provider_usage"]
    assert usage["logical_calls"] == 1 and usage["reported_tokens"] == 0
    assert usage["calls_without_token_usage"] == 1
    assert "input_tokens" not in usage and "output_tokens" not in usage
    assert "embedding_tokens" not in usage
    # The call is still accounted per model for cost conversion.
    assert usage["by_model"] == {MODEL: {"logical_calls": 1, "calls_without_token_usage": 1}}


def test_embedding_tokens_are_reported_per_model():
    metrics = Metrics()

    def create(**kwargs):
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.5, 0.5])],
                               usage=SimpleNamespace(total_tokens=33))

    provider = OpenAIEmbeddings(client=SimpleNamespace(embeddings=SimpleNamespace(create=create)),
                                model="text-embedding-3-small", dimensions=2, on_usage=metrics.embedding_usage)
    provider.embed("phòng thoáng, gần trường")
    assert provider.tokens == 33
    payload = metrics.snapshot()["provider_usage"]
    assert payload["embedding_tokens"] == 33
    assert payload["by_model"] == {"text-embedding-3-small": {"embedding_calls": 1, "embedding_tokens": 33}}
    assert "embedding_calls_without_usage" not in payload


def test_embedding_without_usage_is_counted_and_never_estimated():
    metrics = Metrics()

    def create(**kwargs):
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.5, 0.5])])

    provider = OpenAIEmbeddings(client=SimpleNamespace(embeddings=SimpleNamespace(create=create)),
                                model="text-embedding-3-small", dimensions=2, on_usage=metrics.embedding_usage)
    provider.embed("phòng yên tĩnh")
    assert provider.usage_missing_calls == 1
    payload = metrics.snapshot()["provider_usage"]
    assert payload["embedding_calls_without_usage"] == 1
    assert "embedding_tokens" not in payload  # no estimation from text length
    assert payload["by_model"] == {"text-embedding-3-small": {"embedding_calls": 1,
                                                              "embedding_calls_without_usage": 1}}


def test_failed_embedding_call_counts_as_missing_usage():
    metrics = Metrics()

    def fail(**kwargs):
        raise RuntimeError("synthetic SDK failure")

    provider = OpenAIEmbeddings(client=SimpleNamespace(embeddings=SimpleNamespace(create=fail)),
                                model="text-embedding-3-small", dimensions=2, on_usage=metrics.embedding_usage)
    try:
        provider.embed("phòng thoáng")
    except Exception:
        pass
    payload = metrics.snapshot()["provider_usage"]
    assert payload["embedding_calls_without_usage"] == 1 and "embedding_tokens" not in payload
