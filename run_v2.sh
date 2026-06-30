#!/bin/bash
# 启动新服务（端口 8769）
# 新接口：POST /api/address/resolve  入参 {address, useAI, cityCode}
cd "$(dirname "$0")"
python3 -m uvicorn address_resolver_v2.server:app --host 0.0.0.0 --port 8769 --reload
