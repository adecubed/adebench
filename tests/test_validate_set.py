"""The validator rejects a set for each rule it breaks (spec section 3)."""
from __future__ import annotations

from adebench import validate_set as v


def world():
    return {"name": "t", "as_of": "2026-06-30",
            "cards": [{"id": "card:svc", "entity": "svc", "text": "The Svc service listens on port 9100.", "date": "2026-06-01"}],
            "corrections": [], "aliases": [{"alias": "watchtower", "canonical": "svc"}],
            "facts": [{"id": "svc_port_old", "entity": "svc", "attribute": "port", "text": "Svc listens on port 9000.",
                       "date": "2026-02-01", "supersedes": None},
                      {"id": "svc_port", "entity": "svc", "attribute": "port", "text": "Svc now listens on port 9100.",
                       "date": "2026-06-01", "supersedes": "svc_port_old"},
                      {"id": "svc_owner", "entity": "svc", "attribute": "owner", "text": "Svc is run by Dana.",
                       "date": "2026-03-01", "supersedes": None},
                      {"id": "svc_future", "entity": "svc", "attribute": "region", "text": "Svc runs in Oslo.",
                       "date": "2026-08-01", "supersedes": None}],
            "episodes": [{"id": "ep1", "created_at": "2026-06-02T10:00:00", "repl": "chat",
                          "input": "Check the Svc port", "output": "Port 9100 confirmed"}]}


def cases():
    qs = [{"question": "Which port does Svc use?", "expected": [["9100"]], "forbidden": [["9000"]],
           "kind": "replaced", "evidence": ["svc_port"]},
          {"question": "Who runs the service?", "expected": [["Dana"]], "kind": "fact", "evidence": ["svc_owner"]},
          {"question": "What is the owner's phone number?", "expected": [["+47"]], "kind": "never_stored", "evidence": []}]
    ab = [{"question": "What does the Zarvik module do?", "entity": "Zarvik"}]
    return qs, ab


def run(w=None, qs=None, ab=None, repo=None):
    q0, a0 = cases()
    return v.check(w or world(), qs if qs is not None else q0, ab if ab is not None else a0, repo or {}, None)


def test_a_good_set_passes():
    assert all(not p for p in run().values()), run()


def test_evidence_must_contain_the_answer():
    qs, _ = cases()
    qs[1]["evidence"] = ["svc_port"]
    assert run(qs=qs)["answerable"]


def test_superseded_evidence_fails():
    qs, _ = cases()
    qs[0]["evidence"] = ["svc_port_old"]
    qs[0]["expected"] = [["9000"]]
    qs[0]["forbidden"] = []
    assert run(qs=qs)["answerable"]


def test_evidence_after_as_of_fails():
    qs, _ = cases()
    qs.append({"question": "Where does Svc run?", "expected": [["Oslo"]], "kind": "fact", "evidence": ["svc_future"]})
    assert run(qs=qs)["answerable"]


def test_retired_value_as_a_current_fact_fails():
    w = world()
    w["facts"].append({"id": "svc_note", "entity": "svc", "attribute": "note", "text": "Clients connect on 9000.",
                       "date": "2026-06-10", "supersedes": None})
    assert run(w=w)["retired"]


def test_never_stored_answer_present_anywhere_fails():
    assert run(repo={"svc.py": "PHONE = '+47 555'\n"})["never_stored"]


def test_invented_entity_present_or_aliased_fails():
    w = world()
    w["aliases"].append({"alias": "zarvik", "canonical": "svc"})
    assert run(w=w)["invented"]
    w2 = world()
    w2["facts"][2]["text"] = "Svc is run by Dana from the Zarvik team."
    assert run(w=w2)["invented"]


def test_leading_question_fails():
    qs, _ = cases()
    qs[1]["question"] = "Is the service run by Dana?"
    assert run(qs=qs)["leading"]


def test_structure_mix_ids_dates_aliases():
    w = world()
    w["facts"][1]["id"] = "svc_port_old"
    assert run(w=w)["structure"]
    w = world()
    w["aliases"].append({"alias": "x", "canonical": "nobody"})
    assert run(w=w)["structure"]
    w = world()
    w["facts"][0]["date"] = "2026-13-45"
    assert run(w=w)["structure"]
    qs, ab = cases()
    assert v.check(world(), qs, ab, {}, {"door": {"fact": 2}, "abstention": 1})["structure"]


def test_normalisation_ignores_case_accents_and_punctuation():
    assert v.has_token("Brambillesco", "a note on brambillèsco, today")
    assert not v.has_token("9000", "port 19000")
    assert v.has_token("9100", "moved to 9100.")


def test_a_dated_answer_must_be_in_the_text():
    # a memory that is given no dates (memU, Nemp) can still deliver a date written in the text
    qs, _ = cases()
    qs.append({"question": "When did Svc move to its new port?", "expected": [["2026-06-01"]], "kind": "dated",
               "evidence": ["svc_port"]})
    assert run(qs=qs)["answerable"]
    w = world()
    w["facts"][1]["text"] = "On 2026-06-01 Svc moved from 9000 to 9100."
    assert not run(w=w, qs=qs)["answerable"]


def test_an_expected_token_must_be_a_specific_short_value():
    qs, _ = cases()
    qs[2]["expected"] = [["null"]]          # a JSON door carries "null": the question would pass by accident
    assert run(qs=qs)["structure"]
    qs, _ = cases()
    qs[1]["expected"] = [["Dana the senior site reliability lead"]]
    assert run(qs=qs)["structure"]


def test_a_cited_fact_must_name_its_entity():
    w = world()
    w["facts"][2]["text"] = "It is run by Dana."
    assert run(w=w)["answerable"]
    w["facts"][2]["text"] = "The svc team is run by Dana."
    assert not run(w=w)["answerable"]


def test_a_retired_value_may_not_sit_in_a_card_or_a_later_statement():
    w = world()
    w["cards"][0]["text"] = "The Svc service listens on ports 9000 and 9100."
    assert run(w=w)["retired"]


def test_an_alias_must_be_another_name_not_the_same_words():
    w = world()
    w["aliases"].append({"alias": "svc_the", "canonical": "svc"})
    assert run(w=w)["structure"]


def test_answers_are_checked_the_way_the_scorer_reads_them():
    qs, _ = cases()
    w = world()
    w["facts"][2]["text"] = "Svc is encrypted with AES 256."
    qs[1]["expected"] = [["AES-256"]]
    assert run(w=w, qs=qs)["answerable"]


def test_the_replacing_fact_does_not_name_the_old_value():
    w = world()
    w["facts"][1]["text"] = "Svc moved from 9000 to 9100."
    assert run(w=w)["retired"]


def test_a_question_kind_outside_the_mix_is_rejected():
    qs, ab = cases()
    mix = {"door": {"replaced": 1, "fact": 1}, "abstention": 1}
    assert v.check(world(), qs, ab, {}, mix)["structure"]          # the never_stored one
    assert not v.check(world(), qs[:2], ab, {}, mix)["structure"]
