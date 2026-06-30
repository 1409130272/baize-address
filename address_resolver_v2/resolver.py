import re
import asyncio
from .data_loader import AreaDataLoader, AreaInfo
from .fuzzy_matcher import fuzzy_match
from .alias_dict import make_short_name, ETHNIC_FRAGMENTS, ADMIN_WORDS

_FULL_WIDTH_MAP = {chr(i): chr(i - 0xFEE0) for i in range(0xFF01, 0xFF5F)}
_FULL_WIDTH_MAP["　"] = " "

_SINGLE_CHAR_PROVINCE_SHORT = {"京", "津", "沪", "渝", "冀", "晋", "辽", "吉", "黑", "苏", "浙", "皖", "闽", "赣", "鲁", "豫", "鄂", "湘", "粤", "桂", "琼", "川", "蜀", "黔", "贵", "滇", "云", "陕", "秦", "甘", "陇", "青", "藏", "蒙", "宁", "新", "港", "澳", "台"}

_SUFFIX_CHARS = ("区", "县", "市", "旗", "省", "州", "盟")

_STREET_SUFFIX_WORDS = ("大道", "大厦", "广场", "小区", "花园", "公寓", "新村", "嘉园", "名邸", "路", "街", "弄", "巷", "号", "室", "栋", "幢", "楼", "院", "门", "座")

_BUILDING_WORDS = ("医院", "学校", "公园", "中心", "大楼", "商城", "酒店", "宾馆", "体育馆", "图书馆", "火车站", "汽车站", "机场")

_MUNICIPALITY_CODES = {110100, 310100, 120100, 500100}

_MUNI_PROV_NORMALIZE = {110100: 110000, 310100: 310000, 120100: 120000, 500100: 500000}

_NO_DISTRICT_CITY_CODES = {442000, 441900, 460400, 620200}


def _preprocess(address):
    if not address:
        return ""
    text = address.strip()
    text = "".join(_FULL_WIDTH_MAP.get(c, c) for c in text)
    text = re.sub(r"\s+", "", text)
    return text


class MatchPiece:
    def __init__(self, start, end, word, info, source, score):
        self.start = start
        self.end = end
        self.word = word
        self.info = info
        self.source = source
        self.score = score


class Candidate:
    def __init__(self):
        self.province = None
        self.city = None
        self.county = None
        self.village = None
        self.score = 0
        self.match_end = 0
        self.province_source = None
        self.city_source = None
        self.county_source = None
        self.confidence = 0
        self.source = "rule"
        self.need_ai_review = False
        self.reason = ""
        self.guided = False

    def to_result(self, address):
        return {
            "address": address,
            "provinceCode": str(self.province.code) if self.province else None,
            "provinceName": self.province.name if self.province else None,
            "cityCode": str(self.city.code) if self.city else None,
            "cityName": self.city.name if self.city else None,
            "countyCode": str(self.county.code) if self.county else None,
            "countyName": self.county.name if self.county else None,
            "village": self.village,
            "confidence": int(round(self.confidence)),
            "source": self.source,
            "reason": self.reason,
        }


class ResolveResult:
    def __init__(self, candidates, ai_used=False, ai_cache_hit=False, ai_attempted=False, ai_cost_info=None):
        self.candidates = candidates
        self.ai_used = ai_used
        self.ai_cache_hit = ai_cache_hit
        self.ai_attempted = ai_attempted
        # 本次调用 AI API 的费用信息 dict：
        #   {inputCacheHitTokens, inputCacheMissTokens, outputTokens, totalCost(人民币元), isPeak(是否高峰时段)}
        # 仅在实际调用 AI API（非本地缓存命中）时填实际值，否则为零值结构
        self.ai_cost_info = ai_cost_info or {
            "inputCacheHitTokens": 0,
            "inputCacheMissTokens": 0,
            "outputTokens": 0,
            "totalCost": 0.0,
            "isPeak": False,
        }

    @property
    def empty(self):
        return not self.candidates


class AddressResolver:
    def __init__(self, excel_path, ai_resolver=None):
        self.loader = AreaDataLoader(excel_path)
        self.ai_resolver = ai_resolver
        from .config import AITriggerConfig
        self._ai_confidence_threshold = AITriggerConfig.confidence_threshold
        self._ai_ambiguity_gap = AITriggerConfig.ambiguity_gap
        self._ai_min_confidence = AITriggerConfig.min_confidence

    def resolve(self, address, max_candidates=3, use_ai=False, city_code=None):
        if not address or not address.strip():
            return ResolveResult([])
        text = _preprocess(address)
        if not text:
            return ResolveResult([])

        candidates = self._rule_resolve(text)

        if city_code:
            try:
                cc_int = int(city_code)
            except (ValueError, TypeError):
                cc_int = 0
            if cc_int > 0:
                guided = self._city_code_guided_resolve(text, cc_int)
                if guided:
                    candidates.extend(guided)
                    candidates = self._dedup_and_sort(candidates)
                    for c in candidates:
                        c.village = self._extract_village(text, c)
                        c.confidence = self._calc_confidence(c, candidates, text)
                self._apply_city_hint(candidates, cc_int)

        ai_used = False
        ai_cache_hit = False
        ai_attempted = False
        ai_cost_info = None
        if use_ai and self.ai_resolver and self._need_ai(candidates):
            ai_attempted = True
            try:
                ai_cands, ai_cache_hit, ai_cost_info = self.ai_resolver.resolve(address, text, candidates, self.loader, city_code=city_code)
            except Exception:
                ai_cands = []
            if ai_cands:
                ai_used = True
                for ac in ai_cands:
                    if ac.village is None:
                        ac.village = self._extract_village(text, ac)
                    ac.confidence = max(ac.confidence, self._ai_min_confidence)
                    self._normalize_candidate(ac)
                for c in candidates:
                    self._normalize_candidate(c)
                candidates = self._merge_ai_candidates(candidates, ai_cands)
                if city_code:
                    self._apply_city_hint(candidates, city_code)

        for c in candidates:
            self._normalize_candidate(c)
            new_end = self._consume_admin_residue(text, c)
            if new_end > c.match_end:
                c.match_end = new_end
                c.village = self._extract_village(text, c)
        for c in candidates:
            c.confidence = self._calc_confidence(c, candidates, text)
        candidates.sort(key=lambda c: (-c.confidence, -c.score))
        return ResolveResult(candidates[:max_candidates], ai_used=ai_used, ai_cache_hit=ai_cache_hit, ai_attempted=ai_attempted, ai_cost_info=ai_cost_info)

    def _apply_city_hint(self, candidates, city_code):
        try:
            city_code_int = int(city_code)
        except (ValueError, TypeError):
            return
        if city_code_int <= 0:
            return
        same_province_codes = self.loader.get_same_province_city_codes(city_code_int)
        for c in candidates:
            cand_city_code = c.city.code if c.city else 0
            if cand_city_code == city_code_int:
                c.confidence = min(100.0, c.confidence + 20)
            elif cand_city_code in same_province_codes:
                c.confidence = min(100.0, c.confidence + 10)

    def _city_code_guided_resolve(self, text, city_code):
        city_info = self.loader.get_by_code(city_code)
        if not city_info:
            return []
        if city_info.level == "province" and city_info.code in _MUNICIPALITY_CODES:
            prov_info = city_info
            sub_areas = self.loader.get_cities(city_info.code)
            target_level = "city"
        elif city_info.level == "city":
            prov_info = self.loader.get_by_code(city_info.province_code)
            if not prov_info:
                return []
            sub_areas = self.loader.get_counties(city_code)
            target_level = "county"
        else:
            return []
        for s, e, w, infos in self.loader.search_full(text):
            for info in infos:
                if info.level == "province" and info.code != prov_info.code:
                    return []
        guided = []
        for area in sub_areas:
            if area.name and area.name in text:
                idx = text.find(area.name)
                cand = Candidate()
                cand.province = prov_info
                cand.city = city_info if target_level == "county" else prov_info
                cand.county = area if target_level == "county" else area
                cand.province_source = "infer"
                cand.city_source = "infer"
                cand.county_source = "full"
                cand.match_end = idx + len(area.name)
                cand.score = 90
                cand.guided = True
                guided.append(cand)
                continue
            short = make_short_name(area.name, target_level)
            if short and len(short) >= 2 and short != area.name and short in text:
                idx = text.find(short)
                if idx + len(short) < len(text) and text[idx + len(short)] in _SUFFIX_CHARS:
                    cand = Candidate()
                    cand.province = prov_info
                    cand.city = city_info if target_level == "county" else prov_info
                    cand.county = area if target_level == "county" else area
                    cand.province_source = "infer"
                    cand.city_source = "infer"
                    cand.county_source = "short"
                    cand.match_end = idx + len(short)
                    cand.score = 75
                    cand.guided = True
                    guided.append(cand)
        return guided

    def _normalize_candidate(self, cand):
        if cand.province and cand.province.code in _MUNICIPALITY_CODES:
            orig_prov_code = cand.province.code
            promoted = False
            if cand.city and not cand.county and cand.city.parent_code == orig_prov_code:
                cand.county = cand.city
                cand.county_source = cand.city_source
                cand.city = cand.province
                cand.city_source = "infer"
                promoted = True
            elif not cand.city:
                cand.city = cand.province
                cand.city_source = "infer"
            new_prov_code = _MUNI_PROV_NORMALIZE[orig_prov_code]
            cand.province = AreaInfo(
                new_prov_code, cand.province.name, "province", 0,
            )
            # AI 候选被系统做了直辖市规范化（区从 city 提升到 county），
            # 需在 reason 末尾追加系统规范化说明，避免与原始 AI 描述冲突
            # （AI 按 prompt 把区填到 city 字段、reason 写"county留null"，
            # 系统提升后输出实际 county=区，需澄清）
            if promoted and getattr(cand, "source", "") == "ai":
                note = f"系统已将直辖市下辖区({cand.county.name})规范化至county字段"
                if note not in (cand.reason or ""):
                    cand.reason = cand.reason.rstrip("。；;.")
                    cand.reason = cand.reason + "；" + note
        if cand.city and cand.city.code in _NO_DISTRICT_CITY_CODES and not cand.county:
            city_info = cand.city
            cand.county = AreaInfo(
                city_info.code, "市辖区", "county", city_info.code,
                province_code=city_info.province_code, province_name=city_info.province_name,
                city_code=city_info.code, city_name=city_info.name,
            )
            cand.county_source = "infer"

    async def resolve_async(self, address, max_candidates=3, use_ai=False, city_code=None):
        if not address or not address.strip():
            return ResolveResult([])
        text = _preprocess(address)
        if not text:
            return ResolveResult([])

        candidates = await asyncio.to_thread(self._rule_resolve, text)

        if city_code:
            try:
                cc_int = int(city_code)
            except (ValueError, TypeError):
                cc_int = 0
            if cc_int > 0:
                guided = await asyncio.to_thread(self._city_code_guided_resolve, text, cc_int)
                if guided:
                    candidates.extend(guided)
                    candidates = self._dedup_and_sort(candidates)
                    for c in candidates:
                        c.village = self._extract_village(text, c)
                        c.confidence = self._calc_confidence(c, candidates, text)
                self._apply_city_hint(candidates, cc_int)

        ai_used = False
        ai_cache_hit = False
        ai_attempted = False
        ai_cost_info = None
        if use_ai and self.ai_resolver and self._need_ai(candidates):
            ai_attempted = True
            try:
                ai_cands, ai_cache_hit, ai_cost_info = await self.ai_resolver.resolve_async(address, text, candidates, self.loader, city_code=city_code)
            except Exception:
                ai_cands = []
            if ai_cands:
                ai_used = True
                for ac in ai_cands:
                    if ac.village is None:
                        ac.village = self._extract_village(text, ac)
                    ac.confidence = max(ac.confidence, self._ai_min_confidence)
                    self._normalize_candidate(ac)
                for c in candidates:
                    self._normalize_candidate(c)
                candidates = self._merge_ai_candidates(candidates, ai_cands)
                if city_code:
                    self._apply_city_hint(candidates, city_code)

        for c in candidates:
            self._normalize_candidate(c)
            new_end = self._consume_admin_residue(text, c)
            if new_end > c.match_end:
                c.match_end = new_end
                c.village = self._extract_village(text, c)
        for c in candidates:
            c.confidence = self._calc_confidence(c, candidates, text)
        candidates.sort(key=lambda c: (-c.confidence, -c.score))
        return ResolveResult(candidates[:max_candidates], ai_used=ai_used, ai_cache_hit=ai_cache_hit, ai_attempted=ai_attempted, ai_cost_info=ai_cost_info)

    def _rule_resolve(self, text):
        province_pieces = self._match_province(text)
        city_pieces = self._match_city(text, province_pieces)
        county_pieces = self._match_county(text, province_pieces, city_pieces)

        city_pieces = self._remove_covered_by_county(city_pieces, county_pieces)
        county_pieces = self._remove_covered_by_city(county_pieces, city_pieces)

        candidates = self._combine(text, province_pieces, city_pieces, county_pieces)

        if not candidates:
            candidates = self._fuzzy_resolve(text)

        candidates = self._dedup_and_sort(candidates)
        for c in candidates:
            c.village = self._extract_village(text, c)
            c.confidence = self._calc_confidence(c, candidates, text)
        return candidates

    def _need_ai(self, candidates):
        if not candidates:
            return True
        top = candidates[0]
        if getattr(top, "need_ai_review", False):
            return True
        if top.confidence <= self._ai_confidence_threshold:
            return True
        if len(candidates) >= 2 and (candidates[0].confidence - candidates[1].confidence) < self._ai_ambiguity_gap:
            return True
        return False

    def _is_weak_rule_candidate(self, cand):
        """规则候选为「弱猜测」：规则未在原文中精确匹配到区县
        （区县缺失或仅靠 infer/fuzzy 撞字反推）。此时候选不完整，
        允许 AI 自由补全区县后应被丢弃。
        典型场景：地址缺省市区规则凭撞字反推（如「灵石路」→ 灵石县）、
        地址只到省市区县缺失（如「上海灵石路656号」只匹配到上海市）。"""
        if cand is None:
            return True
        if getattr(cand, "source", "") == "ai":
            return False
        precise = {"full", "short"}
        if cand.county_source in precise:
            return False
        return True

    def _merge_ai_candidates(self, rule_cands, ai_cands):
        merged = {}
        for c in ai_cands:
            key = (c.province.code if c.province else 0, c.city.code if c.city else 0, c.county.code if c.county else 0)
            if key not in merged or c.confidence > merged[key].confidence:
                merged[key] = c
        # 若 AI 已给出结果，丢弃规则的「弱猜测」候选，避免乱猜结果污染输出
        drop_weak = bool(merged)
        for c in rule_cands:
            if drop_weak and self._is_weak_rule_candidate(c):
                continue
            key = (c.province.code if c.province else 0, c.city.code if c.city else 0, c.county.code if c.county else 0)
            if key not in merged or c.confidence > merged[key].confidence:
                merged[key] = c
        return list(merged.values())

    def _remove_covered_by_county(self, city_pieces, county_pieces):
        county_full_spans = [(p.start, p.end) for p in county_pieces if p.source == "full"]
        result = []
        for cp in city_pieces:
            covered = False
            for cs, ce in county_full_spans:
                if cp.start >= cs and cp.end <= ce and cp.end < ce:
                    covered = True
                    break
                if cp.start == cs and cp.end < ce:
                    covered = True
                    break
            if not covered:
                result.append(cp)
        return result

    def _remove_covered_by_city(self, county_pieces, city_pieces):
        city_full_spans = [(p.start, p.end) for p in city_pieces if p.source == "full"]
        result = []
        for ctp in county_pieces:
            covered = False
            for cs, ce in city_full_spans:
                if ctp.start >= cs and ctp.end <= ce and ctp.end < ce:
                    covered = True
                    break
            if not covered:
                result.append(ctp)
        return result

    def _match_province(self, text):
        pieces = []
        for start, end, word, infos in self.loader.search_full(text):
            for info in infos:
                if info.level == "province":
                    pieces.append(MatchPiece(start, end, word, info, "full", 100))
        for start, end, word, infos in self.loader.search_short(text):
            if self._is_short_invalid(text, start, end, word):
                continue
            for info in infos:
                if info.level == "province":
                    pieces.append(MatchPiece(start, end, word, info, "short", 80))
        return pieces

    def _match_city(self, text, province_pieces):
        full_pieces = []
        short_pieces = []
        for start, end, word, infos in self.loader.search_full(text):
            for info in infos:
                if info.level == "city":
                    full_pieces.append(MatchPiece(start, end, word, info, "full", 100))
        for start, end, word, infos in self.loader.search_short(text):
            if self._is_short_invalid(text, start, end, word):
                continue
            for info in infos:
                if info.level == "city":
                    short_pieces.append(MatchPiece(start, end, word, info, "short", 80))

        pieces = self._merge_full_short(full_pieces, short_pieces)

        if province_pieces:
            filtered = []
            for p in pieces:
                for pp in province_pieces:
                    if p.info.province_code == pp.info.code and p.start >= pp.end:
                        filtered.append(p)
                        break
            if filtered:
                return filtered
        return pieces

    def _match_county(self, text, province_pieces, city_pieces):
        full_pieces = []
        short_pieces = []
        for start, end, word, infos in self.loader.search_full(text):
            for info in infos:
                if info.level == "county":
                    full_pieces.append(MatchPiece(start, end, word, info, "full", 100))
        for start, end, word, infos in self.loader.search_short(text):
            if self._is_short_invalid(text, start, end, word):
                continue
            if self._is_county_short_street_conflict(text, start, end, word):
                continue
            for info in infos:
                if info.level == "county":
                    short_pieces.append(MatchPiece(start, end, word, info, "short", 80))

        pieces = self._merge_full_short(full_pieces, short_pieces)

        if city_pieces:
            filtered = []
            for p in pieces:
                for cp in city_pieces:
                    if p.info.city_code == cp.info.code and p.start >= cp.end:
                        filtered.append(p)
                        break
            if filtered:
                return filtered

        if province_pieces:
            filtered = []
            for p in pieces:
                for pp in province_pieces:
                    if p.info.province_code == pp.info.code and p.start >= pp.end:
                        filtered.append(p)
                        break
            if filtered:
                return filtered
        return pieces

    def _merge_full_short(self, full_pieces, short_pieces):
        full_spans = {(p.start, p.end) for p in full_pieces}
        result = list(full_pieces)
        for sp in short_pieces:
            overlap = False
            for fs, fe in full_spans:
                if sp.start < fe and sp.end > fs:
                    overlap = True
                    break
            if not overlap:
                result.append(sp)
        return result

    def _is_short_invalid(self, text, start, end, word):
        if end < len(text):
            next_char = text[end]
            if next_char in _SUFFIX_CHARS:
                if end + 1 >= len(text):
                    return True
                rest = text[end:]
                has_area = False
                for s, e, w, d in self.loader.search_full(rest):
                    for info in d:
                        if info.level in ("county", "city") and s == 0:
                            has_area = True
                            break
                    if has_area:
                        break
                if not has_area:
                    for s, e, w, d in self.loader.search_short(rest):
                        for info in d:
                            if info.level in ("county", "city") and s == 0 and len(w) >= 2:
                                has_area = True
                                break
                        if has_area:
                            break
                if not has_area:
                    if self._is_short_plus_suffix_full(text, start, end):
                        return True
        if len(word) == 1 and word in _SINGLE_CHAR_PROVINCE_SHORT:
            return True
        return False

    def _is_short_plus_suffix_full(self, text, start, end):
        if end >= len(text):
            return False
        combined = text[start:end + 1]
        for s, e, w, d in self.loader.search_full(combined):
            if s == 0 and e == len(combined):
                return True
        return False

    def _is_county_short_street_conflict(self, text, start, end, word):
        if end < len(text):
            rest = text[end:]
            for sw in _STREET_SUFFIX_WORDS:
                if rest.startswith(sw):
                    return True
        return False

    def _combine(self, text, province_pieces, city_pieces, county_pieces):
        candidates = []

        if province_pieces:
            for pp in province_pieces:
                matched_cities = [c for c in city_pieces if c.start >= pp.end and c.info.province_code == pp.info.code]

                if matched_cities:
                    for cp in matched_cities:
                        matched_counties = [ct for ct in county_pieces if ct.start >= cp.end and ct.info.city_code == cp.info.code]
                        if matched_counties:
                            for ctp in matched_counties:
                                cand = Candidate()
                                cand.province = pp.info
                                cand.city = cp.info
                                cand.county = ctp.info
                                cand.province_source = pp.source
                                cand.city_source = cp.source
                                cand.county_source = ctp.source
                                cand.score = pp.score + cp.score + ctp.score + 10
                                cand.match_end = ctp.end
                                candidates.append(cand)
                        else:
                            overlap_counties = [ct for ct in county_pieces if ct.start >= pp.end and ct.info.city_code == cp.info.code and ct.start < cp.end]
                            if overlap_counties and cp.source == "full":
                                short_city = self._find_short_city(text, cp, province_pieces, pp)
                                if short_city:
                                    for ctp in overlap_counties:
                                        if ctp.start >= short_city.end:
                                            cand = Candidate()
                                            cand.province = pp.info
                                            cand.city = short_city.info
                                            cand.county = ctp.info
                                            cand.province_source = pp.source
                                            cand.city_source = short_city.source
                                            cand.county_source = ctp.source
                                            cand.score = pp.score + short_city.score + ctp.score + 10
                                            cand.match_end = ctp.end
                                            candidates.append(cand)
                                    continue
                            cand = Candidate()
                            cand.province = pp.info
                            cand.city = cp.info
                            cand.province_source = pp.source
                            cand.city_source = cp.source
                            cand.score = pp.score + cp.score + 5
                            cand.match_end = cp.end
                            candidates.append(cand)
                else:
                    overlap_cities = [c for c in city_pieces if c.start < pp.end and c.end > pp.start and c.info.province_code != pp.info.code]
                    if overlap_cities:
                        for cp in overlap_cities:
                            real_prov = self.loader.get_by_code(cp.info.province_code)
                            matched_counties = [ct for ct in county_pieces if ct.start >= cp.end and ct.info.city_code == cp.info.code]
                            if matched_counties:
                                for ctp in matched_counties:
                                    cand = Candidate()
                                    cand.province = real_prov
                                    cand.city = cp.info
                                    cand.county = ctp.info
                                    cand.province_source = "infer"
                                    cand.city_source = cp.source
                                    cand.county_source = ctp.source
                                    cand.score = cp.score + ctp.score + 5
                                    cand.match_end = ctp.end
                                    candidates.append(cand)
                            else:
                                cand = Candidate()
                                cand.province = real_prov
                                cand.city = cp.info
                                cand.province_source = "infer"
                                cand.city_source = cp.source
                                cand.score = cp.score + 3
                                cand.match_end = cp.end
                                candidates.append(cand)
                        continue
                    matched_counties = [ct for ct in county_pieces if ct.start >= pp.end and ct.info.province_code == pp.info.code]
                    if matched_counties:
                        for ctp in matched_counties:
                            city_info = self.loader.get_by_code(ctp.info.city_code)
                            cand = Candidate()
                            cand.province = pp.info
                            cand.city = city_info
                            cand.county = ctp.info
                            cand.province_source = pp.source
                            cand.city_source = "infer"
                            cand.county_source = ctp.source
                            cand.score = pp.score + ctp.score + 5
                            cand.match_end = ctp.end
                            candidates.append(cand)
                    else:
                        cand = Candidate()
                        cand.province = pp.info
                        cand.province_source = pp.source
                        cand.match_end = pp.end
                        cand.score = pp.score
                        candidates.append(cand)
        elif city_pieces:
            for cp in city_pieces:
                matched_counties = [ct for ct in county_pieces if ct.start >= cp.end and ct.info.city_code == cp.info.code]
                if matched_counties:
                    for ctp in matched_counties:
                        province_info = self.loader.get_by_code(cp.info.province_code)
                        cand = Candidate()
                        cand.province = province_info
                        cand.city = cp.info
                        cand.county = ctp.info
                        cand.province_source = "infer"
                        cand.city_source = cp.source
                        cand.county_source = ctp.source
                        cand.score = cp.score + ctp.score + 8
                        cand.match_end = ctp.end
                        candidates.append(cand)
                else:
                    province_info = self.loader.get_by_code(cp.info.province_code)
                    cand = Candidate()
                    cand.province = province_info
                    cand.city = cp.info
                    cand.province_source = "infer"
                    cand.city_source = cp.source
                    cand.score = cp.score + 3
                    cand.match_end = cp.end
                    candidates.append(cand)
        elif county_pieces:
            for ctp in county_pieces:
                city_info = self.loader.get_by_code(ctp.info.city_code)
                province_info = self.loader.get_by_code(ctp.info.province_code) if city_info else None
                cand = Candidate()
                cand.province = province_info
                cand.city = city_info
                cand.county = ctp.info
                cand.province_source = "infer" if province_info else None
                cand.city_source = "infer" if city_info else None
                cand.county_source = ctp.source
                cand.score = ctp.score + 3
                cand.match_end = ctp.end
                candidates.append(cand)

        return candidates

    def _find_short_city(self, text, full_city, province_pieces, pp):
        for start, end, word, infos in self.loader.search_short(text):
            if self._is_short_invalid(text, start, end, word):
                continue
            for info in infos:
                if info.level == "city" and info.code == full_city.info.code:
                    if start >= pp.end and start >= full_city.start and end <= full_city.end and end < full_city.end:
                        return MatchPiece(start, end, word, info, "short", 80)
        return None

    def _fuzzy_resolve(self, text):
        candidates = []
        segments = re.findall(r"[\u4e00-\u9fa5]{2,8}", text)
        if not segments:
            return candidates

        county_hits = []
        city_hits = []
        for seg in segments:
            for info, score, method in fuzzy_match(seg, self.loader.get_all_cities(), max_distance=1):
                city_hits.append((seg, info, score))
            for info, score, method in fuzzy_match(seg, self.loader.get_all_counties(), max_distance=2):
                county_hits.append((seg, info, score))

        for seg, info, score in county_hits:
            city_info = self.loader.get_by_code(info.city_code)
            province_info = self.loader.get_by_code(info.province_code) if city_info else None
            cand = Candidate()
            cand.province = province_info
            cand.city = city_info
            cand.county = info
            cand.province_source = "fuzzy" if province_info else None
            cand.city_source = "fuzzy" if city_info else None
            cand.county_source = "fuzzy"
            cand.score = score
            idx = text.find(seg)
            cand.match_end = idx + len(seg) if idx >= 0 else len(text)
            candidates.append(cand)

        for seg, info, score in city_hits:
            province_info = self.loader.get_by_code(info.province_code)
            cand = Candidate()
            cand.province = province_info
            cand.city = info
            cand.province_source = "fuzzy" if province_info else None
            cand.city_source = "fuzzy"
            cand.score = score
            idx = text.find(seg)
            cand.match_end = idx + len(seg) if idx >= 0 else len(text)
            candidates.append(cand)

        return candidates

    def _dedup_and_sort(self, candidates):
        seen = set()
        unique = []
        for c in candidates:
            key = (
                c.province.code if c.province else 0,
                c.city.code if c.city else 0,
                c.county.code if c.county else 0,
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(c)
        unique.sort(key=lambda c: (-c.score, -c.match_end))
        return unique

    def _extract_village(self, text, candidate):
        end = candidate.match_end
        if end <= 0 or end >= len(text):
            return None
        village = text[end:]
        village = village.lstrip(" ,，、。.·#-—_")
        if not village:
            return None
        return village

    def _consume_admin_residue(self, text, candidate):
        end = candidate.match_end
        if end <= 0 or end >= len(text):
            return end
        admin_name = None
        if candidate.county and candidate.county_source == "short":
            admin_name = candidate.county.name
        elif candidate.city and candidate.city_source == "short" and not candidate.county:
            admin_name = candidate.city.name
        if not admin_name or len(admin_name) < 4 or "自治" not in admin_name:
            return end
        rest = text[end:]
        county_chars = set(admin_name)
        pos = 0
        n = len(rest)
        while pos < n:
            remaining = rest[pos:]
            if any(remaining.startswith(sw) for sw in _STREET_SUFFIX_WORDS):
                break
            matched = False
            for aw in ADMIN_WORDS:
                if remaining.startswith(aw):
                    pos += len(aw)
                    matched = True
                    break
            if matched:
                continue
            for ef in ETHNIC_FRAGMENTS:
                if remaining.startswith(ef):
                    pos += len(ef)
                    matched = True
                    break
            if matched:
                continue
            ch = rest[pos]
            if ch in _SUFFIX_CHARS:
                next_pos = pos + 1
                if next_pos < n:
                    next_rem = rest[next_pos:]
                    if any(next_rem.startswith(sw) for sw in _STREET_SUFFIX_WORDS):
                        break
                    next_ch = rest[next_pos]
                    if next_ch in county_chars or next_ch in _SUFFIX_CHARS or self._starts_with_ethnic_or_admin(next_rem):
                        pos += 1
                        continue
                    break
                else:
                    pos += 1
                    continue
            if ch in county_chars:
                pos += 1
                continue
            break
        return end + pos

    @staticmethod
    def _starts_with_ethnic_or_admin(s):
        for ef in ETHNIC_FRAGMENTS:
            if s.startswith(ef):
                return True
        for aw in ADMIN_WORDS:
            if s.startswith(aw):
                return True
        return False

    def _calc_confidence(self, cand, all_candidates, text):
        reasons = []
        if getattr(cand, "guided", False):
            if cand.county_source == "full":
                confidence = 90.0
                reasons.append("cityCode引导(区县全称匹配)")
            else:
                confidence = 75.0
                reasons.append("cityCode引导(区县简称匹配)")
            if cand.province and cand.city and cand.county:
                reasons.append("省市区层级完整")
            cand.reason = "；".join(reasons) + f"；最终置信度{confidence:.0f}"
            return confidence
        # AI 候选保留其自身的置信度与理由，不按规则重算
        # （规则打分会把 ai source 误判为"全称匹配"给 100 分，覆盖 AI 的真实判断，
        # 导致缺区地址也显示 100 分。AI 的 confidence 在 resolve 流程中已做下限保护。）
        if getattr(cand, "source", "") == "ai":
            confidence = float(cand.confidence)
            if confidence < 0:
                confidence = 0
            if confidence > 100:
                confidence = 100
            reason = cand.reason or "AI兜底解析"
            if "最终置信度" not in reason:
                reason = f"{reason}；最终置信度{confidence:.0f}"
            cand.reason = reason
            return confidence
        sources = [s for s in (cand.province_source, cand.city_source, cand.county_source) if s]
        if not sources:
            base = 50
            reasons.append("无匹配层级")
        elif "fuzzy" in sources:
            base = 60
            reasons.append("模糊匹配")
        elif "infer" in sources and "full" not in sources:
            base = 70
            reasons.append("简称+推断匹配")
        elif "short" in sources:
            base = 80
            reasons.append("简称匹配")
        else:
            base = 100
            reasons.append("全称匹配")

        has_prov = cand.province is not None
        has_city = cand.city is not None
        has_county = cand.county is not None
        if has_prov and has_city and has_county:
            level_bonus = 20
            reasons.append("省市区层级完整")
        elif has_prov and has_city:
            level_bonus = 10
            reasons.append("省市层级完整")
        elif has_prov or has_city:
            level_bonus = 5
            reasons.append("仅省或市级")
        else:
            level_bonus = 0

        stability = 10
        if len(all_candidates) >= 2:
            if (all_candidates[0].score - all_candidates[1].score) < 15:
                stability = -20
                reasons.append("候选差异小存在歧义")

        village_penalty = 0
        if cand.village:
            if any(ch in cand.village for ch in _SUFFIX_CHARS):
                village_penalty = -25
                cand.need_ai_review = True
                reasons.append("街道残留区划后缀")
            elif cand.village[:1] in ("路", "街", "弄", "巷", "号", "道"):
                village_penalty = -25
                cand.need_ai_review = True
                reasons.append("街道被截断")

        same_name_penalty = 0
        if cand.county:
            same_name_count = sum(1 for ct in self.loader.get_all_counties() if ct.name == cand.county.name)
            if same_name_count > 1:
                same_name_penalty = -15
                reasons.append(f"同名区县({same_name_count}个)")

        building_conflict_penalty = 0
        if cand.county and same_name_penalty and cand.village:
            for bw in _BUILDING_WORDS:
                if cand.village.startswith(bw):
                    building_conflict_penalty = -10
                    cand.need_ai_review = True
                    reasons.append("同名区县+建筑名词")
                    break

        single_char_short_penalty = 0
        if cand.county and cand.county_source == "short":
            short_name = make_short_name(cand.county.name, "county")
            if short_name and len(short_name) == 1:
                single_char_short_penalty = -25
                cand.need_ai_review = True
                reasons.append("单字区县简称风险")

        truncation_penalty = 0
        for info, source in ((cand.county, cand.county_source), (cand.city, cand.city_source)):
            if info and source == "full":
                for s, e, w, infos in self.loader.search_full(text):
                    for fi in infos:
                        if fi.code != info.code and w.endswith(info.name) and len(w) > len(info.name) and e == cand.match_end:
                            truncation_penalty = -30
                            cand.need_ai_review = True
                            reasons.append("检测到截断匹配")
                            break
                    if truncation_penalty:
                        break
            if truncation_penalty:
                break

        county_missing_penalty = 0
        if not cand.county:
            if cand.village and cand.village[:1] in ("路", "街", "弄", "巷", "号", "道"):
                county_missing_penalty = -20
                cand.need_ai_review = True
                reasons.append("区县缺失且街道疑似截断")
            elif cand.village:
                county_missing_penalty = -10
                cand.need_ai_review = True
                reasons.append("区县缺失")
            else:
                cand.need_ai_review = True
                reasons.append("地址未包含区县信息")

        confidence = base + level_bonus + stability + village_penalty + same_name_penalty + building_conflict_penalty + single_char_short_penalty + truncation_penalty + county_missing_penalty
        if confidence < 0:
            confidence = 0
        if confidence > 100:
            confidence = 100

        cand.reason = "；".join(reasons) + f"；最终置信度{confidence:.0f}"
        return float(confidence)
