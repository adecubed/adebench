"""Tests that need no memory service: a fake adapter drives the sections,
and the client is exercised against a local HTTP server.

Each test guards one way the score could lie:
  - an HTTP error is never an answer (health false, cases ERROR, no PASS)
  - a memory without a feature is SKIP and leaves the denominator
  - expected words match whole tokens ('8766' is not inside '18766')
  - two runs in the same minute get two files; the delta only compares
    comparable runs (same adapter, door, golden set)
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from adebench import adattatore, report, sezioni
from adebench.config import CFG


# ─── a fake memory ───────────────────────────────────────────────────────────

class Finto:
    """Adapter with knobs: what the door answers, whether calls fail."""

    def __init__(self, risposta=None, errore: Exception | None = None, schede=(), archi=0, nodi_fact=(0, 0)):
        self._risposta = risposta or {"summary": ""}
        self._errore = errore
        self._schede = list(schede)
        self._archi = archi
        self._nodi_fact = nodi_fact
        self.working: dict = {}

    def _r(self):
        if self._errore:
            raise self._errore
        return dict(self._risposta)

    def health(self): return self._errore is None
    def riscalda(self): return 1.0
    def porte(self): return ["unica"]
    def testo_della_porta(self, q, porta): r = self._r(); return r.get("summary", ""), r
    def chiedi(self, q): return self._r()
    def schede(self): return self._schede
    def correzioni(self): return []
    def alias(self): return []
    def traccia_aggiornamenti(self): return {"superseded_vivi": 0, "relation_updates": 1}
    def quota_event_date(self): return (0, 0)
    def giorni_recenti(self, n): return []
    def episodi_del_giorno(self, g, limit): return []
    def episodi_firmati(self, p): return 0
    def working_scrivi(self, s, k, v, ttl): self.working[(s, k)] = v; return True
    def working_leggi(self, s, k): return self.working.get((s, k))
    def working_cancella(self, s): self.working = {kk: v for kk, v in self.working.items() if kk[0] != s}
    def working_eta_minuti(self, s, k): return None
    def ricerca_file(self, q, limit): return []
    def grafo_vicini(self, e): return self._archi
    def grafo_orfani(self): return self._nodi_fact
    def grafo_conteggi(self): return {"nodi": 0, "archi": 0}
    def salute(self): return {}, []
    def porte_misurate(self): return []
    def tracce(self): return []
    def sonda_porte(self, d): pass


@pytest.fixture
def casi(tmp_path, monkeypatch):
    (tmp_path / "domande.json").write_text(json.dumps([
        {"domanda": "porta?", "attese": [["8766"]], "validata": True}]), encoding="utf-8")
    (tmp_path / "astensione.json").write_text(json.dumps(["Cos'e' Zarpetta?"]), encoding="utf-8")
    monkeypatch.setattr(CFG, "casi", tmp_path)
    monkeypatch.setattr(CFG, "storico", tmp_path / "storico")
    monkeypatch.setattr(CFG, "porta", "unica")
    monkeypatch.setattr(CFG, "collaudo", None)
    monkeypatch.setattr(CFG, "repo", None)
    return tmp_path


def _usa(ada):
    adattatore.imposta(ada)
    return ada


# ─── the contract ────────────────────────────────────────────────────────────

def test_contratto_verificato_prima_di_partire():
    with pytest.raises(TypeError, match="non implementa"):
        adattatore.carica("builtins:object")
    assert len(adattatore.metodi_richiesti()) >= 20


def test_finto_rispetta_il_contratto():
    mancanti = [m for m in adattatore.metodi_richiesti() if not callable(getattr(Finto(), m, None))]
    assert mancanti == []


# ─── errors are never passes ─────────────────────────────────────────────────

def test_errore_del_servizio_non_e_astensione(casi):
    _usa(Finto(errore=RuntimeError("HTTP 500")))
    s = sezioni.astensione()
    assert s["conteggi"]["ERROR"] == 1 and s["conteggi"]["PASS"] == 0
    assert s["punteggio"] == 0.0


def test_errore_nella_porta_e_error_non_fail_silenzioso(casi):
    _usa(Finto(errore=RuntimeError("HTTP 500")))
    s = sezioni.porta()
    assert [c["stato"] for c in s["casi"]] == ["ERROR"]


def test_risposta_vuota_non_e_astensione(casi):
    _usa(Finto(risposta={"summary": ""}))
    s = sezioni.astensione()
    assert s["conteggi"]["ERROR"] == 1


def test_astensione_vera_passa(casi):
    _usa(Finto(risposta={"summary": "Nessun risultato", "episodic": [{"_fallback": True}]}))
    s = sezioni.astensione()
    assert s["conteggi"]["PASS"] == 1 and s["punteggio"] == 1.0


# ─── missing features are SKIP, out of the denominator ───────────────────────

def test_grafo_vuoto_non_fa_punti(casi):
    _usa(Finto(schede=[], archi=0, nodi_fact=(0, 0)))
    s = sezioni.grafo()
    assert s["punteggio"] is None
    assert s["conteggi"]["SKIP"] == 2 and s["conteggi"]["PASS"] == 0


def test_grafo_con_dati_misura(casi):
    _usa(Finto(schede=[{"entita": "brain", "content": "x", "data": "2026"}], archi=3, nodi_fact=(0, 10)))
    s = sezioni.grafo()
    assert s["punteggio"] == 1.0 and s["conteggi"]["PASS"] == 2


def test_schede_assenti_skip(casi):
    _usa(Finto(schede=[]))
    assert sezioni.schede()["punteggio"] is None


def test_aggiornamento_senza_collaudo_non_fa_punti(casi):
    _usa(Finto())
    s = sezioni.aggiornamento(con_collaudo=False)
    assert s["punteggio"] is None
    assert s["misure"]["relation_updates"] == 1  # the trace is reported, not scored


def test_totale_esclude_le_sezioni_non_misurate():
    sez = [{"nome": "a", "peso": 25, "punteggio": 1.0, "casi": []},
           {"nome": "b", "peso": 15, "punteggio": None, "casi": []},
           {"nome": "salute", "peso": 0, "punteggio": None, "casi": []}]
    punti, misurato, totale = report.punteggio_totale(sez)
    assert (punti, misurato, totale) == (25.0, 25, 40)


# ─── whole-token matching ───────────────────────────────────────────────────

@pytest.mark.parametrize("testo,atteso,trovato", [
    ("gira sulla porta 8766", "8766", True),
    ("gira sulla porta 18766", "8766", False),
    ("gira sulla porta 87660", "8766", False),
    ("versione 0.2.4 installata", "0.2.4", True),
    ("versione 10.2.4 installata", "0.2.4", False),
    ("salvato in C:\\Users\\simon\\ade\\report.docx", "C:\\Users\\simon\\ade", True),
    ("Model Context Protocol (MCP)", "MCP", True),
    ("usa la MCPHost", "MCP", False),
    ("il masker anonimizza i dati", "anonimizz*", True),
    ("il masker anonimizza i dati", "anonimizz", False),
    ("disanonimizzato", "anonimizz*", False),
])
def test_attese_a_token_intero(testo, atteso, trovato):
    assert (sezioni._presente(testo, [atteso]) is not None) == trovato


def test_porta_con_attesa_giusta(casi):
    _usa(Finto(risposta={"summary": "Il Brain risponde sulla porta 8766."}))
    assert sezioni.porta()["punteggio"] == 1.0
    _usa(Finto(risposta={"summary": "Il Brain risponde sulla porta 18766."}))
    assert sezioni.porta()["punteggio"] == 0.0


# ─── history: no collisions, only comparable deltas ─────────────────────────

def _corsa(casi_dir):
    return [{"nome": "porta", "peso": 25, "punteggio": 1.0, "casi": [], "conteggi": {}, "misure": {}, "avvisi": []}]


def test_due_corse_nello_stesso_secondo_non_si_sovrascrivono(casi):
    cfg = {"adattatore": "x:A", "porta": "unica", "hash_casi": "h"}
    pj1, _, _ = report.salva(_corsa(casi), cfg)
    pj2, _, _ = report.salva(_corsa(casi), cfg)
    assert pj1 != pj2 and pj1.exists() and pj2.exists()


def test_delta_solo_tra_corse_comparabili(casi):
    report.salva(_corsa(casi), {"adattatore": "x:A", "porta": "unica", "hash_casi": "h"})
    _, _, c2 = report.salva(_corsa(casi), {"adattatore": "y:B", "porta": "unica", "hash_casi": "h"})
    assert c2["delta"]["totale"] is None  # different adapter: nothing to compare with
    _, _, c3 = report.salva(_corsa(casi), {"adattatore": "x:A", "porta": "unica", "hash_casi": "altro"})
    assert c3["delta"]["totale"] is None  # different golden set
    _, _, c4 = report.salva(_corsa(casi), {"adattatore": "x:A", "porta": "unica", "hash_casi": "h"})
    assert c4["delta"]["totale"] == 0.0  # comparable: delta computed


# ─── the HTTP client never returns an error body as an answer ───────────────

class _Server500(BaseHTTPRequestHandler):
    def _rispondi(self):
        self.send_response(500)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"detail": "boom"}')

    do_GET = _rispondi
    do_POST = _rispondi

    def log_message(self, *a):  # silence
        pass


@pytest.fixture
def server_500(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), _Server500)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    monkeypatch.setattr(CFG, "brain_url", f"http://127.0.0.1:{srv.server_port}")
    yield srv
    srv.shutdown()


def test_http_500_non_e_vivo(server_500):
    from adebench import client
    assert client.health() == {}


def test_http_500_solleva_non_risponde(server_500):
    from adebench import client
    with pytest.raises(client.RispostaErrore):
        client.ask("ciao", [])


def test_adattatore_ade_health_falso_su_500(server_500):
    from adebench.ade import AdattatoreADE
    assert AdattatoreADE().health() is False
