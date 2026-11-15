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


def test_named_company_research_and_passages_flow_in():
    r = {"symbol": "TCS", "name": "Tata Consultancy Services", "analysis": {"verdict": "Margins held.",
         "guidance_now": [{"metric": "EBIT margin", "target": "26-28%"}]},
         "numbers": {"snapshot": {"pe": 15.9}},
         "chunks": [{"id": "T2:p7", "title": "Q1 FY27 call", "text": "We expect EBIT margin of 26 to 28 percent."},
                    {"id": "T1:p3", "title": "Q4 FY26 call", "text": "Deal wins were strong in BFSI."}]}
    llm = FakeLLM({"answer": "TCS guided EBIT margin of 26-28% R:TCS:T2:p7.", "cites": ["R:TCS"],
                   "follow_ups": ["Did TCS hit 26% last quarter?"], "needs_research": ["TCS", "INFY"]})
    out = copilot.chat({"holdings": [], "filings": []}, "what did TCS guide on margin", [], llm, research_docs=[r])
    assert "R:TCS:T2:p7" in out["cites"] and out["passages"][0]["text"].startswith("We expect")
    assert out["needs_research"] == ["INFY"]           # TCS is already researched
    assert "margin" in llm.prompt and "R:TCS:T2:p7" in llm.prompt


def test_never_says_data():
    llm = FakeLLM({"answer": "The DATA does not contain information about TCS.", "cites": []})
    assert "DATA" not in copilot.chat({}, "tcs?", [], llm)["answer"]
