"""Global stock data adapters for US/HK research inputs."""

from src.data_sources.global_stock.client import GlobalStockClient, normalize_hk_symbol

__all__ = ["GlobalStockClient", "normalize_hk_symbol"]
