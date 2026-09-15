"""One judge for every reader, on the same stratified subset.

The readers' answers are already in their logs (qa_log_gemini-3-flash-preview.jsonl,
qa_log_gpt-6-astra.jsonl, qa_log_ollama_gpt-oss_20b.jsonl, ...). This script
asks a single judge about all of them with the official LongMemEval prompts,
so the numbers are comparable to each other (not to runs judged by GPT-4o).

    LME_SUBSET=100 LME_JUDGE_MODEL=gpt-5.1-2025-11-13 python longmemeval_rejudge.py longmemeval_s.json
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
os.environ.setdefault("LME_SUBSET", "100")
import longmemeval_reader as r  # noqa: E402

JUDGE = os.environ.get("LME_JUDGE_MODEL", "gpt-5.1-2025-11-13")
SUBSET = int(os.environ["LME_SUBSET"])
READERS = {"gemini-3-flash-preview": "qa_log_gemini-3-flash-preview.jsonl",
           "gpt-6-astra": "qa_log_gpt-6-astra.jsonl",
           "ollama:gpt-oss:20b": "qa_log_ollama_gpt-oss_20b.jsonl"}


def judge(prompt: str, tries: int = 4) -> str:
    body = json.dumps({"model": JUDGE, "messages": [{"role": "user", "content": prompt}],
                       "reasoning_effort": "none", "max_completion_tokens": 20}).encode()
    for i in range(tries):
        try:
            req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=body, method="POST",
                                         headers={"Content-Type": "application/json",
                                                  "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                return (json.loads(resp.read())["choices"][0]["message"]["content"] or "").strip()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                return f"[judge error: {e}]"
            time.sleep(5 * (i + 1))
    return ""


def main():
    data = {q["question_id"]: q for q in json.load(open(sys.argv[1], encoding="utf-8"))}
    tops = {json.loads(l)["id"]: json.loads(l)["top"] for l in (HERE / "top5.jsonl").read_text(encoding="utf-8").splitlines()}
    ids = [i for i in tops if i in data]
    ids = r.stratified(ids, {i: ("abstention" if i.endswith("_abs") else data[i]["question_type"]) for i in ids}, SUBSET)
    tag = JUDGE.replace(".", "_").replace(":", "_")
    cache_path = HERE / f"judge_{tag}_log.jsonl"
    cache = {}
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            if "error" not in c["verdict"][:20]:
                cache[(c["reader"], c["id"])] = c

    jobs = []
    for reader, path in READERS.items():
        p = HERE / path
        if not p.exists():
            print(f"skip {reader}: no log")
            continue
        log = {}
        for line in p.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            log[rec["id"]] = rec
        jobs += [(reader, log[i]) for i in ids if i in log]

    def one(job):
        reader, rec = job
        if (reader, rec["id"]) in cache:
            return cache[(reader, rec["id"])]
        q = data[rec["id"]]
        if rec["id"].endswith("_abs"):
            prompt = r.JUDGE_ABSTENTION.format(q["question"], q["answer"], rec["answer"])
        else:
            prompt = r.JUDGE_TEMPLATES[q["question_type"]].format(q["question"], q["answer"], rec["answer"])
        verdict = judge(prompt)
        out = {"reader": reader, "id": rec["id"], "verdict": verdict, "correct": "yes" in verdict.lower(),
               "retrieval_ok": rec["retrieval_ok"],
               "type": "abstention" if rec["id"].endswith("_abs") else q["question_type"]}
        with open(cache_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(out, ensure_ascii=False) + "\n")
        return out

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(one, jobs))

    report = {"judge": JUDGE, "subset": SUBSET, "readers": {}}
    for reader in READERS:
        rs = [x for x in results if x["reader"] == reader]
        if not rs:
            continue
        by_type = collections.defaultdict(collections.Counter)
        for x in rs:
            by_type[x["type"]]["n"] += 1
            by_type[x["type"]]["correct"] += x["correct"]
        report["readers"][reader] = {
            "n": len(rs), "correct": sum(x["correct"] for x in rs),
            "correct_when_retrieved": sum(x["correct"] and x["retrieval_ok"] for x in rs),
            "retrieval_ok": sum(x["retrieval_ok"] for x in rs),
            "judge_errors": sum("error" in x["verdict"][:20] for x in rs),
            "by_type": {t: dict(v) for t, v in sorted(by_type.items())}}
    (HERE / f"result_qa_judge_{tag}_subset{SUBSET}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
