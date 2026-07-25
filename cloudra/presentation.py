"""终端输出辅助：ANSI 颜色、横幅与管道日志。"""


class Color:
    PURPLE = "\033[95m"
    CYAN = "\033[96m"
    DARKCYAN = "\033[36m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"


def print_banner() -> None:
    print(f"{Color.BLUE}{Color.BOLD}")
    print("  Cloudra - AI 化学科研助手")
    print(f"  版本: v1.8.0{Color.END}")
    print("-" * 45)


def pipe_logger(process, agent_name: str) -> None:
    prefix = f"{Color.CYAN}[{agent_name}]{Color.END}"
    for line in iter(process.stdout.readline, ""):
        if not line:
            continue
        for subline in line.splitlines():
            print(f"{prefix} {subline}")
    process.stdout.close()
