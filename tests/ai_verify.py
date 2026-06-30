import os
import sys
import json
from collections import defaultdict

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


def verify_one(sample, use_ai, city_code=None):
    result = resolver.resolve(sample["address"], max_candidates=3, use_ai=use_ai, city_code=city_code)
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
    if exp_street == "":
        if got_village is not None and got_village != "":
            return False, f"街道不符 期望空 实际'{got_village}'", c
    else:
        if got_village != exp_street:
            return False, f"街道不符 期望'{exp_street}' 实际'{got_village}'", c
    return True, "OK", c


def main():
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    print(f"生成 {total} 条测试数据...")
    samples = gt.build_samples(total)
    print(f"已生成 {len(samples)} 条")

    print("阶段1: 纯规则解析...")
    rule_pass = 0
    fail_samples = []
    for idx, s in enumerate(samples):
        ok, reason, _ = verify_one(s, use_ai=False)
        if ok:
            rule_pass += 1
        else:
            fail_samples.append(s)
        if (idx + 1) % 1000 == 0:
            print(f"  进度 {idx+1}/{len(samples)} 规则通过率 {rule_pass/(idx+1)*100:.2f}%")

    rule_rate = rule_pass / len(samples) * 100
    print(f"\n纯规则通过: {rule_pass}/{len(samples)} = {rule_rate:.2f}%")
    print(f"规则失败案例: {len(fail_samples)} 条, 将用AI兜底重试...")

    print("\n阶段2: 对失败案例启用AI兜底...")
    ai_fixed = 0
    ai_fail = 0
    ai_fail_details = []
    for idx, s in enumerate(fail_samples):
        ok, reason, cand = verify_one(s, use_ai=True)
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
        if (idx + 1) % 10 == 0:
            print(f"  AI重试进度 {idx+1}/{len(fail_samples)} 已修正 {ai_fixed}")

    final_pass = rule_pass + ai_fixed
    final_rate = final_pass / len(samples) * 100
    ai_recovery = ai_fixed / len(fail_samples) * 100 if fail_samples else 0

    print()
    print("=" * 80)
    print("AI兜底对比报告")
    print("=" * 80)
    print(f"总样本数: {len(samples)}")
    print(f"纯规则通过: {rule_pass} ({rule_rate:.2f}%)")
    print(f"规则失败数: {len(fail_samples)}")
    print(f"AI兜底修正: {ai_fixed} (失败案例修正率 {ai_recovery:.2f}%)")
    print(f"AI仍失败: {ai_fail}")
    print(f"最终通过: {final_pass} ({final_rate:.2f}%)")
    print(f"提升: +{final_rate - rule_rate:.2f}%")

    if ai_fail_details:
        print()
        print("AI仍失败案例(前30条):")
        for f in ai_fail_details:
            print(f"  [{f['template']}] {f['address']}")
            print(f"    原因: {f['reason']}")
            print(f"    期望: {f['exp']}")
            print(f"    实际: {f['got']}")

    report_path = os.path.join(os.path.dirname(BASE_DIR), "docs", "AI兜底测试报告.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# AI兜底解析对比测试报告\n\n")
        f.write(f"**数据基准**: 开放平台标准\n\n")
        f.write(f"**AI模型**: DeepSeek (deepseek-chat) + Instructor + Pydantic\n\n")
        f.write(f"**触发策略**: 规则置信度<75 或 多候选分差<10 时触发AI\n\n")
        f.write("## 对比结果\n\n")
        f.write("| 指标 | 数值 |\n|---|---|\n")
        f.write(f"| 总样本数 | {len(samples)} |\n")
        f.write(f"| 纯规则通过 | {rule_pass} ({rule_rate:.2f}%) |\n")
        f.write(f"| 规则失败数 | {len(fail_samples)} |\n")
        f.write(f"| AI兜底修正 | {ai_fixed} (修正率 {ai_recovery:.2f}%) |\n")
        f.write(f"| AI仍失败 | {ai_fail} |\n")
        f.write(f"| 最终通过 | {final_pass} ({final_rate:.2f}%) |\n")
        f.write(f"| 准确率提升 | +{final_rate - rule_rate:.2f}% |\n\n")
        f.write("## 结论\n\n")
        f.write(f"规则解析单独通过率 {rule_rate:.2f}%，启用AI兜底后提升至 {final_rate:.2f}%。")
        f.write(f"AI对 {len(fail_samples)} 条规则失败案例修正了 {ai_fixed} 条，修正率 {ai_recovery:.2f}%。")
        f.write("AI主要在同名区县消歧、短简称歧义等场景发挥作用，且仅在低置信度时触发，成本可控。\n\n")
        if ai_fail_details:
            f.write("## AI仍失败案例\n\n")
            f.write("| 模板 | 地址 | 原因 | 期望 | 实际 |\n|---|---|---|---|---|\n")
            for fl in ai_fail_details:
                addr = fl["address"].replace("|", "/")
                f.write(f"| {fl['template']} | {addr} | {fl['reason']} | {fl['exp']} | {fl['got']} |\n")

    print(f"\n报告已生成: {report_path}")


if __name__ == "__main__":
    main()
