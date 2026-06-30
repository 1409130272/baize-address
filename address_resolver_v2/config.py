import os
import configparser
from typing import Optional

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")

_config = configparser.ConfigParser()
_config.read(_CONFIG_PATH, encoding="utf-8")


class AIConfig:
    enabled: bool = _config.getboolean("ai", "enabled", fallback=True)
    api_key: str = os.environ.get("DEEPSEEK_API_KEY", "") or _config.get("ai", "api_key", fallback="")
    base_url: str = _config.get("ai", "base_url", fallback="https://api.deepseek.com")
    model: str = _config.get("ai", "model", fallback="deepseek-v4-flash")
    thinking_enabled: bool = _config.getboolean("ai", "thinking_enabled", fallback=False)
    timeout: int = _config.getint("ai", "timeout", fallback=30)
    temperature: float = _config.getfloat("ai", "temperature", fallback=0.1)
    max_retries: int = _config.getint("ai", "max_retries", fallback=2)


class AITriggerConfig:
    confidence_threshold: float = _config.getfloat("ai_trigger", "confidence_threshold", fallback=75)
    ambiguity_gap: float = _config.getfloat("ai_trigger", "ambiguity_gap", fallback=10)
    min_confidence: float = _config.getfloat("ai_trigger", "min_confidence", fallback=60)


class AICacheConfig:
    enabled: bool = _config.getboolean("ai_cache", "enabled", fallback=True)
    maxsize: int = _config.getint("ai_cache", "maxsize", fallback=10000)
    ttl: int = _config.getint("ai_cache", "ttl", fallback=86400)


class AICostConfig:
    # 单位：人民币元 / 百万 tokens
    # 平时单价
    price_input_cache_hit: float = _config.getfloat("ai_cost", "price_input_cache_hit", fallback=0.2)
    price_input_cache_miss: float = _config.getfloat("ai_cost", "price_input_cache_miss", fallback=1.0)
    price_output: float = _config.getfloat("ai_cost", "price_output", fallback=2.0)
    # 高峰时段单价（DeepSeek V4 起引入峰谷定价）
    price_peak_input_cache_hit: float = _config.getfloat("ai_cost", "price_peak_input_cache_hit", fallback=0.04)
    price_peak_input_cache_miss: float = _config.getfloat("ai_cost", "price_peak_input_cache_miss", fallback=2.0)
    price_peak_output: float = _config.getfloat("ai_cost", "price_peak_output", fallback=4.0)
    # 高峰时段定义（北京时间，24小时制，左闭右开）
    # 多个时段用分号分隔，每个时段格式 "HH:MM-HH:MM"；留空则不区分峰谷
    peak_hours: str = _config.get("ai_cost", "peak_hours", fallback="09:00-12:00;14:00-18:00")


class ServerConfig:
    max_candidates: int = _config.getint("server", "max_candidates", fallback=3)
    host: str = _config.get("server", "host", fallback="0.0.0.0")
    port: int = _config.getint("server", "port", fallback=8769)
