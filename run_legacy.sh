#!/bin/bash
# 启动老服务（端口 8500）
# 老接口：POST /analysis/  入参 {address}
cd "$(dirname "$0")/legacy"
python3 address_api.py
