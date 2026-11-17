"""One test per rule. Run: python3 -m unittest -v"""
import random, unittest
from slave import Game, parse as P, new_round, deal, show, score, standings

def game(*hands, leader=0, first=False, king=None, direction=1):
    """Rule examples run clockwise (seat 0 -> 1 -> 2 -> 3) so turns read top to bottom.
    The official counter-clockwise default is tested in class Direction."""
    return Game([list(P(h)) for h in hands], leader, must_lead_3c=first, king=king, direction=direction)

class Ranking(unittest.TestCase):
    def test_two_beats_ace_beats_king(self):
        g = game("Kc", "Ac", "2c 4c", "5c")
        g.step(P("Kc")); g.step(P("Ac")); self.assertIn(P("2c"), g.legal())

    def test_three_is_lowest(self):
        g = game("4c 5c", "3s 6c", "7c", "8c")
        g.step(P("4c")); self.assertNotIn(P("3s"), g.legal())

    def test_same_rank_higher_suit_beats(self):
        g = game("7d 8c", "7h 9c", "7c 10c", "Jc")
        g.step(P("7d"))
        self.assertIn(P("7h"), g.legal())
        g.step(P("7h"))
        self.assertNotIn(P("7c"), g.legal())        # ♣ < ♥

    def test_pair_compared_by_highest_suit(self):
        g = game("9c 9s 3c", "9d 9h 4c", "5c", "6c")
        g.step(P("9c 9s")); self.assertNotIn(P("9d 9h"), g.legal())

class Combos(unittest.TestCase):
    def test_lead_any_same_rank_set(self):
        g = game("5c 5d 5h 5s 6c", "7c", "8c", "9c")
        for m in ["5c", "5c 5d", "5c 5d 5h", "5c 5d 5h 5s"]: self.assertIn(P(m), g.legal())
        self.assertNotIn(P("5c 6c"), g.legal())     # no mixed ranks / runs

    def test_same_rank_pair_higher_top_suit_beats(self):
        g = game("5d 5h", "5c 5s", "6c", "7c")
        g.step(P("5d 5h")); self.assertIn(P("5c 5s"), g.legal())   # top ♠ > top ♥

    def test_triple_overrides_any_single(self):
        g = game("2s", "3c 3d 3h", "6c", "7c")
        g.step(P("2s")); self.assertIn(P("3c 3d 3h"), g.legal())

    def test_quad_overrides_any_pair(self):
        g = game("2s 2h", "3c 3d 3h 3s", "6c", "7c")
        g.step(P("2s 2h")); self.assertIn(P("3c 3d 3h 3s"), g.legal())

    def test_no_other_overrides(self):
        for top, bomb in [("2s", "3c 3d 3h 3s"),          # quad on single
                          ("2s 2h", "3c 3d 3h"),          # triple on pair
                          ("Kc Kd Kh", "3c 3d 3h 3s")]:   # quad on triple
            g = game(top, bomb, "6c", "7c")
            g.step(P(top)); self.assertNotIn(P(bomb), g.legal(), (top, bomb))

    def test_after_quad_override_need_higher_quad(self):
        g = game("2s 2h", "4c 4d 4h 4s", "3c 3d 3h 3s", "6c 6d 6h 6s")
        g.step(P("2s 2h")); g.step(P("4c 4d 4h 4s"))
        self.assertEqual(g.legal(), [()])                           # seat 2: 3333 too low, must pass
        g.step(()); self.assertIn(P("6c 6d 6h 6s"), g.legal())     # seat 3: higher quad beats

    def test_after_override_need_higher_same_size(self):
        g = game("2s", "4c 4d 4h", "3c 3d 3h 5c 5d 5h", "6c 6d 6h 6s")
        g.step(P("2s")); g.step(P("4c 4d 4h"))
        legal = g.legal()
        self.assertIn(P("5c 5d 5h"), legal)
        self.assertNotIn(P("3c 3d 3h"), legal)                    # lower triple can't
        self.assertNotIn(P("5c"), legal)                          # single can't come back
        g.step(P("5c 5d 5h")); self.assertNotIn(P("6c 6d 6h 6s"), g.legal())  # quad can't beat triple

    def test_pair_cannot_beat_single_and_single_cannot_beat_pair(self):
        g = game("4c", "5c 5d", "6c", "7c")
        g.step(P("4c")); self.assertNotIn(P("5c 5d"), g.legal())

    def test_must_follow_same_count(self):
        g = game("4c 4d", "Ac 5c 5d", "6c", "7c")
        g.step(P("4c 4d"))
        self.assertNotIn(P("Ac"), g.legal())
        self.assertIn(P("5c 5d"), g.legal())

    def test_cannot_pass_when_leading(self):
        self.assertNotIn((), game("4c", "5c", "6c", "7c").legal())

class Turns(unittest.TestCase):
    def test_pass_locks_you_out_of_trick(self):
        g = game("4c Kc", "5c 2s", "6c 9c", "7c 8c")
        g.step(P("4c")); g.step(()); g.step(P("6c")); g.step(P("7c"))
        self.assertEqual(g.turn, 0)                  # seat 1 skipped
        g.step(P("Kc")); self.assertEqual(g.turn, 2)

    def test_all_pass_owner_leads_fresh(self):
        g = game("Ac 4c", "5c 6c", "7c 8c", "9c 10c")
        g.step(P("Ac")); g.step(()); g.step(()); g.step(())
        self.assertEqual((g.turn, g.trick), (0, ()))
        self.assertIn(P("4c"), g.legal())

    def test_winner_out_trick_continues_back_to_A(self):
        # user example: A 10♣, B goes out with J♦, C and D pass -> turn returns to A, who may still beat J♦
        g = game("10c Qc 4c", "Jd", "5c 6c", "7c 8c")
        g.step(P("10c")); g.step(P("Jd"))
        self.assertEqual(g.finished, [1])
        g.step(()); g.step(())
        self.assertEqual((g.turn, g.trick), (0, P("Jd")))
        self.assertIn(P("Qc"), g.legal())
        g.step(P("Qc"))                              # A is the only one not passed -> A leads next
        self.assertEqual((g.turn, g.trick), (0, ()))

    def test_winner_out_all_pass_last_player_who_played_leads(self):
        g = game("10c Qc 4c", "Jd", "5c 6c", "7c 8c")
        g.step(P("10c")); g.step(P("Jd")); g.step(()); g.step(()); g.step(())
        self.assertEqual((g.turn, g.trick), (0, ()))  # A played 10♣ before B went out

    def test_winner_out_nobody_else_played_last_passer_leads(self):  # [assumed]
        g = game("2s", "5c 6c", "7c 8c", "9c 10c")
        g.step(P("2s")); g.step(()); g.step(()); g.step(())
        self.assertEqual((g.turn, g.trick), (3, ()))

    def test_first_lead_must_include_3c(self):
        g = game("3c 3d 9c", "5c", "6c", "7c", first=True)
        self.assertEqual(sorted(g.legal()), sorted([P("3c"), P("3c 3d")]))
        self.assertEqual(new_round([[1, 2], [0, 3], [4, 5], [6, 7]]).turn, 1)

class Ending(unittest.TestCase):
    def test_last_player_is_slave(self):
        g = game("2s", "3c 4c", "Ac", "Kc")
        g.step(P("2s")); g.step(()); g.step(()); g.step(())   # 0 out unbeaten -> 3 (last passer) leads, direction flips
        g.step(P("Kc"))                                        # 3 out -> next is 2 (flipped direction)
        g.step(P("Ac"))                                        # 2 out -> round over, 1 is Slave
        self.assertTrue(g.over())
        self.assertEqual(g.finished, [0, 3, 2, 1])

class KingFalls(unittest.TestCase):
    def test_king_not_first_becomes_slave_immediately(self):
        g = game("5c", "2s 2h", "6c 7c", "8c 9c", king=1)
        g.step(P("5c"))                              # seat 0 out first; King (1) falls now
        self.assertEqual(g.fallen, [1])
        self.assertEqual(g.turn, 2)                  # King skipped, never plays again
        g.step(P("6c")); g.step(P("8c")); g.step(())  # 2 passes -> 3 leads
        self.assertEqual(g.turn, 3)
        g.step(P("9c"))
        self.assertTrue(g.over())
        self.assertEqual(g.finished, [0, 3, 2, 1])   # King=0, Queen=3, People=2, Slave=old King
        self.assertNotIn(1, [seat for seat, _ in g.history])

    def test_king_wins_first_stays(self):
        g = game("5c", "6c 7c", "8c 9c", "10c Jc", king=0)
        g.step(P("5c"))
        self.assertEqual((g.fallen, g.finished), ([], [0]))

    def test_round_one_has_no_king(self):
        self.assertIsNone(new_round([[1, 2], [0, 3], [4, 5], [6, 7]]).king)

class Direction(unittest.TestCase):
    def test_default_is_counter_clockwise(self):
        g = Game([list(P(h)) for h in ["4c 5c", "6c 7c", "8c 9c", "10c Jc"]], leader=0)
        g.step(P("4c")); self.assertEqual(g.turn, 3)
        g.step(P("10c")); self.assertEqual(g.turn, 2)

    def test_round_two_slave_leads_counter_clockwise(self):
        # user example: seats A B C D = 0 1 2 3. B Slave, A People, C Queen, D King -> B A D C
        order = [3, 2, 0, 1]
        hands = [list(range(i, 52, 4)) for i in range(4)]
        g = new_round(hands, order, give=lambda seat, hand, k: hand[:k])
        seq = [g.turn]
        for _ in range(3): g.step(min(m for m in g.legal() if m)); seq.append(g.turn)
        self.assertEqual(seq, [1, 0, 3, 2])

    def test_winner_out_all_pass_direction_flips(self):
        # user example (clockwise A B C D): B goes out, C D A pass -> A leads, play goes A D C
        g = game("4c 5c 6c", "Jd", "7c 8c", "9c 10c")
        g.step(P("4c")); g.step(P("Jd")); g.step(()); g.step(()); g.step(())
        self.assertEqual((g.turn, g.dir), (0, -1))
        g.step(P("5c")); self.assertEqual(g.turn, 3)
        g.step(P("9c")); self.assertEqual(g.turn, 2)

    def test_winner_beaten_direction_stays(self):
        # B goes out, C D pass, A beats it -> A leads, play stays A C D
        g = game("4c Qc 5c", "Jd", "7c 8c", "9c 10c")
        g.step(P("4c")); g.step(P("Jd")); g.step(()); g.step(()); g.step(P("Qc"))
        self.assertEqual((g.turn, g.dir), (0, 1))
        g.step(P("5c")); self.assertEqual(g.turn, 2)

class Scoring(unittest.TestCase):
    def test_points_summed_over_rounds(self):
        # King +2, Queen +1, People -1, Slave -2
        self.assertEqual(score([[0, 1, 2, 3], [1, 0, 2, 3], [3, 2, 1, 0]]), [1, 2, -1, -2])

    def test_tie_finished_later_in_last_round_ranks_higher(self):
        # seats 0 and 1 both +2; in the last round seat 0 was King (out first), seat 1 People (out later)
        orders = [[0, 1, 2, 3], [1, 2, 3, 0], [0, 2, 1, 3]]
        self.assertEqual(score(orders), [2, 2, 1, -5])
        self.assertEqual(standings(orders), [1, 0, 2, 3])

    def test_default_four_players(self):
        self.assertEqual([len(h) for h in deal()], [13] * 4)

class Exchange(unittest.TestCase):
    def test_slave_gives_best_king_returns_choice(self):
        hands = [list(P("4c 5c 6c")), list(P("7c 8c 9c")), list(P("10c Jc Qc")), list(P("3c Ac 2s"))]
        order = [0, 1, 2, 3]                         # 0 King, 1 Queen, 2 People, 3 Slave
        g = new_round(hands, order, give=lambda seat, hand, k: hand[:k])
        self.assertEqual(show(g.hands[0]), show(P("6c Ac 2s")))   # got A♣ 2♠, returned 4♣ 5♣
        self.assertEqual(show(g.hands[3]), show(P("3c 4c 5c")))
        self.assertEqual(show(g.hands[1]), show(P("8c 9c Qc")))   # got Q♣, returned 7♣
        self.assertEqual(show(g.hands[2]), show(P("7c 10c Jc")))
        self.assertEqual((g.turn, g.king), (3, 0))   # Slave leads, seat 0 is reigning King

    def test_blind_trade_king_picks_before_seeing(self):
        hands = [list(P("4c 5c 6c")), list(P("7c 8c 9c")), list(P("10c Jc Qc")), list(P("3c Ac 2s"))]
        seen = {}
        def give(seat, hand, k):
            seen[seat] = show(hand)
            return hand[-k:]                         # pick own best -> can't be the incoming A♣ 2♠
        g = new_round(hands, [0, 1, 2, 3], give)
        self.assertEqual(seen[0], show(P("4c 5c 6c")))          # King chose from his own 13 only
        self.assertEqual(show(g.hands[0]), show(P("4c Ac 2s")))
        self.assertEqual(show(g.hands[3]), show(P("3c 5c 6c")))

class Invariants(unittest.TestCase):
    def test_random_games_conserve_cards(self):
        for seed in range(500):
            rng = random.Random(seed)
            g = new_round(deal(4, rng))
            while not g.over(): g.step(rng.choice(g.legal()))
            self.assertEqual(sum(len(m) for _, m in g.history) + sum(map(len, g.hands)), 52)
            self.assertEqual(sorted(g.finished), [0, 1, 2, 3])

    def test_illegal_move_rejected(self):
        with self.assertRaises(ValueError): game("4c", "5c", "6c", "7c").step(P("5c"))

if __name__ == "__main__":
    unittest.main()
