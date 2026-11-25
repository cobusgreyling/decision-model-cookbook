import unittest

from cookbook.desk import (
    COMPOUND_SPLIT,
    FITS_MIN,
    JAILBREAK_BLOCK,
    ROUTE_MIN,
    decide,
    refund_requested,
)


def _answers(
    team: str = "billing",
    team_p: float = 0.91,
    fits: float = 0.95,
    compound: float = 0.05,
    refund: float = 0.02,
    jailbreak: float = 0.02,
) -> dict:
    others = {"billing": 0.03, "technical": 0.03, "shipping": 0.02, "accounts": 0.01}
    probabilities = {name: (1.0 - team_p) / 3 for name in others}
    probabilities[team] = team_p
    return {
        "team": {"type": "choice", "choice": team, "probabilities": probabilities, "confidence": team_p},
        "fits": {"type": "noul", "noul": fits},
        "compound": {"type": "noul", "noul": compound},
        "refund": {"type": "noul", "noul": refund},
        "jailbreak": {"type": "noul", "noul": jailbreak},
        "contact": {"type": "noul", "noul": 0.1},
        "angry": {"type": "noul", "noul": 0.1},
        "urgency": {"type": "score", "score": 1.2},
    }


class DecideTests(unittest.TestCase):
    def test_routes_a_peaked_choice(self) -> None:
        self.assertEqual(decide(_answers()), "route:billing")

    def test_jailbreak_stops_the_desk(self) -> None:
        answers = _answers(jailbreak=JAILBREAK_BLOCK, compound=0.99)
        self.assertEqual(decide(answers), "block")

    def test_compound_is_not_one_queue(self) -> None:
        self.assertEqual(decide(_answers(compound=COMPOUND_SPLIT)), "split")

    def test_nothing_to_handle_closes(self) -> None:
        self.assertEqual(decide(_answers(fits=FITS_MIN - 0.01)), "close")

    def test_soft_team_goes_to_a_person(self) -> None:
        self.assertEqual(decide(_answers(team_p=ROUTE_MIN - 0.01)), "review")

    def test_unknown_team_goes_to_a_person(self) -> None:
        answers = _answers()
        answers["team"]["choice"] = "other"
        self.assertEqual(decide(answers), "review")

    def test_refund_flag_uses_its_own_threshold(self) -> None:
        self.assertFalse(refund_requested(_answers(refund=0.79)))
        self.assertTrue(refund_requested(_answers(refund=0.80)))


if __name__ == "__main__":
    unittest.main()
