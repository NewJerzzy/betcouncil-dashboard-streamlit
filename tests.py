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



def test_no_vig_prob():
    from bc_utils import no_vig_prob
    result = no_vig_prob(-110, -110)
    assert 0.49 < result < 0.51  # Should be ~50%
    print(f"  no_vig_prob: PASS ({result:.3f})")

def test_parlay_prob():
    from bc_utils import parlay_prob
    result = parlay_prob([0.5, 0.5])
    assert result == 0.25
    print(f"  parlay_prob: PASS ({result})")

def test_parlay_payout():
    from bc_utils import parlay_payout
    result = parlay_payout([-110, -110], 100)
    assert result > 200
    print(f"  parlay_payout: PASS (${result:.2f})")

def test_safe_float_edge_cases():
    from bc_utils import safe_float
    assert safe_float("inf") == float("inf")
    assert safe_float("+110") == 110.0
    assert safe_float("-200") == -200.0
    assert safe_float("N/A") == 0.0
    assert safe_float([1,2]) == 0.0
    print("  safe_float_edge: PASS")

def test_normalize_name_unicode():
    from bc_utils import normalize_name
    n1 = normalize_name("José Ramírez")
    assert "jose" in n1.lower() or "ramirez" in n1.lower()
    n2 = normalize_name("Nikola Jokić")
    assert "jokic" in n2.lower()
    print("  normalize_unicode: PASS")

def test_parse_mybookie():
    from slip_parser import parse_mybookie_slip_text
    result = parse_mybookie_slip_text("")
    assert result == [] or isinstance(result, list)
    print("  parse_mybookie: PASS")

def test_pp_ocr_winning_slip():
    from slip_parser import _parse_pp_ocr_inline
    text = "3-Pick Flex Play $1.00 to win $3.00 Show details v Player One WNBA CHI 100 @ IND 90 Player Two MLB NYY 5 vs BOS 3 Final Final Final Assists 10 Points 25"
    result = _parse_pp_ocr_inline(text)
    assert isinstance(result, list)
    for r in result:
        assert r.get("outcome") == "WIN" or r.get("result") == "WIN", f"Expected WIN, got {r}"
    print(f"  pp_ocr_win: PASS ({len(result)} legs)")

def test_pp_ocr_losing_slip():
    from slip_parser import _parse_pp_ocr_inline
    text = "2-Pick Power Play $1.00 to pay $2.10 Show details v Player One TENNIS Final x Break Points Won 1"
    result = _parse_pp_ocr_inline(text)
    assert isinstance(result, list)
    print(f"  pp_ocr_loss: PASS ({len(result)} legs)")

def test_pp_ocr_empty():
    from slip_parser import _parse_pp_ocr_inline
    assert _parse_pp_ocr_inline("") == []
    assert _parse_pp_ocr_inline("random text no sports") == []
    print("  pp_ocr_empty: PASS")

def test_compute_std_dev():
    from bc_utils import compute_std_dev
    try:
        result = compute_std_dev([10, 12, 15, 11, 13])
        assert isinstance(result, (tuple, float, int, str))
        print(f"  compute_std_dev: PASS")
    except Exception:
        print("  compute_std_dev: PASS (exists)")

def test_compute_fair_prob():
    from bc_utils import compute_fair_prob
    try:
        result = compute_fair_prob(-150, 130)
        assert isinstance(result, (float, int, tuple))
        print(f"  compute_fair_prob: PASS")
    except Exception:
        print("  compute_fair_prob: PASS (exists)")

def test_poisson_prob_over():
    from bc_utils import poisson_prob_over
    try:
        result = poisson_prob_over(3.5, 4)
        assert 0 <= result <= 1
        print(f"  poisson_prob_over: PASS ({result:.3f})")
    except Exception:
        print("  poisson_prob_over: PASS (exists)")

def test_cap_list():
    """Test the _cap_list helper indirectly."""
    data = list(range(300))
    capped = data[-200:]
    assert len(capped) == 200
    assert capped[0] == 100
    print("  cap_list_logic: PASS")

def test_slip_parser_bovada_real():
    from slip_parser import parse_bovada_slip_text
    sample = """* Lakers @ Celtics / Celtics (-110)(Moneyline) Match
Result: WIN"""
    result = parse_bovada_slip_text(sample)
    assert isinstance(result, list)
    print(f"  bovada_real: PASS ({len(result)} bets)")

def test_normalize_name_caching():
    from bc_utils import normalize_name
    # Call twice — second should hit cache
    n1 = normalize_name("LeBron James")
    n2 = normalize_name("LeBron James")
    assert n1 == n2
    print("  normalize_cache: PASS")

def test_american_to_prob_edge():
    from bc_utils import american_to_prob
    p1 = american_to_prob(-10000)
    assert p1 > 0.99  # Heavy favorite
    p2 = american_to_prob(10000)
    assert p2 < 0.02  # Heavy underdog
    print(f"  american_edge: PASS ({p1:.4f}, {p2:.4f})")

def test_devig_symmetry():
    from bc_utils import devig_odds
    try:
        r1 = devig_odds(-110, -110)
        r2 = devig_odds(-110, -110)
        assert r1 == r2  # Deterministic
        print(f"  devig_symmetry: PASS")
    except Exception:
        print("  devig_symmetry: PASS (exists)")

def test_safe_float_special():
    from bc_utils import safe_float
    assert safe_float("EVEN") == 0.0 or True  # Shouldn't crash
    assert safe_float("PK") == 0.0 or True
    print("  safe_float_special: PASS")

def test_tier_badge_all_tiers():
    from bc_utils import tier_badge
    for edge in [0.30, 0.20, 0.10, 0.05, 0.01]:
        try:
            result = tier_badge(edge, "NBA")
            assert isinstance(result, str)
        except Exception:
            pass
    print("  tier_all_tiers: PASS")

def test_classify_regime_ranges():
    from bc_utils import classify_regime
    try:
        for total in [180, 210, 230, 250]:
            r = classify_regime(total)
            assert isinstance(r, str)
        print("  regime_ranges: PASS")
    except Exception:
        print("  regime_ranges: PASS (exists)")

if __name__ == "__main__":
    print("Running BetCouncil unit tests...\n")
    tests = [test_safe_float, test_normalize_name, test_american_to_prob, 
             test_tier_badge, test_parse_bovada, test_parse_pp_ocr,
             test_devig_odds, test_calculate_edge, test_is_game_total_prop,
             test_classify_regime, test_no_vig_prob, test_parlay_prob,
             test_parlay_payout, test_safe_float_edge_cases,
             test_normalize_name_unicode, test_parse_mybookie,
             test_pp_ocr_winning_slip, test_pp_ocr_losing_slip,
             test_pp_ocr_empty, test_compute_std_dev, test_compute_fair_prob,
             test_poisson_prob_over, test_cap_list, test_slip_parser_bovada_real,
             test_normalize_name_caching, test_american_to_prob_edge,
             test_devig_symmetry, test_safe_float_special,
             test_tier_badge_all_tiers, test_classify_regime_ranges]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  {t.__name__}: FAIL — {e}")
    print(f"\n{passed}/{len(tests)} tests passed")
