"""Search bots (not in the pool): guess the hidden cards, play each legal move out, keep the best average.
Experimental bots are registered in BY_NAME and SEARCH at import; bots.ALL is untouched."""
import itertools, math, os, sys
from collections import namedtuple
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "game")); sys.path.insert(0, HERE)
from slave import Game, POINTS, ROUNDS_PER_MATCH, OVERRIDE
from bots import BY_NAME, GiveLonely, Lowest, Counter

SEARCH = {}

def register(cls): SEARCH[cls.name] = BY_NAME[cls.name] = cls; return cls

def variant(base, name, **attrs): return register(type(name, (base,), {"name": name, **attrs}))


class Sim(Game):
    """Game that builds the legal-move list once per turn (step() asks for it again to validate) and counts steps."""
    _legal = None; steps = 0
    def __init__(self, *a, **k): Game.__init__(self, *a, **k); self.played = set()   # every card played this round
    def legal(self):
        if self._legal is None: self._legal = Game.legal(self)
        return self._legal
    def step(self, move):
        Game.step(self, move); self._legal = None; self.steps += 1; self.played.update(move)


def rebuild(v, on_step=None):
    """Replay this round's public moves to get the engine state (trick, passes, finish order, direction).
    Hidden cards don't affect that state, so opponents hold placeholders: what they played + any unseen cards."""
    played = [[] for _ in range(4)]
    for s, m in v.history: played[s] += m
    spare = iter(sorted(set(range(52)) - set(v.hand) - {c for p in played for c in p}))
    hands = [played[p] + (v.hand if p == v.seat else [next(spare) for _ in range(v.counts[p])]) for p in range(4)]
    g = Sim(hands, v.history[0][0] if v.history else v.seat, must_lead_3c=v.round == 0, king=v.king)
    for s, m in v.history:
        assert g.turn == s, "rebuild out of sync"
        if on_step: on_step(g, s, m)
        g.step(m)
    g.steps = 0
    return g

def with_hands(base, hands):
    g = Sim.__new__(Sim); g.__dict__.update(base.__dict__)
    g.hands, g.history, g._legal, g.steps, g.played = hands, [], None, 0, set(base.played)
    g.passed, g.finished, g.fallen, g.trick_plays = set(base.passed), base.finished[:], base.fallen[:], base.trick_plays[:]
    return g

def unseen(v):
    seen = set(v.hand) | {c for _, m in v.history for c in m}
    return [c for c in range(52) if c not in seen]


def guess(v, rng, unseen):
    """Deal the unseen cards to the opponents: right counts, consistent with what I know from the trade."""
    hands = {p: [] for p in range(4) if p != v.seat}
    pool, low, bound = set(unseen), None, None
    if v.titles:                                    # rounds 2-3: King<->Slave, Queen<->People
        i = v.titles.index(v.seat); partner = v.titles[3 - i]
        for c in v.gave:                            # what I gave sits in their hand until they play it
            if c in pool: hands[partner].append(c); pool.discard(c)
        if i < 2: low, bound = partner, min(v.got)  # they had to give me their best, so the rest is lower
    pool = list(pool); rng.shuffle(pool)
    if low is not None:
        k = v.counts[low] - len(hands[low])
        pick = [c for c in pool if c < bound][:k]
        if len(pick) == k: hands[low] += pick; pool = [c for c in pool if c not in pick]
    for p in hands:
        k = v.counts[p] - len(hands[p]); hands[p] += pool[:k]; del pool[:k]
    return hands


def value(order, v):
    """Round points in rounds 1-2; in the last round, the final match rank itself (0 = 1st .. -3 = 4th)."""
    if v.round < ROUNDS_PER_MATCH - 1: return POINTS[order.index(v.seat)]
    total = [v.points[s] + POINTS[order.index(s)] for s in range(4)]
    return -sorted(range(4), key=lambda s: (-total[s], -order.index(s))).index(v.seat)

PV = namedtuple("PV", "hand trick legal")
LOWEST = Lowest(None)


class MC(GiveLonely):
    """Guess the hidden cards many times; in each guess play every legal move out with `policy` for all 4
    players; pick the move with the best average result. Budget is simulated moves, not seconds. Trades like give_lonely."""
    name = "mc"
    work = 20000                                    # simulated moves per decision (Task 8 calibrates)

    def sample(self, v, unseen): return guess(v, self.rng, unseen)
    def policy(self, g): return LOWEST.act(PV(g.hands[g.turn], g.trick, g.legal()))
    def playout(self, g, v):
        while not g.over(): g.step(self.policy(g))
        return value(g.finished, v)

    def prepare(self, v): pass                      # per-decision setup hook for subclasses

    def evaluate(self, v):
        self.prepare(v)
        base, un = rebuild(v), unseen(v)
        total, n, steps = dict.fromkeys(v.legal, 0.0), 0, 0
        while n == 0 or steps < self.work:
            self.before = steps                     # steps spent before the last world (for the budget test)
            world = self.sample(v, un); world[v.seat] = v.hand
            hands = [sorted(world[p]) for p in range(4)]
            for m in v.legal:                       # same guessed cards for every move: fair comparison
                g = with_hands(base, [h[:] for h in hands])
                g.step(m); total[m] += self.playout(g, v); steps += g.steps
            n += 1
        self.spent = steps
        return {m: t / n for m, t in total.items()}, n

    def act(self, v):
        if len(v.legal) == 1: return v.legal[0]
        ev, _ = self.evaluate(v)
        return max(v.legal, key=ev.get)

register(MC)


def passes(v):
    """[(seat, table, index in v.history)] for every pass this round."""
    out, i = [], [0]
    def see(g, s, m):
        if not m: out.append((s, g.trick, i[0]))
        i[0] += 1
    rebuild(v, see)
    return out

def can_beat(hand, table):
    """Does `hand` hold a set legal against `table` under the engine's rules?"""
    k = len(table); by = {}
    for c in hand: by.setdefault(c // 4, []).append(c)
    return any((len(cs) >= k and max(cs) > max(table)) or (len(cs) >= OVERRIDE.get(k, 99)) for cs in by.values())

def voluntary_passes(v, hands, ps=None):
    """Passes that a guessed world says were voluntary (the passer held a legal set; hands = guessed current hands)."""
    n = 0
    for s, table, i in (passes(v) if ps is None else ps):
        if s == v.seat: continue
        then = list(hands[s]) + [c for t, m in v.history[i + 1:] if t == s for c in m]
        n += can_beat(then, table)
    return n


class MCRead(MC):
    """Like MC, but worlds where opponents passed with a playable set are rarer: P(world) ~ q^(voluntary passes).
    Rejection sampling, at most 50 tries, then the best-weight guess seen."""
    name = "mc_read"
    q = 0.3

    def prepare(self, v): self._ps = passes(v)      # constant per decision, so replay once

    def sample(self, v, unseen):
        best, bw, ps = None, -1, self._ps
        for _ in range(50):
            w = guess(v, self.rng, unseen); wt = self.q ** voluntary_passes(v, w, ps)
            if wt >= 1 or self.rng.random() < wt: return w
            if wt > bw: best, bw = w, wt
        return best

register(MCRead)
for _q in (0.1, 0.3, 0.6): variant(MCRead, f"mc_read_q{_q}", q=_q)


CV = namedtuple("CV", "hand trick legal history")
COUNTER = Counter(None)

class MCCounter(MC):
    """Like MC, but every player in a playout plays bots.Counter's rule (unseen = 52 - own hand - cards played)."""
    name = "mc_counter"
    def policy(self, g):
        h = g.hands[g.turn]
        return COUNTER.act(CV(h, g.trick, g.legal(), [(0, tuple(g.played))]))

register(MCCounter)


class ISMCTS(MC):
    """Single-observer information-set MCTS: each iteration samples one world, then descends one shared tree
    (UCB1 with availability counts) where every node's move is scored for the player who made it; leaves play out
    with `policy`. Budget as MC (every step counts). Score per root move = its share of the visits."""
    name = "ismcts"
    c = 0.7

    def evaluate(self, v):
        self.prepare(v)
        base, un = rebuild(v), unseen(v)
        lo, hi = (-3, 0) if v.round == ROUNDS_PER_MATCH - 1 else (min(POINTS), max(POINTS))
        tree, n, steps = {}, 0, 0                   # full move sequence from the root -> [visits, total value, availability]
        while n == 0 or steps < self.work:
            self.before = steps
            world = self.sample(v, un); world[v.seat] = v.hand
            g = with_hands(base, [sorted(world[p]) for p in range(4)])
            path, edges = (), []
            while not g.over():
                legal = g.legal(); new = [m for m in legal if path + (m,) not in tree]
                for m in legal:
                    if path + (m,) in tree: tree[path + (m,)][2] += 1
                if new: m = self.rng.choice(new); tree[path + (m,)] = [0, 0.0, 1]
                else: m = max(legal, key=lambda m: self.ucb(tree[path + (m,)]))
                path += (m,); edges.append((path, g.turn)); g.step(m)
                if new: break
            while not g.over(): g.step(self.policy(g))
            for key, s in edges:
                e = tree[key]; e[0] += 1; e[1] += (value(g.finished, v._replace(seat=s)) - lo) / (hi - lo)
            n += 1; steps += g.steps
        self.spent = steps
        vis = {m: tree.get((m,), [0])[0] for m in v.legal}      # a root move the budget never reached has 0 visits
        return {m: k / sum(vis.values()) for m, k in vis.items()}, n

    def ucb(self, e): return e[1] / e[0] + self.c * math.sqrt(math.log(e[2]) / e[0])

register(ISMCTS)


class MCEnd(MC):
    """MC whose playouts solve my own endgame exactly: once I hold <= K cards, at each of my turns try every legal
    move (opponents play `policy`) and keep the best. Child steps are added to the parent's count (budget)."""
    name = "mc_end"
    K = 5

    cap = 3000                                      # steps one world's search may spend; then plain policy play

    room = cap

    def prepare(self, v): self.room = min(self.cap, max(50, self.work // len(v.legal)))   # first world plays every move, so split the budget

    def playout(self, g, v): return self.solve(g, v, self.room)

    def solve(self, g, v, room):
        start = g.steps
        while not g.over():
            if g.turn != v.seat or len(g.hands[v.seat]) > self.K or g.steps - start >= room: g.step(self.policy(g)); continue
            best = None
            for m in g.legal():
                c = with_hands(g, [h[:] for h in g.hands]); c.step(m)
                r = self.solve(c, v, room - (g.steps - start)); g.steps += c.steps
                if best is None or r > best: best = r
            return best
        return value(g.finished, v)

register(MCEnd)


class MCTrade(MC):
    """MC whose trade gift is searched: candidates = k-subsets of my 6 lowest cards; per candidate deal the other 39
    cards at random, apply the engine's exchange, play the round with `policy`, average my value."""
    name = "mc_trade"

    def give(self, v, k):
        order, me = v.titles, v.seat
        mine = sorted(v.hand); rest = [c for c in range(52) if c not in mine]
        cands = list(itertools.combinations(mine[:6], k))
        total, n = [0.0] * len(cands), [0] * len(cands)
        for i, cand in enumerate(cands):
            steps = 0
            while n[i] == 0 or steps < self.work / len(cands):
                self.rng.shuffle(rest)
                hands = {s: mine[:] if s == me else None for s in range(4)}
                for j, s in enumerate(x for x in range(4) if x != me): hands[s] = sorted(rest[13 * j: 13 * j + 13])
                for top, bot, kk in [(order[0], order[-1], 2), (order[1], order[-2], 1)]:
                    # assumption: a bot top other than me gives its lowest kk cards (stand-in for its own give rule)
                    down = cand if top == me else tuple(hands[top][:kk])
                    up = hands[bot][-kk:]
                    for c in up: hands[bot].remove(c); hands[top].append(c)
                    for c in down: hands[top].remove(c); hands[bot].append(c)
                g = Sim([sorted(hands[s]) for s in range(4)], order[-1], must_lead_3c=False, king=order[0])
                total[i] += self.playout(g, v); n[i] += 1; steps += g.steps
        return max(zip(cands, (t / m for t, m in zip(total, n))), key=lambda x: x[1])[0]

register(MCTrade)
