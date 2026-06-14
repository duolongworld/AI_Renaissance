#!/bin/bash
# Industrial Sentinel Pipeline 启动脚本
# 用法: ./run.sh <股票代码/名称> [选项]
# 示例: ./run.sh 002916.SZ
#       ./run.sh 002916.SZ --preset pcb

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE="$SCRIPT_DIR/core/pipeline.py"

show_help() {
    cat << 'EOF'
Industrial Sentinel Pipeline
产业链中观分析框架 — 真实数据驱动

用法:
    ./run.sh <股票代码/名称> [选项]

示例:
    ./run.sh 002916.SZ                    # 通过股票代码（自动检测preset）
    ./run.sh 002916.SZ --preset pcb       # 强制指定preset
    ./run.sh AXTI.US                      # 美股标的
    ./run.sh AXTI.US --preset optical-module   # 强制指定preset

选项:
    --preset <name>         强制指定产业链preset（不自动检测）
    --auto                  强制重新执行本地 preset 路由（覆盖JSON中的配置）
    --help, -h              显示本帮助信息

支持的preset (黄仁勋AI五层蛋糕):
    L1 能源:       ai-energy
    L2 芯片:       ai-chip, semiconductor-equipment, storage
    L3 基础设施:   optical-module, ai-infrastructure, pcb
    L4 模型:       ai-model
    L5 应用:       robotics

	preset 路由逻辑:
	    轮1: 识别 preset / 行业关键词 / 常见名称
	    轮2: 查本地 preset 路由表（只用于选择分析框架）
	    轮3: 查用户补充映射
	    兜底: 提示用户手动指定 --preset
	    注意: 外部 provider 识别属于项目 data_sources/，不在 Skill 内直接联网

步骤:
    Step 1: 加载真实财报数据 (data/<code>_real_data.json)
    Step 2: 自动检测产业链preset（如启用）
    Step 3: 产业链生命周期判定
    Step 4: 拐点状态判定（五态模型）
    Step 5: System B 个股类型判定 + HTML报告生成

输出:
    生成 HTML 分析报告于 reports/ 目录

数据准备:
    1. 搜索财报和行业数据
    2. 运行 python scripts/generate_data_template.py <code> 生成空白模板
    3. 将搜索到的数据填入 data/<code>_real_data.json
    4. 运行 python scripts/validate_data.py <code> 验证数据完整性
    5. 运行 ./run.sh <code> 生成报告

环境:
    Python 3.9+ 必须
    core/ 目录包含 pipeline.py, system_a.py, system_b.py
EOF
}

# 解析参数
STOCK_INPUT=""
FORCE_PRESET=""
FORCE_AUTO=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h)
            show_help
            exit 0
            ;;
        --preset)
            if [ -n "$2" ] && [ "${2:0:1}" != "-" ]; then
                FORCE_PRESET="$2"
                shift 2
            else
                echo "❌ 错误: --preset 需要参数"
                exit 1
            fi
            ;;
        --auto)
            FORCE_AUTO=true
            shift
            ;;
        -*)
            echo "❌ 未知选项: $1"
            echo "使用 --help 查看帮助"
            exit 1
            ;;
        *)
            STOCK_INPUT="$1"
            shift
            ;;
    esac
done

if [ -z "$STOCK_INPUT" ]; then
    echo "❌ 错误：缺少股票代码/名称参数"
    echo ""
    echo "用法: ./run.sh <股票代码/名称> [选项]"
    echo "示例: ./run.sh 002916.SZ"
    echo "      ./run.sh 002916.SZ --preset pcb"
    echo ""
    echo "使用 --help 查看完整帮助"
    exit 1
fi

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误：未找到 python3，请安装 Python 3.9+"
    exit 1
fi

# 检查 pipeline.py
if [ ! -f "$PIPELINE" ]; then
    echo "❌ 错误：未找到 pipeline.py ($PIPELINE)"
    exit 1
fi

# 构建额外参数
EXTRA_ARGS=""
if [ -n "$FORCE_PRESET" ]; then
    EXTRA_ARGS="$EXTRA_ARGS --preset $FORCE_PRESET"
fi
if [ "$FORCE_AUTO" = true ]; then
    EXTRA_ARGS="$EXTRA_ARGS --auto"
fi

# 执行
echo "=================================================="
echo "Industrial Sentinel"
echo "目标: $STOCK_INPUT"
if [ -n "$FORCE_PRESET" ]; then
    echo "Preset: $FORCE_PRESET（强制指定）"
elif [ "$FORCE_AUTO" = true ]; then
    echo "Preset: 强制自动检测"
else
    echo "Preset: 自动检测（JSON无配置时启用）"
fi
echo "=================================================="
python3 "$PIPELINE" "$STOCK_INPUT" $EXTRA_ARGS
