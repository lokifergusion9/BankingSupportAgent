from bankingsupportagent.config import get_llm, LLM_TIMEOUT_SECONDS, LLM_MAX_RETRIES

def test_config(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY","test-key")       # Fake key, no request is sent
    llm = get_llm()

    assert llm.request_timeout == LLM_TIMEOUT_SECONDS
    assert llm.max_retries == LLM_MAX_RETRIES