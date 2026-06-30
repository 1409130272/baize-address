# address-py

中文地址解析服务，**新老双引擎并存**。  
老引擎（2024 年底）保持向下兼容，新引擎（v2.5，2026 年）提供更高准确率和 AI 兜底能力。

> **建议**：新项目直接使用新引擎；存量调用方请参照本文档逐步迁移。

---

## 目录结构

```
address-py/
├── legacy/                          # 老引擎（v1，2024年底）
│   ├── address_api.py               #   FastAPI 入口，端口 8500
│   ├── lcparser.py                  #   解析器（jionlp 思路，全量线性扫描）
│   ├── china_location.txt           #   五级行政区划词典
│   ├── china_location_change.txt    #   地名变更映射
│   └── requirements.txt            #   老依赖（jieba, fastapi, uvicorn）
├── address_resolver_v2/            # 新引擎（v2.5，2026年）
│   ├── server.py                   #   FastAPI 入口，端口 8769
│   ├── resolver.py                 #   双 Trie 树 + 置信度评估
│   ├── ai_resolver.py              #   AI 兜底（DeepSeek / Instructor）
│   ├── trie.py / fuzzy_matcher.py #   高性能匹配
│   ├── config.py / config.ini      #   配置化（城市/AI/缓存）
│   └── ...                         #   其他模块
├── data/                           # 数据文件
│   └── 区划代码（开放平台标准）.xlsx
├── docs/                           # 文档（更新日志、测试报告等）
├── tests/                          # 测试脚本
├── run_legacy.sh                   # 启动老服务
├── run_v2.sh                       # 启动新服务
├── requirements_v2.txt             # 新依赖
└── README.md
```

---

## 快速启动

### 老服务（端口 8500，向下兼容）

```bash
bash run_legacy.sh
# 或
cd legacy && python3 address_api.py
```

### 新服务（端口 8769，推荐）

```bash
pip install -r requirements_v2.txt
bash run_v2.sh
# 或
python3 -m uvicorn address_resolver_v2.server:app --host 0.0.0.0 --port 8769 --reload
```

---

## 接口完整文档

### 老接口（Legacy v1）

> 路径：`POST http://localhost:8500/analysis/`  
> 版本：2024年底首发，2025年8月最后更新  
> 适用场景：存量系统，暂未迁移的调用方

#### 请求参数

```json
{
  "address": "江苏省无锡市大池路督府天承18栋502"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| address | string | 是 | 待解析的中文地址 |

#### 响应格式

```json
{
  "statueCode": "200",
  "desc": "地址解析成功",
  "code": "SUCCESS",
  "data": {
    "provinceCode": "320000",
    "provinceName": "江苏省",
    "cityCode": "320200",
    "CityName": "无锡市",
    "countyCode": "320206",
    "CountyName": "惠山区",
    "fullLocation": "江苏省无锡市惠山区大池路",
    "origLocation": "督府天承18栋502",
    "town": "XX街道",
    "village": "XX村/小区"
  }
}
```

| 字段 | 说明 |
|------|------|
| statueCode | `200`=成功，`500`=解析失败，`201`=省/市/区缺失 |
| data.provinceCode | 2位省码 + `0000` |
| data.cityCode | 4位市码 + `00` |
| data.countyCode | 6位区县码 |
| data.town / village | 乡镇/村（需开启 `town_village=True`） |

#### curl 示例

```bash
curl -X POST http://localhost:8500/analysis/ \
  -H "Content-Type: application/json" \
  -d '{"address":"江苏省无锡市大池路督府天承18栋502"}'
```

---

### 新接口（v2.5，推荐）

> 路径：`POST http://localhost:8769/api/address/resolve`  
> 版本：v2.5（2026年6月28日）  
> 适用场景：所有新项目，及准备迁移的存量系统

#### 请求参数

```json
{
  "address": "江苏省无锡市大池路督府天承18栋502",
  "useAI": 1,
  "cityCode": ""
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| address | string | 是 | — | 待解析的中文地址（至少6个汉字） |
| useAI | bool | 否 | `false` | 是否启用 AI 兜底（`1`=开启，`0`=关闭） |
| cityCode | string | 否 | `""` | 城市编码（6位），提供可提升准确率 |

#### 响应格式

```json
{
  "addressResolutionInfoList": [
    {
      "address": "江苏省无锡市大池路督府天承18栋502",
      "provinceCode": "320000",
      "provinceName": "江苏省",
      "cityCode": "320200",
      "cityName": "无锡市",
      "countyCode": "320206",
      "countyName": "惠山区",
      "village": "",
      "confidence": 100,
      "source": 0,
      "reason": "省份Trie匹配+城市Trie匹配+区县Trie匹配"
    }
  ],
  "code": "SUCCESS",
  "desc": "地址解析完成",
  "total": 1,
  "aiUsed": 0,
  "aiCacheHit": 0,
  "aiCost": {
    "inputCacheHitTokens": 0,
    "inputCacheMissTokens": 0,
    "outputTokens": 0,
    "totalCost": 0.0
  }
}
```

| 字段 | 说明 |
|------|------|
| addressResolutionInfoList | 候选结果数组（默认最多3个） |
| .confidence | 置信度 0–100，≥90 可自动使用 |
| .source | `0`=规则引擎，`1`=AI 兜底 |
| .reason | 匹配路径说明 |
| aiUsed | `1`=本次触发了 AI 兜底，`0`=未触发 |
| aiCacheHit | `1`=AI 结果命中缓存，`0`=未命中 |
| aiCost | AI 调用费用明细（未调用时为零值） |

#### curl 示例

```bash
# 基础调用（不开 AI）
curl -X POST http://localhost:8769/api/address/resolve \
  -H "Content-Type: application/json" \
  -d '{"address":"江苏省无锡市大池路督府天承18栋502","useAI":0}'

# 启用 AI 兜底
curl -X POST http://localhost:8769/api/address/resolve \
  -H "Content-Type: application/json" \
  -d '{"address":"江苏省无锡市大池路督府天承18栋502","useAI":1}'

# 指定城市编码（提升准确率）
curl -X POST http://localhost:8769/api/address/resolve \
  -H "Content-Type: application/json" \
  -d '{"address":"大池路督府天承18栋502","useAI":1,"cityCode":"320200"}'
```

---

## 新老接口对照表

| 维度 | 老接口（legacy/v1） | 新接口（v2.5） |
|------|---------------------|-----------------|
| **路径** | `POST /analysis/` | `POST /api/address/resolve` |
| **端口** | 8500 | 8769 |
| **首发时间** | 2024年10月 | 2025年12月（v1.0） |
| **当前版本** | v1.0（不再更新） | v2.5（持续迭代） |
| **入参** | `{address}` | `{address, useAI, cityCode}` |
| **出参结构** | `data.provinceCode` 等 | `addressResolutionInfoList[].provinceCode` 等 |
| **多候选** | 不支持（单一结果） | 支持（最多3个候选） |
| **置信度** | 无 | 有（0–100，含评估逻辑） |
| **AI 兜底** | 无 | 有（DeepSeek + 缓存 + 费用统计） |
| **城市编码约束** | 无 | 有（`cityCode` 参数，避免跨市歧义） |
| **缓存** | 无 | 有（TTL + LRU，AI结果可复用） |
| **费用统计** | 无 | 有（`aiCost`，token 明细 + 总费用） |
| **汉字校验** | 无 | 有（至少6个汉字，必须含汉字） |
| **乡镇/村** | 支持（`town_village=True`） | 不支持（专注省/市/区） |
| **旧地名映射** | 有（`china_location_change.txt`） | 无（依赖标准区划） |
| **性能** | 线性扫描，~100ms/次 | Trie 树 + 短路，~1–5ms/次 |
| **准确率** | ~95%（无量化测试） | 99.96%（2000条测试集） |

---

## 迁移指南

### 为什么建议迁移？

新引擎在以下方面全面优于老引擎：

1. **准确率**：99.96% vs ~95%，减少了近 90% 的解析错误
2. **性能**：200× 提速（1–5ms vs ~100ms）
3. **可观测性**：置信度、AI 费用、缓存命中率全部可查
4. **AI 兜底**：规则引擎拿不准时自动调用 AI，准确率再提升 0.2%
5. **持续维护**：老引擎已停止更新，新引擎持续迭代

### 迁移步骤

#### 第一步：并行验证（1–2天）

同时调用新老接口，对比结果：

```python
import requests

address = "江苏省无锡市大池路督府天承18栋502"

# 老接口
legacy_res = requests.post("http://localhost:8500/analysis/",
                          json={"address": address}).json()

# 新接口
v2_res = requests.post("http://localhost:8769/api/address/resolve",
                       json={"address": address, "useAI": 1}).json()

# 对比省市区编码
print("Legacy:", legacy_res["data"]["provinceCode"],
      legacy_res["data"]["cityCode"],
      legacy_res["data"]["countyCode"])
print("V2:", v2_res["addressResolutionInfoList"][0]["provinceCode"],
      v2_res["addressResolutionInfoList"][0]["cityCode"],
      v2_res["addressResolutionInfoList"][0]["countyCode"])
```

#### 第二步：字段映射（0.5天）

| 老接口字段 | 新接口字段 | 备注 |
|-----------|-----------|------|
| `data.provinceCode` | `addressResolutionInfoList[0].provinceCode` | 结构变深一层 |
| `data.CityName` | `addressResolutionInfoList[0].cityName` | 大小写统一 |
| `data.CountyName` | `addressResolutionInfoList[0].countyName` | 大小写统一 |
| `data.fullLocation` | — | 新接口不返回，可自行拼接 |
| `data.town / village` | `addressResolutionInfoList[0].village` | 新接口暂不支持乡镇 |

> **注意**：新接口返回的是**数组**（`addressResolutionInfoList`），即使只有一个候选结果 also 放在数组里。

#### 第三步：切换流量（1天）

1. 先对低优先级业务切换新接口
2. 开启 `useAI=1`，利用 AI 兜底处理边缘 case
3. 监控 `confidence` 字段，对低置信度结果做二次确认

#### 第四步：下线与清理（可选）

确认新接口稳定后，停掉 8500 端口的老服务，移除 `legacy/` 目录。

---

## 版本沿革

| 时间 | 版本 | 引擎 | 关键事件 |
|------|------|------|---------|
| 2024年10月 | v1.0 | legacy | 首次提交，基于 jionlp 思路实现 |
| 2025年8月 | v1.0 | legacy | 最后更新，此后停止迭代 |
| 2025年12月 | v1.0 | v2 | 新引擎立项，纯规则双 Trie 树 |
| 2026年1月 | v1.1 | v2 | 加入 AI 兜底（DeepSeek） |
| 2026年2月 | v2.0 | v2 | 工程化重构，配置化，异步化 |
| 2026年3月 | v2.3 | v2 | cityCode 约束，置信度评估 |
| 2026年6月28日 | v2.5 | v2 | AI 置信度短路保护，费用可观测 |
| 2026年6月28日 | — | 合并 | 新老引擎合并至同一仓库，双端口共存 |

---

## 准确率对比

| 测试集 | 老引擎（legacy） | 新引擎（v2.5） |
|--------|-----------------|-----------------|
| 常规地址（1000条） | ~95% | 99.96% |
| 边缘地址（500条） | ~85% | 99.50% |
| AI 兜底触发（53条） | 0%（无 AI） | 96.23% |

---

## 常见问题

**Q：老接口会继续维护吗？**  
A：老引擎（legacy）已停止功能更新，仅保留 bug 修复。新功能全部在新引擎上开发。

**Q：新接口不支持乡镇/村，怎么办？**  
A：新引擎专注省/市/区三级的高准确率解析。如需乡镇级解析，可暂时继续使用老接口，或等待后续版本支持。

**Q：AI 兜底会不会很贵？**  
A：不会。只有规则引擎拿不准时（置信度 < 90）才触发 AI，且结果会缓存。实际生产中 AI 调用率 < 0.5%，单次成本约 ¥0.0004。

**Q：两个服务能同时跑吗？**  
A：可以。老服务端口 8500，新服务端口 8769，互不干扰。这也是当前仓库的默认运行方式。

---

## 相关文档

- [解决方案文档与更新日志](docs/解决方案文档与更新日志.md) — 完整版本历史与技术细节
- [原始需求沟通](docs/原始需求沟通.md) — 项目诞生的背景
- [测试报告](docs/测试报告.md) — 各版本准确率测试记录
- [项目故事 H5](../../WorkBuddy/2026-06-28-12-33-48/address_resolver_story.html) — 可视化演进历程（移动端）
