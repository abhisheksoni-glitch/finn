from finn.engine import copilot


class FakeLLM:
    available = True

    def __init__(self, out):
        self.out, self.prompt = out, None

    def ask(self, prompt, tier="fast", system=None):
        self.prompt = prompt
        return self.out


CTX = {"holdings": [{"symbol": "KAYNES"}], "filings": [{"id": "nse:1", "symbol": "KAYNES"}],
       "research": [{"symbol": "KAYNES"}]}


def test_keeps_only_real_citations_and_strips_inline_ids():
    llm = FakeLLM({"answer": "KAYNES PAT fell 65.6% YoY [F:nse:1]. Price [P:KAYNES].",
                   "cites": ["F:nse:1", "F:made-up"], "follow_ups": ["Why did margins fall?"]})
    out = copilot.chat(CTX, "how were kaynes results", [], llm)
    assert out["cites"] == ["F:nse:1", "P:KAYNES"]
    assert "F:" not in out["answer"] and out["answer"].startswith("KAYNES PAT fell 65.6% YoY.")
    assert "QUESTION: how were kaynes results" in llm.prompt


def test_no_model_means_phone_answers():
    class Off:
        available = False
    assert copilot.chat(CTX, "hi", [], Off()) is None
