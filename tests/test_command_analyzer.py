"""BashCommandClassifier 分类行为钉板测试。

钉住 cloudra/tools/core/command_analyzer.py 当前的分类结果，包括若干
已知的覆盖盲区（用注释标明，属于现状而非期望）：
- '&&' / ';' 连接的命令只分析首段（"ls && rm -rf x" 判为 READ）。
- 紧贴的 redirect（"echo hi>out.txt"）检测不到。
- fork炸弹（":(){ :|:& };:"）判为 NONE。
- 带扩展名后缀的 mkfs（"mkfs.ext4"）判为 NONE。
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
        # 现状：git 整体在 READ_CMDS，git push/reset 不额外升级权限
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

    def test_fork_bomb_not_detected(self):
        # 已知盲区：fork炸弹被拆成普通 token，判为 NONE
        a = classify(":(){ :|:& };:")
        assert a.permissions == Permission.NONE
        assert not a.has_pipe

    def test_mkfs_with_fs_suffix_not_detected(self):
        # 已知盲区：mkfs.ext4 经版本号裁剪后变成 'mkfs.ext'，匹配不到 mkfs
        assert classify("mkfs.ext4 /dev/sda1").permissions == Permission.NONE


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

    def test_and_chain_only_first_segment_analyzed(self):
        # 已知盲区：'&&' 不是分段符，后续命令完全不影响分类
        a = classify("ls && rm -rf x")
        assert a.pipe_commands == ["ls"]
        assert a.permissions == Permission.READ
        assert not a.has_pipe

    def test_semicolon_attached_makes_command_unrecognized(self):
        # 已知盲区：';' 不分段且紧贴命令名，'ls;' 匹配不到任何命令池
        a = classify("ls; rm -rf x")
        assert a.pipe_commands == ["ls;"]
        assert a.permissions == Permission.NONE


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

    def test_append_redirect_not_detected(self):
        # 已知盲区：'>>' 是两个字符，\d*[<>] 只 fullmatch 单字符 redirect
        a = classify("echo hi >> out.txt")
        assert a.has_redirect is False
        assert a.permissions == Permission.READ

    def test_attached_redirect_not_detected(self):
        # 已知盲区：redirect 紧贴文件名时是单个 token，fullmatch 失败
        a = classify("echo hi>out.txt")
        assert a.has_redirect is False
        assert a.permissions == Permission.READ

    def test_2_greater_ampersand_1_not_detected_as_redirect(self):
        # 已知盲区：'2>&1' 不匹配任何 REDIRECT_PATTERNS 的 fullmatch
        a = classify("grep x f 2>&1")
        assert a.has_redirect is False


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
        assert a.permissions == Permission.NONE

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

    def test_unknown_command_is_none(self):
        a = classify("someobscuretool --flag")
        assert a.primary_cmd == "someobscuretool"
        assert a.permissions == Permission.NONE
