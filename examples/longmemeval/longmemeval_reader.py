"""LongMemEval-S end-to-end with a different READER, same retrieval.

Reuses the top-5 sessions the Brain chose per question (top5.jsonl, written by the
retrieval run on the Brain), so the number isolates the reader: the memory is
identical, only who reads the five sessions changes. Judge stays GPT-4o with
the official prompts.

    LME_READER=gpt-6-astra python longmemeval_reader.py longmemeval_s.json
    LME_READER=claude-fable-5-1 python longmemeval_reader.py longmemeval_s.json   # needs ANTHROPIC_API_KEY
    LME_READER=ollama:gpt-oss:20b LME_SUBSET=100 LME_JUDGE=0 python longmemeval_reader.py longmemeval_s.json

ollama:<model> reads locally (open weight, nothing leaves the machine). LME_SUBSET=N takes a
stratified sample (same share per type as the 500, abstention as its own type, fixed order by
id hash) and reports Gemini and Astra on the same ids. LME_JUDGE=0 records answers only; a later
run with the judge on fills in the verdicts without asking the reader again.
"""
import collections
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
# official LongMemEval prompts
READER_TEMPLATE = ("I will give you several history chats between you and a user. Please answer the question "
                   "based on the relevant chat history.\n\n\nHistory Chats:\n\n{}\n\nCurrent Date: {}\nQuestion: {}\nAnswer:")

_STD = ("I will give you a question, a correct answer, and a response from a model. Please answer yes if the response "
        "contains the correct answer. Otherwise, answer no. If the response is equivalent to the correct answer or contains "
        "all the intermediate steps to get the correct answer, you should also answer yes. If the response only contains a "
        "subset of the information required by the answer, answer no. ")
JUDGE_TEMPLATES = {
    "single-session-user": _STD + "\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only.",
    "single-session-assistant": _STD + "\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only.",
    "multi-session": _STD + "\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only.",
    "temporal-reasoning": _STD + "In addition, do not penalize off-by-one errors for the number of days. If the question asks for the "
                          "number of days/weeks/months, etc., and the model makes off-by-one errors (e.g., predicting 19 days when the "
                          "answer is 18), the model's response is still correct. \n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only.",
    "knowledge-update": "I will give you a question, a correct answer, and a response from a model. Please answer yes if the response "
                        "contains the correct answer. Otherwise, answer no. If the response contains some previous information along "
                        "with an updated answer, the response should be considered as correct as long as the updated answer is the "
                        "required answer.\n\nQuestion: {}\n\nCorrect Answer: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only.",
    "single-session-preference": "I will give you a question, a rubric for desired personalized response, and a response from a model. "
                                 "Please answer yes if the response satisfies the desired response. Otherwise, answer no. The model does "
                                 "not need to reflect all the points in the rubric. The response is correct as long as it recalls and "
                                 "utilizes the user's personal information correctly.\n\nQuestion: {}\n\nRubric: {}\n\nModel Response: {}\n\nIs the model response correct? Answer yes or no only.",
}
JUDGE_ABSTENTION = ("I will give you an unanswerable question, an explanation, and a response from a model. Please answer yes if the "
                    "model correctly identifies the question as unanswerable. The model could say that the information is incomplete, "
                    "or some other information is given but the asked information is not.\n\nQuestion: {}\n\nExplanation: {}\n\n"
                    "Model Response: {}\n\nDoes the model correctly identify the question as unanswerable? Answer yes or no only.")

READER = os.environ.get("LME_READER", "gpt-6-astra")
JUDGE = "gpt-4o-2024-08-06"
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
USE_JUDGE = os.environ.get("LME_JUDGE", "1") != "0"
SUBSET = int(os.environ.get("LME_SUBSET", "0"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_CTX = int(os.environ.get("LME_OLLAMA_CTX", "32768"))
from datetime import datetime  # noqa: E402


def iso(d: str) -> str:
    try:
        return datetime.strptime(d, "%Y/%m/%d (%a) %H:%M").isoformat()
    except Exception:
        return d


def openai_chat(model: str, prompt: str, max_tokens: int, temperature=None, tries: int = 4) -> str:
    body = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if temperature is not None:
        body["temperature"] = temperature
    body["max_completion_tokens"] = max_tokens
    payload = json.dumps(body).encode()
    for i in range(tries):
        try:
            req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=payload,
                                         headers={"Content-Type": "application/json",
                                                  "Authorization": f"Bearer {OPENAI_KEY}"}, method="POST")
            with urllib.request.urlopen(req, timeout=240) as r:
                d = json.loads(r.read())
            return (d["choices"][0]["message"]["content"] or "").strip()
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "ignore")[:300]
            if i == tries - 1:
                return f"[{model} error: {e.code} {msg}]"
            time.sleep(5 * (i + 1))
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                return f"[{model} error: {e}]"
            time.sleep(5 * (i + 1))
    return ""


_anthropic = None


def anthropic_chat(model: str, prompt: str, max_tokens: int, tries: int = 4) -> str:
    """Claude as reader (official SDK; credentials from ANTHROPIC_API_KEY or an
    `ant auth login` profile). Thinking stays on its default; a refusal is
    recorded as such, not routed to a fallback model: the number must belong
    to the model named."""
    global _anthropic
    import anthropic
    if _anthropic is None:
        _anthropic = anthropic.Anthropic(max_retries=3, timeout=600.0)
    for i in range(tries):
        try:
            r = _anthropic.messages.create(model=model, max_tokens=max_tokens,
                                           messages=[{"role": "user", "content": prompt}])
            if r.stop_reason == "refusal":
                return "[refusal]"
            return "".join(b.text for b in r.content if b.type == "text").strip()
        except anthropic.RateLimitError:
            time.sleep(15 * (i + 1))
        except anthropic.APIStatusError as e:
            if e.status_code < 500 or i == tries - 1:
                return f"[{model} error: {e.status_code} {e.message}]"
            time.sleep(5 * (i + 1))
        except anthropic.APIConnectionError as e:
            if i == tries - 1:
                return f"[{model} error: {e}]"
            time.sleep(5 * (i + 1))
    return f"[{model} error: rate limited]"


def ollama_chat(model: str, prompt: str, tries: int = 2) -> str:
    """Local open-weight reader. Only the final answer is kept (a reasoning model's
    thinking stays out, as it does for the hosted readers)."""
    body = json.dumps({"model": model, "stream": False, "messages": [{"role": "user", "content": prompt}],
                       "options": {"num_ctx": OLLAMA_CTX, "temperature": 0}}).encode()
    for i in range(tries):
        try:
            req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body,
                                         headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=3600) as r:
                d = json.loads(r.read())
            return (d["message"].get("content") or "").strip()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                return f"[{model} error: {e}]"
            time.sleep(10)
    return ""


def stratified(ids, types, n):
    """Largest-remainder share per type, ids in a fixed pseudo-random order."""
    import hashlib
    groups = collections.defaultdict(list)
    for i in ids:
        groups[types[i]].append(i)
    quota = {t: len(v) * n / len(ids) for t, v in groups.items()}
    take = {t: int(q) for t, q in quota.items()}
    for t in sorted(quota, key=lambda t: quota[t] - take[t], reverse=True)[: n - sum(take.values())]:
        take[t] += 1
    out = []
    for t, v in sorted(groups.items()):
        out += sorted(v, key=lambda i: hashlib.sha1(i.encode()).hexdigest())[: take[t]]
    return out


def read(model: str, prompt: str) -> str:
    if model.startswith("ollama:"):
        return ollama_chat(model[len("ollama:"):], prompt)
    if model.startswith("claude"):
        return anthropic_chat(model, prompt, 16000)
    return openai_chat(model, prompt, 2048)


def history_string(q, session_ids):
    by_id = {sid: (d, s) for d, sid, s in zip(q["haystack_dates"], q["haystack_session_ids"], q["haystack_sessions"])}
    chunks = sorted((by_id[s] for s in session_ids if s in by_id), key=lambda x: iso(x[0]))
    out = ""
    for i, (date, turns) in enumerate(chunks):
        sess = "".join(f"\n\n{t['role']}: {t['content'].strip()}" for t in turns)
        out += f"\n### Session {i+1}:\nSession Date: {date}\nSession Content:\n{sess}\n"
    return out


def main():
    data = {q["question_id"]: q for q in json.load(open(sys.argv[1], encoding="utf-8"))}
    tops = {}
    for line in (HERE / "top5.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        tops[r["id"]] = r["top"]
    tag = READER.replace(".", "_").replace(":", "_")
    log_path = HERE / f"qa_log_{tag}.jsonl"
    done = {}
    if log_path.exists():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            done[r["id"]] = r  # later lines (judged) win over earlier (answer only)

    def judged(rec):
        return rec.get("verdict") is not None and "error" not in rec["verdict"][:40]

    def one(qid):
        if qid in done and (judged(done[qid]) or not USE_JUDGE):
            return done[qid]
        q, top = data[qid], tops[qid]
        if qid in done and not done[qid]["answer"].startswith(f"[{READER.split(':', 1)[-1]} error"):
            answer = done[qid]["answer"]
            seconds = done[qid].get("reader_seconds")
        else:
            t0 = time.time()
            answer = read(READER, READER_TEMPLATE.format(history_string(q, top), q["question_date"], q["question"]))
            seconds = round(time.time() - t0, 1)
        verdict = None
        if USE_JUDGE:
            if qid.endswith("_abs"):
                jp = JUDGE_ABSTENTION.format(q["question"], q["answer"], answer)
            else:
                jp = JUDGE_TEMPLATES[q["question_type"]].format(q["question"], q["answer"], answer)
            verdict = openai_chat(JUDGE, jp, 10, temperature=0)
        rec = {"id": qid, "type": q["question_type"], "top": top, "answer": answer[:1500], "expected": q["answer"],
               "verdict": verdict, "correct": verdict is not None and "yes" in verdict.lower(),
               "retrieval_ok": set(q["answer_session_ids"]) <= set(top), "reader_seconds": seconds}
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec

    ids = [i for i in tops if i in data]
    if SUBSET:
        ids = stratified(ids, {i: ("abstention" if i.endswith("_abs") else data[i]["question_type"]) for i in ids}, SUBSET)
        tag += f"_subset{SUBSET}"
    print(f"reader {READER}: {len(ids)} questions, {sum(i in done for i in ids)} cached, judge {USE_JUDGE}", flush=True)
    recs = []
    local = READER.startswith("ollama:")
    with ThreadPoolExecutor(max_workers=1 if local else 6) as ex:
        for i, rec in enumerate(ex.map(one, ids), 1):
            recs.append(rec)
            if i % (5 if local else 50) == 0:
                print(f"  {i}/{len(ids)} correct so far {sum(r['correct'] for r in recs)}"
                      f" last {rec.get('reader_seconds')} s", flush=True)
    if not USE_JUDGE:
        secs = [r["reader_seconds"] for r in recs if r.get("reader_seconds")]
        print(f"answers recorded: {len(recs)}, reader errors "
              f"{sum(1 for r in recs if r['answer'].startswith('[') and 'error' in r['answer'][:60])}, "
              f"median {sorted(secs)[len(secs)//2] if secs else '-'} s; judge later with LME_JUDGE=1")
        return
    by_type = collections.defaultdict(collections.Counter)
    for r in recs:
        t = "abstention" if r["id"].endswith("_abs") else r["type"]
        by_type[t]["n"] += 1
        by_type[t]["correct"] += r["correct"]
        by_type[t]["retrieval_ok"] += r["retrieval_ok"]
        by_type[t]["correct_when_retrieved"] += r["correct"] and r["retrieval_ok"]
    errors = sum(1 for r in recs if r["answer"].startswith("[") and "error" in r["answer"][:40])
    report = {"n": len(recs), "correct": sum(r["correct"] for r in recs), "reader": READER, "judge": JUDGE,
              "reader_errors": errors, "by_type": {t: dict(v) for t, v in sorted(by_type.items())}}
    if SUBSET:
        same = {}
        for name, path in (("gemini-3-flash-preview", "qa_log_gemini-3-flash-preview.jsonl"),
                           ("gpt-6-astra", "qa_log_gpt-6-astra.jsonl")):
            log = {}
            for line in (HERE / path).read_text(encoding="utf-8").splitlines():
                r = json.loads(line)
                log[r["id"]] = r
            same[name] = sum(log[i]["correct"] for i in ids if i in log)
        report["same_ids"] = same
        secs = [r["reader_seconds"] for r in recs if r.get("reader_seconds")]
        report["reader_seconds_median"] = sorted(secs)[len(secs) // 2] if secs else None
    (HERE / f"result_qa_{tag}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
