# AGENTS.md

Guidance for coding agents working in this repository.

An engine for the Thai card game "Slave" (Slap 'em UP! rules plus the user's house rules) and a harness that plays bot strategies against each other and measures them. Python 3 standard library only: nothing to install, no build or lint step.

## Where each truth lives

| Topic | Home |
|---|---|
| Game rules | module docstring of `game/slave.py` |
| What a bot may see and do, the 1 s limit, how bots are measured | `bot/bot.md` |
| Strategy specs, default lead/follow/trade, results, bets | `bot/strategies.md` |

Edit a fact in its home; this file only points to it, so nothing drifts.

## Commands

```bash
python3 game/test_slave.py                       # all rule tests (-v for names)
python3 game/test_slave.py Combos.test_triple_overrides_any_single   # one test; a class name runs that class
python3 game/example_game.py > game/example_game.txt   # regenerate the narrated every-rule example
python3 bot/run.py --epochs 20                   # pool + bet experiments -> log/<YYYYmmdd_HHMM>/report.md
python3 bot/run.py --until 07:15                 # same, stopping at a wall-clock time (overnight runs)
python3 bot/run.py --replay bet 1000004203       # print one match from its experiment + seed
python3 bot/test_search.py                       # search bots: state rebuild, world sampling, tournament runner
python3 bot/tourney.py run --bot mc --field rule --phase screen --deals 100   # duplicate tournament -> log/tourney/
python3 bot/tourney.py compare mc counter --field rule --phase screen
python3 game/slave.py                            # hot-seat CLI for a human playing all four seats
```

Nothing is a package. Scripts run from any directory (bot scripts add `game/` to `sys.path`), but a bare `python3 -m unittest` at the root reports "NO TESTS RAN" — that is not a pass.

## Add a bot

1. Add its row to `bot/strategies.md`, following that file's header rules. Done when every lead, follow and trade choice is either stated or covered by the defaults defined there.
2. Subclass `Bot` in `bot/bots.py` with `name` set to the row's ID, override only what differs from the defaults (`Bot` already implements them), and append the class to `ALL`, which is the pool. Done when `python3 bot/run.py --epochs 1` finishes and the bot appears in the new report.
   - To restrict choices, filter `v.legal` and pass `v._replace(legal=...)` to `lead_whole` / `weakest_follow`, as `Saver` and `LowThenPower` do. When the filter empties the list while leading, fall back to the full list: a leader cannot pass, and `min()` of an empty list raises.
   - Keep experimental bots out of `ALL`, because any change to `ALL` reshuffles every pool lineup (see Replay). Register them with `BY_NAME[name] = Cls` at module level of the script that runs them, so pool workers see them under any multiprocessing start method.
3. Measure it over at least 2 epochs: with one, ± prints `nan` and the bet line still names a winner. For a head-to-head, set `BET` in `bot/run.py`: the `bet` experiment seats those two bots plus two random fillers at every table. Done when the two ± ranges no longer overlap (bot.md §5), or still overlap after a long run, which is a tie; then fill the bot's Result entry in `strategies.md` from `report.md`.

## Change a game rule

1. Edit the rule's line in the `game/slave.py` docstring and tag it `[official]` (stated by Slap 'em UP!), `[user]` (decided by the user) or `[assumed]` (unstated, common Thai rule).
2. Change the engine and add or fix the tests for that rule in `game/test_slave.py`. The `game()` helper plays clockwise so turns read top to bottom, while the engine defaults to counter-clockwise: pass `direction=-1` or build `Game` directly for a counter-clockwise example. Done when `python3 game/test_slave.py` passes.
3. Update every copy of rule knowledge outside the engine that the change touches:
   - exchange (sizes, who must give their best): `run.play_match` (`best`/`know`), `search.guess`, `bot/bot.md` §1
   - overrides: `bots.Counter._is_boss`; `weakest_follow`, `Highest`, `Dumper` and `OverrideEager` treat any different-size move as an override
   - round start, direction, scoring: `search.rebuild` and `search.value`, and the `-1` direction in the trade `View` built by `run.play_match`
   - a new mutable `Game` attribute: copy it in `search.with_hands` (its shallow copy would share it across rollouts) and add it to the field list in `FIELDS` of `bot/test_search.py`

   Done when every touched copy matches the rule and `python3 bot/test_search.py` passes (it covers `rebuild` and `guess`).
4. Regenerate `example_game.txt`; for a new kind of event, first add it to `RULES` in `game/example_game.py` and detect it in `play()`. Done when every box under "Rules used:" is `[x]`.

## How the pieces fit

- **Cards** are ints 0–51 in strength order (`rank = c // 4`, `suit = c % 4` in ♣♦♥♠ order), so `max(move)` is a set's top card and 3♣ is `0`. A move is a sorted tuple; `()` is a pass. Convert with `parse("3c 10h As")` and `show(cards)`.
- **Rounds**: a match is 3 *game rounds* (one deal each, one `Game` object); a *card round* is a trick inside a game round.
- **Engine → bot bridge**: `run.play_match` is the only place engine state reaches a bot. For each decision it builds a `View` of public information (namedtuple in `run.py`) and calls `act(v)` or `give(v, k)`. Treat `View` fields as read-only: `history` and `passed` are the engine's live objects. An illegal move (`ValueError`), an invalid trade (`AssertionError` in `exchange`) or a decision over 1 s (`RuntimeError` from `run.timed`) stops the whole run. A bot that needs more information gets a new `View` field, never the `Game` (bot.md §1). Search bots rebuild engine state from public history with `search.rebuild`.
- **Replay**: every match replays exactly from its experiment and seed, as long as bots draw randomness only from `self.rng`. Any change to the engine, to any bot, or to `ALL`/`BET` (they pick each seed's lineup) makes old seeds replay *different* matches, and a bot with a wall-clock budget never replays exactly (`MC`'s rollout count depends on CPU load). Compare bots only within one run.
- **Logs**: `log/` is gitignored, so copy results worth keeping into `strategies.md`. Read `report.md` first; it refreshes as epochs finish, at most every 30 s. Full move histories exist only for epochs 0–2 and every `--full-every`th; replay any other match with `--replay`. Runs started in the same minute share one log dir and overwrite each other, so stagger parallel runs.

## Conventions

- Back every "bot X beats bot Y" claim with a run: avg rank ± range from `run.py`, or the same-seat gap from `tourney.py`, judged by bot.md §5. An untested strategy argument becomes a row in `strategies.md`, not a conclusion.
- Match the existing density: one-line `def f(): return ...` for small helpers, short `;`-joined statements, no type hints, comments only for a why.
- Use the standard library only. There is no requirements file, so any third-party import breaks the scripts on a fresh machine.
