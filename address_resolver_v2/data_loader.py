import os
import pandas as pd
from .trie import Trie
from .alias_dict import get_aliases, ADMIN_SUFFIX_SKIP_CHARS


class AreaInfo:
    def __init__(self, code, name, level, parent_code, province_code=0, province_name="", city_code=0, city_name=""):
        self.code = code
        self.name = name
        self.level = level
        self.parent_code = parent_code
        self.province_code = province_code
        self.province_name = province_name
        self.city_code = city_code
        self.city_name = city_name

    def to_dict(self):
        return {
            "code": self.code,
            "name": self.name,
            "level": self.level,
            "parent_code": self.parent_code,
            "province_code": self.province_code,
            "province_name": self.province_name,
            "city_code": self.city_code,
            "city_name": self.city_name,
        }


class AreaDataLoader:
    def __init__(self, excel_path):
        self.excel_path = excel_path
        self.by_code = {}
        self.provinces = []
        self.cities_by_province = {}
        self.counties_by_city = {}
        self.all_cities = []
        self.all_counties = []
        self.full_trie = Trie()
        self.short_trie = Trie()
        self.pinyin_index = {}
        self._load()

    def _load(self):
        df = pd.read_excel(self.excel_path)
        df["code"] = df["区划代码"].astype(int)
        df["name"] = df["区划名称"].astype(str).str.strip()
        df["parent_code"] = df["上级区划代码"].astype(int)

        province_codes = set(df[df["parent_code"] == 0]["code"].tolist())
        city_codes = set(df[df["parent_code"].isin(province_codes)]["code"].tolist())

        name_by_code = {}
        parent_by_code = {}
        for _, row in df.iterrows():
            name_by_code[row["code"]] = row["name"]
            parent_by_code[row["code"]] = row["parent_code"]

        for _, row in df.iterrows():
            code = row["code"]
            name = row["name"]
            parent = row["parent_code"]
            if parent == 0:
                level = "province"
                info = AreaInfo(code, name, level, parent)
                self.by_code[code] = info
                self.provinces.append(info)
            elif parent in province_codes:
                level = "city"
                p_name = name_by_code.get(parent, "")
                info = AreaInfo(code, name, level, parent, province_code=parent, province_name=p_name)
                self.by_code[code] = info
                self.all_cities.append(info)
                self.cities_by_province.setdefault(parent, []).append(info)
            else:
                level = "county"
                city_name = name_by_code.get(parent, "")
                province_code = parent_by_code.get(parent, 0)
                province_name = name_by_code.get(province_code, "")
                info = AreaInfo(
                    code, name, level, parent,
                    province_code=province_code, province_name=province_name,
                    city_code=parent, city_name=city_name,
                )
                self.by_code[code] = info
                self.all_counties.append(info)
                self.counties_by_city.setdefault(parent, []).append(info)

        self._build_trie()
        self._build_pinyin_index()

    def _build_trie(self):
        for info in self.provinces:
            self.full_trie.insert(info.name, info)
            for alias in get_aliases(info.name, "province"):
                self.short_trie.insert(alias, info)
        for info in self.all_cities:
            self.full_trie.insert(info.name, info)
            for alias in get_aliases(info.name, "city"):
                self.short_trie.insert(alias, info)
        for info in self.all_counties:
            self.full_trie.insert(info.name, info)
            for alias in get_aliases(info.name, "county"):
                self.short_trie.insert(alias, info)

    def _build_pinyin_index(self):
        try:
            from pypinyin import lazy_pinyin
        except ImportError:
            return
        for info in list(self.by_code.values()):
            py = "".join(lazy_pinyin(info.name))
            self.pinyin_index.setdefault(py, []).append(info)

    def get_by_code(self, code):
        return self.by_code.get(code)

    def find_by_name(self, name, level=None, province_code=0, city_code=0):
        """按名称反查区划信息。可选限定 level / 上级代码以消歧。
        若存在多个同名，返回第一个匹配项。"""
        if not name:
            return None
        pools = []
        if level is None or level == "province":
            pools.append(self.provinces)
        if level is None or level == "city":
            pools.append(self.all_cities)
        if level is None or level == "county":
            pools.append(self.all_counties)
        for pool in pools:
            for info in pool:
                if info.name != name:
                    continue
                if level and info.level != level:
                    continue
                if province_code and info.province_code != province_code:
                    continue
                if city_code and info.city_code != city_code:
                    continue
                return info
        return None

    def get_cities(self, province_code):
        return self.cities_by_province.get(province_code, [])

    def get_counties(self, city_code):
        return self.counties_by_city.get(city_code, [])

    def get_all_cities(self):
        return self.all_cities

    def get_all_counties(self):
        return self.all_counties

    def get_province_code_of_city(self, city_code):
        info = self.by_code.get(city_code)
        if info is None:
            return 0
        if info.level == "province":
            return info.code
        if info.level == "city":
            return info.province_code
        if info.level == "county":
            return info.province_code
        return 0

    def get_same_province_city_codes(self, city_code):
        province_code = self.get_province_code_of_city(city_code)
        if province_code == 0:
            return set()
        return {c.code for c in self.get_cities(province_code)}

    def get_provinces(self):
        return self.provinces

    def search_full(self, text):
        return self.full_trie.search_all(text)

    def search_short(self, text):
        return self.short_trie.search_all(text)

    @staticmethod
    def is_suffix_next(text, end):
        if end >= len(text):
            return False
        return text[end] in ADMIN_SUFFIX_SKIP_CHARS
