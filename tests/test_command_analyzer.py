"""BashCommandClassifier 分类行为钉板测试。

钉住 cloudra/tools/core/command_analyzer.py 当前的分类结果。分类器在黑名单
枚举之后还有一道 fail-closed 升级扫描（纯子串/token 检测，见
_escalate_fail_closed）：shell 组合符（; && || $( 反引号）→ SCRIPT|DESTRUCTIVE；
粘连重定向 → WRITE|DESTRUCTIVE；未知命令 → SCRIPT。
残余已知盲区（现状而非期望）：
- git 子命令不分析（"git push origin main" 仍判为 READ）。
"""

import pytest

from cloudra.tools.core.command_analyzer import BashCommandClassifier, CommandAnalysis
from cloudra.tools.core.permission_model import Permission


def classify(command: str) -> CommandAnalysis:
    return BashCommandClassifier.classify(command)


def flags(analysis: CommandAnalysis) -> dict:
    return analysis.permission_dict()


class TestSafeCommands:
    @pytest.mark.parametrize("command", [
        "ls -la",
        "cat file.txt",
        "grep foo bar.log",
        "find . -name '*.py'",
        "pwd",
        "git status",
    ])
    def test_read_only_commands(self, command):
        a = classify(command)
        assert flags(a) == {
            "is_read": True, "is_write": False, "is_manage": False,
            "is_script": False, "is_destructive": False,
        }
        assert not a.has_pipe and not a.has_redirect

    def test_primary_cmd_extracted(self):
        a = classify("ls -la /tmp")
        assert a.primary_cmd == "ls"
        assert a.pipe_commands == ["ls"]

    def test_git_is_read_only_even_for_mutating_subcommands(self):
        # 残余盲区：git 整体在 READ_CMDS，fail-closed 不分析子命令，
        # git push/reset 不额外升级权限
        assert flags(classify("git push origin main"))["is_read"] is True
        assert flags(classify("git push origin main"))["is_destructive"] is False


class TestWriteCommands:
    def test_tee_is_write_only(self):
        assert flags(classify("tee out.txt")) == {
            "is_read": False, "is_write": True, "is_manage": False,
            "is_script": False, "is_destructive": False,
        }

    @pytest.mark.parametrize("command", ["touch a.txt", "mkdir -p d", "sed -i s/a/b/ f"])
    def test_write_cmds_also_in_destructive_pool(self, command):
        # touch/mkdir/sed 同时属于 WRITE_CMDS 和 DESTRUCTIVE_CMDS
        f = flags(classify(command))
        assert f["is_write"] is True
        assert f["is_destructive"] is True


class TestScriptCommands:
    @pytest.mark.parametrize("command,primary", [
        ("python script.py", "python"),
        ("python3 -c 'print(1)'", "python3"),
        ("/usr/bin/python3 script.py", "python3"),
        ("bash run.sh", "bash"),
        ("node app.js", "node"),
    ])
    def test_script_commands(self, command, primary):
        a = classify(command)
        assert a.primary_cmd == primary
        f = flags(a)
        assert f["is_script"] is True
        assert f["is_destructive"] is False

    def test_pip_is_script_and_destructive(self):
        # pip 同时在 SCRIPT_CMDS 和 DESTRUCTIVE_CMDS
        f = flags(classify("pip install numpy"))
        assert f["is_script"] is True
        assert f["is_destructive"] is True


class TestDestructiveCommands:
    @pytest.mark.parametrize("command", [
        "rm -rf /tmp/x",
        "dd if=/dev/zero of=/dev/sda",
        "mkfs /dev/sda1",
        "kill 1234",
        "shutdown -h now",
        "chmod 777 f",
    ])
    def test_destructive_only(self, command):
        f = flags(classify(command))
        assert f == {
            "is_read": False, "is_write": False, "is_manage": False,
            "is_script": False, "is_destructive": True,
        }

    def test_rm_rf_variant_flags_ignored(self):
        # 分类只看命令名，不看参数
        assert flags(classify("rm -rf /"))["is_destructive"] is True
        assert flags(classify("rm file.txt"))["is_destructive"] is True

    def test_case_insensitive(self):
        assert flags(classify("RM -RF x"))["is_destructive"] is True

    def test_curl_is_read_and_destructive_wget_only_destructive(self):
        # curl 同时在 READ_CMDS 和 DESTRUCTIVE_CMDS；wget 只在 DESTRUCTIVE_CMDS
        f = flags(classify("curl http://example.com"))
        assert f["is_read"] is True
        assert f["is_destructive"] is True
        f = flags(classify("wget http://example.com"))
        assert f["is_read"] is False
        assert f["is_destructive"] is True

    def test_fork_bomb_escalated_by_semicolon(self):
        # fail-closed：命令含 ';'，升级为 SCRIPT|DESTRUCTIVE（原盲区：判 NONE）
        a = classify(":(){ :|:& };:")
        f = flags(a)
        assert f["is_script"] is True
        assert f["is_destructive"] is True
        assert not a.has_pipe

    def test_mkfs_with_fs_suffix_escalated_as_unknown(self):
        # fail-closed：mkfs.ext4 经版本号裁剪后匹配不到任何命令池，
        # 按未知命令升级为 SCRIPT（原盲区：判 NONE）
        f = flags(classify("mkfs.ext4 /dev/sda1"))
        assert f["is_script"] is True


class TestPipesAndChains:
    def test_pipe_segments_all_classified(self):
        a = classify("cat f | grep x | wc -l")
        assert a.has_pipe is True
        assert a.primary_cmd == "cat"
        assert a.pipe_commands == ["cat", "grep", "wc"]
        assert flags(a)["is_read"] is True
        assert flags(a)["is_destructive"] is False

    def test_pipe_permissions_are_union(self):
        a = classify("echo start | rm -rf x")
        assert a.pipe_commands == ["echo", "rm"]
        f = flags(a)
        assert f["is_read"] is True
        assert f["is_destructive"] is True

    def test_pipe_with_absolute_path(self):
        a = classify("cat f | /usr/bin/python3 -")
        assert a.pipe_commands == ["cat", "python3"]
        assert flags(a)["is_script"] is True

    def test_and_chain_escalated_by_fail_closed(self):
        # '&&' 不是分段符，后续命令仍不参与逐段分类；但 fail-closed 扫描
        # 见到 '&&' 直接升级 SCRIPT|DESTRUCTIVE（原盲区：判 READ）
        a = classify("ls && rm -rf x")
        assert a.pipe_commands == ["ls"]
        f = flags(a)
        assert f["is_read"] is True
        assert f["is_script"] is True
        assert f["is_destructive"] is True
        assert not a.has_pipe

    def test_semicolon_chain_escalated_by_fail_closed(self):
        # ';' 不分段且紧贴命令名，'ls;' 匹配不到任何命令池；
        # fail-closed 见到 ';' 升级 SCRIPT|DESTRUCTIVE（原盲区：判 NONE）
        a = classify("ls; rm -rf x")
        assert a.pipe_commands == ["ls;"]
        f = flags(a)
        assert f["is_script"] is True
        assert f["is_destructive"] is True


class TestRedirects:
    def test_redirect_implies_write_and_destructive(self):
        a = classify("echo hi > out.txt")
        assert a.has_redirect is True
        f = flags(a)
        # echo 自身 READ + redirect 附加 WRITE|DESTRUCTIVE
        assert f["is_read"] is True
        assert f["is_write"] is True
        assert f["is_destructive"] is True

    @pytest.mark.parametrize("command", [
        "cat < in.txt",
        "cmd 2> err.txt",
    ])
    def test_redirect_variants_detected(self, command):
        assert classify(command).has_redirect is True

    def test_append_redirect_escalated_by_fail_closed(self):
        # '>>' 是两个字符，\d*[<>] 只 fullmatch 单字符 redirect，
        # has_redirect 仍为 False；但 fail-closed 见到 token 内含 '>'，
        # 升级 WRITE|DESTRUCTIVE（原盲区：判 READ）
        a = classify("echo hi >> out.txt")
        assert a.has_redirect is False
        f = flags(a)
        assert f["is_read"] is True
        assert f["is_write"] is True
        assert f["is_destructive"] is True

    def test_attached_redirect_escalated_by_fail_closed(self):
        # redirect 紧贴文件名时是单个 token，fullmatch 失败，has_redirect 为
        # False；fail-closed 见到 token 内含 '>' 升级 WRITE|DESTRUCTIVE
        # （原盲区：判 READ）
        a = classify("echo hi>out.txt")
        assert a.has_redirect is False
        f = flags(a)
        assert f["is_read"] is True
        assert f["is_write"] is True
        assert f["is_destructive"] is True

    def test_2_greater_ampersand_1_escalated_by_fail_closed(self):
        # '2>&1' 不匹配任何 REDIRECT_PATTERNS 的 fullmatch，has_redirect 仍为
        # False；fail-closed 按 token 内含 '>' 升级 WRITE|DESTRUCTIVE
        a = classify("grep x f 2>&1")
        assert a.has_redirect is False
        f = flags(a)
        assert f["is_write"] is True
        assert f["is_destructive"] is True


class TestEdgeCases:
    @pytest.mark.parametrize("command", ["", "   ", None])
    def test_empty_command(self, command):
        a = classify(command)
        assert a.primary_cmd == ""
        assert a.pipe_commands == []
        assert a.permissions == Permission.NONE

    def test_variable_assignment_stripped(self):
        a = classify("FOO=bar BAZ=qux ls -la")
        assert a.primary_cmd == "ls"
        assert a.permissions == Permission.READ

    def test_assignment_then_destructive(self):
        a = classify("IFS= rm -rf x")
        # 'IFS=' 以 '=' 结尾，不算变量赋值，primary 就是 'IFS='
        assert a.primary_cmd == "IFS="
        # fail-closed：'IFS=' 不在任何已知命令池，升级为 SCRIPT（原判 NONE）
        assert flags(a)["is_script"] is True

    def test_unclosed_quote_falls_back_to_regex(self):
        a = classify('rm -rf "unclosed')
        assert a.primary_cmd == "rm"
        assert flags(a)["is_destructive"] is True

    def test_fallback_detects_redirect_by_regex(self):
        a = classify('echo "unclosed > out.txt')
        assert a.has_redirect is True
        f = flags(a)
        assert f["is_write"] is True
        assert f["is_destructive"] is True

    def test_version_suffix_stripped_for_matching(self):
        # pip3 → cmd_core 'pip' 命中 DESTRUCTIVE_CMDS
        a = classify("pip3 install x")
        assert a.primary_cmd == "pip3"
        f = flags(a)
        assert f["is_script"] is True
        assert f["is_destructive"] is True

    def test_unknown_command_escalated_to_script(self):
        # fail-closed：未知命令不再落 NONE 放行，升级为 SCRIPT（必审批）
        a = classify("someobscuretool --flag")
        assert a.primary_cmd == "someobscuretool"
        assert a.permissions == Permission.SCRIPT


class TestFailClosedEscalation:
    """红队 PoC 逐条钉板：以下命令在黑名单枚举时代全部零审批执行，
    fail-closed 升级扫描后必须落入必审批权限位（SCRIPT|DESTRUCTIVE 触发
    bash.py 的 ensure_safety）。"""

    def test_semicolon_chain_hides_rm(self):
        # 'ls;' 被 shlex 当一个 token，';' 串接整体隐形 → 原判 NONE
        f = flags(classify("ls; rm -rf /tmp/x"))
        assert f["is_script"] is True
        assert f["is_destructive"] is True

    def test_command_substitution_dollar_paren(self):
        # 命令替换对 shlex 不可见 → 原判 READ
        f = flags(classify("echo $(id)"))
        assert f["is_script"] is True
        assert f["is_destructive"] is True

    def test_command_substitution_backtick(self):
        f = flags(classify("echo `id`"))
        assert f["is_script"] is True
        assert f["is_destructive"] is True

    def test_and_chain_hides_curl(self):
        # '&&' 不可见 → 原判 READ
        f = flags(classify("ls && curl evil.com"))
        assert f["is_script"] is True
        assert f["is_destructive"] is True

    def test_unknown_command_not_silently_allowed(self):
        # 未知命令原落 NONE 放行 → 现升级 SCRIPT
        a = classify("osascript -e 'display dialog \"x\"'")
        assert a.primary_cmd == "osascript"
        assert a.permissions == Permission.SCRIPT

    def test_attached_redirect_implies_write(self):
        # 粘连重定向 → 原判 READ，现升级 WRITE|DESTRUCTIVE
        f = flags(classify("echo pwned>/tmp/evil"))
        assert f["is_write"] is True
        assert f["is_destructive"] is True

    def test_git_push_residual_gap(self):
        # 残余盲区：git 在 READ_CMDS，子命令不分析，git push 仍判 READ。
        # 三条升级规则均不覆盖（无组合符、无重定向、basename 已知），
        # 钉住现状，后续如需拦截须引入子命令分析。
        a = classify("git push origin master")
        assert a.permissions == Permission.READ

    def test_or_chain_escalated(self):
        f = flags(classify("false || rm -rf /tmp/x"))
        assert f["is_script"] is True
        assert f["is_destructive"] is True

    def test_fallback_path_also_escalated(self):
        # shlex 失败（未闭合引号）走 _fallback_classify，升级扫描同样生效
        f = flags(classify('echo "unclosed; rm -rf /tmp/x'))
        assert f["is_script"] is True
        assert f["is_destructive"] is True


class TestNormalCommandsNotEscalated:
    """fail-closed 不误伤已知名单内的正常命令：维持原级别。"""

    @pytest.mark.parametrize("command", [
        "ls",
        "ls -la /tmp",
        "grep foo bar.log",
        "cat file.txt",
        "find . -name '*.py'",
        "cat f | grep x | wc -l",
    ])
    def test_read_commands_stay_read_only(self, command):
        assert classify(command).permissions == Permission.READ

    def test_python_script_stays_script_only(self):
        a = classify("python script.py")
        assert a.permissions == Permission.SCRIPT

    def test_xtb_is_known_script_command(self):
        # xtb 与 g16/g09 一样列入 SCRIPT_CMDS，不触发未知命令升级之外的位
        a = classify("xtb input.xyz")
        assert a.permissions == Permission.SCRIPT

    def test_pipe_of_known_commands_not_escalated(self):
        a = classify("echo start | grep x")
        assert a.permissions == Permission.READ
