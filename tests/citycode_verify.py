import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(BASE_DIR)))

from address_resolver.data_loader import AreaDataLoader
from address_resolver.resolver import AddressResolver

EXCEL_PATH = os.path.join(os.path.dirname(BASE_DIR), "data", "区划代码（开放平台标准）.xlsx")
loader = AreaDataLoader(EXCEL_PATH)
resolver = AddressResolver(EXCEL_PATH)

import generate_and_test as gt
gt.loader = loader
gt.resolver = resolver


def verify_one(sample, city_code=None):
    result = resolver.resolve(sample["address"], max_candidates=3, city_code=city_code)
    cands = result.candidates
    if not cands:
        return False, "无解析结果"
    c = cands[0]
    got_prov = c.province.code if c.province else None
    got_city = c.city.code if c.city else None
    got_county = c.county.code if c.county else None
    if got_prov != sample["exp_prov_code"]:
        return False, f"省级不符 期望{sample['exp_prov_code']} 实际{got_prov}"
    if sample["exp_city_code"] is not None and got_city != sample["exp_city_code"]:
        return False, f"市级不符 期望{sample['exp_city_code']} 实际{got_city}"
    if sample["exp_county_code"] is not None and got_county != sample["exp_county_code"]:
        return False, f"区级不符 期望{sample['exp_county_code']} 实际{got_county}"
    exp_street = sample["street"]
    got_village = c.village
    if exp_street == "":
        if got_village is not None and got_village != "":
            return False, f"街道不符 期望空 实际'{got_village}'"
    else:
        if got_village != exp_street:
            return False, f"街道不符 期望'{exp_street}' 实际'{got_village}'"
    return True, "OK"


def main():
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    print(f"生成 {total} 条测试数据...")
    samples = gt.build_samples(total)
    print(f"已生成 {len(samples)} 条")

    print("\n阶段1: 纯规则解析(无cityCode)...")
    rule_pass = 0
    fail_samples = []
    for idx, s in enumerate(samples):
        ok, _ = verify_one(s)
        if ok:
            rule_pass += 1
        else:
            fail_samples.append(s)
        if (idx + 1) % 1000 == 0:
            print(f"  进度 {idx+1}/{len(samples)} 通过率 {rule_pass/(idx+1)*100:.2f}%")
    rule_rate = rule_pass / len(samples) * 100
    print(f"纯规则通过: {rule_pass}/{len(samples)} = {rule_rate:.2f}%")
    print(f"失败案例: {len(fail_samples)} 条")

    print("\n阶段2: 对失败案例注入期望cityCode消歧...")
    hint_fixed = 0
    still_fail = []
    for s in fail_samples:
        city_code = str(s["exp_city_code"]) if s["exp_city_code"] else None
        ok, _ = verify_one(s, city_code=city_code)
        if ok:
            hint_fixed += 1
        else:
            still_fail.append(s)
    hint_rate = hint_fixed / len(fail_samples) * 100 if fail_samples else 0
    final_pass = rule_pass + hint_fixed
    final_rate = final_pass / len(samples) * 100

    print(f"cityCode消歧修正: {hint_fixed}/{len(fail_samples)} = {hint_rate:.2f}%")
    print(f"最终通过: {final_pass}/{len(samples)} = {final_rate:.2f}%")
    print(f"提升: +{final_rate - rule_rate:.2f}%")

    if still_fail:
        print(f"\n仍失败案例(前20条):")
        for s in still_fail[:20]:
            print(f"  [{s['template']}] {s['address']}")
            print(f"    期望: {s['exp_prov_name']}/{s['exp_city_name']}/{s['exp_county_name']} street={s['street']}")


if __name__ == "__main__":
    main()
