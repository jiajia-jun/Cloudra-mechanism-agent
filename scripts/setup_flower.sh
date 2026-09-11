#!/bin/sh
# setup_flower.sh — 安装 FlowER 机理推断外部环境（mechanism_predict 工具的后端）。
#
# 做的事：建独立 conda env `flower`（torch 2.4 等重依赖绝不进主环境）→ clone
# FlowER（pin 到核验过的 commit）→ 从 figshare 拉检查点 → 把 repo_dir /
# env_python / checkpoint 写进 config。**不**替你打开开关：确认冒烟通过后，
# 自己执行 `cloudra config set flower.enabled true`。
#
# 用法：sh scripts/setup_flower.sh
# 可选环境变量：FLOWER_ENV_NAME（默认 flower）、FLOWER_REPO_DIR（默认
# <data_dir>/external/FlowER）、FLOWER_SKIP_SMOKE=1（跳过冒烟）。
set -eu

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$REPO_ROOT"

FLOWER_COMMIT=d0a54aa9d7e6ee3997134be38b48dd85455d1ceb  # master @ 2026-05-29
FIGSHARE_ARTICLE=32513667
ENV_NAME=${FLOWER_ENV_NAME:-flower}

if ! command -v conda >/dev/null 2>&1; then
    echo "error: conda not found on PATH; install Miniconda first." >&2
    exit 1
fi

# cloudra 主环境的 python（取 data_dir、最后写 config 都用它）
if command -v uv >/dev/null 2>&1; then
    CLOUDRA_PY="uv run python"
else
    CLOUDRA_PY="python3"
fi
DATA_DIR=$($CLOUDRA_PY -c "from cloudra.infra.config import get_config; print(get_config().data_dir)")
REPO_DIR=${FLOWER_REPO_DIR:-"$DATA_DIR/external/FlowER"}

echo "==> FlowER repo:  $REPO_DIR"
echo "==> conda env:    $ENV_NAME"

# --- 1. conda env -----------------------------------------------------------
if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    echo "==> env $ENV_NAME exists, reusing"
else
    conda create -y -n "$ENV_NAME" python=3.10
fi
CONDA_BASE=$(conda info --base)
ENV_PYTHON="$CONDA_BASE/envs/$ENV_NAME/bin/python"
[ -x "$ENV_PYTHON" ] || { echo "error: $ENV_PYTHON not found after env creation" >&2; exit 1; }

# --- 2. clone FlowER（pin commit） ------------------------------------------
if [ -d "$REPO_DIR/.git" ]; then
    echo "==> repo exists, fetching pinned commit"
    git -C "$REPO_DIR" fetch --quiet origin
else
    mkdir -p "$(dirname "$REPO_DIR")"
    git clone --quiet https://github.com/FongMunHong/FlowER.git "$REPO_DIR"
fi
git -C "$REPO_DIR" checkout --quiet "$FLOWER_COMMIT"

# --- 3. Python 依赖（官方 requirements.txt） ---------------------------------
"$ENV_PYTHON" -m pip install --quiet -r "$REPO_DIR/requirements.txt"

# --- 4. 检查点（figshare，URL 走 API 解析不写死） ----------------------------
if find "$REPO_DIR/checkpoints" -name "model.*.pt" 2>/dev/null | grep -q .; then
    echo "==> checkpoint already present, skipping download"
else
    DOWNLOAD_URL=$(curl -fsSL "https://api.figshare.com/v2/articles/$FIGSHARE_ARTICLE" \
        | $CLOUDRA_PY -c "
import json, sys
for f in json.load(sys.stdin)['files']:
    if f['name'] == 'checkpoints.zip':
        print(f['download_url'])
        break
else:
    raise SystemExit('checkpoints.zip not found in figshare article')")
    echo "==> downloading checkpoints.zip (~180 MB)"
    curl -fSL --retry 3 -o /tmp/flower_checkpoints.zip "$DOWNLOAD_URL"
    # zip 内层布局不带顶层 checkpoints/（实测 2026-09：根下直接是 <DATA_NAME>/<EXP_NAME>/），
    # 统一归一到 $REPO_DIR/checkpoints/ 下
    TMP_EXTRACT=$(mktemp -d)
    unzip -q -o /tmp/flower_checkpoints.zip -d "$TMP_EXTRACT"
    mkdir -p "$REPO_DIR/checkpoints"
    if [ -d "$TMP_EXTRACT/checkpoints" ]; then
        cp -R "$TMP_EXTRACT/checkpoints/"* "$REPO_DIR/checkpoints/"
    else
        cp -R "$TMP_EXTRACT/"* "$REPO_DIR/checkpoints/"
    fi
    rm -rf "$TMP_EXTRACT" /tmp/flower_checkpoints.zip
fi
CHECKPOINT=$(find "$REPO_DIR/checkpoints" -name "model.*.pt" | head -1)
[ -n "$CHECKPOINT" ] || { echo "error: no model.*.pt found under $REPO_DIR/checkpoints" >&2; exit 1; }
echo "==> checkpoint:   $CHECKPOINT"

# --- 5. 写 config（开关留给你自己开） ----------------------------------------
$CLOUDRA_PY - "$REPO_DIR" "$ENV_PYTHON" "$CHECKPOINT" <<'EOF'
import sys
from cloudra.infra.config import mutate_config

repo_dir, env_python, checkpoint = sys.argv[1:4]

def _apply(cfg):
    cfg.flower.repo_dir = repo_dir
    cfg.flower.env_python = env_python
    cfg.flower.checkpoint = checkpoint

mutate_config(_apply)
print("config written: flower.repo_dir / flower.env_python / flower.checkpoint")
EOF

# --- 6. 冒烟：README 的 pyrazole 例，小规模参数 ------------------------------
if [ "${FLOWER_SKIP_SMOKE:-0}" = "1" ]; then
    echo "==> smoke test skipped (FLOWER_SKIP_SMOKE=1)"
else
    SMOKE_DIR=$(mktemp -d)
    echo "CC(=O)CC(=O)C(F)(F)F.NNc1cccc(Br)c1" > "$SMOKE_DIR/beam.txt"
    echo "==> smoke run (CPU, sample_size=4 max_depth=6; may take a few minutes): $SMOKE_DIR"
    if "$ENV_PYTHON" "$REPO_ROOT/cloudra/tools/Chemtool/_flower_beam_driver.py" \
        --repo "$REPO_DIR" --checkpoint "$CHECKPOINT" \
        --input "$SMOKE_DIR/beam.txt" --result-dir "$SMOKE_DIR/results" \
        --out "$SMOKE_DIR/network.json" \
        --beam-size 3 --nbest 2 --max-depth 6 --sample-size 4; then
        echo "==> smoke OK: $SMOKE_DIR/network.json"
    else
        echo "error: smoke run failed; inspect $SMOKE_DIR before enabling the tool" >&2
        exit 1
    fi
fi

cat <<MSG

Done. FlowER backend is installed and configured (but the tool stays hidden).
To enable it:
    cloudra config set flower.enabled true
MSG
