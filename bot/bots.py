"""Bots from strategies.md. Each bot: act(v) -> move, give(v, k) -> k cards. `v` is a View (see run.py).
Bots only use their own rng (self.rng) so every match replays exactly from its seed."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "game"))
from slave import rank

ACE, TWO = 11, 12


def groups(hand):
    g = {}
    for c in hand: g.setdefault(rank(c), []).append(c)
    return g

def plays(v): return [m for m in v.legal if m]

def is_whole(m, g): return len(m) == len(g[rank(m[0])])

def lead_whole(v, key):
    """Pick a whole-group lead by key; fall back to any legal lead (e.g. forced 3♣)."""
    g = groups(v.hand)
    whole = [m for m in v.legal if m and is_whole(m, g)]
    return min(whole or plays(v), key=key)

def weakest_follow(v, allow_override=True):
    k = len(v.trick)
    same = [m for m in plays(v) if len(m) == k]
    if same: return min(same, key=max)
    over = [m for m in plays(v) if len(m) != k]
    return min(over, key=max) if over and allow_override else ()

LOW = lambda m: (rank(m[0]), max(m))
HIGH = lambda m: (-rank(m[0]), -max(m))


class Bot:
    name = "base"
    def __init__(self, rng): self.rng = rng
    def act(self, v): return self.lead(v) if not v.trick else self.follow(v)
    def lead(self, v): return lead_whole(v, LOW)
    def follow(self, v): return weakest_follow(v)
    def give(self, v, k): return sorted(v.hand)[:k]


# ---- 0. baselines ----
class Random(Bot):
    name = "random"
    def act(self, v): return self.rng.choice(v.legal)
    def give(self, v, k): return self.rng.sample(sorted(v.hand), k)

class RandomNoPass(Random):
    name = "random_nopass"
    def act(self, v): return self.rng.choice(plays(v)) if plays(v) else ()

class Lowest(Bot):
    name = "lowest"

class Highest(Bot):
    name = "highest"
    def lead(self, v): return lead_whole(v, HIGH)
    def follow(self, v):
        p = plays(v)
        return max(p, key=lambda m: (len(m) != len(v.trick), max(m))) if p else ()

class Passer(Bot):
    name = "passer"
    def follow(self, v): return ()


# ---- 1. hand shape ----
class PairKeeper(Bot):
    name = "pair_keeper"
    def follow(self, v):
        if len(v.hand) <= 4: return weakest_follow(v)
        g = groups(v.hand)
        keep = [m for m in plays(v) if is_whole(m, g)]
        return weakest_follow(v._replace(legal=keep + [()]))

class Shedder(Bot):
    name = "shedder"
    def lead(self, v): return lead_whole(v, lambda m: (-len(m), rank(m[0])))

class SingleFirst(Bot):
    name = "single_first"
    def lead(self, v): return lead_whole(v, lambda m: (len(m) != 1, rank(m[0])))


# ---- 2. power cards ----
class Saver(Bot):
    name = "saver"
    def _ok(self, v, m): return len(v.hand) <= 4 or rank(m[0]) < ACE
    def lead(self, v):
        ok = [m for m in v.legal if self._ok(v, m)]
        return lead_whole(v._replace(legal=ok), LOW) if ok else lead_whole(v, LOW)
    def follow(self, v):
        return weakest_follow(v._replace(legal=[m for m in v.legal if not m or self._ok(v, m)]))

class Dumper(Bot):
    name = "dumper"
    def follow(self, v):
        same = [m for m in plays(v) if len(m) == len(v.trick)]
        return max(same, key=max) if same else weakest_follow(v)

class OverrideEager(Bot):
    name = "override_eager"
    def follow(self, v):
        over = [m for m in plays(v) if len(m) != len(v.trick)]
        return min(over, key=max) if over else weakest_follow(v)

class OverrideNever(Bot):
    name = "override_never"
    def follow(self, v): return weakest_follow(v, allow_override=False)

class LowThenPower(Bot):
    """Kai's bet: low cards only; 2s, Aces, triples, quads (incl. cards of a 3+/4 group) wait until hand <= 5."""
    name = "low_then_power"
    def _cheap(self, v, m, g):
        return rank(m[0]) < ACE and len(m) < 3 and len(g[rank(m[0])]) < 3
    def _filter(self, v):
        if len(v.hand) <= 5: return v
        g = groups(v.hand)
        return v._replace(legal=[m for m in v.legal if not m or self._cheap(v, m, g)])
    def lead(self, v):
        f = self._filter(v)
        return lead_whole(f, LOW) if plays(f) else lead_whole(v, LOW)   # all power: must lead something
    def follow(self, v): return weakest_follow(self._filter(v))


# ---- 3. card counting ----
class Counter(Bot):
    """Claude's bet: plays like lowest, but when everything left is boss sets + at most one group,
    plays a boss to keep the lead and go out."""
    name = "counter"
    def _unseen(self, v):
        seen = set(v.hand) | {c for _, m in v.history for c in m}
        return [c for c in range(52) if c not in seen]
    def _is_boss(self, m, by_rank):
        k, top = len(m), max(m)
        for r, u in by_rank.items():
            if len(u) >= k and max(u) > top: return False          # higher same-size set possible
            if k == 1 and len(u) >= 3: return False                # triple override possible
            if k == 2 and len(u) == 4: return False                # quad override possible
        return True
    def _plan_ok(self, hand, by_rank):
        """True if hand = boss groups + at most one other group."""
        g = groups(hand)
        return sum(not self._is_boss(cs, by_rank) for cs in g.values()) <= 1
    def lead(self, v):
        by_rank = groups(self._unseen(v))
        g = groups(v.hand)
        boss = [cs for cs in g.values() if self._is_boss(cs, by_rank)]
        if boss and self._plan_ok(v.hand, by_rank) and len(boss) < len(g):
            m = tuple(min(boss, key=lambda cs: rank(cs[0])))
            if m in v.legal: return m
        return lead_whole(v, LOW)
    def follow(self, v):
        by_rank = groups(self._unseen(v))
        for m in sorted(plays(v), key=max):
            if self._is_boss(m, by_rank):
                rest = [c for c in v.hand if c not in m]
                if not rest or self._plan_ok(rest, by_rank): return m
        return weakest_follow(v)


# ---- 4. opponents ----
class Blocker(Bot):
    name = "blocker"
    def _danger(self, v):
        return any(0 < v.counts[p] <= 2 for p in range(4) if p != v.seat and p not in v.out)
    def lead(self, v):
        if self._danger(v): return lead_whole(v, lambda m: (len(m) == 1, rank(m[0])))
        return super().lead(v)
    def follow(self, v): return Highest.follow(self, v) if self._danger(v) else super().follow(v)


# ---- 5. match / title ----
class KingRacer(Bot):
    name = "king_racer"
    def lead(self, v): return Highest.lead(self, v) if v.king == v.seat else super().lead(v)
    def follow(self, v): return Highest.follow(self, v) if v.king == v.seat else super().follow(v)


# ---- 6. trade ----
class GiveLonely(Bot):
    name = "give_lonely"
    def give(self, v, k):
        g = groups(v.hand)
        lonely = sorted(c for c in v.hand if len(g[rank(c)]) == 1)
        return (lonely + [c for c in sorted(v.hand) if c not in lonely])[:k]

class GiveRandom(Bot):
    name = "give_random"
    def give(self, v, k): return self.rng.sample(sorted(v.hand), k)


ALL = [Random, RandomNoPass, Lowest, Highest, Passer, PairKeeper, Shedder, SingleFirst, Saver, Dumper,
       OverrideEager, OverrideNever, LowThenPower, Counter, Blocker, KingRacer, GiveLonely, GiveRandom]
BY_NAME = {b.name: b for b in ALL}
