# Strategy ideas to test

Each bot is an assumption until an experiment backs it up (see `bot.md` section 5 for how we measure).
Every bot below must be defined precisely enough to code without guessing.

Shared terms:
- **Strength** of a set = its top card (rank, then suit).
- **Group** = all cards of one rank in hand (single, pair, triple or quad).
- **Boss** = a set nobody can beat any more, judged from the cards still unseen (card counting).
- **Default lead** = play the whole group of the lowest rank. **Default follow** = weakest set that
  beats the table; use an override only if no same-size set beats it. **Default trade** = lowest cards.
  A bot uses the defaults for anything its row doesn't mention.

Template for results:

```
## <bot id>
- Expect: <why it should win more>
- Test: <which bots, how many epochs>
- Result: <avg rank ± range>  → kept / dropped
```

## 0. Baselines (floors every bot must beat)
| ID | Rule |
|---|---|
| `random` | Any legal move, including pass. Trades random cards. |
| `random_nopass` | Any legal set; passes only when nothing beats the table. |
| `lowest` | Defaults only: lead lowest whole group, follow with the weakest set, never pass if it can play. |
| `highest` | Lead the highest whole group; follow with the strongest set (overrides count as strongest). Never passes if it can play. |
| `passer` | Lead lowest whole group; always pass when following. Should lose to everything. |

## 1. Hand shape (how to shed cards)
| ID | Rule |
|---|---|
| `pair_keeper` | Never break a group to follow (e.g. no single from a pair); pass instead. Breaks groups only when hand ≤ 4 cards. |
| `shedder` | Lead the group with the most cards (quad > triple > pair > single); tie → lowest rank. |
| `single_first` | Lead singles before groups (lowest single first); keep groups for later. |
| `fewest_groups` | Pick the move that leaves the fewest groups in hand (fewer groups = fewer leads needed to go out); tie → weakest. |
| `split_lead` | Lead one card from the lowest group, keeping the rest to follow later. |

## 2. Power cards (2s, Aces, triples, quads)
| ID | Rule |
|---|---|
| `saver` | Never play a 2 or an Ace until hand ≤ 4 cards (pass instead). |
| `dumper` | Follow with the strongest single/pair available to grab the lead early. |
| `override_eager` | Use a triple-on-single or quad-on-pair whenever possible. |
| `override_hoarder` | Never lead a triple/quad; keep them only for overrides. Plays them as overrides when hand ≤ 6 or an opponent has ≤ 3 cards. |
| `override_never` | Never override; triples and quads are only led. |

## 3. Card counting
| ID | Rule |
|---|---|
| `counter` | Defaults, but when it holds a boss set and the hand is "boss + one group", play the boss then lead the last group to go out. |
| `boss_saver` | Hold boss cards until the end; never spend a boss before hand ≤ 4. |
| `exchange_reader` | Uses exchange knowledge: as King, knows the Slave has nothing above the cards received; as Slave, knows the King's gift. Treats those cards as seen when deciding boss. Otherwise `counter`. |
| `pass_reader` | Remembers who passed on what; assumes a player who passed on rank R has no single above R (until the next game round). Uses it to pick leads opponents can't beat. |

## 4. Opponents (react to the table)
| ID | Rule |
|---|---|
| `blocker` | When any opponent has 1–2 cards: lead pairs/triples instead of singles, and follow with the strongest set to keep them from leading. |
| `next_aware` | When the next player has few cards, avoid leading a size they could finish with. |
| `copycat_size` | Lead the size opponents passed on most often this game round. |

## 5. Match and title (3 game rounds)
| ID | Rule |
|---|---|
| `king_racer` | As the reigning King (rounds 2–3), play like `highest` (falling = Slave anyway, so all-in on going out first). Otherwise defaults. |
| `king_hunter` | Not King: when the King has ≤ 3 cards, play strongest sets to go out first and knock the King down. |
| `score_aware` | Round 3: if 1st place is safe whatever happens, play defaults; if behind, play `highest`; if ahead but not safe, play `pair_keeper`. |
| `tiebreak_aware` | Round 3: if finishing later wins a points tie, and it can't climb higher, it stalls (passes) rather than finishing early. |

## 6. Trade (King/Queen blind trade)
| ID | Rule |
|---|---|
| `give_lonely` | Trade away the lowest cards that are not part of a group (keep pairs/triples intact). |
| `give_break_slave` | Trade away cards that leave the King with no lonely low single (pairs stay). Otherwise lowest. |
| `give_random` | Random cards (pairs with any bot to isolate the value of trading well). |

## 7. Search (uses the 1 second)
| ID | Rule |
|---|---|
| `mc_lowest` | Monte Carlo: deal the unseen cards randomly to opponents (matching card counts and exchange knowledge), play each legal move out with `lowest` for all players, pick the move with the best average final place. Stop at 0.9 s. |
| `mc_smart` | Same, but rollouts use the best heuristic bot found so far. |
| `ismcts` | Information-Set Monte Carlo Tree Search over the same sampled worlds; stop at 0.9 s. |
| `rl_selfplay` | Later: a learned policy trained by self-play against the pool. |

## Questions these bots answer
- Does passing ever help? `random` vs `random_nopass`, `lowest` vs `pair_keeper`.
- Spend power early or late? `dumper` vs `saver` vs `boss_saver`.
- Are overrides worth it? `override_eager` vs `override_hoarder` vs `override_never`.
- Does card counting pay? `lowest` vs `counter` vs `exchange_reader` vs `pass_reader`.
- Does the King race pay off? `king_racer` vs `lowest`.
- Does trading well matter? `give_lonely` vs `give_random` (same play style).
- How much better is search than the best heuristic? `mc_*` / `ismcts` vs the top heuristic.
