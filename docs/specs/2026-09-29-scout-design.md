# scout: finding memory systems to benchmark

Date: 2026-09-29. Status: approved in chat, step 1 of 4.

Update 2026-09-30: step 1 moved out of adebench into its own project,
[topicscout](https://github.com/adecubed/topicscout); the queries and filters below are its
`ai-memory` profile, and the adapters are read with `--known-from "adebench/*.py"`.

## The whole loop (agreed)

1. **Find**: weekly, a script lists new AI memory repos on GitHub. (this spec)
2. **Prepare**: an agent writes adapter + importer from the README, modelled on the
   existing ones; it stops and reports when it needs a paid key or cannot install.
3. **Measure**: adebench on the synthetic set, the same for everyone.
4. **Approve**: Simone reviews repo, score, problems and adapter. On approval the
   agent drafts an issue for the author; the score goes on the site ~7 days later.
   Rejected ones stay off the site.

Open: cost ceiling per repo for steps 2-3 (Simone to decide).

## Step 1: `python -m adebench.scout`

- **Search**: GitHub repository search API (no dependencies, `urllib`), a fixed list
  of topic and keyword queries (`topic:agent-memory`, `"llm memory" in:name,description`,
  ...), always with `fork:false archived:false stars:>=N pushed:>=DATE`.
  `GITHUB_TOKEN` optional: without it the search pauses between queries to stay
  under 10 searches/minute.
- **Drops**: forks, archived, no push in the last `--days` (90), under `--min-stars`
  (10), no language (lists, docs), names/descriptions of curated lists ("awesome",
  "curated list", "papers").
- **Per repo**: full name, url, stars, last push, license, language, description,
  topics, and a guess at the interface from the README (mcp, rest, pip, npm,
  plugin, docker). READMEs are fetched only for repos seen for the first time,
  capped by `--readme-max`.
- **Known**: repos named in the first lines of `adebench/*.py` adapters plus
  `scout/known.txt` (one `owner/repo` per line, `#` comments, for rejected or
  measured-without-url) are marked `known` and never listed as new.
- **Output** (folder `--out`, default `scout/`, git-ignored for now):
  `candidates.json` = state across runs (`first_seen`, `last_seen`, `status`
  new|seen|known), and `new.md` = this run's new repos, most stars first.
- **Rate limit**: on 403/429 wait for the reset if it is under 70 s, otherwise stop
  and save what was found, saying so.
- **Tests**: fake HTTP, no network: filters, known list, state across two runs,
  interface guess, rate-limit stop.
