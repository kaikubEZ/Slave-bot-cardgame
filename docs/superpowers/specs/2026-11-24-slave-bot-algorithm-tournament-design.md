# Slave bot: algorithm tournament and report for the Slap 'em UP! devs

Date: 2026-11-24. Status: draft for approval.

## Intent

Kai wants to contribute to **Slap 'em UP!** (Urnique Studio / THE HAABIZ; Android, iOS, Steam) by giving its
developers the strongest *fair* Slave bot we can find, with proof they can check. Success for Kai = the devs
adopt it ("I win by what I created"), not Kai winning games personally.

Why this approach: the hand-written rule bots plateaued (overnight, 18M matches: the top 4 are within 0.065
avg rank and go 49–53% against each other). A throwaway spike, `bot/spike_mc.py`, showed that search wins
big. It guesses the hidden cards, plays every legal move out, and picks the best average:

| Same 100 deals, same seats, vs counter / give_lonely / pair_keeper | Avg rank | 1st place |
|---|---|---|
| `counter` in the tested seat | 2.48 | 24% |
| `mc` at 0.1 s per move | 2.02 | – |
| `mc` at 0.8 s per move | 1.70 | 54% |

The gap vs `counter` is −0.46 ± 0.13 at 0.1 s and −0.78 ± 0.10 at 0.8 s. Strength grows with thinking time.

## Deliverables

1. **Tournament**: candidate algorithms compared on the same cards with 95% error bars. "Use math to find the
   best algorithm" means this: statistics on real matches decide, not a formula.
2. **Winning bot**: a clean Python reference implementation in the repo.
3. **Report for the devs**: how the bot works, proof it is fair, how strong it is, how to reproduce the
   results, and what it needs from their engine to be rebuilt there.

## Goals

- Find the strongest algorithm under the rules in `game/slave.py`. Kai observed its `[user]` rules in the
  app; the official how-to-play page is wrong.
- Back every number in the report with a same-cards test that can be replayed from seeds.
- Keep the core portable. It needs only these from a host engine: copy the state, list legal moves, apply a
  move, read the finish order. No numpy and no ML runtime in the bot.

## Non-goals

- **No play on live Slap 'em UP! servers, and no automation of the game client**, unless the devs give
  permission. Their ToS bans "unauthorized software or cheat tools".
- No production port to C++/C#: the devs rebuild it on their own engine.
- No trained neural model this round (deferred: option C below).
- No UI or playable app.

## Anti-goals (failure even if it "works")

- Any information leak: the bot must decide from the `View` only (bot.md §1). Guesses must never be shaped by
  the real hands, not even through a bug.
- Numbers without error bars, or numbers that can't be reproduced from recorded seeds.
- Strength shown only against weak bots. The `pool` experiment is not evidence here.
- Going over the 1 s per-decision limit (bot.md §2), except in runs explicitly labeled as speed proxies.

## Constraints

- Rules: `game/slave.py` is the source of truth. If a rule changes, rerun the affected results.
- Machine: 8 cores, no GPU, Python 3.12. PyPy 3 can be installed from apt but needs Kai's `sudo`. g++ is
  available.
- Repo style (see `AGENTS.md`): compact Python, standard library only, bots expose `act(v)` / `give(v, k)`
  with `View` from `run.py`, tests use `unittest` and run as files (`python3 bot/test_search.py`).
- Search bots stay out of `bots.ALL`: they'd slow `pool` / `bet`, and changing `ALL` reshuffles every pool
  lineup. Register them with `BY_NAME[name] = Cls` at module level, so workers see them under any
  multiprocessing start method.

## Approaches considered

| | Approach | Decision |
|---|---|---|
| A | Polish the search bot in Python, keep each upgrade only if the same-cards test shows a gain | **Picked**, together with the report |
| B | Rewrite engine + bot in a fast language | Not now. The devs' language is unknown and they'd use their own engine. Its benefit (speed) comes from PyPy plus longer budgets as a compiled-speed proxy. A C++ simulator is the fallback if testing is too slow |
| C | Model trained by self-play (DouZero-style) | Deferred: days of training plus a model runtime in the game. Possible later on top of A |
| – | Kai's addition: send an algorithm report, not just code | **Picked**. Language-neutral, so the devs can build it on their stack |

## Design

### 1. Search core (from the spike, cleaned up)

- `rebuild(v)`: replay this round's public moves with placeholder opponent cards to get the engine state
  (trick, passes, finish order, fallen King, direction). Hidden cards don't affect that state.
- `guess(v, rng)`: deal the unseen cards to the opponents using the right counts and the exchange facts. A
  card I gave is in my partner's hand until they play it. If I'm the top of the trade (King/Queen), all my
  partner's other cards are lower than the lowest card they gave me.
- `Sim`: a `Game` that builds legal moves once per turn.
- `value(order, v)`: round points (King +2 … Slave −2) in rounds 1–2; in round 3, the final match rank.
- Flat evaluation: for each guess, play out every legal move on the same guessed cards, so the moves are
  compared fairly.
- Trading: every candidate trades like `give_lonely`, except the trade-search candidate.

### 2. Candidates

All search candidates get the same thinking time, **B = 0.5 s per decision**, expressed as a calibrated
playout count (see §3).

| ID | What changes vs `mc` |
|---|---|
| `mc` | Nothing: the spike as-is. Baseline for search |
| `mc_read` | Weighs guesses by what passes reveal. Target: P(guess) ∝ q^(voluntary passes). A pass is voluntary if the guessed hand *at the time* (current guessed hand + cards that player played after the pass) held a set that beat the table. Try q in {0.1, 0.3, 0.6} |
| `mc_counter` | Playouts use `counter`'s decision rule for every player instead of `lowest` |
| `ismcts` | Single-observer information-set MCTS (Cowling, Powley & Whitehouse 2012): one guess per iteration, UCB1 with availability counts, nodes for every player's decisions, each node backs up the value of the player who acted, `lowest` playouts, most-visited root move. Start with c = 0.7 on values scaled to [0, 1] |
| `mc_end` | When my hand has ≤ K cards (start K = 5): in each guessed world, choose my own remaining moves by exhaustive search instead of `lowest`. Opponents still play `lowest` |
| `mc_trade` | Choose King/Queen trade cards by simulation: sample deals consistent with my 13 cards, apply the trade (partner gives their best), play the round out, average my value. Consider only gifts from my 6 lowest cards |

Combination step: merge every upgrade that passes the merge rule (§3) into `best`. Keep `best` only if it is
at least as strong as each single upgrade it contains. Optional extra candidate: guesses that also use what
the *other* pair's trade reveals.

### 3. Tournament protocol (the "math")

- **Budgets are work counts, not seconds.** A wall-clock budget never replays exactly, because the playout
  count depends on CPU load. Each candidate gets a fixed amount of work per decision, counted in simulated
  moves (engine steps), not playouts. Over 659 measured decisions, one playout's cost varied 2.3× and one
  guessed world's 12×, so a playout count tuned to 0.5 s would push the slowest decisions past 1 s.
  Calibrate per candidate: its typical decision takes about B s on this machine under full tournament load,
  and its slowest stays under 1 s. That gives equal thinking time and exact replay from seeds on any machine
  (a slower machine just takes longer). Report the measured seconds next to the counts.
- **Two fields** fill the other three seats:
  - **Rule field**: `counter`, `give_lonely`, `pair_keeper`, the best rule bots overnight. They are easy
    to model: `give_lonely` plays exactly like `lowest`, and neither it nor `counter` ever passes while it
    can play.
  - **Search field**: 3 × `mc` at the 0.1 s work count. They pass on purpose, like people do. Each run costs
    about 1.6× a rule-field run.
- **Duplicate**: each deal seed is played 4 times, with the tested bot rotated through the seats (rivals keep
  their relative order). Seeds start at 3,000,000,000 and are shared by every candidate. Each candidate's
  results per (seed, seat) are saved, so any two candidates can be compared afterwards without rerunning.
- **Metric**: final match rank in the tested seat. A comparison = the paired per-deal difference (mean over
  the 4 seats), with a 95% CI across deals. Also report the 1st-place rate.
- **References**: `counter` and `give_lonely` in the tested seat, on the same seeds.
- **Screening** (seeds from 3,000,000,000): run in batches of 50 deals. Stop when the CI half-width is
  ≤ 0.05, or when the CI excludes 0 after ≥ 100 deals. Hard cap 400 deals. Screening only decides what to
  keep and tunes q, c and K, with q tuned in the search field. Repeated looks inflate false wins (a
  simulation put a useless upgrade's "win" rate at about 7.7% instead of 2.5%), so screening numbers never
  go in the report.
- **Merge rule**: keep an upgrade only if it beats `mc` in at least one field and isn't worse in the other.
  If the two fields' leaders disagree, prefer the search-field leader, because it is closer to human play.
- **Confirmation** (fresh seeds from 4,000,000,000): fixed 400 deals, no early stopping, run once in both
  fields for the final bot, `mc`, the references, and one ablation per kept upgrade (the final bot minus
  that upgrade, so the devs don't build a part that does nothing). Only confirmation numbers go in the
  report. `tourney.py` keeps screening and confirmation results apart.
- **Scaling curve for the winner**: counts calibrated to 0.05, 0.1, 0.2, 0.4 and 0.8 s, within the rule. Add 2 s and 8 s as
  a compiled-speed proxy; these are labeled as outside the 1 s rule and need `run.TIME_LIMIT` raised for
  those runs only. The devs can use the curve as a difficulty slider.
- Compute estimate: about 15 min per 100 deals at 0.5 s in the rule field on 7 workers (from the spike's
  0.8 s run), about 1.6× that in the search field. Screening takes a few nights and confirmation about one
  more.

### 4. Speed

- Write the code and tests on CPython. Before calibration, Kai decides on PyPy (`sudo apt install pypy3`).
  If it's installed, measure the speed-up, then calibrate and run everything under PyPy; otherwise use
  CPython throughout. Never mix interpreters (recalibration would mean rerunning everything), and state in
  the report which one was used.
- Optimize Python internals only where profiling shows a hotspot worth it. C++ only if testing is still too
  slow.

### 5. Correctness checks (`bot/test_search.py`, unittest)

- At every decision across N matches, the rebuilt state equals the real game's state: turn, trick, owner,
  passes, finished, fallen, trick plays, direction, King, 3♣ lead. This is the spike's `--check`, turned
  into a test.
- Guesses: right counts, union = unseen cards, exchange facts hold. The real deal also satisfies the same hard
  facts, which validates the inference.
- Card-reading weights are computed from `View` only (by construction: their functions take only the `View`
  and the guess).
- `run.timed` already enforces the 1 s limit.

### 6. Report

- Audience: Urnique Studio developers. Source in `docs/report/` as Markdown. A shareable page is made when
  it's finished.
- Contents: a summary with headline numbers; the rules the bot assumes (the `[user]` rules as a yes/no
  checklist for the devs); how the bot works (plain words + pseudocode); what it needs from their engine; a
  fairness statement (the exact list of what it sees); results tables with error bars; the scaling curve;
  how to reproduce (commands + seeds); limitations (tested against bots only, rules from observation,
  timings in Python).
- Code license: the repo is MIT (© kaikub).

### 7. Files

- `bot/search.py`: search core + candidates, with a registry separate from `bots.ALL`.
- `bot/tourney.py`: duplicate runner, saved per-candidate results, offline comparisons, scaling curve.
  Reuses `run.play_match` and its seeding.
- `bot/test_search.py`: the checks above.
- `bot/strategies.md`: add the search candidates using its Expect/Test/Result template.
- `bot/spike_mc.py`: delete once `search.py` replaces it, and repoint `AGENTS.md`'s `spike_mc.*` references
  (commands, the rule-change checklist, the engine→bot bridge) to `search.py`.
- Results: `log/tourney/` (gitignored, like `log/`).

## Left to the builder

- How `mc_read` samples (rejection vs weighting) and the final q.
- ISMCTS tuning (c, reuse between turns), the `mc_end` threshold K, `mc_trade` pruning.
- Internal speed work, file names, and the batch size or caps in the stopping rule, if compute demands it.
- Adding further candidates. Each one follows the same protocol.
- If `ismcts` wins, build the other upgrades as parts it can reuse.

## Calls made after the builder review (Claude's, for Kai to check)

1. Both fields count. Upgrades must hold up against search bots that pass on purpose, not only against the
   easy-to-model rule bots.
2. Report numbers come only from a fixed-size run on fresh seeds. Screening wins can be luck.
3. One ablation per kept upgrade on the fresh seeds.
4. Budgets count simulated moves, so decision time stays nearly constant and the 1 s limit holds.
5. CPython first; PyPy only if Kai installs it before calibration.
