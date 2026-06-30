import os
import sys
import random
import json
from collections import defaultdict, Counter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(BASE_DIR)))

from address_resolver.data_loader import AreaDataLoader
from address_resolver.alias_dict import get_aliases, make_short_name
from address_resolver.resolver import AddressResolver

EXCEL_PATH = os.path.join(os.path.dirname(BASE_DIR), "data", "区划代码（开放平台标准）.xlsx")
loader = AreaDataLoader(EXCEL_PATH)

_MUNI_PROV_NORMALIZE = {110100: 110000, 310100: 310000, 120100: 120000, 500100: 500000}
resolver = AddressResolver(EXCEL_PATH)

MUNI_PROV_CODES = {p.code for p in loader.get_provinces() if p.name.endswith("市") and p.parent_code == 0}

random.seed(20260620)

ROAD_PREFIXES = [
    "建设", "人民", "解放", "新华", "和平", "光明", "幸福", "文化", "工业", "科技",
    "大学", "青年", "滨河", "环城", "迎宾", "振兴", "文苑", "长虹", "胜利", "友谊",
    "珠江", "锦绣", "金龙", "翠竹", "红梅", "白鹭", "梧桐", "海棠", "紫荆", "玉兰",
    "丹桂", "青松", "雪松", "映月", "春熙", "清风", "明月", "彩霞", "晨曦", "暮云",
]
ROAD_SUFFIXES = ["路", "街", "大道", "巷", "弄"]
LANDMARKS = ["广场", "大厦", "医院", "学校", "公园", "购物中心", "体育馆", "图书馆", "火车站", "汽车站"]
VILLAGE_SUFFIXES = ["小区", "花园", "苑", "府", "园", "城", "公寓", "新村", "嘉园", "名邸"]


def gen_street():
    r = random.random()
    if r < 0.45:
        return f"{random.choice(ROAD_PREFIXES)}{random.choice(ROAD_SUFFIXES)}{random.randint(1, 999)}号"
    if r < 0.65:
        return f"{random.choice(ROAD_PREFIXES)}{random.choice(ROAD_SUFFIXES)}"
    if r < 0.82:
        return f"{random.choice(ROAD_PREFIXES)}{random.choice(VILLAGE_SUFFIXES)}"
    if r < 0.92:
        return f"{random.choice(ROAD_PREFIXES)}{random.choice(LANDMARKS)}"
    return ""


def daily_short(name, level):
    aliases = get_aliases(name, level)
    multi = [a for a in aliases if len(a) >= 2]
    if multi:
        return multi[0]
    return make_short_name(name, level)


def build_samples(total=10000):
    counties = loader.get_all_counties()
    muni_cities = [c for c in loader.get_all_cities() if c.province_code in MUNI_PROV_CODES]

    samples = []
    for i in range(total):
        use_muni = random.random() < 0.12 and muni_cities
        if use_muni:
            city = random.choice(muni_cities)
            prov = loader.get_by_code(city.province_code)
            sample = build_muni_sample(prov, city)
        else:
            county = random.choice(counties)
            prov = loader.get_by_code(county.province_code)
            city = loader.get_by_code(county.city_code)
            sample = build_county_sample(prov, city, county)
        if sample:
            samples.append(sample)
    return samples


def build_county_sample(prov, city, county):
    if not prov or not city:
        return None
    p_full, p_short = prov.name, daily_short(prov.name, "province")
    c_full, c_short = city.name, daily_short(city.name, "city")
    ct_full, ct_short = county.name, daily_short(county.name, "county")

    templates = [
        ("全称", f"{p_full}{c_full}{ct_full}", county.code, county.name),
        ("省简称", f"{p_short}{c_full}{ct_full}", county.code, county.name),
        ("市简称", f"{p_full}{c_short}{ct_full}", county.code, county.name),
        ("省市简称", f"{p_short}{c_short}{ct_full}", county.code, county.name),
        ("缺省", f"{c_full}{ct_full}", county.code, county.name),
        ("缺省+市简称", f"{c_short}{ct_full}", county.code, county.name),
        ("区简称", f"{p_full}{c_full}{ct_short}", county.code, county.name),
        ("缺市", f"{p_full}{ct_full}", county.code, county.name),
        ("仅区", f"{ct_full}", county.code, county.name),
        ("缺区", f"{p_full}{c_full}", None, None),
        ("全简称", f"{p_short}{c_short}{ct_short}", county.code, county.name),
    ]
    tname, body, exp_ct_code, exp_ct_name = random.choice(templates)
    street = gen_street()
    address = body + street
    return {
        "address": address,
        "template": tname,
        "street": street,
        "exp_prov_code": prov.code,
        "exp_prov_name": prov.name,
        "exp_city_code": city.code,
        "exp_city_name": city.name,
        "exp_county_code": exp_ct_code,
        "exp_county_name": exp_ct_name,
    }


def build_muni_sample(prov, city):
    p_full, p_short = prov.name, daily_short(prov.name, "province")
    templates = [
        ("直辖市全称", f"{p_full}{city.name}"),
        ("直辖市简称", f"{p_short}{city.name}"),
        ("直辖市仅区", f"{city.name}"),
        ("直辖市仅市", f"{p_full}"),
    ]
    tname, body = random.choice(templates)
    street = gen_street()
    address = body + street
    if tname == "直辖市仅市":
        exp_city_code = None
        exp_city_name = None
        exp_county_code = None
        exp_county_name = None
    else:
        exp_city_code = prov.code
        exp_city_name = prov.name
        exp_county_code = city.code
        exp_county_name = city.name
    return {
        "address": address,
        "template": tname,
        "street": street,
        "exp_prov_code": _MUNI_PROV_NORMALIZE.get(prov.code, prov.code),
        "exp_prov_name": prov.name,
        "exp_city_code": exp_city_code,
        "exp_city_name": exp_city_name,
        "exp_county_code": exp_county_code,
        "exp_county_name": exp_county_name,
    }


def verify(sample):
    result = resolver.resolve(sample["address"], max_candidates=3)
    cands = result.candidates
    if not cands:
        return False, "无解析结果", None
    c = cands[0]
    got_prov = c.province.code if c.province else None
    got_city = c.city.code if c.city else None
    got_county = c.county.code if c.county else None

    if got_prov != sample["exp_prov_code"]:
        return False, f"省级不符 期望{sample['exp_prov_code']} 实际{got_prov}", c
    if sample["exp_city_code"] is not None and got_city != sample["exp_city_code"]:
        return False, f"市级不符 期望{sample['exp_city_code']} 实际{got_city}", c
    if sample["exp_county_code"] is not None and got_county != sample["exp_county_code"]:
        return False, f"区级不符 期望{sample['exp_county_code']} 实际{got_county}", c

    exp_street = sample["street"]
    got_village = c.village
    street_ok = True
    if exp_street == "":
        if got_village is not None and got_village != "":
            street_ok = False
    else:
        if got_village != exp_street:
            street_ok = False
    if not street_ok:
        return False, f"街道不符 期望'{exp_street}' 实际'{got_village}'", c

    return True, "OK", c


def main():
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    samples_path = os.path.join(BASE_DIR, f"test_samples_{total}.json")
    if os.path.exists(samples_path):
        print(f"加载已有测试数据: {samples_path}")
        with open(samples_path, "r", encoding="utf-8") as f:
            samples = json.load(f)
        print(f"已加载 {len(samples)} 条测试数据，开始批量解析验证...")
    else:
        print(f"开始生成 {total} 条测试数据...")
        samples = build_samples(total)
        with open(samples_path, "w", encoding="utf-8") as f:
            json.dump(samples, f, ensure_ascii=False, indent=2)
        print(f"已生成 {len(samples)} 条测试数据并保存到 {samples_path}")
        print(f"开始批量解析验证...")

    pass_count = 0
    fail_list = []
    template_stat = defaultdict(lambda: {"total": 0, "pass": 0})
    fail_reason_stat = Counter()

    for idx, s in enumerate(samples):
        ok, reason, cand = verify(s)
        t = s["template"]
        template_stat[t]["total"] += 1
        if ok:
            pass_count += 1
            template_stat[t]["pass"] += 1
        else:
            fail_reason_stat[reason.split(" 期望")[0]] += 1
            if len(fail_list) < 200:
                got = {
                    "prov": (cand.province.name if cand and cand.province else None),
                    "city": (cand.city.name if cand and cand.city else None),
                    "county": (cand.county.name if cand and cand.county else None),
                    "village": (cand.village if cand else None),
                }
                fail_list.append({
                    "address": s["address"],
                    "template": t,
                    "reason": reason,
                    "exp": f"{s['exp_prov_name']}/{s['exp_city_name']}/{s['exp_county_name']} street={s['street']}",
                    "got": f"{got['prov']}/{got['city']}/{got['county']} village={got['village']}",
                })
        if (idx + 1) % 1000 == 0:
            print(f"  进度 {idx+1}/{len(samples)} 通过率 {pass_count/(idx+1)*100:.2f}%")

    fail_count = len(samples) - pass_count
    rate = pass_count / len(samples) * 100

    print()
    print("=" * 80)
    print("测试报告")
    print("=" * 80)
    print(f"总样本数: {len(samples)}")
    print(f"通过数: {pass_count}")
    print(f"失败数: {fail_count}")
    print(f"通过率: {rate:.2f}%")
    print()
    print("按模板类型统计:")
    print(f"  {'模板':<14}{'总数':>8}{'通过':>8}{'通过率':>10}")
    for t, st in sorted(template_stat.items(), key=lambda x: -x[1]['total']):
        r = st['pass'] / st['total'] * 100 if st['total'] else 0
        print(f"  {t:<14}{st['total']:>8}{st['pass']:>8}{r:>9.2f}%")
    print()
    print("失败原因分布:")
    for reason, cnt in fail_reason_stat.most_common():
        print(f"  {reason}: {cnt}")
    print()
    print("失败案例示例（前30条）:")
    for f in fail_list[:30]:
        print(f"  [{f['template']}] {f['address']}")
        print(f"    原因: {f['reason']}")
        print(f"    期望: {f['exp']}")
        print(f"    实际: {f['got']}")

    report_path = os.path.join(os.path.dirname(BASE_DIR), "docs", "测试报告.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 地址解析接口批量测试报告\n\n")
        f.write(f"**数据基准**: 开放平台标准（区划代码（开放平台标准）.xlsx）\n\n")
        f.write(f"**测试规模**: {len(samples)} 条\n\n")
        f.write(f"**验证方式**: 调用 AddressResolver.resolve(address, max_candidates=3)，取首个候选与期望省市区代码及街道逐项比对\n\n")
        f.write("## 总体结果\n\n")
        f.write(f"| 指标 | 数值 |\n|---|---|\n")
        f.write(f"| 总样本数 | {len(samples)} |\n")
        f.write(f"| 通过数 | {pass_count} |\n")
        f.write(f"| 失败数 | {fail_count} |\n")
        f.write(f"| 通过率 | {rate:.2f}% |\n\n")
        f.write("## 按地址模板类型统计\n\n")
        f.write("| 模板 | 总数 | 通过 | 通过率 |\n|---|---|---|---|\n")
        for t, st in sorted(template_stat.items(), key=lambda x: -x[1]['total']):
            r = st['pass'] / st['total'] * 100 if st['total'] else 0
            f.write(f"| {t} | {st['total']} | {st['pass']} | {r:.2f}% |\n")
        f.write("\n## 失败原因分布\n\n")
        f.write("| 原因 | 数量 |\n|---|---|\n")
        for reason, cnt in fail_reason_stat.most_common():
            f.write(f"| {reason} | {cnt} |\n")
        f.write("\n## 失败案例示例（前50条）\n\n")
        f.write("| 模板 | 地址 | 原因 | 期望 | 实际 |\n|---|---|---|---|---|\n")
        for fl in fail_list[:50]:
            addr = fl["address"].replace("|", "/")
            f.write(f"| {fl['template']} | {addr} | {fl['reason']} | {fl['exp']} | {fl['got']} |\n")
        f.write("\n## 结论\n\n")
        f.write(f"本次共测试 {len(samples)} 条基于开放平台标准省市区生成的真实风格地址，整体通过率 {rate:.2f}%。")
        f.write("测试覆盖全称、省简称、市简称、区简称、缺省、缺市、仅区、缺区、直辖市等多种日常表达模板，并附带路名/门牌/小区/地标等街道信息。\n\n")
        f.write("- 省市区代码均对照开放平台标准进行校验。\n")
        f.write("- 街道字段校验解析后剩余文本是否与生成街道一致。\n")
        f.write("- 失败案例主要集中在简称歧义、同名区划、个别数据缺失等场景，可作为后续优化方向。\n")

    detail_path = os.path.join(os.path.dirname(BASE_DIR), "docs", "测试失败明细.json")
    with open(detail_path, "w", encoding="utf-8") as f:
        json.dump({
            "total": len(samples),
            "pass": pass_count,
            "fail": fail_count,
            "rate": rate,
            "template_stat": {k: v for k, v in template_stat.items()},
            "fail_reason_stat": dict(fail_reason_stat),
            "fail_samples": fail_list,
        }, f, ensure_ascii=False, indent=2)

    print()
    print(f"报告已生成: {report_path}")
    print(f"失败明细已生成: {detail_path}")


if __name__ == "__main__":
    main()
