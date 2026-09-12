"""
adebench — a benchmark for an ADE Brain, on its own terms.

It does not measure "a memory" in the abstract. It measures what the voice
client hears in the first 2,400 characters of /sofia/ask, whether the entity
cards honour the owner's corrections, whether facts get updated instead of
piling up, whether the age of a memory reaches the model, whether the live
state (working memory) is fresh, whether the Brain can say "I don't know",
whether it finds files like grep would, and whether the graph links the
entities that have a card.

    python -m adebench                      # all sections, report in storico/
    python -m adebench --casi my/cases --repo /path/to/repo
    python -m adebench --validazione        # sheet to validate the golden set
    python -m adebench --adattatore mymemory.bench:MyAdapter   # another memory system

The sections talk to a memory only through the adapter contract in
adattatore.py; ade.py is the adapter for an ADE Brain and the worked example.

The Brain must be running. Production memory is only read; the only writes
are a canary in working memory (session 'adebench', TTL 1 h, removed at the
end of the run) and, optionally, a sandbox test script you point to.
"""
__version__ = "0.1.0"
