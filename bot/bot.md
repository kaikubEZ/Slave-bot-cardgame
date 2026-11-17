# Bot rulebook

Every bot must follow these rules. Game rules themselves live in `game/slave.py` (top of file).
Strategy ideas to test go in `strategies.md`, not here.

## 1. What a bot can see
- Own hand, the cards on the table, every move so far (public history), how many cards each player
  holds, who passed this card round, who is out, titles, points so far, current direction, whose turn it is.
- Never other players' hands. No peeking at the engine.
- Exchange knowledge:
  - King knows the 2 cards he received (= Slave's 2 best), so the Slave holds nothing higher than those.
  - Slave knows the 2 cards they gave the King and the 2 cards the King gave them.
  - Same for Queen/People with 1 card.
- A bot may remember everything from earlier game rounds in the same match (card counting allowed).

## 2. What a bot decides
- `act(view) -> move` each turn: a legal set of cards, or pass (pass only when not leading).
- `give(view, k) -> k cards` when it is King/Queen in the blind trade.
- Max 1 second per decision.
- An illegal move or going over 1 second is a bug: the match stops with an error.

## 3. Bots play fair
- Bots never talk or team up; each plays for itself.

## 4. What a bot is trying to win
- The best final rank after a match of 3 game rounds (points total, then the tie-break).
- Every place counts, not only 1st.

## 5. How bots are measured
- **Pool** = every bot in `strategies.md` that has been coded.
- **Match setup**: pick 4 different bots from the pool at random and seat them at random.
- **Epoch** = 100 matches with random seeds (seeds recorded so any match can be replayed).
- Per epoch, each bot gets its **average final rank** (1 = best, 4 = worst) over the matches it played,
  and how often it finished 1st / 2nd / 3rd / 4th.
- Repeat for many epochs with new seeds. Report each bot's mean across epochs and the spread
  (95% range). A bot is only "better" when its range does not overlap the other's.
- Bots with few matches so far get a wide range; keep running epochs until the ranges settle.
- To settle a specific question (e.g. `saver` vs `dumper`), run a focused test: those bots plus
  fillers picked at random, same seeds for both.

## 6. Baseline bots
- See `strategies.md` section 0 (`random`, `random_nopass`, `lowest`, `highest`, `passer`).
- Any new bot is first compared against these.
