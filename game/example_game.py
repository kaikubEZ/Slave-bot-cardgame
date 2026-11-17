"""Print a fully narrated example match that triggers every rule. Run: python3 example_game.py [seed]
Moves are random legal moves; the script searches seeds until one match uses every rule."""
import random, sys
from slave import new_round, deal, show, rank, score, standings, TITLES, ROUNDS_PER_MATCH, N_PLAYERS

SEAT = "ABCD"
RULES = {
    "3c": "first lead includes 3♣", "pair": "pair played", "triple": "triple played",
    "suit": "same rank beaten by higher suit", "lockout": "passed player skipped until card round ends",
    "beaten": "winner's last card beaten -> direction stays", "flip": "winner's last card unbeaten -> direction flips",
    "fall": "King not first -> Slave immediately", "exchange": "exchange before game rounds 2-3",
    "tie": "tied total broken by later finish in last round",
    "pairsuit": "same-rank pair beaten by higher top suit", "over3": "triple overrides a single",
    "over4": "quad overrides a pair", "triple2": "higher triple beats triple after override",
}

def play(seed):
    rng, log, used = random.Random(seed), [], set()
    say = log.append
    order, orders = None, []
    for r in range(ROUNDS_PER_MATCH):
        say(f"\n================ GAME ROUND {r + 1} ================")
        hands = deal(N_PLAYERS, rng)
        def give(seat, hand, k):
            cs = rng.sample(hand, k)
            say(f"  {SEAT[seat]} ({TITLES[order.index(seat)]}) picks {show(cs)} to trade (blind)")
            return cs
        if order:
            used.add("exchange")
            king, queen, people, slave = order
            say(f"Exchange: Slave {SEAT[slave]} must give 2 best {show(sorted(hands[slave])[-2:])} to King {SEAT[king]}; "
                f"People {SEAT[people]} must give best {show(sorted(hands[people])[-1:])} to Queen {SEAT[queen]}")
        g = new_round(hands, order, give)
        for s in range(N_PLAYERS): say(f"  {SEAT[s]} hand: {show(g.hands[s])}")
        say(f"Leader: {SEAT[g.turn]} ({'holds 3♣' if order is None else 'Slave'}), direction counter-clockwise"
            + (f", reigning King = {SEAT[g.king]}" if g.king is not None else ""))
        cr, over_trick = 1, False
        say(f"-- card round {cr} --")
        while not g.over():
            s, top, owner, out_before, dir_before = g.turn, g.trick, g.trick_owner, g.out(), g.dir
            passed_before = set(g.passed)
            plays = [m for m in g.legal() if m]
            move = rng.choice(g.legal()) if rng.random() < 0.8 or not top else ()
            notes = []
            if g.must_lead_3c: used.add("3c"); notes.append("must include 3♣")
            if len(move) == 2: used.add("pair")
            if len(move) == 3: used.add("triple")
            if move and top and len(move) > len(top):
                used.add("over3" if len(move) == 3 else "over4")
                notes.append(f"OVERRIDE: {len(move)} cards beat {len(top)}")
            if move and top and len(move) == len(top) == 2 and rank(move[0]) == rank(top[0]): used.add("pairsuit")
            if move and top and len(move) == len(top) == 3 and over_trick: used.add("triple2")
            if move and top and len(move) > len(top): over_trick = True
            if not top: over_trick = False
            if move and top and rank(move[0]) == rank(top[0]):
                used.add("suit"); notes.append(f"same rank, {show(move)} > {show(top)} by suit")
            if move and owner in out_before: used.add("beaten"); notes.append("beats the card of a player who is out")
            if not move and plays: notes.append("chooses to pass")
            g.step(move)
            # skipped players this turn = passed players between s and the next turn
            if g.trick and passed_before - out_before and g.turn != s:
                step_seats = [(s + dir_before * i) % N_PLAYERS for i in range(1, N_PLAYERS)]
                skipped = [p for p in step_seats[:step_seats.index(g.turn)] if p in passed_before and p not in g.out()]
                if skipped: used.add("lockout"); notes.append(f"skips {','.join(SEAT[p] for p in skipped)} (already passed)")
            if s in g.finished[:len(out_before) + 1] and s not in out_before:
                notes.append(f"OUT -> {TITLES[g.finished.index(s)]}")
            if len(g.fallen) and g.fallen[0] not in out_before:
                used.add("fall"); notes.append(f"King {SEAT[g.fallen[0]]} did not win first -> Slave now")
            say(f"  {SEAT[s]}: {show(move):12s}" + (f"  [{'; '.join(notes)}]" if notes else ""))
            if not g.over() and not g.trick and (move or top):
                why = ""
                if g.dir != dir_before:
                    used.add("flip"); why = f" (winner's card unbeaten: DIRECTION FLIPS to {'clockwise' if g.dir > 0 else 'counter-clockwise'})"
                cr += 1
                say(f"-- card round {cr}: {SEAT[g.turn]} leads{why} --")
        order = g.finished
        orders.append(order)
        say("Result: " + ", ".join(f"{TITLES[i]} {SEAT[s]}" for i, s in enumerate(order)))
        say("Points so far: " + ", ".join(f"{SEAT[s]} {t:+d}" for s, t in enumerate(score(orders))))
    totals = score(orders)
    if len(set(totals)) < N_PLAYERS: used.add("tie")
    say("\n================ FINAL ================")
    say("Points per game round (K+2 Q+1 P-1 S-2): " + " | ".join(
        ", ".join(f"{SEAT[s]} {TITLES[i]}" for i, s in enumerate(o)) for o in orders))
    for i, s in enumerate(standings(orders)):
        say(f"  #{i + 1} {SEAT[s]}  {totals[s]:+d}  (finished #{orders[-1].index(s) + 1} in last game round)")
    return log, used

if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else None
    seeds = [seed] if seed is not None else range(100000)
    for sd in seeds:
        log, used = play(sd)
        if seed is not None or used >= set(RULES): break
    print(f"seed {sd}\n" + "\n".join(log))
    print("\nRules used:\n" + "\n".join(f"  [{'x' if k in used else ' '}] {v}" for k, v in RULES.items()))
