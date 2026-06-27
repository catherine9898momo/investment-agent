"""Resolve reusable sector and peer universes for attribution analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from src.research.models import ResolvedEntity

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "peer_universe.yaml"


@dataclass(frozen=True)
class PeerSymbol:
    symbol: str
    group: str
    label: str = ""


@dataclass(frozen=True)
class SectorPeerSet:
    symbol: str
    sector_indexes: list[PeerSymbol]
    peers: list[PeerSymbol]
    confidence: Literal["high", "medium", "low"] = "low"
    rationale: str = ""
    universe_refs: list[str] = field(default_factory=list)


def resolve_sector_peer_set(entity: ResolvedEntity, config_path: Path = DEFAULT_CONFIG_PATH) -> SectorPeerSet:
    config = _load_config(config_path)
    symbol = entity.symbol.upper()
    symbol_config = _symbol_config(config, symbol)
    if not symbol_config:
        return _fallback_set(symbol, config)

    sector_indexes = _items(symbol_config.get("sector_indexes") or [])
    peers = _items(symbol_config.get("peers") or [])
    universe_refs = list(symbol_config.get("universe_refs") or [])
    for ref in universe_refs:
        universe = (config.get("universes") or {}).get(ref) or {}
        sector_indexes.extend(_items(universe.get("sector_indexes") or []))
        peers.extend(_peers_from_universe(universe, symbol, ref))
    peers.extend(_items(symbol_config.get("extra_peers") or []))
    sector_indexes = _dedupe(sector_indexes)
    peers = _dedupe(peers)
    return SectorPeerSet(
        symbol=symbol,
        sector_indexes=sector_indexes,
        peers=peers,
        confidence=symbol_config.get("confidence", "medium"),
        rationale=symbol_config.get("rationale", "Configured peer universe."),
        universe_refs=universe_refs,
    )


def _load_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}


def _symbol_config(config: dict[str, Any], symbol: str) -> dict[str, Any] | None:
    symbols = config.get("symbols") or {}
    matched_universes: list[str] = []
    for universe_name, universe in (config.get("universes") or {}).items():
        universe_symbols = [str(item).upper() for item in universe.get("symbols") or []]
        if symbol in universe_symbols:
            matched_universes.append(universe_name)
    if symbol in symbols:
        explicit = dict(symbols[symbol])
        refs = list(explicit.get("universe_refs") or [])
        explicit["universe_refs"] = refs + [ref for ref in matched_universes if ref not in refs]
        return explicit
    if matched_universes:
        return {
            "confidence": "high",
            "rationale": f"{symbol} belongs to configured universes {', '.join(matched_universes)}.",
            "universe_refs": matched_universes,
        }
    return None


def _fallback_set(symbol: str, config: dict[str, Any]) -> SectorPeerSet:
    defaults = config.get("defaults") or {}
    return SectorPeerSet(
        symbol=symbol,
        sector_indexes=_items(defaults.get("sector_indexes") or []),
        peers=[],
        confidence="low",
        rationale="No configured peer universe; using broad market fallback only.",
    )


def _items(raw_items: list[dict[str, Any]]) -> list[PeerSymbol]:
    items: list[PeerSymbol] = []
    for item in raw_items:
        if not isinstance(item, dict) or not item.get("symbol"):
            continue
        items.append(PeerSymbol(str(item["symbol"]).upper(), str(item.get("group") or "unknown"), str(item.get("label") or "")))
    return items


def _peers_from_universe(universe: dict[str, Any], own_symbol: str, group: str) -> list[PeerSymbol]:
    label = str(universe.get("label") or group)
    return [PeerSymbol(str(symbol).upper(), group, label) for symbol in universe.get("symbols") or [] if str(symbol).upper() != own_symbol]


def _dedupe(items: list[PeerSymbol]) -> list[PeerSymbol]:
    seen: set[str] = set()
    deduped: list[PeerSymbol] = []
    for item in items:
        if item.symbol in seen:
            continue
        seen.add(item.symbol)
        deduped.append(item)
    return deduped
