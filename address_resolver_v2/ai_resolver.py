import os
import time
import asyncio
from collections import OrderedDict
from typing import Optional

from pydantic import BaseModel, Field

from .resolver import Candidate


class AIAddressItem(BaseModel):
    province_code: str = Field(description="省级6位区划代码")
    province_name: str = Field(description="省级名称")
    city_code: Optional[str] = Field(default=None, description="市级6位区划代码，无则填null")
    city_name: Optional[str] = Field(default=None, description="市级名称，无则填null")
    county_code: Optional[str] = Field(default=None, description="区县级6位区划代码，无则填null")
    county_name: Optional[str] = Field(default=None, description="区县级名称，无则填null")
    village: Optional[str] = Field(default=None, description="街道及以下详细地址，无则填null")
    confidence: float = Field(description="本次判断的置信度0-100")
    reason: str = Field(description="选择该结果的简短理由")


class AIAddressResponse(BaseModel):
    results: list[AIAddressItem] = Field(description="解析结果列表，按可能性从高到低排序")


class AICache:
    def __init__(self, maxsize=10000, ttl=86400):
        self.maxsize = maxsize
        self.ttl = ttl
        self._cache = OrderedDict()
        self._lock = asyncio.Lock()

    def _make_key(self, address, city_code):
        return (address, city_code or 0)

    async def get(self, address, city_code):
        key = self._make_key(address, city_code)
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            ts, value = entry
            if time.time() - ts > self.ttl:
                self._cache.pop(key, None)
                return None
            self._cache.move_to_end(key)
            return value

    async def put(self, address, city_code, value):
        key = self._make_key(address, city_code)
        async with self._lock:
            self._cache[key] = (time.time(), value)
            self._cache.move_to_end(key)
            while len(self._cache) > self.maxsize:
                self._cache.popitem(last=False)

    def stats(self):
        return {"size": len(self._cache), "maxsize": self.maxsize, "ttl": self.ttl}


class AIResolver:
    def __init__(self, api_key=None, base_url="https://api.deepseek.com", model="deepseek-chat", timeout=30,
                 enable_cache=True, cache_maxsize=10000, cache_ttl=86400,
                 temperature=0.1, max_retries=2, thinking_enabled=False,
                 price_input_cache_hit=0.0, price_input_cache_miss=0.0, price_output=0.0,
                 price_peak_input_cache_hit=None, price_peak_input_cache_miss=None, price_peak_output=None,
                 peak_hours=""):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.enable_cache = enable_cache
        self.cache = AICache(maxsize=cache_maxsize, ttl=cache_ttl) if enable_cache else None
        self.temperature = temperature
        self.max_retries = max_retries
        # 思考模式开关：False 时通过 extra_body 显式关闭，兼容 instructor 的 tool_choice；
        # True 时不传 extra_body，使用模型默认行为（注意：与 instructor 结构化输出不兼容）
        self.thinking_enabled = thinking_enabled
        # 计费单价（人民币元 / 百万 tokens）
        # 平时单价
        self.price_input_cache_hit = price_input_cache_hit
        self.price_input_cache_miss = price_input_cache_miss
        self.price_output = price_output
        # 高峰时段单价（未配置时回退为平时单价，等价于不开峰谷）
        self.price_peak_input_cache_hit = (
            price_peak_input_cache_hit if price_peak_input_cache_hit is not None else price_input_cache_hit
        )
        self.price_peak_input_cache_miss = (
            price_peak_input_cache_miss if price_peak_input_cache_miss is not None else price_input_cache_miss
        )
        self.price_peak_output = (
            price_peak_output if price_peak_output is not None else price_output
        )
        # 高峰时段（北京时间），解析为 [(start_min, end_min), ...] 的分钟区间列表，左闭右开
        self.peak_ranges = self._parse_peak_hours(peak_hours)
        self._extra_body = None if thinking_enabled else {"thinking": {"type": "disabled"}}
        self._sync_client = None
        self._sync_instructor = None
        self._async_client = None
        self._async_instructor = None

    def _ensure_sync_client(self):
        if self._sync_instructor is not None:
            return self._sync_instructor
        try:
            import instructor
            from openai import OpenAI
        except ImportError as e:
            raise RuntimeError(f"缺少依赖: {e}, 请安装 openai 和 instructor") from e
        if not self.api_key:
            raise RuntimeError("未配置 DEEPSEEK_API_KEY")
        self._sync_client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
        self._sync_instructor = instructor.from_openai(self._sync_client)
        return self._sync_instructor

    async def _ensure_async_client(self):
        if self._async_instructor is not None:
            return self._async_instructor
        try:
            import instructor
            from openai import AsyncOpenAI
        except ImportError as e:
            raise RuntimeError(f"缺少依赖: {e}, 请安装 openai 和 instructor") from e
        if not self.api_key:
            raise RuntimeError("未配置 DEEPSEEK_API_KEY")
        self._async_client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)
        self._async_instructor = instructor.from_openai(self._async_client)
        return self._async_instructor

    def _build_candidates_text(self, rule_candidates, loader):
        lines = []
        seen = set()
        for c in rule_candidates:
            key = (c.province.code if c.province else 0, c.city.code if c.city else 0, c.county.code if c.county else 0)
            if key in seen:
                continue
            seen.add(key)
            p = f"{c.province.code}/{c.province.name}" if c.province else "-"
            ci = f"{c.city.code}/{c.city.name}" if c.city else "-"
            co = f"{c.county.code}/{c.county.name}" if c.county else "-"
            lines.append(f"  候选: 省={p} 市={ci} 区县={co}")
        return "\n".join(lines) if lines else "  (规则解析无候选)"

    def _build_truncation_candidates(self, rule_candidates, text, loader):
        if not rule_candidates:
            return ""
        top = rule_candidates[0]
        if not getattr(top, "need_ai_review", False):
            return ""
        lines = []
        for matched_info in (top.county, top.city):
            if matched_info is None:
                continue
            for ct in loader.get_all_counties():
                if ct.name != matched_info.name and ct.name.endswith(matched_info.name) and len(ct.name) > len(matched_info.name):
                    if ct.name in text or matched_info.name in text:
                        prov = loader.get_by_code(ct.province_code)
                        city = loader.get_by_code(ct.city_code)
                        p = f"{prov.name}" if prov else "-"
                        ci = f"{city.name}" if city else "-"
                        lines.append(f"  {ct.code} {ct.name} (省={p} 市={ci})")
            for ci_info in loader.get_all_cities():
                if ci_info.name != matched_info.name and ci_info.name.endswith(matched_info.name) and len(ci_info.name) > len(matched_info.name):
                    if ci_info.name in text or matched_info.name in text:
                        prov = loader.get_by_code(ci_info.province_code)
                        p = f"{prov.name}" if prov else "-"
                        lines.append(f"  {ci_info.code} {ci_info.name} (省={p})")
        if not lines:
            return ""
        return "可能被截断的区划候选(原文可能包含更长的区划名):\n" + "\n".join(lines[:8])

    def _build_same_name_candidates(self, rule_candidates, loader):
        if not rule_candidates:
            return ""
        top = rule_candidates[0]
        if not top.county:
            return ""
        same_name = [ct for ct in loader.get_all_counties() if ct.name == top.county.name]
        if len(same_name) <= 1:
            return ""
        lines = ["同名区县候选(供消歧):"]
        for ct in same_name[:8]:
            prov = loader.get_by_code(ct.province_code)
            city = loader.get_by_code(ct.city_code)
            p = f"{prov.name}" if prov else "-"
            ci = f"{city.name}" if city else "-"
            lines.append(f"  {ct.code} {ct.name} (省={p} 市={ci})")
        return "\n".join(lines)

    def _build_city_hint_text(self, city_code, loader):
        if not city_code:
            return ""
        try:
            city_code_int = int(city_code)
        except (ValueError, TypeError):
            return ""
        city_info = loader.get_by_code(city_code_int)
        if city_info is None:
            return ""
        prov_info = loader.get_by_code(city_info.province_code) if city_info.province_code else None
        prov_name = prov_info.name if prov_info else "-"
        city_name = city_info.name if city_info.level == "city" else "-"
        same_province = loader.get_same_province_city_codes(city_code_int)
        same_province_names = []
        for code in list(same_province)[:10]:
            ci = loader.get_by_code(code)
            if ci:
                same_province_names.append(ci.name)
        hint = f"业务上下文提示: 用户当前投保地市为 {prov_name} {city_name}(代码{city_code_int})。"
        if same_province_names:
            hint += f"同省地市包括: {'、'.join(same_province_names)}。"
        hint += "若存在同名歧义，优先选择该地市或同省地市的区县。"
        return hint

    def _is_weak_rule_candidates(self, rule_candidates):
        """判断规则候选是否为「弱猜测」：规则未在原文中精确匹配到区县
        （区县缺失或仅靠单字简称/fuzzy 撞字反推）。此时规则候选不完整，
        不应约束 AI 只能从候选中选择，应允许 AI 结合常识自由补全区县。
        典型场景：
        - 地址缺省市区，规则凭撞字反推（如「灵石路」→ 灵石县）
        - 地址只到省市，区县缺失（如「上海灵石路656号」只匹配到上海市，区县为空）
        """
        if not rule_candidates:
            return True
        top = rule_candidates[0]
        return self._is_weak_rule_candidate(top)

    @staticmethod
    def _is_weak_rule_candidate(cand):
        if cand is None:
            return True
        if getattr(cand, "source", "") == "ai":
            return False
        # 区县在原文中精确匹配（full/short）即视为候选完整，非弱猜测。
        # 区县缺失或仅靠 infer/fuzzy 撞字反推时判为弱猜测，允许 AI 自由补全。
        # 这样既覆盖「省市区全缺」场景，也覆盖「只匹配到省市、区县缺失」场景，
        # 同时不影响「区县精确匹配但同名歧义」（如西湖区）的正常约束路径。
        precise = {"full", "short"}
        if cand.county_source in precise:
            return False
        return True

    def _build_system_prompt(self, city_code, weak=False):
        prompt = (
            "你是中国行政区划地址解析专家。任务：根据用户输入的中文地址，选出最匹配的省市区。\n"
            "规则：\n"
        )
        if weak:
            prompt += (
                "1. 规则引擎给出的候选仅为参考，可能存在单字简称或模糊撞字误匹配"
                "（如「48单元」的「单」误匹配「单县」、「灵石路」的「灵石」误匹配「灵石县」）。"
                "若候选与地址明显不符，应拒绝候选，基于常识从全国真实行政区划中选择。\n"
                "   重要：不确定6位区划代码时，province_name/city_name/county_name 必须填写真实名称，"
                "对应的 code 字段可留 null，系统会按名称补全代码。切勿因为不知道代码就留空整个层级"
                "（如知道是「上海市静安区」就填 county_name='静安区'，county_code 留 null）。\n"
            )
        else:
            prompt += (
                "1. 只能从候选列表中选择省市区代码，严禁编造不在候选中的代码。\n"
            )
        prompt += (
            "2. 直辖市(北京/上海/天津/重庆)数据模型：province 填直辖市本身(如'上海市')，"
            "其下辖的区(如'静安区''浦东新区')填到 city 字段，county 字段留 null。"
            "系统会自动把区归到 county 层级输出。即对'上海静安区'应填："
            "province_name='上海市'、city_name='静安区'、county=null。\n"
            "3. village字段填写地址中省市区之后的街道及详细部分，若无则为null。\n"
            "4. 返回1-3个结果，按可能性从高到低排序。\n"
            "5. 当存在同名区县(如多个市都有'城区''市中区''郊区')且地址无足够上下文消歧时，"
            "不要强行猜测，应返回所有同名候选，按城市知名度/可能性排序，并在reason中说明'同名歧义'。\n"
            "6. 当县与市同名(如'伊宁县'与'伊宁市'、'和田县'与'和田市')且简称相同时，"
            "优先考虑'县'，因为日常地址中县名更常被直接使用；若无法确定则两者都返回。\n"
            "7. 区县推断规则：当地址明确写出省市但缺区县时，若能根据街道、路名、小区/楼盘名等"
            "高置信度地唯一确定所属区县（如'无锡市大池路督府天承'→滨湖区、'上海市南京东路'→黄浦区），"
            "必须填入 county_name 并尽量补 county_code（不确定代码时 county_code 可留 null，系统按名称补全）。"
            "仅当无法可靠推断（如存在跨区同名路、信息不足）时才将 county 留 null，并在 reason 中说明'区县无法推断'。"
            "切勿因为地址字面未写区县就直接留空——能推断则必须推断填写。"
        )
        if city_code:
            prompt += "\n8. 若提供了'业务上下文提示'，在存在歧义时必须优先选择提示地市或同省地市的区县。"
        return prompt

    def _build_cost_info(self, usage):
        """根据 token 用量与配置单价构建费用信息。
        usage 为 OpenAI ChatCompletion.usage 对象，可能为 None。
        返回 dict，含 tokens 明细（input_cache_hit/input_cache_miss/output）、总费用 totalCost（人民币元）
        以及本次计费所处时段 isPeak（true=高峰，false=平时）。
        DeepSeek: prompt_tokens = prompt_cache_hit_tokens + prompt_cache_miss_tokens
        """
        if usage is None:
            return self._zero_cost()
        try:
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            cache_hit = int(getattr(usage, "prompt_cache_hit_tokens", 0) or 0)
        except (TypeError, ValueError):
            return self._zero_cost()
        cache_miss = max(prompt_tokens - cache_hit, 0)
        is_peak = self._is_peak_now()
        if is_peak:
            p_hit = self.price_peak_input_cache_hit
            p_miss = self.price_peak_input_cache_miss
            p_out = self.price_peak_output
        else:
            p_hit = self.price_input_cache_hit
            p_miss = self.price_input_cache_miss
            p_out = self.price_output
        total_cost = (
            cache_hit * p_hit
            + cache_miss * p_miss
            + completion_tokens * p_out
        ) / 1_000_000.0
        return {
            "inputCacheHitTokens": cache_hit,
            "inputCacheMissTokens": cache_miss,
            "outputTokens": completion_tokens,
            "totalCost": round(total_cost, 6),
            "isPeak": is_peak,
        }

    @staticmethod
    def _parse_peak_hours(peak_hours):
        """解析高峰时段配置字符串，返回 [(start_min, end_min), ...] 分钟区间列表（左闭右开）。
        格式：多个时段用分号分隔，每个时段 "HH:MM-HH:MM"；非法或空则返回 []。
        时区按北京时间处理（调用方负责使用北京时间判断）。
        """
        if not peak_hours or not peak_hours.strip():
            return []
        ranges = []
        for part in peak_hours.split(";"):
            part = part.strip()
            if not part or "-" not in part:
                continue
            left, right = part.split("-", 1)
            try:
                sh, sm = [int(x) for x in left.strip().split(":", 1)]
                eh, em = [int(x) for x in right.strip().split(":", 1)]
            except (ValueError, IndexError):
                continue
            if not (0 <= sh < 24 and 0 <= sm < 60 and 0 <= eh < 24 and 0 <= em < 60):
                continue
            start_min = sh * 60 + sm
            end_min = eh * 60 + em
            if end_min <= start_min:
                # 不支持跨日或空区间，跳过
                continue
            ranges.append((start_min, end_min))
        return ranges

    def _is_peak_now(self):
        """判断当前北京时间是否处于高峰时段。未配置 peak_ranges 时返回 False。"""
        if not self.peak_ranges:
            return False
        try:
            from datetime import datetime, timezone, timedelta
        except ImportError:
            return False
        tz = timezone(timedelta(hours=8))  # 北京时间 UTC+8
        now = datetime.now(tz)
        minute_of_day = now.hour * 60 + now.minute
        for start_min, end_min in self.peak_ranges:
            if start_min <= minute_of_day < end_min:
                return True
        return False

    @staticmethod
    def _zero_cost():
        """未实际调用 AI API 时的零费用结构（缓存命中/初始化失败/调用异常）。"""
        return {
            "inputCacheHitTokens": 0,
            "inputCacheMissTokens": 0,
            "outputTokens": 0,
            "totalCost": 0.0,
            "isPeak": False,
        }

    def _build_user_prompt(self, address, candidates_text, same_name_text, truncation_text, city_hint_text, weak=False):
        label = "规则解析候选(仅供参考，可能为误匹配)" if weak else "规则解析候选"
        user_prompt = f"待解析地址: {address}\n\n{label}:\n{candidates_text}\n"
        if same_name_text:
            user_prompt += f"\n{same_name_text}\n"
        if truncation_text:
            user_prompt += f"\n{truncation_text}\n"
        if city_hint_text:
            user_prompt += f"\n{city_hint_text}\n"
        if weak:
            user_prompt += (
                "\n请结合常识判断最匹配的省市区。若候选明显为误匹配(如单字简称撞字)，"
                "应拒绝候选并基于常识给出真实存在的区划；若候选确实正确则可采用。"
            )
        else:
            user_prompt += "\n请从候选中选择最匹配的省市区，并提取街道信息。若存在同名歧义请返回所有候选。"
        return user_prompt

    def resolve(self, address, text, rule_candidates, loader, city_code=None):
        if self.enable_cache and self.cache:
            cached = None
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    cached = None
                else:
                    cached = loop.run_until_complete(self.cache.get(address, city_code))
            except RuntimeError:
                cached = None
            if cached is not None:
                # 本地缓存命中，未调用 AI API，不计费
                return self._clone_candidates(cached), True, self._zero_cost()

        try:
            client = self._ensure_sync_client()
        except RuntimeError:
            return [], False, self._zero_cost()

        result, cost_info = self._do_resolve(client, address, text, rule_candidates, loader, city_code, is_async=False)

        if self.enable_cache and self.cache and result:
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_running():
                    loop.run_until_complete(self.cache.put(address, city_code, result))
            except RuntimeError:
                pass
        return result, False, cost_info

    async def resolve_async(self, address, text, rule_candidates, loader, city_code=None):
        if self.enable_cache and self.cache:
            cached = await self.cache.get(address, city_code)
            if cached is not None:
                # 本地缓存命中，未调用 AI API，不计费
                return self._clone_candidates(cached), True, self._zero_cost()

        try:
            client = await self._ensure_async_client()
        except RuntimeError:
            return [], False, self._zero_cost()

        result, cost_info = await self._do_resolve(client, address, text, rule_candidates, loader, city_code, is_async=True)

        if self.enable_cache and self.cache and result:
            await self.cache.put(address, city_code, result)
        return result, False, cost_info

    def _do_resolve(self, client, address, text, rule_candidates, loader, city_code, is_async):
        candidates_text = self._build_candidates_text(rule_candidates, loader)
        same_name_text = self._build_same_name_candidates(rule_candidates, loader)
        truncation_text = self._build_truncation_candidates(rule_candidates, text, loader)
        city_hint_text = self._build_city_hint_text(city_code, loader)

        weak = self._is_weak_rule_candidates(rule_candidates)
        system_prompt = self._build_system_prompt(city_code, weak=weak)
        user_prompt = self._build_user_prompt(address, candidates_text, same_name_text, truncation_text, city_hint_text, weak=weak)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            if is_async:
                return self._call_async(client, messages, loader, text)
            return self._call_sync(client, messages, loader, text)
        except Exception:
            return [], self._zero_cost()

    def _call_sync(self, client, messages, loader, text):
        kwargs = dict(
            model=self.model,
            response_model=AIAddressResponse,
            messages=messages,
            temperature=self.temperature,
            max_retries=self.max_retries,
        )
        if self._extra_body is not None:
            kwargs["extra_body"] = self._extra_body
        resp = client.chat.completions.create(**kwargs)
        # instructor 返回的是结构化 pydantic 对象，原始 ChatCompletion 挂在 _raw_response
        raw = getattr(resp, "_raw_response", None)
        cost_info = self._build_cost_info(getattr(raw, "usage", None))
        return self._parse_response(resp, loader, text), cost_info

    async def _call_async(self, client, messages, loader, text):
        kwargs = dict(
            model=self.model,
            response_model=AIAddressResponse,
            messages=messages,
            temperature=self.temperature,
            max_retries=self.max_retries,
        )
        if self._extra_body is not None:
            kwargs["extra_body"] = self._extra_body
        resp = await client.chat.completions.create(**kwargs)
        raw = getattr(resp, "_raw_response", None)
        cost_info = self._build_cost_info(getattr(raw, "usage", None))
        return self._parse_response(resp, loader, text), cost_info

    def _parse_response(self, resp, loader, text):
        result = []
        for item in resp.results:
            cand = self._to_candidate(item, loader, text)
            if cand is not None:
                result.append(cand)
        return result

    def _clone_candidates(self, candidates):
        cloned = []
        for c in candidates:
            new = Candidate()
            new.province = c.province
            new.city = c.city
            new.county = c.county
            new.village = c.village
            new.score = c.score
            new.match_end = c.match_end
            new.province_source = c.province_source
            new.city_source = c.city_source
            new.county_source = c.county_source
            new.confidence = c.confidence
            new.source = c.source
            new.need_ai_review = c.need_ai_review
            new.reason = c.reason
            cloned.append(new)
        return cloned

    def _locate_match_end(self, text, province, city, county):
        end = 0
        for info in (county, city, province):
            if info is None:
                continue
            idx = text.rfind(info.name)
            if idx >= 0:
                end = max(end, idx + len(info.name))
                break
        if end == 0:
            for info in (county, city, province):
                if info is None:
                    continue
                idx = text.find(info.name)
                if idx >= 0:
                    end = max(end, idx + len(info.name))
                    break
        return end

    # 数据集里直辖市的省级代码是 xx0100（如 310100），而国标省级码是 xx0000（如 310000）。
    # AI 按国标返回 xx0000 时数据集查不到，这里做反向兼容映射。
    _MUNI_PROV_AI_COMPAT = {110000: 110100, 310000: 310100, 120000: 120100, 500000: 500100}

    def _to_candidate(self, item: AIAddressItem, loader, text):
        try:
            prov_code = int(item.province_code) if item.province_code else 0
            city_code = int(item.city_code) if item.city_code else 0
            county_code = int(item.county_code) if item.county_code else 0
        except (ValueError, TypeError):
            return None

        # 优先按 code 查；code 缺失、查不到、或查到的名称与 AI 给的名称不符时按 name 反查
        # （AI 常知道名称但不知道代码，会瞎填 code，需以 name 为准）
        province = loader.get_by_code(prov_code) if prov_code else None
        if province is None and prov_code in self._MUNI_PROV_AI_COMPAT:
            province = loader.get_by_code(self._MUNI_PROV_AI_COMPAT[prov_code])
        if item.province_name and (province is None or province.name != item.province_name):
            province_by_name = loader.find_by_name(item.province_name, level="province")
            if province_by_name is not None:
                province = province_by_name

        city = loader.get_by_code(city_code) if city_code else None
        if item.city_name and (city is None or city.name != item.city_name):
            prov_code_for_city = province.code if province and province.level == "province" else (province.parent_code if province else 0)
            city_by_name = loader.find_by_name(item.city_name, level="city", province_code=prov_code_for_city) if prov_code_for_city else loader.find_by_name(item.city_name, level="city")
            if city_by_name is not None:
                city = city_by_name

        county = loader.get_by_code(county_code) if county_code else None
        if item.county_name and (county is None or county.name != item.county_name):
            county_by_name = loader.find_by_name(item.county_name, level="county", city_code=city.code) if city else loader.find_by_name(item.county_name, level="county")
            if county_by_name is not None:
                county = county_by_name

        # 从属关系校验：AI 可能给出省和市不匹配的错误组合（如浙江省+南昌市），
        # 检测到不一致时丢弃不一致的层级，避免拼出错误组合。
        if province and city:
            prov_code_for_city = province.code if province.level == "province" else province.parent_code
            if city.province_code != prov_code_for_city:
                # 省市不匹配，丢弃较不可信的一级：优先保留有 AI name 支持的或 city（通常更细）
                if item.city_name and not item.province_name:
                    province = None
                elif item.province_name and not item.city_name:
                    city = None
                else:
                    # 两者都有 name，无法判断，以 city 为准反推 province
                    real_prov = loader.get_by_code(city.province_code)
                    province = real_prov if real_prov else province
        if city and county:
            if county.city_code != city.code:
                # 市县不匹配，以 county 为准反推 city
                real_city = loader.get_by_code(county.city_code)
                if real_city:
                    city = real_city
                    real_prov = loader.get_by_code(city.province_code)
                    if real_prov:
                        province = real_prov

        if not province and not city and not county:
            return None

        cand = Candidate()
        cand.province = province
        cand.city = city
        cand.county = county
        cand.province_source = "ai"
        cand.city_source = "ai"
        cand.county_source = "ai"
        cand.source = "ai"
        cand.confidence = float(item.confidence) if item.confidence else 70.0
        cand.score = 200
        cand.match_end = self._locate_match_end(text, province, city, county)
        cand.reason = item.reason or "AI兜底解析"
        if item.village:
            cand.village = item.village
        return cand
