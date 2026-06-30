import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(BASE_DIR)))

from address_resolver.data_loader import AreaDataLoader
from address_resolver.resolver import AddressResolver
from address_resolver.ai_resolver import AIResolver

EXCEL_PATH = os.path.join(os.path.dirname(BASE_DIR), "data", "区划代码（开放平台标准）.xlsx")
loader = AreaDataLoader(EXCEL_PATH)
ai = AIResolver()
resolver = AddressResolver(EXCEL_PATH, ai_resolver=ai)

import generate_and_test as gt
gt.loader = loader
gt.resolver = resolver


def verify_one(sample, use_ai=False, city_code=None):
    result = resolver.resolve(sample["address"], max_candidates=3, use_ai=use_ai, city_code=city_code)
    cands = result.candidates
    if not cands:
        return False, "无解析结果", None

    # 判定标准：期望的省市区在候选列表中即算通过（同名歧义场景返回多候选是合理的）。
    # 街道校验仅对匹配到期望省市区的那个候选进行。
    exp_prov = sample["exp_prov_code"]
    exp_city = sample["exp_city_code"]
    exp_county = sample["exp_county_code"]
    exp_street = sample["street"]

    matched = None
    for c in cands:
        gp = c.province.code if c.province else None
        gc = c.city.code if c.city else None
        gx = c.county.code if c.county else None
        if gp != exp_prov:
            continue
        if exp_city is not None and gc != exp_city:
            continue
        if exp_county is not None and gx != exp_county:
            continue
        matched = c
        break

    if matched is None:
        top = cands[0]
        got = f"{top.province.code if top.province else '-'}/{top.city.code if top.city else '-'}/{top.county.code if top.county else '-'}"
        return False, f"期望省市区不在候选中(候选{len(cands)}条, 期望{exp_prov}/{exp_city}/{exp_county}, top={got})", top

    # 街道校验
    got_village = matched.village
    if exp_street == "":
        if got_village is not None and got_village != "":
            return False, f"街道不符 期望空 实际'{got_village}'", matched
    else:
        if got_village != exp_street:
            return False, f"街道不符 期望'{exp_street}' 实际'{got_village}'", matched
    return True, "OK", matched


def main():
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    print(f"生成 {total} 条测试数据...")
    samples = gt.build_samples(total)
    print(f"已生成 {len(samples)} 条")

    print("\n阶段1: 纯规则解析(无cityCode无AI)...")
    rule_pass = 0
    fail_samples = []
    for idx, s in enumerate(samples):
        ok, _, _ = verify_one(s)
        if ok:
            rule_pass += 1
        else:
            fail_samples.append(s)
        if (idx + 1) % 1000 == 0:
            print(f"  进度 {idx+1}/{len(samples)} 通过率 {rule_pass/(idx+1)*100:.2f}%")
    rule_rate = rule_pass / len(samples) * 100
    print(f"纯规则通过: {rule_pass}/{len(samples)} = {rule_rate:.2f}%, 失败{len(fail_samples)}条")

    print("\n阶段2: 对失败案例注入期望cityCode(纯规则消歧)...")
    hint_fixed = 0
    still_fail_after_hint = []
    for s in fail_samples:
        city_code = str(s["exp_city_code"]) if s["exp_city_code"] else None
        ok, _, _ = verify_one(s, city_code=city_code)
        if ok:
            hint_fixed += 1
        else:
            still_fail_after_hint.append(s)
    hint_rate = hint_fixed / len(fail_samples) * 100 if fail_samples else 0
    print(f"cityCode消歧修正: {hint_fixed}/{len(fail_samples)} = {hint_rate:.2f}%")

    print("\n阶段3: 对仍失败案例启用AI+cityCode兜底...")
    ai_fixed = 0
    ai_fail = 0
    ai_fail_details = []
    for idx, s in enumerate(still_fail_after_hint):
        city_code = str(s["exp_city_code"]) if s["exp_city_code"] else None
        ok, reason, cand = verify_one(s, use_ai=True, city_code=city_code)
        if ok:
            ai_fixed += 1
        else:
            ai_fail += 1
            if len(ai_fail_details) < 30:
                got = f"{cand.province.name if cand and cand.province else '-'}/{cand.city.name if cand and cand.city else '-'}/{cand.county.name if cand and cand.county else '-'} village={cand.village if cand else '-'} src={cand.source if cand else '-'}"
                ai_fail_details.append({
                    "address": s["address"],
                    "template": s["template"],
                    "reason": reason,
                    "exp": f"{s['exp_prov_name']}/{s['exp_city_name']}/{s['exp_county_name']} street={s['street']}",
                    "got": got,
                })
        if (idx + 1) % 5 == 0:
            print(f"  AI重试进度 {idx+1}/{len(still_fail_after_hint)} 已修正 {ai_fixed}")

    final_pass = rule_pass + hint_fixed + ai_fixed
    final_rate = final_pass / len(samples) * 100

    print()
    print("=" * 80)
    print("完整对比报告 (规则 + cityCode消歧 + AI兜底)")
    print("=" * 80)
    print(f"总样本数: {len(samples)}")
    print(f"纯规则通过: {rule_pass} ({rule_rate:.2f}%)")
    print(f"cityCode消歧修正: {hint_fixed} (修正率 {hint_rate:.2f}%)")
    print(f"AI兜底修正: {ai_fixed}")
    print(f"最终通过: {final_pass} ({final_rate:.2f}%)")
    print(f"总提升: +{final_rate - rule_rate:.2f}%")

    if ai_fail_details:
        print(f"\nAI仍失败案例(前30条):")
        for f in ai_fail_details:
            print(f"  [{f['template']}] {f['address']}")
            print(f"    原因: {f['reason']}")
            print(f"    期望: {f['exp']}")
            print(f"    实际: {f['got']}")


if __name__ == "__main__":
    main()
