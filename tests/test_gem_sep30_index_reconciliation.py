"""Official October 2026 S&P index additions cannot enter September month-end."""
import pytest
from gem_data.gem_sep30_index_reconciliation import adjust_sep30_current_membership

def synthetic_current():
    current={f"X{i:03d}":str(100000+i%498).zfill(10) for i in range(501)}
    current["VYLR"]="0002128626"
    current["TWLO"]="0001447669"
    assert len(current)==503 and len(set(current.values()))==500
    return current

def test_sep30_replaces_post_month_end_stocks_from_official_s_and_p_notice():
    current=synthetic_current()
    result=adjust_sep30_current_membership(current)
    assert len(result["members"])==503
    assert len(set(result["members"].values()))==500
    assert "VYLR" not in result["members"]
    assert "TWLO" not in result["members"]
    assert result["members"]["CTVA"]=="0001755672"
    assert result["members"]["WBD"]=="0001437107"
    assert result["removed_post_signal"]==["VYLR","TWLO"]
    assert not result["historical_membership_full_audit_complete"]
    assert not result["trading_authorized"]
    assert "VYLR" in current and "TWLO" in current

def test_missing_current_replacement_does_not_guess():
    current=synthetic_current()
    current.pop("TWLO")
    current["WBD"]="0001437107"
    with pytest.raises(ValueError):
        adjust_sep30_current_membership(current)
