"""The agentmemory adapter implements the whole adebench contract, and its
parsing of the MCP text is checked offline on a recorded answer.

Checked without a server: the methods are read off the class, nothing is
instantiated, the same way test_aionforge_adapter_complete.py checks the
Aionforge adapter. RECALL is the text memory_recall returned (agentmemory
0.9.29, keyless, the synthetic memory) for "Does the owner commute by train
for the Turin trip?", limit 4.
"""
from datetime import datetime

from adebench import adapter, agentmemory
from adebench.config import LOCAL_TZ

RECALL = r"""{
  "format": "full",
  "results": [
    {
      "observation": {
        "concepts": [],
        "facts": [
          "The owner commutes by train."
        ],
        "files": [],
        "id": "mem_munt9qal_7fd06eafc438",
        "importance": 7,
        "narrative": "The owner commutes by train.",
        "sessionId": "memory",
        "timestamp": "2026-09-30T07:56:05.080Z",
        "title": "The owner commutes by train.",
        "type": "decision"
      },
      "score": 1.0366666666666668,
      "sessionId": "memory"
    },
    {
      "observation": {
        "concepts": [],
        "facts": [
          "The owner is Alex, a product designer based in Turin who commutes by train and prefers morning meetings. Updated 2026-09-05."
        ],
        "files": [],
        "id": "mem_adebench_502acb507b00",
        "importance": 7,
        "narrative": "The owner is Alex, a product designer based in Turin who commutes by train and prefers morning meetings. Updated 2026-09-05.",
        "sessionId": "memory",
        "timestamp": "2026-09-05T12:00:00+02:00",
        "title": "The owner is Alex, a product designer based in Turin who commutes by train and p",
        "type": "decision"
      },
      "score": 1.0330645161290322,
      "sessionId": "memory"
    },
    {
      "observation": {
        "concepts": [],
        "confidence": 0.3,
        "facts": [],
        "files": [],
        "id": "obs_munt9qeb_012b106fbb61",
        "importance": 5,
        "narrative": "Plan the Turin trip by train",
        "origin": {
          "capturedAt": "2026-09-09T11:00:00+02:00",
          "channel": "import",
          "detail": "jsonl"
        },
        "sessionId": "adebench-episode-2",
        "timestamp": "2026-09-09T11:00:00+02:00",
        "title": "prompt_submit",
        "type": "conversation"
      },
      "score": 1.0299999999999998,
      "sessionId": "adebench-episode-2"
    },
    {
      "observation": {
        "concepts": [],
        "facts": [
          "In summer the owner sometimes commutes by bike."
        ],
        "files": [],
        "id": "mem_munt9qbc_dae57000f4b1",
        "importance": 7,
        "narrative": "In summer the owner sometimes commutes by bike.",
        "sessionId": "memory",
        "timestamp": "2026-09-30T07:56:05.111Z",
        "title": "In summer the owner sometimes commutes by bike.",
        "type": "decision"
      },
      "score": 0.9915432692307692,
      "sessionId": "memory"
    }
  ],
  "tokens_used": 583,
  "truncated": false
}"""

ORIGINS = {"mem_munt9qal_7fd06eafc438": "agent", "mem_adebench_502acb507b00": "import",
           "mem_munt9qbc_dae57000f4b1": "agent"}


def test_agentmemory_adapter_honours_the_contract():
    missing = [m for m in adapter.required_methods()
               if not callable(getattr(agentmemory.AgentmemoryAdapter, m, None))]
    assert missing == [], f"AgentmemoryAdapter is missing: {missing}"


def test_agentmemory_adapter_has_the_write_probes_it_can_honour():
    for m in ("write_fact", "forget_memory", "import_memory", "settle", "declared_bytes"):
        assert callable(getattr(agentmemory.AgentmemoryAdapter, m, None)), m
    # the Stop hook does not send the assistant's answer: no write-back path
    assert not hasattr(agentmemory.AgentmemoryAdapter, "ingest_exchange")


def test_the_door_text_is_the_mcp_text_as_received():
    r = agentmemory.parse_answer(RECALL, "q", "recall", ORIGINS)
    assert r["summary"] == RECALL
    assert "[since" not in r["summary"]


def test_memories_and_observations_are_split():
    r = agentmemory.parse_answer(RECALL, "q", "recall", ORIGINS)
    assert [s["key"] for s in r["semantic"]] == ["mem_munt9qal_7fd06eafc438", "mem_adebench_502acb507b00",
                                                  "mem_munt9qbc_dae57000f4b1"]
    assert [e["key"] for e in r["episodic"]] == ["obs_munt9qeb_012b106fbb61"]
    assert r["episodic"][0]["input_summary"] == "Plan the Turin trip by train"
    assert r["episodic"][0]["created_at"].startswith("2026-09-09T11:00:00")
    assert r["unknown_terms"] == []


def test_only_an_imported_memory_is_given_an_age():
    sem = agentmemory.parse_answer(RECALL, "q", "recall", ORIGINS)["semantic"]
    assert sem[0]["content"] == "The owner commutes by train."          # memory_save: the save time is no age
    assert sem[1]["content"].startswith("[since 2026-09-05] The owner is Alex")
    assert not sem[2]["content"].startswith("[")


def test_an_empty_answer_is_the_only_abstention():
    r = agentmemory.parse_answer('{"format": "full", "results": [], "tokens_used": 0, "truncated": false}',
                                 "What is the Zarpetta module?", "recall", {})
    assert r["semantic"] == [] and r["episodic"] == []
    assert r["unknown_terms"] == ["Zarpetta", "module"]


def test_iso_keeps_local_time_and_accepts_a_space():
    local = datetime(2026, 9, 10, 9, 12).replace(tzinfo=LOCAL_TZ).isoformat()
    assert agentmemory._iso("2026-09-10T09:12:00") == local
    assert agentmemory._iso("2026-09-10 09:12:00") == local
    assert agentmemory._iso("2026-09-10T09:12:00Z") == "2026-09-10T09:12:00+00:00"
    assert agentmemory._iso("2026-09-10T09:12:00+05:30") == "2026-09-10T09:12:00+05:30"
    assert agentmemory._iso("2021-03-14") == datetime(2021, 3, 14, 12, 0).replace(tzinfo=LOCAL_TZ).isoformat()
