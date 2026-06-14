#!/bin/bash

# ==============================================================================
# Cloudra - AI 化学科研助手 完整功能自动化展示脚本 (Automated Demo)
# ==============================================================================
# 
# 本脚本将顺序执行项目核心功能展示，无需人工干预。
#
# ==============================================================================

# 设置颜色和格式
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# 打印横幅
print_banner() {
    echo -e "${BLUE}${BOLD}"
    echo "  ____ _                    _               "
    echo " / ___| | ___  _   _  __| |_ __ __ _      "
    echo "| |   | |/ _ \| | | |/ _\` | '__/ _\` |     "
    echo "| |___| | (_) | |_| | (_| | | | (_| |     "
    echo " \____|_|\___/ \__,_|\__,_|_|  \__,_|     "
    echo -e "                                            ${NC}"
    echo -e "${GREEN}${BOLD}Cloudra: 面向化学科研的 AI Agent 协作框架${NC}"
    echo -e "${BLUE}----------------------------------------------------${NC}"
}

# 辅助函数：打印阶段标题
print_step() {
    echo -e "\n${BOLD}${BLUE}>>> STEP: $1${NC}"
    echo -e "${BLUE}----------------------------------------------------${NC}"
}

# 主程序逻辑
print_banner
# 1. 环境与依赖检查
print_step "环境与依赖检查"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: 未找到 python3${NC}"
    exit 1
fi

if ! python3 -c "import cloudra" &> /dev/null; then
    echo -e "${YELLOW}正在安装项目依赖...${NC}"
    pip install -e . --quiet
fi
echo -e "${GREEN}[OK] 环境准备就绪${NC}"

# 2. 配置信息展示
print_step "配置信息展示 (脱敏)"
cloudra config show
echo ""

# 3. 自动化测试套件展示
print_step "运行系统单元测试 (验证稳定性)"
export PYTHONPATH=$PYTHONPATH:.
pytest tests/ -v
if [ $? -eq 0 ]; then
    echo -e "${GREEN}[PASS] 所有核心组件测试通过${NC}"
else
    echo -e "${RED}[FAIL] 部分测试未通过，请检查环境${NC}"
fi

# 4. 功能模块 1: 文献调研 (Researcher Agent)
print_step "功能演示 1: 文献调研与总结 (Researcher Agent)"
echo -e "${YELLOW}场景: 搜索关于“钙钛矿太阳能电池”的最新 2 篇论文并总结${NC}"
# 注意: 为了防止演示时间过长，将数量限制为 2
cloudra run "搜索关于钙钛矿太阳能电池(Perovskite Solar Cells)的最新 2 篇论文并给出中文总结" --new

# 5. 功能模块 2: 分子处理 (Visionary/Chem Agent)
print_step "功能演示 2: 化学结构识别与绘图 (Visionary Agent)"
echo -e "${YELLOW}场景: 搜索咖啡因的 SMILES 字符串并调用 RDKit 绘制结构图${NC}"
cloudra run "搜索咖啡因的 SMILES 字符串，使用分子绘图工具画出结构图，并保存为 caffeine.png" --new

# 6. 功能模块 3: 多 Agent 深度协作 (Coordinator Orchestration)
print_step "功能演示 3: 跨 Agent 复杂任务调度 (Multi-Agent Collaboration)"
echo -e "${YELLOW}场景: 调研催化剂合成方法并生成模拟代码${NC}"
# 优化提示词，引导 Agent 明确分工，提高成功率
cloudra run "请先指派 Researcher 调研 ZSM-5 沸石的经典水热合成配方，然后指派 Writer 将其总结为一份报告并附带模拟反应动力学的 Python 伪代码。" --new

# 7. 历史记录展示
print_step "查看 Session 历史记录"
cloudra history

# 结束
echo -e "\n${GREEN}${BOLD}====================================================${NC}"
echo -e "${GREEN}${BOLD}展示任务全部执行完毕！${NC}"
echo -e "${GREEN}${BOLD}====================================================${NC}"
echo -e "详细推理过程可查看: ${BLUE}$(cloudra config get data_dir)/conversations/${NC}"
