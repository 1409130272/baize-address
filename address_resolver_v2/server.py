import os
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from .config import AIConfig, AICacheConfig, AICostConfig, ServerConfig
from .resolver import AddressResolver
from .ai_resolver import AIResolver

# 项目根目录（address_resolver_v2/ 的上一级）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
EXCEL_PATH = os.path.join(PROJECT_ROOT, "data", "区划代码（开放平台标准）.xlsx")

app = FastAPI(title="地址解析服务", version="2.2.0")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    err = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(x) for x in err.get("loc", [])) if err else ""
    msg = err.get("msg", "请求参数不合法")
    desc = f"参数错误：{field} {msg}".strip()
    return JSONResponse(
        status_code=200,
        content={
            "addressResolutionInfoList": [],
            "code": "GO_BACK",
            "desc": desc,
            "total": 0,
            "aiUsed": 0,
            "aiCacheHit": 0,
        },
    )


_ai_resolver = AIResolver(
    api_key=AIConfig.api_key,
    base_url=AIConfig.base_url,
    model=AIConfig.model,
    timeout=AIConfig.timeout,
    enable_cache=AICacheConfig.enabled,
    cache_maxsize=AICacheConfig.maxsize,
    cache_ttl=AICacheConfig.ttl,
    temperature=AIConfig.temperature,
    max_retries=AIConfig.max_retries,
    thinking_enabled=AIConfig.thinking_enabled,
    price_input_cache_hit=AICostConfig.price_input_cache_hit,
    price_input_cache_miss=AICostConfig.price_input_cache_miss,
    price_output=AICostConfig.price_output,
    price_peak_input_cache_hit=AICostConfig.price_peak_input_cache_hit,
    price_peak_input_cache_miss=AICostConfig.price_peak_input_cache_miss,
    price_peak_output=AICostConfig.price_peak_output,
    peak_hours=AICostConfig.peak_hours,
) if AIConfig.enabled else None
resolver = AddressResolver(EXCEL_PATH, ai_resolver=_ai_resolver)


class ResolveRequest(BaseModel):
    address: str | None = None
    useAI: bool = False
    cityCode: str | None = None


class AddressItem(BaseModel):
    address: str
    provinceCode: str | None = None
    provinceName: str | None = None
    cityCode: str | None = None
    cityName: str | None = None
    countyCode: str | None = None
    countyName: str | None = None
    village: str | None = None
    confidence: int = 0
    source: int = 0
    reason: str = ""


class AICostInfo(BaseModel):
    # 百万tokens输入（缓存命中）数量
    inputCacheHitTokens: int = 0
    # 百万tokens输入（缓存未命中）数量
    inputCacheMissTokens: int = 0
    # 百万tokens输出数量
    outputTokens: int = 0
    # 本次调用总费用（人民币元）；未实际调用 AI API（含本地缓存命中）时为 0
    totalCost: float = 0.0
    # 本次计费是否按高峰时段单价计算（true=高峰，false=平时/未实际调用）
    isPeak: bool = False


class ResolveResponse(BaseModel):
    addressResolutionInfoList: list[AddressItem]
    code: str
    desc: str
    total: int
    aiUsed: int = 0
    aiCacheHit: int = 0
    # 本次调用 AI API 的费用信息（含 token 明细与总费用）；未调用 AI 时为零值
    aiCost: AICostInfo = AICostInfo()


@app.get("/")
def root():
    return {"service": "address-resolver", "status": "running", "version": "2.2.0"}


@app.get("/health")
def health():
    return {"code": "SUCCESS", "desc": "服务正常"}


@app.get("/stats")
def stats():
    info = {"version": "2.2.0"}
    if _ai_resolver.cache:
        info["ai_cache"] = _ai_resolver.cache.stats()
    return info


def _to_int_source(src: str) -> int:
    return 1 if src == "ai" else 0


@app.post("/api/address/resolve", response_model=ResolveResponse)
async def resolve_address(req: ResolveRequest):
    address = (req.address or "").strip()
    if not address:
        return ResolveResponse(
            addressResolutionInfoList=[],
            code="GO_BACK",
            desc="地址不能为空",
            total=0,
            aiUsed=0,
            aiCacheHit=0,
        )
    # 汉字数量校验：地址必须至少包含6个汉字，且必须含有汉字
    chinese_count = sum(1 for ch in address if "\u4e00" <= ch <= "\u9fff")
    if chinese_count == 0:
        return ResolveResponse(
            addressResolutionInfoList=[],
            code="GO_BACK",
            desc="地址必须包含汉字",
            total=0,
            aiUsed=0,
            aiCacheHit=0,
        )
    if chinese_count < 6:
        return ResolveResponse(
            addressResolutionInfoList=[],
            code="GO_BACK",
            desc=f"地址汉字数量不足，至少需要6个汉字，当前{chinese_count}个",
            total=0,
            aiUsed=0,
            aiCacheHit=0,
        )
    try:
        result = await resolver.resolve_async(
            address,
            max_candidates=ServerConfig.max_candidates,
            use_ai=req.useAI,
            city_code=req.cityCode,
        )
    except Exception as e:
        return ResolveResponse(
            addressResolutionInfoList=[],
            code="GO_BACK",
            desc=f"地址解析异常：{type(e).__name__}",
            total=0,
            aiUsed=0,
            aiCacheHit=0,
        )

    candidates = result.candidates
    if not candidates:
        return ResolveResponse(
            addressResolutionInfoList=[],
            code="GO_BACK",
            desc=("AI兜底已尝试但无结果" if result.ai_attempted else "无法解析该地址"),
            total=0,
            aiUsed=1 if result.ai_used else 0,
            aiCacheHit=1 if result.ai_cache_hit else 0,
        )

    items = []
    for c in candidates:
        rd = c.to_result(address)
        items.append(AddressItem(
            address=rd["address"],
            provinceCode=rd["provinceCode"],
            provinceName=rd["provinceName"],
            cityCode=rd["cityCode"],
            cityName=rd["cityName"],
            countyCode=rd["countyCode"],
            countyName=rd["countyName"],
            village=rd["village"],
            confidence=int(round(rd["confidence"])),
            source=_to_int_source(rd["source"]),
            reason=rd["reason"],
        ))

    desc = "地址解析完成"
    if result.ai_used:
        desc += "，AI兜底已生效"
    if result.ai_cache_hit:
        desc += "（命中缓存）"

    return ResolveResponse(
        addressResolutionInfoList=items,
        code="SUCCESS",
        desc=desc,
        total=len(items),
        aiUsed=1 if result.ai_used else 0,
        aiCacheHit=1 if result.ai_cache_hit else 0,
        aiCost=AICostInfo(**result.ai_cost_info),
    )
