"""
adebench — a benchmark for personal AI memory, on its own terms.

It does not measure "a memory" in the abstract. It measures what the client
actually receives through a door (for a voice assistant: the first 2,400
characters it hears), whether the entity cards honour the owner's
corrections, whether facts get updated instead of piling up, whether the age
of a memory reaches the model, whether the live state is fresh, whether the
memory can say "I don't know", whether it finds files like grep would, and
whether the graph links the entities that have a card.

    python -m adebench                      # all sections, report in history/
    python -m adebench --cases my/cases --repo /path/to/repo
    python -m adebench --validation         # sheet to validate the golden set
    python -m adebench --adapter mymemory.bench:MyAdapter   # another memory system

The sections talk to a memory only through the adapter contract in
adapter.py; ade.py is the adapter for an ADE Brain and the worked example.
The memory service must be running. Production memory is only read; the
only writes are a canary in working memory (session 'adebench', TTL 1 h,
removed at the end of the run) and, optionally, a sandbox test script you
point to.
"""
__version__ = "0.2.5"
