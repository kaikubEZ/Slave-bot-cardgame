"""Epoch runner (bot.md section 5).

  python3 bot/run.py --until 07:15            # run experiments until that time, report in log/<run>/report.md
  python3 bot/run.py --epochs 20              # fixed number of epochs per experiment
  python3 bot/run.py --replay bet 1000004203  # print the full game of one match (any match replays from its seed)

Experiments (interleaved):
  pool : every match = 4 different bots drawn at random from the whole pool, random seats.
  bet  : low_then_power vs counter + 2 random fillers, random seats.
"""
import argparse, datetime as dt, gzip, json, math, os, random, sys, time
from collections import namedtuple
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "game"))
sys.path.insert(0, HERE)
from slave import deal, new_round, show, score, standings, name, ROUNDS_PER_MATCH, TITLES
from bots import ALL, BY_NAME

MATCHES_PER_EPOCH = 100
TIME_LIMIT = 1.0
EXPERIMENTS = {"pool": 0, "bet": 1_000_000_000}   # seed base per experiment
BET = ("low_then_power", "counter")

View = namedtuple("View", "seat round hand trick legal counts history past passed out king dir titles points gave got")


def lineup_for(exp, seed):
    rng = random.Random(seed)
    if exp == "pool":
        return [b.name for b in rng.sample(ALL, 4)]
    names = list(BET) + rng.sample([b.name for b in ALL if b.name not in BET], 2)
    rng.shuffle(names)
    return names


def timed(fn, *a):
    t = time.perf_counter(); r = fn(*a); d = time.perf_counter() - t
    if d > TIME_LIMIT: raise RuntimeError(f"{fn.__qualname__} took {d:.2f}s > {TIME_LIMIT}s")
    return r


def play_match(names, seed, keep_history=False):
    rng = random.Random(seed)
    bots = [BY_NAME[n](random.Random(seed * 10 + i)) for i, n in enumerate(names)]
    order, orders, past, rounds = None, [], [], []
    for r in range(ROUNDS_PER_MATCH):
        hands = deal(4, rng)
        know = {}                                   # seat -> (gave, got)
        if order:
            best = {order[-1]: sorted(hands[order[-1]])[-2:], order[-2]: sorted(hands[order[-2]])[-1:]}
            partner = {order[0]: order[-1], order[1]: order[-2]}
            def give(seat, hand, k):
                v = View(seat, r, hand, (), [], [len(h) for h in hands], [], past, set(), set(), order[0], -1,
                         order, score(orders), (), ())
                cs = tuple(sorted(timed(bots[seat].give, v, k)))
                low = partner[seat]
                know[seat], know[low] = (cs, tuple(best[low])), (tuple(best[low]), cs)
                return cs
        else:
            give = None
        g = new_round(hands, order, give)
        start = [h[:] for h in g.hands]
        while not g.over():
            s = g.turn
            gv, gt = know.get(s, ((), ()))
            v = View(s, r, g.hands[s][:], g.trick, g.legal(), [len(h) for h in g.hands], g.history, past,
                     g.passed, g.out(), g.king, g.dir, order, score(orders) if orders else [0] * 4, gv, gt)
            g.step(timed(bots[s].act, v))
        order = g.finished
        orders.append(order)
        past.append(g.history)
        if keep_history:
            rounds.append({"hands": [show(h) for h in start], "exchange": {str(s): [show(a), show(b)] for s, (a, b) in know.items()},
                           "moves": [f"{s}:{show(m)}" for s, m in g.history], "order": order})
    rec = {"seed": seed, "bots": names, "orders": orders, "points": score(orders), "standing": standings(orders)}
    if keep_history: rec["rounds"] = rounds
    return rec


def run_epoch(task):
    exp, epoch, full, logdir = task
    base = EXPERIMENTS[exp] + epoch * MATCHES_PER_EPOCH
    recs = [play_match(lineup_for(exp, s), s, keep_history=full) for s in range(base, base + MATCHES_PER_EPOCH)]
    if full:
        with gzip.open(os.path.join(logdir, "games", f"{exp}_epoch{epoch:06d}.jsonl.gz"), "wt") as f:
            for rec in recs: f.write(json.dumps(rec) + "\n")
    # compact result per match: seed, bots, final place of each seat (1..4)
    return exp, epoch, [(r["seed"], r["bots"], [r["standing"].index(s) + 1 for s in range(4)]) for r in recs]


class Stats:
    def __init__(self):
        self.d = {e: {"epochs": 0, "bots": {}, "h2h": {}} for e in EXPERIMENTS}

    def add(self, exp, matches):
        e = self.d[exp]; e["epochs"] += 1
        per_epoch = {}
        for _, names, places in matches:
            for n, p in zip(names, places):
                b = e["bots"].setdefault(n, {"matches": 0, "places": [0, 0, 0, 0], "epoch_avgs": []})
                b["matches"] += 1; b["places"][p - 1] += 1
                per_epoch.setdefault(n, []).append(p)
            for i in range(4):
                for j in range(4):
                    if i != j:
                        h = e["h2h"].setdefault(names[i], {}).setdefault(names[j], [0, 0])
                        h[0] += places[i] < places[j]; h[1] += 1
        for n, ps in per_epoch.items(): e["bots"][n]["epoch_avgs"].append(sum(ps) / len(ps))

    @staticmethod
    def summary(b):
        n = b["matches"]; avg = sum((i + 1) * c for i, c in enumerate(b["places"])) / n
        xs = b["epoch_avgs"]; k = len(xs); m = sum(xs) / k
        sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (k - 1)) if k > 1 else float("nan")
        return avg, 1.96 * sd / math.sqrt(k) if k > 1 else float("nan")

    def report(self, started, matches_done, rate):
        L = [f"# Bot report", "", f"Started {started:%Y-%m-%d %H:%M}, updated {dt.datetime.now():%H:%M:%S}. "
             f"{matches_done:,} matches played ({rate:,.0f} matches/s).", "",
             "Avg rank: 1 = best, 4 = worst. ± = 95% range across epochs. Win = finished 1st.", ""]
        for exp, e in self.d.items():
            if not e["epochs"]: continue
            L += [f"## Experiment `{exp}` — {e['epochs']:,} epochs", "",
                  "| # | Bot | Avg rank | ± | Win % | 2nd % | 3rd % | 4th % | Matches |", "|---|---|---|---|---|---|---|---|---|"]
            rows = sorted(e["bots"].items(), key=lambda kv: self.summary(kv[1])[0])
            for i, (n, b) in enumerate(rows):
                avg, ci = self.summary(b); P = [100 * c / b["matches"] for c in b["places"]]
                L.append(f"| {i + 1} | `{n}` | {avg:.3f} | {ci:.3f} | {P[0]:.1f} | {P[1]:.1f} | {P[2]:.1f} | {P[3]:.1f} | {b['matches']:,} |")
            if exp == "bet":
                a, c = BET; h = e["h2h"].get(a, {}).get(c, [0, 0])
                sa, sc = (self.summary(e["bots"][x]) for x in BET)
                verdict = ("not settled yet (ranges overlap)" if abs(sa[0] - sc[0]) < sa[1] + sc[1]
                           else f"**{a if sa[0] < sc[0] else c} wins the bet**")
                L += ["", f"**Bet:** `{a}` finished above `{c}` in {100 * h[0] / max(h[1], 1):.1f}% of {h[1]:,} shared tables. "
                      f"Avg rank {sa[0]:.3f} ± {sa[1]:.3f} vs {sc[0]:.3f} ± {sc[1]:.3f} → {verdict}."]
            L += ["", "Head-to-head: % of shared tables where the **row** bot finished above the **column** bot.", ""]
            names = [n for n, _ in rows]
            L.append("| | " + " | ".join(f"`{n}`" for n in names) + " |")
            L.append("|---" * (len(names) + 1) + "|")
            for a in names:
                cells = []
                for c in names:
                    h = e["h2h"].get(a, {}).get(c)
                    cells.append("–" if a == c or not h else f"{100 * h[0] / h[1]:.0f}")
                L.append(f"| `{a}` | " + " | ".join(cells) + " |")
            L.append("")
        return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--until", help="stop time HH:MM (next occurrence)")
    ap.add_argument("--epochs", type=int, help="epochs per experiment")
    ap.add_argument("--workers", type=int, default=max(1, os.cpu_count() - 1))
    ap.add_argument("--full-every", type=int, default=100, help="save full game history every N epochs (first 3 always)")
    ap.add_argument("--replay", nargs=2, metavar=("EXP", "SEED"))
    a = ap.parse_args()

    if a.replay:
        exp, seed = a.replay[0], int(a.replay[1])
        rec = play_match(lineup_for(exp, seed), seed, keep_history=True)
        print(f"seed {seed}: seats 0-3 = {rec['bots']}")
        for r, rd in enumerate(rec["rounds"]):
            print(f"\n=== game round {r + 1} ===")
            for s, h in enumerate(rd["hands"]): print(f"  seat {s} {rec['bots'][s]:15s} {h}")
            for s, (gv, gt) in rd["exchange"].items(): print(f"  exchange seat {s}: gave {gv}, got {gt}")
            for m in rd["moves"]: print("  " + m)
            print("  result: " + ", ".join(f"{TITLES[i]} seat {s}" for i, s in enumerate(rd["order"])))
        print(f"\npoints {rec['points']}, final standing (best first): seats {rec['standing']}")
        return

    stop = None
    if a.until:
        h, m = map(int, a.until.split(":"))
        now = dt.datetime.now(); stop = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if stop <= now: stop += dt.timedelta(days=1)
    started = dt.datetime.now()
    logdir = os.path.join(HERE, "..", "log", f"{started:%Y%m%d_%H%M}")
    os.makedirs(os.path.join(logdir, "games"), exist_ok=True)
    print(f"logging to {os.path.abspath(logdir)}" + (f", stopping at {stop:%H:%M}" if stop else ""), flush=True)

    def tasks():
        ep = 0
        while a.epochs is None or ep < a.epochs:
            for exp in EXPERIMENTS:
                yield exp, ep, ep < 3 or ep % a.full_every == 0, logdir
            ep += 1

    stats, done, last_write, t0 = Stats(), 0, 0, time.time()
    results = gzip.open(os.path.join(logdir, "results.jsonl.gz"), "wt")
    def write_report():
        with open(os.path.join(logdir, "report.md"), "w") as f:
            f.write(stats.report(started, done, done / max(time.time() - t0, 1e-9)))
        with open(os.path.join(logdir, "stats.json"), "w") as f: json.dump(stats.d, f)
    with Pool(a.workers) as pool:
        for exp, epoch, matches in pool.imap_unordered(run_epoch, tasks(), chunksize=1):
            stats.add(exp, matches); done += len(matches)
            results.write(json.dumps({"exp": exp, "epoch": epoch, "matches": matches}) + "\n")
            if time.time() - last_write > 30:
                write_report(); results.flush(); last_write = time.time()
            if stop and dt.datetime.now() >= stop:
                pool.terminate(); break
    results.close()
    write_report()
    print(f"done: {done:,} matches, report at {os.path.abspath(os.path.join(logdir, 'report.md'))}")


if __name__ == "__main__":
    main()
