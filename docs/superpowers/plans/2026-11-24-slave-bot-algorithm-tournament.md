# Slave Bot Algorithm Tournament Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Find the strongest fair Slave bot by tournament, ship it as a Python reference, and write the report for the Slap 'em UP! devs.

**Architecture:** `bot/search.py` holds the search core (rebuild state from public history, guess hidden cards, play out) plus every candidate as a subclass of `MC`, each overriding one hook. `bot/tourney.py` runs duplicate matches in two fields, saves per-(seed, seat) results, and compares bots offline. Budgets are counted in simulated moves so every match replays exactly.

**Tech Stack:** Python 3 standard library only (CPython; PyPy only if Kai installs it before Task 8). Tests use `unittest`, run as files.

**Spec:** `docs/superpowers/specs/2026-11-24-slave-bot-algorithm-tournament-design.md`

## Global Constraints

- Standard library only; no numpy or ML runtime in the bot.
- Bots decide from `View` only (bot.md §1); never pass a `Game` to a bot.
- Max 1 s per decision; only scaling-curve runs labeled "compiled-speed proxy" raise `run.TIME_LIMIT`.
- Search bots stay out of `bots.ALL`; register with `BY_NAME[name] = Cls` at module level.
- Screening seeds from 3,000,000,000; confirmation seeds from 4,000,000,000; never mix phases.
- Thinking time B = 0.5 s per decision, as a calibrated simulated-move count; search field = 3 × `mc` at the 0.1 s count.
- Rule field = `counter`, `give_lonely`, `pair_keeper`. Metric = final match rank in the tested seat, paired per deal (mean of 4 seats), 95% CI across deals, plus 1st-place rate.
- One interpreter for every calibrated run; state it in the report.
- No code that touches live Slap 'em UP! servers or the game client.

## Review Focus

1. A fallen King still holds cards: guesses must give them exactly `counts[king]` cards, and they never act. Test in Task 1.
2. A decision with one legal move (forced pass) must not search and must not consume rng (replay stays aligned). Test in Task 1.
3. The same bot and seed must give an identical match twice (count budgets, no wall clock). Test in Task 1.
4. The largest lead positions (up to 25 legal moves, early round) must stay under 1 s at the calibrated count. Test in Task 8.
5. Comparing two bots whose result files cover different seeds must use only the shared complete deals, never crash or silently mix. Test in Task 2.

---

### Task 1: Search core and `mc` baseline

**Files:**
- Create: `bot/search.py`
- Create: `bot/test_search.py`

**Interfaces:**
- Consumes: `run.View`, `run.play_match(names, seed)`, `run.new_round`, `bots.GiveLonely`, `bots.Lowest`, `bots.BY_NAME`, `slave.Game/POINTS/ROUNDS_PER_MATCH`.
- Produces:
  - `class Sim(Game)` — legal moves cached per turn; attribute `steps: int` counts `step()` calls.
  - `rebuild(v) -> Sim`, `with_hands(base: Sim, hands: list[list[int]]) -> Sim`
  - `unseen(v) -> list[int]`, `guess(v, rng, unseen) -> dict[int, list[int]]`, `value(order: list[int], v) -> float`
  - `class MC(GiveLonely)`: `name = "mc"`, `work: int` (simulated moves per decision, default 20000 until Task 8 calibrates), hooks `sample(self, v, unseen) -> dict`, `policy(self, g: Sim) -> tuple`, `playout(self, g: Sim, v) -> float`; `evaluate(v) -> (dict[move, float], int worlds)`; `act(v)`.
  - `SEARCH: dict[str, type]` and `register(cls) -> cls` (adds to `SEARCH` and `BY_NAME`); `variant(base, name, **attrs) -> type` (subclass with overridden attributes, registered).

Port from `bot/spike_mc.py`. Changes: budget loop stops when the summed `steps` of this decision's playouts ≥ `self.work`, finishing the current world (every legal move) first, and always doing at least one world; no `time` calls in the bot. `act` returns `v.legal[0]` without touching rng when `len(v.legal) == 1`.

- [ ] **Step 1: Write failing tests in `bot/test_search.py`** (header: `"""Run: python3 bot/test_search.py"""`, `unittest.main()` at bottom)
  - `test_rebuild_matches_engine`: spy `run.new_round` as the spike's `check()` does; over 40 matches (seat `seed % 4`, rivals counter/give_lonely/pair_keeper) assert every field in `turn trick trick_owner passed finished fallen trick_plays dir king must_lead_3c` equals the real game's at every decision.
  - `test_guess_consistent`: same harness; each guess has `len(w[p]) == v.counts[p]`, union == `unseen(v)`, and gift/bound facts hold for both the guess and the real partner hand (spike asserts). Includes fallen-King case (Review Focus 1): assert the King's guessed count equals `v.counts[king]` whenever `king in v.out`.
  - `test_forced_move_no_rng` (Review Focus 2): a View with `legal=[()]` returns `()` and `bot.rng.getstate()` is unchanged.
  - `test_replay_identical` (Review Focus 3): `run.play_match(["mc","counter","give_lonely","pair_keeper"], 7)` twice with `MC.work = 2000` gives equal records.
  - `test_work_budget`: wrap `evaluate`; with `work = 2000`, every searched decision simulated ≥ 2000 steps and < 2000 + (steps of one world).

- [ ] **Step 2: Run** `python3 bot/test_search.py` — Expected: FAIL (`No module named search`).
- [ ] **Step 3: Implement `bot/search.py`** with the interfaces above; register `MC` at module level.
- [ ] **Step 4: Run** `python3 bot/test_search.py` — Expected: `OK`.
- [ ] **Step 5: Commit** `git add bot/search.py bot/test_search.py && git commit -m "feat: search core and mc baseline"`

### Task 2: Tournament runner

**Files:**
- Create: `bot/tourney.py`
- Modify: `bot/test_search.py` (add runner tests)
- Delete: `bot/spike_mc.py`
- Modify: `AGENTS.md` (repoint every `spike_mc.*` reference to `search.*`; replace the `spike_mc.py --check` command with `python3 bot/test_search.py` and add the `tourney.py` commands)
- Create: `bot/budgets.json` (`{}`; filled in Task 8; committed so replays are exact)

**Interfaces:**
- Consumes: `search.SEARCH`, `search.register`, `run.play_match`.
- Produces (CLI, all results under `log/tourney/<phase>/<field>/<bot>.jsonl`, one line `{"seed", "seat", "place", "secs_max", "secs_mean"}`):
  - `run --bot B --field rule|search --phase screen|confirm --deals N` — appends deals not yet in the file; rule bots allowed as B.
  - `compare A B --field F --phase P` — prints `n deals, A avg/1st%, B avg/1st%, gap ± CI (verdict)` over deals complete for both.
  - `screen A --vs mc --field F` — batches of 50 for A and the reference until CI half-width ≤ 0.05 or CI excludes 0 with ≥ 100 deals, cap 400; prints each batch's compare line.
  - `calibrate --bot B --secs S` — runs 10 search-field matches, sets work so the mean searched decision ≈ S s; writes `budgets.json[B][str(S)]`; prints mean and max seconds.
  - Python: `load(phase, field, bot) -> dict[(seed, seat), place]`, `gap(a: dict, b: dict) -> (n, mean, ci, a_avg, b_avg, a_win, b_win)`.
- Search field opponents are a registered `mc_field` = `variant(MC, "mc_field", work=budgets["mc"]["0.1"])`, falling back to `MC.work // 5` before calibration. Bots read their work from `budgets.json` at import when an entry exists for `0.5`.

- [ ] **Step 1: Write failing tests**
  - `test_gap_uses_shared_complete_deals` (Review Focus 5): A covers seeds {1,2,3} × 4 seats, B covers {2,3,4} × 4 plus seed 5 with 3 seats; `gap` returns `n == 2`.
  - `test_gap_math`: hand-built places giving per-deal diffs [-1, 0, -0.5] → mean -0.5 and CI `1.96*stdev/sqrt(3)`.
  - `test_run_appends_only_missing`: `run` for 2 deals then 3 deals with `MC.work=500` leaves 12 lines, no duplicates.
- [ ] **Step 2: Run** `python3 bot/test_search.py` — Expected: FAIL on the new tests.
- [ ] **Step 3: Implement `bot/tourney.py`** (Pool workers; register bots at module level per AGENTS.md).
- [ ] **Step 4: Run** `python3 bot/test_search.py` — Expected: `OK`. Then `python3 bot/tourney.py run --bot mc --field rule --phase screen --deals 2 && python3 bot/tourney.py run --bot counter --field rule --phase screen --deals 2 && python3 bot/tourney.py compare mc counter --field rule --phase screen` — Expected: one compare line, `2 deals`.
- [ ] **Step 5: Commit** `git rm bot/spike_mc.py && git add bot/tourney.py bot/budgets.json bot/test_search.py AGENTS.md && git commit -m "feat: duplicate tournament runner"`

### Tasks 3–7: Candidates

Each task: add the class to `bot/search.py`, add its tests to `bot/test_search.py`, add a row to `bot/strategies.md` §7 with the template (Expect / Test / Result left blank), run `python3 bot/test_search.py` (Expected `OK`), commit `feat: <id> candidate`. Each candidate overrides only the hook named.

**Task 3: `mc_read`** — overrides `sample`. Target P(guess) ∝ q^(voluntary passes); a pass by p facing table T is voluntary if p's guessed hand at that time (current guessed hand + cards p played after that pass this round, from `v.history`) held a set legal against T under the engine's rules (same size and higher top, or the override size). Builder picks rejection vs weighting; registered variants `mc_read_q0.1`, `mc_read_q0.3`, `mc_read_q0.6` via `variant`.
  - Tests: `test_voluntary_pass_count` on a hand-built View (a player passed on 9♦ while the guessed hand at that time holds J♥ → count 1; holds only 7s → 0); `test_read_q1_equals_mc_distribution`: with q=1 the hook returns the same guess as `MC.sample` for the same rng state.

**Task 4: `mc_counter`** — overrides `policy`: every player in playouts uses `bots.Counter`'s decision rule, with that player's unseen cards computed from the `Sim` (track played cards in `Sim`, copied in `with_hands`).
  - Test: `test_counter_policy_matches_bot`: on 200 random `Sim` states, the hook's move equals `Counter(None).act(view)` for a View built from the same public facts.

**Task 5: `ismcts`** — overrides `evaluate`: SO-ISMCTS (one `sample` per iteration, UCB1 with availability counts, c = 0.7 on values scaled to [0, 1] by `(value - min) / (max - min)` over the round's value range, nodes for every player, each node backs up the value of the player who acted, `lowest` playouts, budget = same step count, return most-visited root move's visit share as its score).
  - Tests: `test_ismcts_legal_and_replays` (two identical matches with work 2000); `test_ismcts_finds_forced_win`: hand-built round-3 position where one move wins the match outright and others lose → that move chosen.

**Task 6: `mc_end`** — overrides `playout`: when my hand has ≤ K cards (K = 5), in each world choose my own remaining moves by exhaustive search (opponents `lowest`), counting every simulated step against the budget.
  - Test: `test_end_orders_last_groups`: hand-built position (my hand = a boss pair + a low single, opponents can only beat singles) → plays the pair first; plain `MC` with `lowest` playouts is allowed to differ.

**Task 7: `mc_trade`** — overrides `give`: candidate gifts are k-card subsets of my 6 lowest cards; for each, sample the other three hands from the remaining 39 cards, apply the trade (partner gives their best k), play the round from the start with `lowest`, average my value; same step budget split evenly across gifts.
  - Test: `test_trade_returns_own_cards` (k cards from my hand, from my 6 lowest); `test_trade_replays` (same seed → same gift).

### Task 8: Calibrate and screen

**Files:** Modify `bot/budgets.json`, `bot/strategies.md` (Result lines, marked "screening").

- [ ] **Step 1:** Ask Kai whether PyPy is installed (`pypy3 --version`). If yes, run Steps 2–4 with `pypy3`; otherwise `python3`. Record the interpreter in `bot/budgets.json` as `"_interpreter"`.
- [ ] **Step 2:** `python3 bot/tourney.py calibrate --bot mc --secs 0.1`, then `--secs 0.5` for every candidate. Expected: max seconds < 1.0 for every 0.5 s entry (Review Focus 4); if not, lower that bot's work until it is.
- [ ] **Step 3:** For each candidate X in both fields: `python3 bot/tourney.py screen X --vs mc --field rule` and `--field search` (background, overnight).
- [ ] **Step 4:** Apply the merge rule (beats `mc` in ≥ 1 field, not worse in the other; on conflict prefer the search field). Pick q by the search field. Write each verdict into `strategies.md`. Commit.

### Task 9: Combine, confirm, scale

**Files:** Modify `bot/search.py` (class `best` combining kept hooks), `bot/test_search.py`, `bot/budgets.json`, `bot/strategies.md`.

- [ ] **Step 1:** Implement `best` and its ablations `best_minus_<id>` via `variant`/hook composition; test `test_best_replays`. Calibrate `best` to 0.5 s.
- [ ] **Step 2:** Screen `best` against each kept single upgrade (both fields); keep `best` only if not worse than any.
- [ ] **Step 3:** Confirmation, `--phase confirm --deals 400`, both fields, for: `best`, `mc`, `counter`, `give_lonely`, every `best_minus_<id>`. No early stopping.
- [ ] **Step 4:** Scaling curve for `best` in the rule field, confirm seeds, 200 deals each at counts calibrated to 0.05, 0.1, 0.2, 0.4, 0.8 s; plus 2 s and 8 s labeled compiled-speed proxy with `run.TIME_LIMIT` raised in those runs only.
- [ ] **Step 5:** Record confirmation results in `strategies.md`; commit.

### Task 10: Report

**Files:** Create `docs/report/slave-bot-report.md`.

- [ ] **Step 1:** Write the sections the spec §6 lists, using confirmation numbers only, every number with its ± and deal count: summary; the `[user]` rules from `game/slave.py` as a yes/no checklist; how it works (plain words + pseudocode of `best`); what it needs from their engine (copy state, legal moves, apply move, finish order, public history, trade facts); fairness (the `View` field list); results tables (both fields, 1st-place rates, ablations); scaling curve as a table; reproduce commands with seeds and interpreter; limitations; MIT license.
- [ ] **Step 2:** Verify every number against `tourney.py compare` output; fix any mismatch.
- [ ] **Step 3:** Commit, then ask Kai about the report language and publishing a shareable page.
