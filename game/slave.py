"""Thai Slave base game, rules follow Slap 'em UP! (slapthemup.com/en/how-to-play).
No dependencies. Run `python3 slave.py` to play all seats in the terminal.

Rules ([official] = stated by Slap 'em UP!, [assumed] = not stated, common Thai rule):
- [official] 4 players (King, Queen, People, Slave), 52 cards, 13 each.
- [official] Rank 3 < 4 < ... < K < A < 2. Suit ♣ < ♦ < ♥ < ♠.
- [user] Play singles, pairs, triples or quads of the same rank (no straights). Any of them can lead.
- [official] To follow: same count, higher top card (rank first, then the highest suit in the set),
  e.g. 5♣ 5♠ beats 5♦ 5♥ because ♠ > ♥.
- [user] Override (only these two): a triple beats any single, a quad beats any pair, whatever the rank
  (3♣ 3♦ 3♥ beats a single 2♠). After that, the card round continues at the new size.
  Not allowed: quad on single, triple on pair, quad on triple.
- [user] Passing locks you out until the trick ends. The trick ends when every player still in has passed
  except one; that player leads the next trick.
- [user] If a player goes out with their last card, the trick keeps going among the others. When all of them
  have passed, the last player still in the round who played a card in that trick leads.
  If nobody still in played in that trick, the last player to pass leads. In both cases the direction
  of play flips. (If someone beats the winner's last card instead, the direction stays.)
- [user] Play goes counter-clockwise (seat 3 -> 2 -> 1 -> 0 -> 3): DIRECTION = -1.
  [user] A flip lasts for the rest of the game round; each game round starts counter-clockwise again.
- [official] The first round starts with whoever holds 3♣ (lead must include 3♣).
  [user] Game rounds 2 and 3 start with the Slave.
- [official] A match is 3 rounds. Before rounds 2 and 3: King and Slave swap 2 cards, Queen and People swap 1.
  [user] It is a blind trade: King/Queen first pick any cards from their own 13 (without seeing what they
  will get), then both sides swap at once. Slave/People must give their best cards.
- [user] Rounds 2 and 3: if someone other than the reigning King goes out first, the King becomes Slave
  immediately and stops playing; the rest play on for Queen and People.
- [user] Score per round: King +2, Queen +1, People -1, Slave -2. Final standing = total over 3 rounds.
  [user] Tied totals: whoever finished later in the last game round ranks higher.
"""
import itertools, random

RANKS = "3 4 5 6 7 8 9 10 J Q K A 2".split()
SUITS = "♣♦♥♠"
TITLES = ["King", "Queen", "People", "Slave"]
MAX_SET = 4          # singles, pairs, triples, quads
OVERRIDE = {1: 3, 2: 4}  # table size -> set size that beats it regardless of rank
ROUNDS_PER_MATCH = 3
N_PLAYERS = 4        # default table size
POINTS = [2, 1, -1, -2]  # King, Queen, People, Slave
DIRECTION = -1       # counter-clockwise: seat s plays after seat s+1
def rank(c): return c // 4
def name(c): return RANKS[rank(c)] + SUITS[c % 4]
def show(cards): return " ".join(name(c) for c in sorted(cards)) or "pass"

def parse(text):
    """'3c 10h As' or '3♣' -> card ids. Raises ValueError on bad input."""
    out = []
    for tok in text.upper().split():
        r, s = tok[:-1], tok[-1]
        s = {"C": 0, "D": 1, "H": 2, "S": 3, "♣": 0, "♦": 1, "♥": 2, "♠": 3}.get(s)
        if r not in RANKS or s is None: raise ValueError(f"bad card {tok!r}")
        out.append(RANKS.index(r) * 4 + s)
    return tuple(sorted(out))


class Game:
    """One round. Seats 0..n-1. `history` = list of (seat, move) where move=() is a pass."""

    def __init__(self, hands, leader, must_lead_3c=False, king=None, direction=DIRECTION):
        self.hands = [sorted(h) for h in hands]
        self.n = len(hands)
        self.turn = leader
        self.trick = ()               # current top play
        self.trick_owner = None
        self.passed = set()           # seats locked out of this trick
        self.finished = []            # seats that emptied their hand, in order; full King..Slave order once over()
        self.fallen = []              # reigning King knocked down to Slave
        self.king = king              # reigning King (rounds 2-3), None in round 1
        self.trick_plays = []         # seats that played a card in the current trick, in order
        self.history = []
        self.must_lead_3c = must_lead_3c
        self.dir = direction          # -1 counter-clockwise, +1 clockwise

    def out(self): return set(self.finished) | set(self.fallen)
    def over(self): return self.n - len(self.out()) <= 1

    def legal(self):
        hand = self.hands[self.turn]
        by_rank = {}
        for c in hand: by_rank.setdefault(rank(c), []).append(c)
        k = len(self.trick)
        moves = []
        for cards in by_rank.values():
            for size in range(1, min(len(cards), MAX_SET) + 1):
                if k and size != k and OVERRIDE.get(k) != size: continue   # same size, or override
                for combo in itertools.combinations(cards, size):
                    if size != k or max(combo) > max(self.trick):
                        moves.append(combo)
        if self.must_lead_3c:
            moves = [m for m in moves if 0 in m]
        if k: moves.append(())        # can only pass when following
        return moves

    def _next_active(self, s):
        for i in range(1, self.n + 1):
            t = (s + self.dir * i) % self.n
            if t not in self.out(): return t

    def step(self, move):
        s = self.turn
        move = tuple(sorted(move))
        if move not in self.legal(): raise ValueError(f"illegal move {show(move)} for seat {s}")
        self.history.append((s, move))
        self.must_lead_3c = False
        if move:
            for c in move: self.hands[s].remove(c)
            self.trick, self.trick_owner = move, s
            self.trick_plays.append(s)
            if not self.hands[s]:
                self.finished.append(s)
                if len(self.finished) == 1 and self.king not in (None, s):
                    self.fallen.append(self.king)        # King didn't win first -> Slave now
        else:
            self.passed.add(s)
        out = self.out()
        if self.over():
            self.finished += [p for p in range(self.n) if p not in out] + self.fallen
            return
        still_in = {p for p in range(self.n) if p not in out and p not in self.passed}
        if not still_in - {self.trick_owner}:            # nobody left to beat it -> trick ends
            leader = next((p for p in reversed(self.trick_plays) if p not in out), None)
            if leader is None: leader = s if s not in out else self._next_active(s)
            if self.trick_owner in out: self.dir = -self.dir   # winner's last card went unbeaten -> flip
            self.turn = leader
            self.trick, self.trick_owner, self.passed, self.trick_plays = (), None, set(), []
        else:                                            # next seat still in this trick
            self.turn = next(t for t in ((s + self.dir * i) % self.n for i in range(1, self.n + 1)) if t in still_in)


def deal(n=N_PLAYERS, rng=random):
    deck = list(range(52)); rng.shuffle(deck)
    return [deck[i::n] for i in range(n)]

def exchange(hands, order, give):
    """order[0]=King ... order[-1]=Slave. give(seat, hand, k) -> k cards the top player gives away,
    chosen from their own hand before the swap (blind trade)."""
    for top, bot, k in [(order[0], order[-1], 2), (order[1], order[-2], 1)][: len(hands) // 2]:
        down = tuple(give(top, sorted(hands[top]), k))
        assert len(set(down)) == k and all(c in hands[top] for c in down), "must give k own cards"
        up = sorted(hands[bot])[-k:]
        for c in up: hands[bot].remove(c); hands[top].append(c)
        for c in down: hands[top].remove(c); hands[bot].append(c)

def new_round(hands, order=None, give=None):
    """First round (order=None): 3♣ holder leads with 3♣. Later: exchange, then Slave leads."""
    if order is None:
        return Game(hands, leader=next(i for i, h in enumerate(hands) if 0 in h), must_lead_3c=True)
    exchange(hands, order, give)
    return Game(hands, leader=order[-1], king=order[0])

def score(orders):
    """orders: list of per-round finish orders (King..Slave). Returns total points per seat."""
    totals = [0] * len(orders[0])
    for order in orders:
        for place, seat in enumerate(order): totals[seat] += POINTS[place]
    return totals

def standings(orders):
    """Final ranking, best first: by total points; ties -> the one who finished later in the last round."""
    totals, last = score(orders), orders[-1]
    return sorted(range(len(totals)), key=lambda s: (-totals[s], -last.index(s)))


# ---------------- terminal hot-seat play (you control every seat) ----------------

def ask(prompt, check):
    while True:
        try: return check(input(prompt))
        except ValueError as e: print("  ", e)

def cli():
    rng, order, orders = random.Random(), None, []
    for r in range(ROUNDS_PER_MATCH):
        print(f"\n===== Round {r + 1} of {ROUNDS_PER_MATCH} =====")
        def give(seat, hand, k):
            print(f"\nSeat {seat} ({TITLES[order.index(seat)]}) hand: {show(hand)}")
            def chk(t):
                cs = parse(t)
                if len(cs) != k or not set(cs) <= set(hand): raise ValueError(f"pick {k} cards from your hand")
                return cs
            return ask(f"Pick {k} card(s) to trade away (you won't see what you get first): ", chk)
        g = new_round(deal(N_PLAYERS, rng), order, give)
        fallen_seen = set()
        while not g.over():
            s = g.turn
            print(f"\nTable: {show(g.trick) if g.trick else '(empty - you lead)'}"
                  f"   cards left: {[len(h) for h in g.hands]}   passed: {sorted(g.passed)}"
                  f"   direction: {'counter-clockwise' if g.dir < 0 else 'clockwise'}")
            print(f"Seat {s} hand: {show(g.hands[s])}")
            def chk(t):
                m = () if t.strip().lower() in ("p", "pass") else parse(t)
                if m not in g.legal(): raise ValueError(f"illegal. legal: {', '.join(show(x) for x in g.legal())}")
                return m
            g.step(ask("Play (e.g. '7h 7s', or 'p' to pass): ", chk))
            if g.fallen and g.fallen[0] not in fallen_seen:
                fallen_seen.add(g.fallen[0]); print(f"\n!! Seat {g.fallen[0]} (King) did not win first -> Slave")
        order = g.finished
        orders.append(order)
        print("\nRound over: " + ", ".join(f"seat {s} = {TITLES[i]}" for i, s in enumerate(order)))
    totals = score(orders)
    print("\nFinal standing: " + ", ".join(f"#{i + 1} seat {s} ({totals[s]:+d})" for i, s in enumerate(standings(orders))))

if __name__ == "__main__":
    cli()
