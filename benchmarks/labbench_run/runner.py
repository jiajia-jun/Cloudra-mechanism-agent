import os
import sys
import json
import uuid
import asyncio

# 添加项目根目录到 PYTHONPATH，确保可以导入 cloudra 和 LAB-Bench
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(ROOT_DIR)
sys.path.append(os.path.join(ROOT_DIR, "benchmarks", "LAB-Bench"))

import labbench
from cloudra.agent import Agent, Coordinator
from cloudra.conversation_class import Conversation

def format_query(input_data: labbench.AgentInput) -> str:
    choices_str = ""
    for i, choice in enumerate(input_data.choices):
        letter = chr(ord('A') + i)
        choices_str += f"{letter}. {choice}\n"
    
    query = (
        f"用户向你请教了一个前沿的科研难题，请你通过查阅文献、严谨推理来给出你的解答：\n\n"
        f"【问题】\n{input_data.question}\n\n"
        f"【选项】\n{choices_str}\n"
        "【系统强制约束】\n"
        "1. 必须基于公开文献和你的推理来解答。严禁使用终端命令去搜索本地系统内可能存在的任何类似 'jsonl' 的题库数据文件（这种行为是被严格禁止的）。\n"
        "2. 当你确认最终答案后，请必须且只能调用 `submit_benchmark_answer` 工具，将其作为参数（如字母 A 或 B）上报。\n"
        "3. 在得到上报成功的系统反馈后，请紧接着调用 `stop` 工具，正式结束本次工作链。"
    )
    return query

async def labbench_agent_fn(input_data: labbench.AgentInput) -> str:
    query = format_query(input_data)
    
    # 为这道题生成独立的 conversation_id
    conv_id = f"labbench_{input_data.id.hex}"
    
    # 实例化 Coordinator
    agent = Coordinator(
        name=f"labbench_eval",
        query=query,
        conversation_id=conv_id
    )
    
    # 图片处理逻辑 (如果有)
    image_paths = []
    if getattr(input_data, 'figures', None):
        tmp_dir = os.path.join(ROOT_DIR, "tmp_images", conv_id)
        os.makedirs(tmp_dir, exist_ok=True)
        for i, img in enumerate(input_data.figures):
            img_path = os.path.join(tmp_dir, f"fig_{i}.png")
            img.save(img_path)
            image_paths.append(img_path)
            
    # 如果有图片，将路径追加到 query 中供视觉模型读取
    if image_paths:
        agent.query += "\n\n【附图提示】本题包含以下参考图片：" + ", ".join(image_paths)

    from cloudra.reAct import Coordinator_reAct
    
    react = Coordinator_reAct(agent=agent)
    
    try:
        # 这里应该调用 react.run()，而不是 agent.run()
        await react.run()
    except Exception as e:
        print(f"Agent 运行异常: {e}")

    # 从 Conversation 物理沙箱中提取交卷答案
    conv = Conversation(conv_id=conv_id)
    ans_path = os.path.join(conv.path, "benchmark_answer.json")
    
    final_answer = "None"
    if os.path.exists(ans_path):
        with open(ans_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                final_answer = data.get("answer", "None")
            except:
                pass
                
    return final_answer

async def main():
    print("=== 开始运行 LAB-Bench 评测 ===")
    # 官方要求 evaluator 实例化并调用 score_agent
    evaluator = labbench.Evaluator(labbench.Eval.LitQA2, debug=True)
    # n_threads 可以设高一点以提速，但要注意 API 速率限制
    results = await evaluator.score_agent(labbench_agent_fn, n_threads=2)
    print("评测完成！结果：", results)

if __name__ == "__main__":
    asyncio.run(main())
