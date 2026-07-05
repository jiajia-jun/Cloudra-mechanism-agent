#!/usr/bin/env bash
#
# ChemBench CLI-vs-CLI comparison runner.
#
# Runs the same ChemBench questions through:
#   1. OpenCode CLI (`opencode run`)
#   2. Cloudra CLI  (`cloudra run --new --yolo`)
#   3. Comparison merge (`chembench-compare compare`)
#
# Usage:
#   ./run_comparison.sh --limit 10
#   ./run_comparison.sh --limit 100 --timeout 300
#   LIMIT=50 TIMEOUT=200 ./run_comparison.sh
#

set -euo pipefail

# ── Helper functions ─────────────────────────────────────────────────────────
_show_help() {
    cat <<'EOF'
Usage: run_comparison.sh [OPTIONS]

Options:
  --limit N              Number of questions to evaluate (default: 10)
  --subset KEYWORD       Only evaluate questions containing this keyword
  --timeout SECONDS      Per-question timeout (default: 300)
  --max-retries N        Max retries on extraction/invocation failure (default: 2)
  --run-id PREFIX        Prefix for run IDs (default: run_YYYYMMDD_HHMMSS)
  --opencode-model MODEL OpenCode model name (default: Cloudra coordinator model)
  --data-dir PATH        ChemBench data directory
  -h, --help             Show this help

Environment variables (override CLI options):
  LIMIT, SUBSET, TIMEOUT, MAX_RETRIES, RUN_ID_PREFIX, OPENCODE_MODEL, DATA_DIR, CLOUDRA_DATA_DIR
EOF
}

log() {
    echo -e "\033[96m[compare-run]\033[0m $*"
}

# ── 默认配置 ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

LIMIT="${LIMIT:-10}"
TIMEOUT="${TIMEOUT:-300}"
MAX_RETRIES="${MAX_RETRIES:-2}"
SUBSET="${SUBSET:-}"
RUN_ID_PREFIX="${RUN_ID_PREFIX:-}"
OPENCODE_MODEL="${OPENCODE_MODEL:-}"
DATA_DIR="${DATA_DIR:-${PROJECT_ROOT}/benchmarks/data/chembench-repo/data}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_PREFIX="${RUN_ID_PREFIX:-run_${TIMESTAMP}}"

OPENCODE_RUN_ID="${RUN_PREFIX}_opencode"
CLOUDRA_RUN_ID="${RUN_PREFIX}_cloudra"

# Cloudra 数据目录，用于存放报告
CLOUDRA_DATA_DIR="${CLOUDRA_DATA_DIR:-${HOME}/.local/share/cloudra}"
LOG_DIR="${CLOUDRA_DATA_DIR}/benchmarks/chembench-compare/logs/${TIMESTAMP}"

# ── 参数解析 ──────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --limit)
            LIMIT="$2"
            shift 2
            ;;
        --subset)
            SUBSET="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --run-id)
            RUN_PREFIX="$2"
            OPENCODE_RUN_ID="${RUN_PREFIX}_opencode"
            CLOUDRA_RUN_ID="${RUN_PREFIX}_cloudra"
            shift 2
            ;;
        --max-retries)
            MAX_RETRIES="$2"
            shift 2
            ;;
        --opencode-model)
            OPENCODE_MODEL="$2"
            shift 2
            ;;
        --data-dir)
            DATA_DIR="$2"
            shift 2
            ;;
        -h|--help)
            _show_help
            exit 0
            ;;
        *)
            echo "未知参数: $1" >&2
            _show_help >&2
            exit 1
            ;;
    esac
done

# ── 前置检查 ──────────────────────────────────────────────────────────────────
if ! command -v chembench-compare &>/dev/null; then
    echo "错误: 未找到 chembench-compare 命令，请先将其加入 PATH。" >&2
    exit 1
fi

if ! command -v opencode &>/dev/null; then
    echo "错误: 未找到 opencode CLI。" >&2
    exit 1
fi

if ! command -v cloudra &>/dev/null; then
    echo "错误: 未找到 cloudra CLI。" >&2
    exit 1
fi

if [[ ! -d "${DATA_DIR}" ]]; then
    echo "错误: ChemBench 数据目录不存在: ${DATA_DIR}" >&2
    exit 1
fi

mkdir -p "${LOG_DIR}"

log "配置信息:"
log "  数据目录: ${DATA_DIR}"
log "  题目数量: ${LIMIT}"
log "  每题超时: ${TIMEOUT}s"
log "  最大重试: ${MAX_RETRIES}"
[[ -n "${SUBSET}" ]] && log "  子集过滤: ${SUBSET}"
[[ -n "${OPENCODE_MODEL}" ]] && log "  OpenCode 模型: ${OPENCODE_MODEL}"
log "  OpenCode run_id: ${OPENCODE_RUN_ID}"
log "  Cloudra  run_id: ${CLOUDRA_RUN_ID}"
log "  日志目录: ${LOG_DIR}"

# ── 1. 跑 OpenCode ────────────────────────────────────────────────────────────
log ""
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "步骤 1/3: 运行 OpenCode 基线"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

OPENCODE_ARGS=(
    run --runner opencode
    --data-dir "${DATA_DIR}"
    --limit "${LIMIT}"
    --timeout "${TIMEOUT}"
    --max-retries "${MAX_RETRIES}"
    --run-id "${OPENCODE_RUN_ID}"
)
[[ -n "${SUBSET}" ]] && OPENCODE_ARGS+=(--subset "${SUBSET}")
[[ -n "${OPENCODE_MODEL}" ]] && OPENCODE_ARGS+=(--opencode-model "${OPENCODE_MODEL}")

chembench-compare "${OPENCODE_ARGS[@]}" 2>&1 | tee "${LOG_DIR}/opencode.log"

# ── 2. 跑 Cloudra ─────────────────────────────────────────────────────────────
log ""
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "步骤 2/3: 运行 Cloudra CLI"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

CLOUDRA_ARGS=(
    run --runner cloudra-cli
    --data-dir "${DATA_DIR}"
    --limit "${LIMIT}"
    --timeout "${TIMEOUT}"
    --max-retries "${MAX_RETRIES}"
    --run-id "${CLOUDRA_RUN_ID}"
)
[[ -n "${SUBSET}" ]] && CLOUDRA_ARGS+=(--subset "${SUBSET}")

chembench-compare "${CLOUDRA_ARGS[@]}" 2>&1 | tee "${LOG_DIR}/cloudra.log"

# ── 3. 合并对比 ───────────────────────────────────────────────────────────────
log ""
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "步骤 3/3: 生成对比报告"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

COMPARE_OUTPUT="${LOG_DIR}/comparison"

COMPARE_ARGS=(
    compare
    --baseline "${OPENCODE_RUN_ID}"
    --baseline-mode opencode
    --baseline-label OpenCode
    --treatment "${CLOUDRA_RUN_ID}"
    --treatment-mode cloudra-cli
    --treatment-label Cloudra
    --output "${COMPARE_OUTPUT}"
)

chembench-compare "${COMPARE_ARGS[@]}" 2>&1 | tee "${LOG_DIR}/compare.log"

# ── 完成 ──────────────────────────────────────────────────────────────────────
log ""
log "✅ 对比完成"
log "  报告目录: ${COMPARE_OUTPUT}"
log "  Markdown: ${COMPARE_OUTPUT}/comparison.md"
log "  JSON:     ${COMPARE_OUTPUT}/comparison.json"
log "  CSV:      ${COMPARE_OUTPUT}/per_question.csv"
log "  日志目录: ${LOG_DIR}"
log ""
log "快速查看报告:"
log "  cat ${COMPARE_OUTPUT}/comparison.md"
