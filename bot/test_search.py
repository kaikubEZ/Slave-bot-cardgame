"""Run: python3 bot/test_search.py"""
import json, math, os, statistics, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run, search
from search import MC, MCRead, MCCounter, MCEnd, MCTrade, ISMCTS, Sim, rebuild, guess, unseen, voluntary_passes
from bots import BY_NAME
import tourney

RIVALS = ["counter", "give_lonely", "pair_keeper"]
FIELDS = "turn trick trick_owner passed finished fallen trick_plays dir king must_lead_3c".split()

def checked(check, seeds=40):
    """Play matches with a bot that runs check(bot, v, real_game) at every decision."""
    real, orig = {}, run.new_round
    def spy(*a, **k): real["g"] = orig(*a, **k); return real["g"]
    class Checked(MC):
        work = 1
        def act(self, v): check(self, v, real["g"]); return super().act(v)
    BY_NAME["checked"] = Checked; run.new_round = spy
    try:
        for seed in range(seeds):
            names = RIVALS[:]; names.insert(seed % 4, "checked"); run.play_match(names, seed)
    finally: run.new_round = orig


class T(unittest.TestCase):
    def test_rebuild_matches_engine(self):
        def check(bot, v, g):
            b = rebuild(v)
            for f in FIELDS: self.assertEqual(getattr(b, f), getattr(g, f), f)
        checked(check)

    def test_guess_consistent(self):
        def check(bot, v, g):
            un = sorted(unseen(v)); w = guess(v, bot.rng, un)
            self.assertEqual(sorted(c for h in w.values() for c in h), un)
            for p in w: self.assertEqual(len(w[p]), v.counts[p])
            if v.king in v.out and v.king != v.seat: self.assertEqual(len(w[v.king]), v.counts[v.king])
            if v.titles:
                i = v.titles.index(v.seat); partner = v.titles[3 - i]
                for hand in (g.hands[partner], w[partner]):
                    self.assertTrue(all(c in hand for c in v.gave if c in un))
                    if i < 2: self.assertTrue(all(c < min(v.got) for c in hand if c not in v.gave))
        checked(check)

    def test_forced_move_no_rng(self):
        bot = MC(__import__("random").Random(1)); st = bot.rng.getstate()
        v = run.View(*[None] * 16)._replace(legal=[()])
        self.assertEqual(bot.act(v), ()); self.assertEqual(bot.rng.getstate(), st)

    def test_replay_identical(self):
        old, MC.work = MC.work, 2000
        try:
            names = ["mc"] + RIVALS
            self.assertEqual(run.play_match(names, 7), run.play_match(names, 7))
        finally: MC.work = old

    def test_work_budget(self):
        used = []
        class Spy(MC):
            work = 2000
            def evaluate(self, v): r = super().evaluate(v); used.append((self.before, self.spent)); return r
        BY_NAME["spy"] = Spy
        run.play_match(["spy"] + RIVALS, 3)
        self.assertTrue(used)
        for before, spent in used: self.assertLess(before, 2000); self.assertGreaterEqual(spent, 2000)  # last world finished, then stop

class Read(unittest.TestCase):
    def view(self):  # seat 0 (me); seat 3 led 9 of diamonds, seats 2 and 1 passed (play runs 3,2,1,0)
        return run.View(*[None] * 16)._replace(seat=0, round=1, hand=[0, 4, 8], legal=[()], counts=[3, 5, 5, 4],
                                               history=[(3, (25,)), (2, ()), (1, ())], king=0)

    def test_voluntary_pass_count(self):
        v = self.view()   # 9 = rank 6 (cards 24-27); J = rank 8 (32); 7 = rank 4 (16-19)
        hands = {3: [30, 1, 2, 3], 2: [32, 36, 6, 7, 9], 1: [16, 17, 8, 12, 20]}
        self.assertEqual(voluntary_passes(v, hands), 1)     # seat 2 holds a jack, seat 1 only low cards
        hands[2] = [16, 17, 8, 12, 20]
        self.assertEqual(voluntary_passes(v, hands), 0)
        # (a) a card played after the pass counts: seat 2 passes, then (new trick) plays a jack -> first pass voluntary
        v2 = v._replace(history=[(3, (25,)), (2, ()), (1, ()), (0, ()), (3, (12,)), (2, (32,)), (1, ()), (0, ()), (3, ())])
        h2 = {3: [30, 1, 2, 5], 2: [16, 17, 8, 20, 21], 1: [16, 17, 8, 20, 22]}
        self.assertEqual(voluntary_passes(v2, h2), 1)
        # (b) override: facing a single, a triple of a lower rank (3s) is a legal beat
        hands[2] = [0, 1, 2, 8, 12]
        self.assertEqual(voluntary_passes(v, hands), 1)

    def test_read_q1_equals_mc_distribution(self):
        v = self.view(); un = unseen(v)
        a, b = MC(__import__("random").Random(5)), MCRead(__import__("random").Random(5)); b.q = 1; b._ps = search.passes(v)
        self.assertEqual(a.sample(v, un), b.sample(v, un))

    def test_read_replays(self):
        old, MC.work = MC.work, 2000
        try:
            names = ["mc_read_q0.3"] + RIVALS
            self.assertEqual(run.play_match(names, 7), run.play_match(names, 7))
        finally: MC.work = old


class CounterPolicy(unittest.TestCase):
    def test_counter_policy_matches_bot(self):
        import random
        from bots import Counter
        rng, bot, n = random.Random(3), MCCounter(None), 0
        while n < 200:
            deck = list(range(52)); rng.shuffle(deck)
            hands = [sorted(deck[i::4]) for i in range(4)]
            g = Sim(hands, next(p for p in range(4) if 0 in hands[p]), must_lead_3c=True, king=None)
            for _ in range(rng.randrange(40)):
                if g.over(): break
                v = search.CV(g.hands[g.turn], g.trick, g.legal(), g.history)
                self.assertEqual(bot.policy(g), Counter(None).act(v)); n += 1
                g.step(rng.choice(g.legal()))

class IS(unittest.TestCase):
    def test_ismcts_legal_and_replays(self):
        old, ISMCTS.work = ISMCTS.work, 2000
        try:
            names = ["ismcts"] + RIVALS
            self.assertEqual(run.play_match(names, 7), run.play_match(names, 7))   # play_match rejects illegal moves
        finally: ISMCTS.work = old

    def test_ismcts_finds_forced_win(self):
        # last round, I lead {3c, 2s} against three 1-card hands: 3c lets the next player out first, 2s can't be beaten
        v = run.View(*[None] * 16)._replace(seat=0, round=2, hand=[0, 51], legal=[(0,), (51,)], counts=[2, 1, 1, 1],
                                            history=[], points=[0, 0, 0, 0])
        bot = ISMCTS(__import__("random").Random(1)); bot.work = 2000
        self.assertEqual(bot.act(v), (51,))

    def test_ismcts_tiny_budget_scores_all_moves(self):
        hand = [0, 1, 4, 8, 12, 16]                 # leading: 6 singles + a pair = 7+ legal moves
        legal = [(c,) for c in hand] + [(0, 1)]
        v = run.View(*[None] * 16)._replace(seat=0, round=0, hand=hand, legal=legal, counts=[6, 6, 6, 6],
                                            history=[], points=[0, 0, 0, 0])
        bot = ISMCTS(__import__("random").Random(1)); bot.work = 1
        ev, _ = bot.evaluate(v)
        self.assertEqual(set(ev), set(legal)); self.assertIn(bot.act(v), legal)

    def end_view(self, hand, opp):
        legal = Sim([hand, *opp.values()], 0, must_lead_3c=False, king=None).legal()
        return run.View(*[None] * 16)._replace(seat=0, round=1, hand=hand, legal=legal,
                                               counts=[len(hand)] + [len(h) for h in opp.values()], history=[], points=[0] * 4)

    def fixed(self, cls, opp):
        class Fixed(cls):
            def sample(self, v, un): return {p: h[:] for p, h in opp.items()}
        bot = Fixed(__import__("random").Random(1)); bot.work = 1
        return bot

    def test_end_orders_last_groups(self):
        # found by search: lowest-playouts value every opening at -1 (last place); exhaustive play wins with 23 or 40
        opp = {1: [4, 50], 2: [12, 13], 3: [20, 49]}; v = self.end_view([6, 23, 40], opp)
        mc, _ = self.fixed(MC, opp).evaluate(v); end, _ = self.fixed(MCEnd, opp).evaluate(v)
        self.assertEqual(mc[(23,)], -1.0); self.assertEqual(end[(23,)], 1.0); self.assertEqual(end[(6,)], -1.0)
        self.assertEqual(self.fixed(MCEnd, opp).act(v), (23,))

    def test_end_switches_mid_playout(self):
        # 7 cards (> K) at the start: the search must still engage once my hand shrinks to K
        opp = {1: [4, 50], 2: [12, 13], 3: [20, 49]}; hand = [6, 23, 40, 1, 2, 3, 5]
        g = Sim([sorted(hand), *opp.values()], 0, must_lead_3c=False, king=None)
        v = self.end_view(hand, opp)
        self.assertGreaterEqual(self.fixed(MCEnd, opp).playout(g, v), self.fixed(MC, opp).playout(Sim([sorted(hand), *opp.values()], 0, must_lead_3c=False, king=None), v))

    def test_end_cap_bounds_work(self):
        hand = [0, 1, 4, 5, 8]                      # three groups; 5 cards -> many branches
        opp = {p: [20 + p, 24 + p, 28 + p, 32 + p, 36 + p] for p in (1, 2, 3)}
        v = self.end_view(hand, opp); bot = self.fixed(MCEnd, opp); bot.work = 2000
        bot.evaluate(v)
        self.assertLess(bot.spent, 2000 + (bot.cap + 300) * len(v.legal))   # last world: <= cap + one rollout tail per move

    def test_end_room_bounds_first_world(self):
        hand = [0, 1, 4, 5, 8]; opp = {p: [20 + p, 24 + p, 28 + p, 32 + p, 36 + p] for p in (1, 2, 3)}
        v = self.end_view(hand, opp); bot = self.fixed(MCEnd, opp); bot.work = 200
        bot.evaluate(v)
        self.assertLess(bot.spent, 200 + (bot.room + 300) * len(v.legal))   # was thousands: cap per playout, not per decision

    def trade_view(self, seat, hand):
        order = [seat, 1, 2, 3] if seat != 1 else [1, 0, 2, 3]
        return run.View(*[None] * 16)._replace(seat=seat, round=1, hand=hand, titles=order, points=[0] * 4)

    def test_trade_returns_own_cards(self):
        hand = sorted(__import__("random").Random(5).sample(range(52), 13)); bot = MCTrade(__import__("random").Random(1)); bot.work = 300
        for k in (1, 2):
            gift = bot.give(self.trade_view(0, hand), k)
            self.assertEqual(len(set(gift)), k); self.assertTrue(set(gift) <= set(hand[:6]))

    def test_trade_replays(self):
        hand = list(range(0, 52, 4)); gifts = []
        for _ in range(2):
            bot = MCTrade(__import__("random").Random(7)); bot.work = 300; gifts.append(bot.give(self.trade_view(0, hand), 2))
        self.assertEqual(gifts[0], gifts[1])


class Tourney(unittest.TestCase):
    def test_gap_uses_shared_complete_deals(self):
        a = {(d, s): 2 for d in (1, 2, 3) for s in range(4)}
        b = {(d, s): 3 for d in (2, 3, 4) for s in range(4)}; b.update({(5, s): 1 for s in range(3)})
        self.assertEqual(tourney.gap(a, b)[0], 2)

    def test_gap_math(self):
        a = {(d, s): p for d, p in enumerate((1, 2, 1.5)) for s in range(4)}
        b = {(d, s): 2 for d in range(3) for s in range(4)}
        n, m, ci = tourney.gap(a, b)[:3]
        self.assertEqual(n, 3); self.assertAlmostEqual(m, -0.5)
        self.assertAlmostEqual(ci, 1.96 * statistics.stdev([-1, 0, -0.5]) / math.sqrt(3))

    def test_fit_scales_down_for_slow_max(self):
        calls = []
        def measure(w): calls.append(w); return w / 1000, w / 500          # mean 1 ms/1000 work, max twice that
        work, mean, mx = tourney.fit(measure, 1000, 0.5)
        self.assertEqual(work, 441); self.assertLess(mx, 0.9); self.assertEqual(calls, [1000, 500, 441])

    def test_run_appends_only_missing(self):
        old, MC.work, tourney.LOG = MC.work, 500, tempfile.mkdtemp()
        try:
            tourney.run_bot("mc", "rule", "screen", 2, 2); tourney.run_bot("mc", "rule", "screen", 3, 2)
            lines = open(tourney.path("screen", "rule", "mc")).read().split("\n")[:-1]
            self.assertEqual(len(lines), 12); self.assertEqual(len({(r["seed"], r["seat"]) for r in map(json.loads, lines)}), 12)
        finally: MC.work = old

if __name__ == "__main__": unittest.main()
