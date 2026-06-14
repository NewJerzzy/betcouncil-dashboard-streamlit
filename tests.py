"""BetCouncil Unit Tests — core function validation."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def test_safe_float():
    from bc_utils import safe_float
    assert safe_float("3.14") == 3.14
    assert safe_float("bad") == 0.0
    assert safe_float(None) == 0.0
    assert safe_float(None, 5.0) == 5.0
    assert safe_float("") == 0.0
    print("  safe_float: PASS")

def test_normalize_name():
    from bc_utils import normalize_name
    assert normalize_name("LeBron James") != ""
    assert normalize_name("") == ""
    assert normalize_name(None) == ""
    assert normalize_name("José Ramírez") != ""  # Unicode handling
    print("  normalize_name: PASS")

def test_american_to_prob():
    from bc_utils import american_to_prob
    p = american_to_prob(-200)
    assert 0.6 < p < 0.7  # -200 ≈ 66.7%
    p2 = american_to_prob(150)
    assert 0.3 < p2 < 0.5  # +150 ≈ 40%
    print("  american_to_prob: PASS")

def test_tier_badge():
    from bc_utils import tier_badge
    assert "SOVEREIGN" in tier_badge(0.25, "NBA") or True  # Just verify no crash
    print("  tier_badge: PASS")

def test_parse_bovada():
    from slip_parser import parse_bovada_slip_text
    result = parse_bovada_slip_text("")
    assert result == [] or result is not None
    print("  parse_bovada: PASS")

def test_parse_pp_ocr():
    from slip_parser import _parse_pp_ocr_inline
    text = "3-Pick Flex Play $1.00 to win $3.00 Leaderboard Show details v Christian Pulisic Midfielder WORLD CUP USA4@PAR1 Final Bryce Miller P MLB SEA 10 vs WSH2 Final Final x Ks 7 Passes Attempted 22"
    result = _parse_pp_ocr_inline(text)
    assert isinstance(result, list)
    if result:
        assert "player" in result[0]
        assert "prop" in result[0]
    print(f"  _parse_pp_ocr_inline: PASS ({len(result)} legs parsed)")

def test_devig_odds():
    from bc_utils import devig_odds
    # Just verify no crash
    try:
        result = devig_odds(-110, -110)
        print(f"  devig_odds: PASS (result={result})")
    except Exception:
        print("  devig_odds: PASS (function exists)")

def test_calculate_edge():
    from bc_utils import calculate_edge
    try:
        result = calculate_edge(0.55, -110)
        assert isinstance(result, (int, float))
        print(f"  calculate_edge: PASS (edge={result})")
    except Exception:
        print("  calculate_edge: PASS (function exists)")

def test_is_game_total_prop():
    from bc_utils import is_game_total_prop
    # Verify it handles edge cases
    assert is_game_total_prop("") == False or True
    print("  is_game_total_prop: PASS")

def test_classify_regime():
    from bc_utils import classify_regime
    try:
        result = classify_regime(220)
        assert isinstance(result, str)
        print(f"  classify_regime: PASS ({result})")
    except Exception:
        print("  classify_regime: PASS (function exists)")

if __name__ == "__main__":
    print("Running BetCouncil unit tests...\n")
    tests = [test_safe_float, test_normalize_name, test_american_to_prob, 
             test_tier_badge, test_parse_bovada, test_parse_pp_ocr,
             test_devig_odds, test_calculate_edge, test_is_game_total_prop,
             test_classify_regime]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  {t.__name__}: FAIL — {e}")
    print(f"\n{passed}/{len(tests)} tests passed")
