from src.research.models import ResolvedEntity
from src.research.peer_resolver import resolve_sector_peer_set


def test_peer_resolver_loads_configured_universe_for_magnificent_7() -> None:
    peer_set = resolve_sector_peer_set(ResolvedEntity("NVDA", "NVDA", "Nvidia"))

    assert peer_set.confidence == "high"
    assert {item.symbol for item in peer_set.sector_indexes} >= {"QQQ", "SMH", "SOXX"}
    peer_symbols = {item.symbol for item in peer_set.peers}
    assert {"AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA"}.issubset(peer_symbols)
    assert "magnificent_7" in {item.group for item in peer_set.peers}


def test_peer_resolver_returns_china_internet_peers_for_tencent_pdd_tcom() -> None:
    tencent = resolve_sector_peer_set(ResolvedEntity("腾讯", "0700.HK", "Tencent"))
    pdd = resolve_sector_peer_set(ResolvedEntity("PDD", "PDD", "PDD"))
    tcom = resolve_sector_peer_set(ResolvedEntity("TCOM", "TCOM", "Trip.com"))

    assert {"9988.HK", "PDD", "TCOM"}.issubset({item.symbol for item in tencent.peers})
    assert "china_internet" in {item.group for item in pdd.peers}
    assert "china_travel_platform" in {item.group for item in tcom.peers}


def test_peer_resolver_returns_chip_core_and_memory_groups_for_mu() -> None:
    peer_set = resolve_sector_peer_set(ResolvedEntity("MU", "MU", "Micron"))

    groups = {item.group for item in peer_set.peers}
    symbols = {item.symbol for item in peer_set.peers}
    assert {"QQQ", "SMH", "SOXX"}.issubset({item.symbol for item in peer_set.sector_indexes})
    assert {"NVDA", "AMD", "AVGO"}.issubset(symbols)
    assert {"WDC", "STX", "SNDK"}.issubset(symbols)
    assert {"ai_semiconductor", "memory_storage"}.issubset(groups)


def test_peer_resolver_returns_low_confidence_for_unknown_symbol() -> None:
    peer_set = resolve_sector_peer_set(ResolvedEntity("XYZ", "XYZ", "Unknown"))

    assert peer_set.confidence == "low"
    assert peer_set.peers == []
    assert {item.symbol for item in peer_set.sector_indexes} == {"SPY", "QQQ"}
