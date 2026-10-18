# Cloudra 系统设计体检（2026-10-18）

> **历史审计快照**：下表和源码片段记录修复前的问题，不代表当前仍未修复。后续修复、回归结果、科学规则边界及未通过的额外场景，见[修复记录](2026-10-18-system-design-repairs.md)。保留原证据，不用修复后的源码覆盖问题现场。

这次 IRC 问题不是孤例。主要病因是：**用弱依据取代真实事实、传递时丢失操作对象、把工程限制算成科学结论，以及把内部协议交给模型维护。** 修法应当减少错误转换和重复判断，不再加一层门。

这是工作区源码审计快照，基于 HEAD `a2cd50dd72afdaa77290514ed29587a779e06f12` 加本轮未提交修改。覆盖 Agent 内核、角色与工具执行、调度与远端计算、结构/构象工具、TS/IRC、DAG/Benchmark、启动器/API/前端、全局记忆与知识检索。不能据此声称整个系统没有其他缺陷。

证据分两类：沿当前源码完整调用链可以确认的行为，以及使用临时文件、内存数据库或替身执行端复现的行为。每项分别标明。没有提交新量化计算、取消真实作业、重启服务或改变评分规则；也没有运行全套测试。普通代码异常、必要科学验收和明确的用户决策不因“有门”就被认定为问题。

## 先看这些问题

以下尚未修复，详细证据见后文对应章节。P1 表示优先处理，P2 表示后续处理；不代表生产中已经发生过对应损失。

| 优先级 | 触发和实际后果 | 错在哪里 | 最小修复方向 | 证据章节 |
| --- | --- | --- | --- | --- |
| P1 | 远端取消命令失败或进程尚未退出，任务仍被确认取消并释放容量 | 把请求当成退出事实 | 保持占用，等执行端或调度器确认真实退出 | 计算执行 §1 |
| P1 | 普通角色配置禁止 bash，目录和调用权限仍允许 bash | deny 保存后没有进入实际能力集合 | 由同一处生成并消费真实工具集合 | Agent 内核 §1 |
| P1 | 用户指定数据库 B 启动，已有健康实例 A 被直接复用 | 健康状态被当作实例身份 | 先解析目标库，再核对现有属主 | 控制面 §1 |
| P2 | 全局记忆压缩等待模型期间，另一项目成功保存的经验被覆盖 | 旧副本整文件覆盖共享事实 | 提交时重读并保留新增内容 | 控制面 §2 |
| P2 | 给 CREST 的 XYZ/MOL 已有完整坐标，却被清除构象、重新嵌入/组装 | 把读取给定几何与从拓扑建模混成一步 | 有坐标就消费原坐标，无坐标才生成 | 计算执行 §4 |
| P2 | 坐标已生成，但廉价力场不支持或未收敛，CREST/xTB 根本不能接手 | 把一种预处理方法的失败当成后续方法无资格 | 区分坐标可用与力场收敛 | 计算执行 §3 |
| P2 | 科学计算缺少原生日志，Slurm/SSH 仍可报 done | 调度完成填补了引擎终止证据缺失 | 对齐后端执行成功语义；shell 另按退出码处理 | 计算执行 §2 |
| P2 | 子 Agent 没有自己的待办，却被同项目他人的计算阻止结束 | 项目范围错套到子任务范围 | Coordinator 查全项目；普通子 Agent 查自己负责的工作 | Agent 内核 §2 |
| P2 | 有真实历史消息，但 transcript 返回空列表且没有截断提示 | 先截所有事件，再筛消息 | 查询时先筛消息，并复用现有分页/迭代能力 | 控制面 §3 |
| P2 | 文件编辑要求模型复制 expected_sha256，覆写漏填即失败 | 内部并发绑定暴露成模型输入 | 程序绑定 session 已读快照，保留并发冲突保护 | Agent 内核 §3 |
| P2 | 知识库故障仍返回来源 available、零命中 | 把注册成功当成本次检索成功 | 返回本次来源状态，保留其他正常来源结果 | 知识检索补扫 |
| P1 | 点击未选中的项目 P 更改目录，实际修改当前 Q | 点击对象在回调中丢失，写操作使用全局选中对象 | 传递并消费被点项目的已有 id | 前端补扫 §1 |
| P1 | 输入框显示回复 B，发送却回答同项目 A 的待办问题 | 项目收件箱第一个问题覆盖当前会话目标 | 普通输入框按当前 session；其他问题由已有专用卡片明确选择 | 前端补扫 §2 |
| P2 | 创建项目被后端拒绝，界面仍提示创建成功 | HTTP 成功被当成业务接受 | 在共同层复用现有 accepted 检查 | 前端补扫 §3 |
| P2 | 正常日志仅加空白越过读取预算，满分变为 unsupported claims 负分 | 工程扫描未完成被算成科学缺证据 | 保留内存限制，必要解析或明确工程 incomplete | Benchmark 补扫 §1 |
| 评分语义待裁定 | 空图、无日志，非空 Gold 仍可得自洽分及总分 0.3 | all([]) 的程序真值被直接换成已交付的自洽奖励 | 先区分未交付与已证明；具体评分不在本轮擅改 | Benchmark 补扫 §2 |

缺少原生日志的 done 是**执行结果归因错误**，本次没有发现它直接绕过 DAG/TS 科学验收。工具 deny 问题也不代表其他权限和审批全部失效。transcript 问题限定该 API，不等于当前前端所有历史丢失。另一 checkout 本身不证明复用了错误数据库，必须有目标 store/data_dir 不同等具体条件。空图得分和大日志误罚均使用临时 fixture 调用了当前真实评分入口，具体复现脚本和输出保留在补扫证据中。

修复顺序建议：先处理真实作业生命周期、操作对象错投和权限配置失效，再处理输入坐标被替换、信息覆盖/丢失及评分证据归因。都优先复用现有执行端、对象身份、查询和校验逻辑，不新增公开控制字段。

## 这轮已经修掉的两处 IRC 工程错误

**第一处：虚频位移启发式提前返回，真实端点证明根本没有执行。** 当前改成只产生提示；正常终止、恰好一个虚频、同一个 TS、真实双向 IRC 末帧、实际 Opt 起止几何、端点零虚频和反应物/产物身份仍需成立。插值、位移比值、监测原子对和几何区间不能替代或否决这条完整证据链。

**第二处：ORCA 日志已经原样回显输入坐标，解析器只认 CARTESIAN 表。** IA8 的 NumFreq 日志属于这种真实格式，第三方整体解析又会在短偶极矩块崩溃。当前直接读取原生日志中的逐原子坐标，没有推测或补造坐标。静态频率计算可以使用该输入几何；Opt/IRC/scan/NEB 的输入不能充当末帧；Opt 来源校验也读取真实输入几何。

IA8 原始请求和日志在当前源码上本地重验得到 `verification_status=pass`，原 watch_pairs 未改，可疑模式的 `[warning]` 保留。回执保存在 `/tmp/cloudra-ia8-local-verification.json`；这是本地源码重验，**不是已运行服务的验收回执，也不是 Gold 回填**。

聚焦回归已通过：`test_ts_guess`、`test_ts_guess_reaction_state`、`test_orca_frames`、`test_log_parser`、`test_irc_endpoint_optimization`、`test_irc_evidence_semantics`、`test_ts_process`、`test_dag_file_science`、`test_benchmark`。可选外部程序相关测试按环境跳过；compileall、ruff 和 diff 空白检查通过。新增回归覆盖启发式异常但证据完整、启发式异常且证据不足、真实 NumFreq 坐标回显、以及禁止把优化输入当末帧。

后面的源码是审计时实际文件的完整相关片段，保留原分支和返回，不使用伪代码或省略号替代调用链。公共工具生命周期统一见“Agent 内核”共用链；化学判定另按下面的本地调用链展示。

## IRC 修复的实际入口、判定与返回链

### `TsGuess.tool_call`

来源：[cloudra/tools/Chemtool/ts_guess.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/ts_guess.py:1339)，行 1339–1394。

```python
    async def tool_call(self, user_input: TsGuess_input_schema, session: Session) -> TsGuess_output_schema:
        if user_input.run_id is not None:
            try:
                return await self._run_guess(user_input, session)
            except (ValueError, OSError) as exc:
                return TsGuess_output_schema(is_success=False, message=f'ts_guess: {exc}')
        # 路径语义收口：所有文件路径字段的相对路径统一解析到 agent 工作
        # 目录（沙箱）；绝对路径保持既有权限语义。
        user_input = user_input.model_copy(
            update={
                **{
                    field: resolve_tool_path(self, value)
                    for field, value in {
                        "reactant_path": user_input.reactant_path,
                        "product_path": user_input.product_path,
                        "input_path": user_input.input_path,
                        "output_path": user_input.output_path,
                        "log_path": user_input.log_path,
                        "ts_candidate_path": user_input.ts_candidate_path,
                        "freq_log": user_input.freq_log,
                        "irc_log": user_input.irc_log,
                        "output_dir": user_input.output_dir,
                    }.items()
                    if value
                },
                **{field: [resolve_tool_path(self, path) for path in getattr(user_input, field)]
                   for field in ("reactant_logs", "product_logs")},
            }
        )
        mode = user_input.mode
        if mode == "scan":
            mode = "scan_parse" if user_input.log_path else "scan_prepare"

        handlers = {
            "xtb_path": self._xtb_path,
            "interpolate": self._interpolate,
            "scan_prepare": self._scan_prepare,
            "scan_parse": self._scan_parse,
            "verify": self._verify,
        }
        if mode not in handlers:
            import difflib
            matches = difflib.get_close_matches(mode, list(handlers.keys()), n=1, cutoff=0.35)
            suggestion = f" Did you mean {matches[0]!r}?" if matches else ""
            return TsGuess_output_schema(
                is_success=False,
                message=f"Unknown mode {mode!r}.{suggestion} Allowed modes: {sorted(handlers.keys())}",
            )
        try:
            # handler 是同步重活（xtb_path 会 proc.communicate 等 xTB 子进程、
            # scan_parse 逐帧啃大日志）：卸载出事件循环，避免冻结整个 API。
            return await asyncio.to_thread(handlers[mode], user_input)
        except _UnconfirmedEndpointMapping as exc:
            return TsGuess_output_schema(is_success=False, message=str(exc), mapping_candidates=exc.candidates)
        except Exception as e:
            return TsGuess_output_schema(is_success=False, message=f"{user_input.mode} failed: {e}")
```

### `_parse_freq_log`

来源：[cloudra/tools/Chemtool/ts_guess.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/ts_guess.py:1200)，行 1200–1322。

```python
def _parse_freq_log(log_path: str, engine: str) -> dict:
    """解析频率日志。除频率与收敛性外，尽量返回末帧元素、坐标与 vibdisps。"""
    with open(log_path, encoding="utf-8", errors="replace") as f:
        text = f.read()

    vibfreqs: Optional[list[float]] = None
    vibdisps = None
    converged: Optional[bool] = None
    symbols: Optional[list[str]] = None
    positions = None

    try:
        import cclib

        data = cclib.io.ccread(log_path)
        if data is not None:
            vf = getattr(data, "vibfreqs", None)
            if vf is not None and len(vf) > 0:
                vibfreqs = [float(v) for v in vf]
            vd = getattr(data, "vibdisps", None)
            if vd is not None and len(vd) > 0:
                import numpy as np

                vibdisps = np.asarray(vd, dtype=float)
            optdone = getattr(data, "optdone", None)
            if isinstance(optdone, bool):
                converged = optdone
            elif optdone:
                converged = True
            atomnos = getattr(data, "atomnos", None)
            atomcoords = getattr(data, "atomcoords", None)
            # openbabel 回退解析失败时会给 shape (n,0) 的畸形空 atomcoords：
            # len(atomcoords)>0（帧数非零）但无原子。必须同时校验 atomnos 与
            # 末帧原子数非空，否则空 symbols/positions 会挡住标准取向回退。
            if (
                atomnos is not None
                and atomcoords is not None
                and len(atomnos) > 0
                and len(atomcoords) > 0
                and getattr(atomcoords[-1], "size", 0) > 0
            ):
                import numpy as np
                from cclib.parser.utils import PeriodicTable

                pt = PeriodicTable()
                symbols = [pt.element[int(z)] for z in atomnos]
                positions = np.asarray(atomcoords[-1], dtype=float)
    except Exception:
        pass

    if vibfreqs is None:
        if engine == "orca":
            # cclib 1.8.x 解析 ORCA 6.x 日志整体抛 IndexError（实测 ORCA 6.1.1 全灭），
            # 且 ExtOpt/NumFreq 等外部 MLIP 日志无 SCF 块 cclib 也常失败——文本回退
            # 走 orca_frames 的 VIBRATIONAL FREQUENCIES 原生解析（Gaussian 的
            # "Frequencies --" 行在 ORCA 日志里不存在，GH #G2）。
            vibfreqs = orca_frames.vibfreqs_from_text(text) or None
        else:
            # 正则回退：Gaussian "Frequencies --" 行（虚频以负值打印）
            freqs: list[float] = []
            for m in gaussian_frames.FREQ_LINE_RE.finditer(text):
                for tok in m.group(1).split():
                    try:
                        freqs.append(float(tok))
                    except ValueError:
                        break
            if freqs:
                vibfreqs = freqs

    if vibfreqs is None:
        raise ValueError(f"Failed to parse vibrational frequencies from the frequency log: {log_path}")

    if vibdisps is None and engine == "gaussian":
        vibdisps = gaussian_frames.vibdisps_from_text(text, len(vibfreqs))
    elif vibdisps is None and engine == "orca":
        # cclib 也可能只解析出裁掉零频的频率。原生位移按完整 3N 轴编号，
        # 必须连同原生频率一起取，不能拿裁剪后的轴推算原子数或匹配位移。
        native_freqs = orca_frames.vibfreqs_from_text(text)
        n_atoms = len(native_freqs) // 3 if native_freqs and len(native_freqs) % 3 == 0 else 0
        if n_atoms > 0:
            native_disps = orca_frames.vibdisps_from_text(text, len(native_freqs), n_atoms)
            if native_disps is not None:
                vibfreqs, vibdisps = native_freqs, native_disps

    if converged is None:
        if engine == "orca":
            # ORCA 没有 Gaussian 的 "Normal termination" 标记（自报 "ORCA TERMINATED
            # NORMALLY"），且跑满最大步数未收敛的优化仍会正常终止——收敛状态优先按
            # ORCA 自己的优化收敛标记判定，非优化作业回退到正常终止标记（GH #G3）。
            opt_state = orca_frames.opt_converged(text)
            converged = opt_state if opt_state is not None else orca_frames.normal_termination(text)
        else:
            # 文本回退：正常终止且无错误标记视为收敛（含纯 freq 作业沿用已收敛几何的情形）
            converged = ("Normal termination" in text) and ("Error termination" not in text)

    if positions is None and engine == "gaussian":
        blocks = gaussian_frames.std_orientation_frames(text)
        if blocks:
            import numpy as np
            from cclib.parser.utils import PeriodicTable

            rows = blocks[-1]
            pt = PeriodicTable()
            symbols = [pt.element[int(z)] for z, *_ in rows]
            positions = np.asarray([[x, y, z] for _, x, y, z in rows], dtype=float)
    elif positions is None and engine == "orca":
        # ORCA 末帧几何同样走文本权威坐标块；cclib 对 ORCA 6.1 崩溃时也保留 TS
        # 几何，供模式方向和 IRC 来源核对使用。
        ts_xyz = orca_frames.final_xyz_from_text(text)
        parsed_xyz = _parse_xyz(ts_xyz) if ts_xyz.strip() else None
        if parsed_xyz is not None:
            import numpy as np

            symbols = list(parsed_xyz[0])
            positions = np.asarray(parsed_xyz[1], dtype=float)

    return {
        "vibfreqs": vibfreqs,
        "vibdisps": vibdisps,
        "converged": converged,
        "symbols": symbols,
        "positions": positions,
    }
```

### `TsGuess._verify`

来源：[cloudra/tools/Chemtool/ts_guess.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/ts_guess.py:2375)，行 2375–2517。

```python
    def _verify(self, user_input: TsGuess_input_schema) -> TsGuess_output_schema:
        if not user_input.freq_log:
            raise ValueError("verify requires freq_log")
        if not os.path.isfile(user_input.freq_log):
            raise ValueError(f"Frequency log does not exist: {user_input.freq_log}")

        engine = detect_qm_engine(user_input.freq_log)
        if engine not in {"gaussian", "orca"}:
            raise ValueError(f"Cannot verify frequency log with unknown or unsupported engine: {engine}")
        if user_input.engine is not None and user_input.engine != engine:
            raise ValueError(
                f"Frequency log engine mismatch: requested {user_input.engine}, detected {engine}"
            )
        # Use the same detected engine for native parsing, IRC dispatch and atom indices.
        user_input = user_input.model_copy(update={"engine": engine})
        freq = _parse_freq_log(user_input.freq_log, user_input.engine)
        vibfreqs = freq["vibfreqs"]
        imag = [f for f in vibfreqs if f < 0]
        n_imag = len(imag)
        checks: list[str] = []
        references = {}
        reference_error = None
        if freq["converged"] and n_imag == 1:
            try:
                references = _reference_molecules(user_input)
            except Exception as exc:
                reference_error = str(exc)

        irc_end_a_path = ""
        irc_end_b_path = ""
        imag_mode_aligned: Optional[bool] = None
        imag_mode_alignment = ""

        def _record_mode_alignment() -> None:
            nonlocal imag_mode_aligned, imag_mode_alignment
            assessment = _assess_imag_mode_alignment(
                vibfreqs,
                freq.get("vibdisps"),
                user_input.watch_pairs,
                symbols=freq.get("symbols"),
                positions=freq.get("positions"),
                index_base=atom_index_base(user_input.engine),
                charge=total_charge(references["reactant"]) if "reactant" in references else user_input.charge or 0,
            )
            imag_mode_aligned = assessment["aligned"]
            imag_mode_alignment = assessment["message"]
            warning = (
                "[warning] Imaginary-mode alignment is advisory; strict verification uses actual IRC endpoint proof. "
                if assessment["status"] in {"missing", "undecidable", "misaligned"} else ""
            )
            checks.append(warning + assessment["message"])
            checks.extend(assessment.get("details") or [])

        if reference_error is not None:
            checks.append(f"Endpoint reference structures could not be parsed: {reference_error}")
            verdict = "inconclusive: the endpoint reference structures could not be parsed."
            status = "inconclusive"
        elif user_input.strict:
            if not freq["converged"]:
                checks.append("The frequency job did not converge normally; the first-order saddle-point premise cannot be established.")
                verdict = "inconclusive: the frequency job did not converge normally; the available material is insufficient for a strict judgement."
                status = "inconclusive"
            elif n_imag != 1:
                if n_imag == 0:
                    checks.append("A normally terminated frequency job has no imaginary frequency: the structure is a minimum, not a first-order saddle point.")
                else:
                    checks.append(
                        f"A normally terminated frequency job has {n_imag} imaginary frequencies "
                        f"({', '.join(f'{f:.1f}' for f in imag)} cm⁻¹): the structure is a higher-order saddle point."
                    )
                verdict = "fail: the strict check requires exactly one imaginary frequency."
                status = "fail"
            else:
                checks.append(f"Exactly 1 imaginary frequency ({imag[0]:.1f} cm⁻¹): the first-order saddle-point premise holds.")
                _record_mode_alignment()
                status, verdict, info = self._strict_path_verdict(user_input, checks, references)
                if info is not None:
                    irc_end_a_path = info["path_a"]
                    irc_end_b_path = info["path_b"]
        else:
            if not freq["converged"]:
                checks.append("The frequency job did not converge normally; cannot judge the TS candidate from it.")
                verdict = "inconclusive: the frequency job did not converge normally."
                status = "inconclusive"
            elif n_imag == 0:
                checks.append("No imaginary frequency: the structure is a minimum, not like a first-order saddle point.")
                verdict = "unlikely: no imaginary frequency; the structure looks more like a minimum."
                status = "fail"
            elif n_imag > 1:
                checks.append(
                    f"{n_imag} imaginary frequencies ({', '.join(f'{f:.1f}' for f in imag)} cm⁻¹): "
                    "the structure looks more like a higher-order saddle point."
                )
                verdict = "unlikely: multiple imaginary frequencies; the structure looks more like a higher-order saddle point."
                status = "fail"
            else:
                checks.append(
                    f"Exactly 1 imaginary frequency ({imag[0]:.1f} cm⁻¹): acceptable as a first-order saddle-point candidate, but this is not sufficient proof."
                )
                _record_mode_alignment()
                irc_ok: Optional[bool] = None
                info = self._extract_irc_endpoints(
                    user_input.irc_log, checks, engine=user_input.engine,
                    output_dir=user_input.output_dir or os.path.splitext(user_input.freq_log)[0] + "_verify",
                    require_two_sides=False,
                )
                if info is not None:
                    irc_end_a_path = info["path_a"]
                    irc_end_b_path = info["path_b"]
                    irc_ok = self._check_irc_connectivity(
                        user_input, info["end_a"], info["end_b"], checks, references,
                    )

                if user_input.irc_log and info is None:
                    verdict = "inconclusive: IRC was provided, but comparable endpoint geometries could not be obtained."
                    status = "inconclusive"
                elif irc_ok is False:
                    verdict = "unlikely: the rough connectivity of the IRC endpoints is inconsistent with the expected structures."
                    status = "fail"
                elif irc_ok == "inconclusive":
                    verdict = (
                        "inconclusive: the IRC endpoints could not be compared with the expected "
                        "structures (atom order or element mismatch); connectivity is undecidable."
                    )
                    status = "inconclusive"
                else:
                    reason = "one imaginary frequency" + ("; rough IRC connectivity consistent" if irc_ok else "")
                    verdict = f"candidate: {reason}; advisory only for the agent's next step, not a strict proof of the TS."
                    status = "candidate"

        return TsGuess_output_schema(
            is_success=True,
            verdict=verdict,
            verification_status=status,
            n_imag=n_imag,
            imag_freqs=[round(f, 2) for f in imag],
            checks=checks,
            irc_end_a_path=irc_end_a_path,
            irc_end_b_path=irc_end_b_path,
            imag_mode_aligned=imag_mode_aligned,
            imag_mode_alignment=imag_mode_alignment,
            message=f"TS verification complete: {verdict}",
        )
```

### `TsGuess._extract_irc_endpoints`

来源：[cloudra/tools/Chemtool/ts_guess.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/ts_guess.py:2519)，行 2519–2585。

```python
    @staticmethod
    def _extract_irc_endpoints(irc_log: str | None, checks: list[str], *,
                               engine: str, output_dir: str,
                               require_two_sides: bool) -> Optional[dict]:
        """提取有坐标的 IRC 外侧帧；strict 时必须分别来自 rx<0 与 rx>0。"""
        if not irc_log:
            checks.append("No IRC log provided.")
            return None
        if not os.path.isfile(irc_log):
            raise ValueError(f"IRC log does not exist: {irc_log}")

        if engine == "orca":
            return TsGuess._extract_orca_irc_endpoints(
                irc_log, checks, output_dir=output_dir, require_two_sides=require_two_sides,
            )

        from cloudra.tools.core import gaussian_frames

        try:
            frames, meta = gaussian_frames.extract_irc(irc_log)
        except Exception as e:
            checks.append(f"IRC endpoint extraction failed: {e}")
            return None

        valid = [frame for frame in frames if frame.xyz.strip()]
        if require_two_sides:
            negative = [
                frame for frame in valid
                if frame.reaction_coordinate is not None and frame.reaction_coordinate < 0
            ]
            positive = [
                frame for frame in valid
                if frame.reaction_coordinate is not None and frame.reaction_coordinate > 0
            ]
            if not negative or not positive:
                checks.append("The IRC log does not provide valid coordinate frames on both rx<0 and rx>0 sides.")
                return None
            end_a = min(negative, key=lambda frame: frame.reaction_coordinate)
            end_b = max(positive, key=lambda frame: frame.reaction_coordinate)
        else:
            if len(valid) < 2:
                checks.append("Fewer than two path frames with coordinates in the IRC log.")
                return None
            end_a, end_b = valid[0], valid[-1]

        out_dir = output_dir
        os.makedirs(out_dir, exist_ok=True)
        path_a = os.path.join(out_dir, "irc_end_a.xyz")
        path_b = os.path.join(out_dir, "irc_end_b.xyz")
        atomic_write_text(path_a, end_a.xyz.rstrip() + "\n")
        atomic_write_text(path_b, end_b.xyz.rstrip() + "\n")
        checks.append(
            f"IRC outer frames extracted: irc_end_a.xyz (rx={end_a.reaction_coordinate}), "
            f"irc_end_b.xyz (rx={end_b.reaction_coordinate}) -> {out_dir}"
        )
        if require_two_sides and not (
            meta.get("forward_converged", False) and meta.get("backward_converged", False)
        ):
            checks.append("The IRC did not reach a minimum on at least one side; strict requires separate optimization and zero-imaginary frequency evidence for its actual outer frames.")
        return {
            "end_a": end_a,
            "end_b": end_b,
            "frames": frames,
            "meta": meta,
            "path_a": path_a,
            "path_b": path_b,
        }
```

### `TsGuess._strict_path_verdict`

来源：[cloudra/tools/Chemtool/ts_guess.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/ts_guess.py:2650)，行 2650–2709。

```python
    def _strict_path_verdict(self, user_input: TsGuess_input_schema,
                             checks: list[str], references) -> tuple[str, str, Optional[dict]]:
        """核对同一 TS 的 IRC 外侧帧实际优化到两侧身份正确的零虚频极小点。"""
        from rdkit import Chem

        from cloudra.tools.core.irc_evidence import verify_short_irc_direction

        def inconclusive(reason: str, info):
            checks.append(_IRC_TRUNCATION_REMEDY)
            return "inconclusive", f"inconclusive: {reason} {_IRC_TRUNCATION_REMEDY}", info

        info = self._extract_irc_endpoints(
            user_input.irc_log, checks, engine=user_input.engine,
            output_dir=user_input.output_dir or os.path.splitext(user_input.freq_log)[0] + "_verify",
            require_two_sides=True,
        )
        if info is None:
            return inconclusive("no usable bidirectional IRC endpoints.", None)
        if not all(role in references for role in ("reactant", "product")):
            return inconclusive("missing the expected reactant and product structures.", info)
        if not user_input.reactant_logs or not user_input.product_logs:
            return inconclusive("missing actual endpoint optimization and zero-imaginary frequency logs.", info)

        def species(role):
            from rdkit.Chem import rdDetermineBonds

            molecule = Chem.Mol(references[role])
            if molecule.HasProp("cloudra_graph_status") and molecule.GetProp("cloudra_graph_status") == "unresolved":
                rdDetermineBonds.DetermineBonds(molecule, charge=total_charge(references[role]))
            molecule = Chem.RemoveHs(molecule)
            for atom in molecule.GetAtoms():
                atom.SetAtomMapNum(0)
            return Chem.MolToSmiles(molecule)

        try:
            reactant_smiles, product_smiles = species("reactant"), species("product")
        except (ValueError, RuntimeError) as exc:
            checks.append(f"Expected endpoint identity cannot be resolved; supply a complete MOL/SDF graph: {exc}")
            return inconclusive("the expected endpoint molecular identity is unresolved.", info)

        passed, details = verify_short_irc_direction(
            user_input.irc_log, [user_input.freq_log],
            user_input.product_logs, user_input.reactant_logs,
            charge=total_charge(references["reactant"]),
            reactant_smiles=reactant_smiles, product_smiles=product_smiles,
        )
        checks.extend(details)
        if passed:
            return (
                "pass",
                "pass: both actual IRC outer frames optimize to the expected zero-imaginary endpoint minima.",
                info,
            )
        checks.append(_IRC_TRUNCATION_REMEDY)
        return (
            "fail",
            "fail: the submitted logs do not prove that both actual IRC outer frames optimize "
            f"to the expected zero-imaginary endpoint minima. {_IRC_TRUNCATION_REMEDY}",
            info,
        )
```

### `verify_short_irc_direction`

来源：[cloudra/tools/core/irc_evidence.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/irc_evidence.py:574)，行 574–659。

```python
def verify_short_irc_direction(
    irc_log,
    ts_logs: Sequence,
    endpoint_a_logs: Sequence,
    endpoint_b_logs: Sequence,
    *,
    charge: int = 0,
    max_scan_bytes: Optional[int] = None,
    atom_bindings=None,
    reactant_smiles: str | list[str] | None = None,
    product_smiles: str | list[str] | None = None,
) -> tuple[bool, list[str]]:
    """同一 TS 双向 IRC 的真实外帧经 Opt/Freq 到正确极小值即方向通过。

    材料：IRC 双侧端点与同一 TS 的单虚频日志；endpoint_a_logs /
    endpoint_b_logs 分别提供产物/反应物的 Opt/Freq 原生日志。首帧须匹配
    真实 IRC 外帧，收敛末帧须匹配零虚频几何，两侧可 direct/swapped 配对。

    返回 (passed, details)：passed=False 时 details 结构化写明缺哪份材料
    或证明为何不成立（缺 TS/端点材料 ⇒ 引导先补对应阶段的绑定证据）。
    """
    details: list[str] = []
    ends = irc_endpoint_geometries(irc_log, max_scan_bytes=max_scan_bytes)
    if ends is None:
        return False, [
            f"the IRC log {irc_log} does not yield usable endpoint geometries on "
            "both sides (Gaussian: outermost coordinated frames on the rx<0 and "
            "rx>0 sides; ORCA: endpoint files or outermost F/B trajectory frames — "
            "an unconverged direction's last frame is a legitimate partial "
            "endpoint); bind the parser output of a finished IRC job log"
        ]
    atom_binding = (atom_bindings or {}).get(str(irc_log))
    ts_geometries = [(geometry, (atom_bindings or {}).get(str(path)))
        for path in ts_logs
        for geometry in _usable_ts_geometries([path], max_scan_bytes=max_scan_bytes, details=details)]
    anchor = irc_start_geometry(irc_log)
    ts_geometries = [item for item in ts_geometries if same_geometry(item[0], anchor)]
    if not ts_geometries:
        details.append('IRC starting saddle is missing or differs from the submitted TS geometry; submit evidence from the same TS calculation geometry.')
    from_geometries = _usable_minimum_geometries(
        endpoint_b_logs, side="endpoint_b (SOURCE/reactant side)",
        max_scan_bytes=max_scan_bytes, details=details,
    )
    to_geometries = _usable_minimum_geometries(
        endpoint_a_logs, side="endpoint_a (TARGET/product side)",
        max_scan_bytes=max_scan_bytes, details=details,
    )
    if not ts_geometries:
        details.append(
            "missing TS material: bind the step's ts_opt/frequency stage evidence "
            "first (a normally terminated first-order saddle log with a final geometry)"
        )
    if not from_geometries:
        details.append(
            "missing endpoint_b material (SOURCE/reactant side): bind endpoint_b "
            "evidence or the source species' geometry stage — a frequency-verified "
            "minimum (zero imaginary frequencies) whose log carries a final geometry"
        )
    if not to_geometries:
        details.append(
            "missing endpoint_a material (TARGET/product side): bind endpoint_a "
            "evidence or the target species' geometry stage — a frequency-verified "
            "minimum (zero imaginary frequencies) whose log carries a final geometry"
        )
    if not (ts_geometries and from_geometries):
        return False, details
    separated = isinstance(product_smiles, list) and len(product_smiles) > 1
    if not separated:
        for ts_geometry, ts_binding in ts_geometries:
            passed, proof_details = _endpoint_optimization_proof(
                ends, ts_geometry, endpoint_b_logs, endpoint_a_logs, charge=charge,
                max_scan_bytes=max_scan_bytes, reactant_smiles=reactant_smiles, product_smiles=product_smiles,
                atom_binding=atom_binding if ts_binding == atom_binding else None,
            )
            if passed:
                return True, proof_details
            details.extend(proof_details)
    if separated:
        for ts_geometry, ts_binding in ts_geometries:
            verdict = verify_separated_product_direction(ends, ts_geometry, from_geometries,
                product_smiles, to_geometries, charge=charge,
                atom_binding=atom_binding if ts_binding == atom_binding else None)
            if verdict["is_match"]:
                return True, verdict["details"]
            details.extend(verdict["details"])
    return False, list(dict.fromkeys(details))
```

### `_usable_ts_geometries`

来源：[cloudra/tools/core/irc_evidence.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/irc_evidence.py:436)，行 436–448。

```python
def _usable_ts_geometries(ts_logs, *, max_scan_bytes, details: list[str]) -> list[tuple]:
    geometries = []
    for path in ts_logs:
        n_imag, geometry = probe_log(path, max_scan_bytes=max_scan_bytes)
        if n_imag == 1 and geometry is not None:
            geometries.append(geometry)
        else:
            details.append(
                f"TS candidate {path} is not usable: a first-order saddle log "
                f"(exactly one imaginary frequency) with a final geometry is "
                f"required; got n_imag={n_imag}, geometry={'yes' if geometry else 'no'}."
            )
    return geometries
```

### `_usable_minimum_geometries`

来源：[cloudra/tools/core/irc_evidence.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/irc_evidence.py:451)，行 451–463。

```python
def _usable_minimum_geometries(logs, *, side: str, max_scan_bytes, details: list[str]) -> list[tuple]:
    geometries = []
    for path in logs:
        n_imag, geometry = probe_log(path, max_scan_bytes=max_scan_bytes)
        if n_imag == 0 and geometry is not None:
            geometries.append(geometry)
        else:
            details.append(
                f"{side} candidate {path} is not usable: a verified minimum log "
                f"(zero imaginary frequencies) with a final geometry is required; "
                f"got n_imag={n_imag}, geometry={'yes' if geometry else 'no'}."
            )
    return geometries
```

### `_endpoint_optimization_proof`

来源：[cloudra/tools/core/irc_evidence.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/irc_evidence.py:520)，行 520–571。

```python
def _endpoint_optimization_proof(ends, ts_geometry, source_logs, target_logs, *,
        charge=0, max_scan_bytes=None, atom_binding=None, reactant_smiles=None, product_smiles=None):
    """Both real IRC sides must terminate in the declared verified minima via Opt."""
    from cloudra.tools.core.irc_path import align_atom_order

    details = []
    source = _optimized_minima(source_logs, smiles=reactant_smiles, side='SOURCE/reactant',
        charge=charge, max_scan_bytes=max_scan_bytes, details=details)
    target = _optimized_minima(target_logs, smiles=product_smiles, side='TARGET/product',
        charge=charge, max_scan_bytes=max_scan_bytes, details=details)
    for name, source_end, target_end in (('direct', ends[0], ends[1]), ('swapped', ends[1], ends[0])):
        for source_start, source_minimum, source_log in source:
            if not same_geometry(source_start, source_end):
                continue
            for target_start, target_minimum, target_log in target:
                if not same_geometry(target_start, target_end):
                    continue
                if atom_binding:
                    # Native Opt rows retain the correspondence of their actual IRC input.
                    # Reorder by the input match, never by similarity of the relaxed minimum.
                    mapping = atom_binding.get('atom_map', [])
                    count = len(ts_geometry[0])
                    if (len(mapping) != count or any(type(index) is not int for index in mapping)
                            or sorted(mapping) != list(range(1, count + 1))):
                        continue
                    source_order = align_atom_order(*source_end, *source_start)
                    target_order = align_atom_order(*target_end, *target_start)
                    if source_order is None or target_order is None:
                        continue
                    source_bound = (source_end[0], [source_minimum[1][index] for index in source_order[0]])
                    target_bound = (target_end[0], [target_minimum[1][index] for index in target_order[0]])
                    target_bound = ([target_bound[0][index - 1] for index in mapping],
                                    [target_bound[1][index - 1] for index in mapping])
                    if (not _ordered_graph_matches(source_bound, atom_binding['reactant_mol'], charge)
                            or not _ordered_graph_matches(target_bound, atom_binding['product_mol'], charge)):
                        details.append('Optimized IRC endpoints differ from the bound complete atom identities.')
                        continue
                result = [f'{name} pairing: both actual IRC outer frames were independently optimized '
                    f'to the correct zero-imaginary minima ({source_log}; {target_log}).']
                try:
                    interval = prove_irc_endpoint_direction(*ts_geometry, *ends, source_minimum, target_minimum,
                        [], charge, atom_orders=bound_atom_orders(ts_geometry, source_minimum, target_minimum, atom_binding))
                    result.extend('[advisory] ' + item for item in interval.get('details', []))
                    if not (interval['is_decidable'] and interval['is_match']):
                        result.append('[warning] Endpoint optimization establishes direction, but the geometric interval '
                            'check failed or is undecidable; inspect the trajectory for suspicious geometry.')
                except Exception as exc:
                    result.append(f'[warning] Endpoint optimization establishes direction, but the geometric interval '
                                  f'could not be evaluated ({exc}); inspect the trajectory.')
                return True, result
    return False, ['The actual IRC outer frames are not connected to both declared zero-imaginary minima '
                   'by converged optimization logs; geometric interval agreement alone is not direction proof.', *details]
```

### `_optimized_minima`

来源：[cloudra/tools/core/irc_evidence.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/irc_evidence.py:501)，行 501–517。

```python
def _optimized_minima(logs, *, smiles, side, charge, max_scan_bytes, details):
    minima = _usable_minimum_geometries(logs, side=side, max_scan_bytes=max_scan_bytes, details=details)
    if smiles is not None:
        from cloudra.tools.core.species_identity import chemical_smiles
        expected = chemical_smiles(smiles)
        minima = [geometry for geometry in minima if _geometry_matches_species(geometry, expected, charge=charge)]
        if not minima:
            details.append(f'{side}: no zero-imaginary minimum matches the declared species.')
    results = []
    for path in logs:
        geometries = _optimization_geometries(path, max_scan_bytes=max_scan_bytes)
        if geometries is not None and any(same_geometry(geometries[1], minimum) for minimum in minima):
            results.append((geometries[0], geometries[1], path))
    if not results:
        details.append(f'{side}: supply a normally converged Opt log starting from the actual IRC outer frame '
                       'and a zero-imaginary Freq log at that optimization final geometry; combined Opt/Freq is accepted.')
    return results
```

### `_geometry_matches_species`

来源：[cloudra/tools/core/irc_evidence.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/irc_evidence.py:338)，行 338–358。

```python
def _geometry_matches_species(geometry, smiles: str, *, charge: int) -> bool:
    """Match the full bond graph and stereochemistry of a real geometry."""
    from rdkit import Chem
    from rdkit.Chem import rdDetermineBonds

    from cloudra.tools.core.irc_path import xyz_block

    expected = Chem.MolFromSmiles(smiles)
    actual = Chem.MolFromXYZBlock(xyz_block(*geometry))
    if expected is None or actual is None or any(atom.GetIsotope() for atom in expected.GetAtoms()):
        return False
    if Chem.AddHs(expected).GetNumAtoms() != actual.GetNumAtoms():
        return False
    try:
        rdDetermineBonds.DetermineBonds(actual, charge=charge)
    except ValueError:
        return False
    for molecule in (expected, actual):
        for atom in molecule.GetAtoms():
            atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(Chem.RemoveHs(actual)) == Chem.MolToSmiles(Chem.RemoveHs(expected))
```

### `_optimization_geometries`

来源：[cloudra/tools/core/irc_evidence.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/irc_evidence.py:466)，行 466–498。

```python
def _optimization_geometries(path, *, max_scan_bytes=None):
    """Native converged Opt input/final geometries, independent of frequency parsing."""
    if not normal_log(path, max_scan_bytes=max_scan_bytes):
        return None
    text = Path(path).read_text(errors='replace')
    engine = qm_engine.detect_qm_engine(str(path))
    if engine == 'orca':
        if orca_frames.opt_converged(text) is not True:
            return None
        index = text.find('CARTESIAN COORDINATES (ANGSTROEM)')
        first = parse_xyz(orca_frames.input_xyz_from_text(text))
        if first is None and index >= 0:
            first = parse_xyz(orca_frames._xyz_block_at(text, index))
        last = parse_xyz(orca_frames.final_xyz_from_text(text))
    elif engine == 'gaussian':
        if ('Optimization stopped.' in text or not any(marker in text for marker in
                ('Optimization completed.', 'Stationary point found.'))):
            return None
        lines = text.splitlines()
        first_rows = next((gaussian_frames._parse_coord_block_after(lines, index + 1, has_type_col=True)
            for index, line in enumerate(lines)
            if 'Input orientation:' in line or 'Standard orientation:' in line), None)
        blocks = gaussian_frames.std_orientation_frames(text)
        last_rows = blocks[-1] if blocks else gaussian_frames._parse_last_input_orientation(text)

        def geometry(rows):
            return parse_xyz(gaussian_frames._coords_to_xyz(
                [row[0] for row in rows], [row[1:] for row in rows])) if rows else None

        first, last = geometry(first_rows), geometry(last_rows)
    else:
        return None
    return (first, last) if first is not None and last is not None else None
```

### `probe_log`

来源：[cloudra/tools/core/irc_evidence.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/irc_evidence.py:228)，行 228–241。

```python
def probe_log(path, *, max_scan_bytes: Optional[int] = None) -> tuple[Optional[int], Optional[tuple]]:
    """(虚频数, 末帧几何)。虚频数 None = 无频率块/文件不可解析。

    只解析 gaussian/orca 日志（内容嗅探，不超过 max_scan_bytes——None 表示
    不设上限，与 ts_guess strict 同；benchmark 侧传 MAX_SCAN_BYTES）。"""
    p = Path(path)
    if not _within_scan_limit(p, max_scan_bytes):
        return None, None
    if not normal_log(p, max_scan_bytes=max_scan_bytes):
        return None, None
    frames, _irc_meta = frames_for(p)
    freqs = freqs_for(p, frames)
    n_imag = len(imag_freqs(freqs)) if freqs else None
    return n_imag, last_geometry(p, frames)
```

### `normal_log`

来源：[cloudra/tools/core/irc_evidence.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/irc_evidence.py:193)，行 193–205。

```python
def normal_log(path, *, max_scan_bytes=None) -> bool:
    """Native normally terminated QM evidence within the caller's read limit."""
    path = Path(path)
    if not path.is_file() or not _within_scan_limit(path, max_scan_bytes):
        return False
    engine = qm_engine.detect_qm_engine(str(path))
    parser = {'orca': orca_frames, 'gaussian': gaussian_frames}.get(engine)
    text = path.read_text(errors='replace')
    if parser is None or not parser.normal_termination(text):
        return False
    if engine == 'orca' and 'ORCA finished by error termination' in text:
        return False
    return frequency_geometry_matches(path)
```

### `frequency_geometry_matches`

来源：[cloudra/tools/core/irc_evidence.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/irc_evidence.py:208)，行 208–225。

```python
def frequency_geometry_matches(path) -> bool:
    """The last spectrum must belong to the final geometry in the native log."""
    engine = qm_engine.detect_qm_engine(str(path))
    text = Path(path).read_text(errors='replace')
    frequency_marker = 'VIBRATIONAL FREQUENCIES' if engine == 'orca' else 'Frequencies --'
    frequency_index = text.rfind(frequency_marker)
    if frequency_index < 0:
        return True  # No frequency claim; probe_log still returns n_imag=None.

    def geometry(region):
        if engine == 'orca':
            return parse_xyz(orca_frames.final_xyz_from_text(region))
        blocks = gaussian_frames.std_orientation_frames(region)
        coords = blocks[-1] if blocks else gaussian_frames._parse_last_input_orientation(region)
        return parse_xyz(gaussian_frames._coords_to_xyz(
            [row[0] for row in coords], [row[1:] for row in coords])) if coords else None

    return same_geometry(geometry(text), geometry(text[:frequency_index]))
```

### `frames_for`

来源：[cloudra/tools/core/irc_evidence.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/irc_evidence.py:50)，行 50–71。

```python
def frames_for(path):
    """Return (frames, irc_meta). 两种解析各自隔离：opt+freq 日志没有 IRC 段
    是正常情况，不能让 extract_irc 的异常把已解析的 frames 一并丢弃。

    IRC meta 已归一化为 dict：gaussian_frames.extract_irc 返回
    (frames, meta) 二元组，orca_frames.extract_irc 直接返回 meta dict。
    """
    engine = qm_engine.detect_qm_engine(str(path))
    mod = orca_frames if engine == "orca" else gaussian_frames
    try:
        frames = mod.extract_frames(str(path))
    except Exception:
        frames = []
    try:
        raw_irc = mod.extract_irc(str(path))
    except Exception:
        raw_irc = None
    if isinstance(raw_irc, tuple):
        irc_meta = raw_irc[1] if len(raw_irc) == 2 else None
    else:
        irc_meta = raw_irc
    return frames, irc_meta
```

### `freqs_for`

来源：[cloudra/tools/core/irc_evidence.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/irc_evidence.py:81)，行 81–94。

```python
def freqs_for(path, frames) -> list[float]:
    """末帧频率；cclib 对 ORCA 6.1 日志裸抛 IndexError（帧为空）时回退
    文本权威 VIBRATIONAL FREQUENCIES 块（统一入口在 orca_frames）。"""
    freqs = _last_freqs(frames)
    if freqs:
        return freqs
    engine = qm_engine.detect_qm_engine(str(path))
    if engine == "orca":
        return orca_frames.frequencies_with_text_fallback(str(path))
    if engine == 'gaussian':
        text = Path(path).read_text(errors='replace').rsplit('Harmonic frequencies', 1)[-1]
        return [float(value) for line in text.splitlines() if 'Frequencies --' in line
                for value in line.partition('Frequencies --')[2].split()]
    return []
```

### `last_geometry`

来源：[cloudra/tools/core/irc_evidence.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/irc_evidence.py:101)，行 101–120。

```python
def last_geometry(path, frames) -> Optional[tuple]:
    """末帧几何 (symbols, positions)；无坐标帧返回 None。

    cclib 对 ORCA 6.1 日志整体崩溃时帧为空——走文本权威
    CARTESIAN COORDINATES 块回退（同频率的文本回退纪律）。
    """
    geometry = None
    for fr in reversed(frames):
        if getattr(fr, "xyz", "").strip():
            geometry = parse_xyz(fr.xyz)
            break
    if geometry is None and qm_engine.detect_qm_engine(str(path)) == "orca":
        geometry = parse_xyz(orca_frames.final_xyz_with_text_fallback(str(path)))
    if geometry is None and qm_engine.detect_qm_engine(str(path)) == 'gaussian':
        text = Path(path).read_text(errors='replace')
        blocks = gaussian_frames.std_orientation_frames(text)
        rows = blocks[-1] if blocks else gaussian_frames._parse_last_input_orientation(text)
        if rows:
            geometry = parse_xyz(gaussian_frames._coords_to_xyz([row[0] for row in rows], [row[1:] for row in rows]))
    return geometry
```

### `irc_start_geometry`

来源：[cloudra/tools/core/irc_evidence.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/irc_evidence.py:27)，行 27–47。

```python
def irc_start_geometry(path):
    """Native IRC starting saddle, never a predictor or a terminal path frame."""
    engine = qm_engine.detect_qm_engine(str(path))
    try:
        if engine == 'gaussian':
            frames, _ = gaussian_frames.extract_irc(str(path))
            return next((parse_xyz(frame.xyz) for frame in frames
                         if frame.reaction_coordinate == 0.0 and frame.xyz.strip()),
                        parse_xyz(gaussian_frames.irc_start_xyz(Path(path).read_text(errors='replace'))))
        if engine == 'orca':
            text = Path(path).read_text(errors='replace')
            orca_frames.extract_irc_from_text(text)
            start = text.find('Intrinsic Reaction Coordinate Calculation')
            if start < 0:
                return None
            index = text.rfind('CARTESIAN COORDINATES (ANGSTROEM)', 0, start)
            xyz = orca_frames._xyz_block_at(text, index) if index >= 0 else orca_frames.input_xyz_from_text(text[:start])
            return parse_xyz(xyz)
    except (ValueError, OSError):
        return None
    return None
```

### `same_geometry`

来源：[cloudra/tools/core/irc_path.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/irc_path.py:37)，行 37–110。

```python
def same_geometry(reference, mobile) -> bool:
    """Same coordinates up to atom order and proper rigid rotation.

    Reuse the existing six-decimal XYZ rounding bound; this is identity of a
    calculation geometry, not a conformer or chemical similarity criterion.
    """
    import numpy as np

    if reference is None or mobile is None:
        return False
    ref_symbols, mob_symbols = reference[0], mobile[0]
    if len(ref_symbols) == 0 or sorted(ref_symbols) != sorted(mob_symbols):
        return False
    ref = np.asarray(reference[1], dtype=float)
    mob = np.asarray(mobile[1], dtype=float)
    ref = ref - ref.mean(axis=0)
    mob = mob - mob.mean(axis=0)
    tolerance = np.sqrt(3) * 10 ** -6

    def proper_rotation(left, right):
        u, _, vt = np.linalg.svd(left.T @ right)
        if np.linalg.det(u @ vt) < 0:
            u[:, -1] *= -1
        return u @ vt

    def matches(perm):
        ordered = mob[perm]
        residual = np.linalg.norm(ordered @ proper_rotation(ordered, ref) - ref, axis=1)
        return bool(np.max(residual) <= tolerance)

    alignment = align_atom_order(*reference, *mobile)
    if alignment is not None and matches(alignment[0]):
        return True

    # Distance-fingerprint ties can choose an improper symmetry, or mix several
    # symmetries. Keep the lineage-aware interval alignment above unchanged, but
    # search alternative strict-identity correspondences here. Two independent
    # centered vectors determine a proper rotation: at most n * (n - 1) anchor
    # pairs, rather than factorial permutations of equivalent atoms.
    d_ref, d_mob = dist_matrix(ref), dist_matrix(mob)
    fp_ref, fp_mob = np.sort(d_ref, axis=1), np.sort(d_mob, axis=1)
    compatible = np.array(mob_symbols)[:, None] == np.array(ref_symbols)[None, :]
    for i in range(len(ref_symbols)):
        # If each atom moves by at most tolerance, a pair distance changes by
        # at most twice that bound. This only prunes correspondence candidates;
        # the original proper-rotation residual remains the acceptance test.
        compatible[:, i] &= np.max(np.abs(fp_mob - fp_ref[i]), axis=1) <= 2 * tolerance
    if not np.all(np.any(compatible, axis=0)):
        return False

    first = int(np.argmax(np.linalg.norm(ref, axis=1)))
    cross = np.linalg.norm(np.cross(ref[first], ref), axis=1)
    second = int(np.argmax(cross))
    for mob_first in np.flatnonzero(compatible[:, first]):
        # Collinear geometries need only one axis; rotation about it is free.
        seconds = np.flatnonzero(compatible[:, second]) if cross[second] > 0 else [None]
        for mob_second in seconds:
            ref_anchors, mob_anchors = [first], [mob_first]
            if mob_second is not None:
                if mob_first == mob_second or abs(
                    d_ref[first, second] - d_mob[mob_first, mob_second]
                ) > 2 * tolerance:
                    continue
                ref_anchors.append(second)
                mob_anchors.append(mob_second)
            rotated = mob @ proper_rotation(mob[mob_anchors], ref[ref_anchors])
            cost = np.linalg.norm(rotated[:, None, :] - ref[None, :, :], axis=2)
            cost[~compatible] = 1e9
            perm = np.argmin(cost, axis=0).tolist()
            if len(set(perm)) != len(perm):
                perm = _hungarian(cost)
            if perm is not None and matches(perm):
                return True
    return False
```

### `final_xyz_from_text`

来源：[cloudra/tools/core/orca_frames.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/orca_frames.py:393)，行 393–407。

```python
def final_xyz_from_text(text: str) -> str:
    """最后一个 CARTESIAN COORDINATES (ANGSTROEM) 块 → 标准 xyz 文本。

    ORCA 每次几何步/作业结束都打印该块，取最后一个即末帧几何；cclib 对
    ORCA 6.1 日志整体解析失败时的文本回退（与 vibfreqs_from_text 同一
    纪律——评分链路不能因 cclib 崩溃而不可判定）。静态计算无该块时
    读取日志原样回显的输入坐标；优化和路径计算不能用输入冒充末帧。"""
    idx = text.rfind("CARTESIAN COORDINATES (ANGSTROEM)")
    if idx >= 0:
        return _xyz_block_at(text, idx)
    # Static jobs evaluate precisely their echoed input geometry. An Opt/IRC/scan
    # input is only its starting point and must never masquerade as a final frame.
    if not detect_job_types_from_text(text) & {'opt', 'ts', 'scan', 'irc', 'neb'}:
        return input_xyz_from_text(text)
    return ''
```

### `input_xyz_from_text`

来源：[cloudra/tools/core/orca_frames.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/orca_frames.py:367)，行 367–390。

```python
def input_xyz_from_text(text: str) -> str:
    """Read the literal inline Cartesian geometry echoed by ORCA, never infer it."""
    rows = []
    in_xyz = False
    for line in text.splitlines():
        prefix, separator, echoed = line.partition('>')
        if not (separator and prefix.strip().startswith('|')
                and prefix.strip()[1:].strip().isdigit()):
            continue
        parts = echoed.split()
        if not in_xyz:
            if len(parts) == 4 and parts[:2] == ['*', 'xyz']:
                in_xyz = True
            continue
        if parts == ['*']:
            return f'{len(rows)}\n\n' + '\n'.join(rows) + '\n' if rows else ''
        if len(parts) != 4:
            return ''
        try:
            coordinates = [float(value) for value in parts[1:]]
        except ValueError:
            return ''
        rows.append(parts[0] + ' ' + ' '.join(str(value) for value in coordinates))
    return ''
```

## TS 恢复操作的耦合：已确认行为，尚不把自动推进本身算作缺陷

IB9 恢复记录没有完成一次新版拆分验收；既存 missing TS geometry 结果不能代表新方案科学失败。历史恢复中断也不能归因成当前代码“不允许新会话接管”：当前同项目有写权限的调用可自动转移属主。

实际需要注意的是：`ts_resume` 明确是写操作，修订提交后立即调用自动驱动。反应输入改变会使依赖证据失效；已有失败步骤也会使对应依赖失效，因此以“只导入证据并重验”的意图调用 resume，可能进入重算。这个行为有公开说明，不能单凭会推进就判成隐蔽 bug；但它确实不能承担无计算副作用的独立重验。

最小方向是复用已有只读检查和验收逻辑处理证据复核，确需计算时才恢复自动推进。不能为了通过验收删掉几何来源校验，也不需要另造版本号、控制开关和并发握手。本次未实际调用 resume、未新增作业。以下保留公开 schema、属主接管、修订失效与驱动调用的实际源码。

### `TsResume_input_schema`

来源：[cloudra/tools/Chemtool/ts_search_process.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/ts_search_process.py:25)，行 25–29。

```python
class TsResume_input_schema(input_schema):
    model_config = ConfigDict(extra='forbid')
    run_id: str = Field(min_length=1)
    changes: TsInputChanges = Field(default_factory=TsInputChanges, description='Within the same calculation, omitted fields retain existing keywords, frequency_mode, orca_blocks and end_setting; explicit empty values clear them. Changing engine, method or basis_set requires {replace: complete_configuration}; changing a named reference uses {replace: {ref: name}}. calculations profile-map omissions remain unchanged, and null removes an unused profile. A scan-coordinate-only patch need not copy calculation. Use the current atom identities/order reported in structures with each field\'s documented index base: structure/reaction references are 1-based; ORCA scan/freeze references are 0-based; Gaussian/xTB scan references are 1-based. A source patch retains omitted fields and null clears them. Explicit file paths import the current file bytes once, including an unchanged path. Proven incoming atom reorderings convert new atom declarations once within owned molecular state; source files remain unchanged.')
    reason: str = Field(min_length=1)
```

### `TsResume.tool_call`

来源：[cloudra/tools/Chemtool/ts_search_process.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/ts_search_process.py:185)，行 185–186。

```python
    async def tool_call(self, user_input: TsResume_input_schema, session: Session):
        return await revise_run(self, user_input.run_id, user_input.changes, user_input.reason, session)
```

### `revise_run`

来源：[cloudra/tools/Chemtool/ts_search_process.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/ts_search_process.py:105)，行 105–145。

```python
async def revise_run(tool, run_id, changes, reason, session, *, expected_revision=None) -> TsProcess_output_schema:
    """Shared run mutation: one scope, revision transaction and queue driver."""
    import asyncio

    from cloudra.services.ts_pipeline_context import pipeline_database
    from cloudra.services.ts_pipeline_store import get_revision_receipt
    try:
        from cloudra.tools.core.permission_model import Permission
        if not tool.subagent.permission_all() & Permission.WRITE:
            raise ValueError('TS mutation requires producer write permission')
        workspace = _resolve_workspace(tool)
        record = await asyncio.to_thread(_read_resume_record, pipeline_database(), workspace, run_id, tool.subagent.conversation_id)
        if tool.subagent.conversation_id != record.owner_conversation_id:
            raise ValueError(f'TS process belongs to a different project ({record.owner_conversation_id})')
        if session and session.id and session.id != record.owner_session_id:
            from cloudra.services.ts_pipeline_store import transfer_process_ownership
            if record.pipeline_id:
                await asyncio.to_thread(
                    transfer_process_ownership,
                    pipeline_database(),
                    process_id=record.pipeline_id,
                    project_id=tool.subagent.conversation_id,
                    new_owner_session_id=session.id,
                )
            record.owner_session_id = session.id
        request_key = _request_key(tool.tool_name)
        accepted = await asyncio.to_thread(get_revision_receipt, pipeline_database(),
            process_id=record.pipeline_id, request_key=request_key)
        if accepted is None and expected_revision is not None and record.revision != expected_revision:
            raise ValueError('stale process revision; inspect the current structure and retry')
        request = TsResumeRequest.model_validate({'changes': changes, 'reason': reason,
            'request_key': request_key,
            'expected_revision': accepted.previous_revision if accepted else record.revision})
        prior_input = await asyncio.to_thread(_revision_request_input, pipeline_database(), record, accepted)
        request.changes = normalize_ts_input_atoms(request.changes, atom_tables={}, current_input=prior_input)
        record = await asyncio.to_thread(resume, record, request)
        out = await asyncio.to_thread(_to_output, record)
        out.receipt = await asyncio.to_thread(get_revision_receipt, pipeline_database(), process_id=record.pipeline_id, request_key=request.request_key)
        return out
    except (ValueError, OSError) as exc:
        return TsProcess_output_schema(is_success=False, run_id=run_id, message=f'{tool.tool_name}: {exc}')
```

### `_read_resume_record`

来源：[cloudra/tools/Chemtool/ts_search_process.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/ts_search_process.py:80)，行 80–90。

```python
def _read_resume_record(db, workspace, run_id, project):
    from cloudra.services.ts_pipeline_store import read_process_snapshot
    state, jobs = read_process_snapshot(db, project_id=project, run_id=run_id, workspace_dir=workspace)
    if state.get('format_version') != 7:
        raise ValueError('Unsupported TS input format; existing compute jobs remain intact.')
    record = TsProcessRecord.model_validate(state)
    states = {job['job_id']: job['state'] for job in jobs}
    for step in [*record.job_steps, *([record.scan_step] if record.scan_step else [])]:
        if step.job_id in states:
            step.state = states[step.job_id]
    return record
```

### `_revision_request_input`

来源：[cloudra/tools/Chemtool/ts_search_process.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/ts_search_process.py:93)，行 93–102。

```python
def _revision_request_input(db, record, accepted):
    """Replay native index conversion against the originally accepted declaration."""
    if accepted is None:
        return record.input
    with db.connect() as con:
        row = con.execute('SELECT payload FROM ts_pipeline_declarations WHERE process_id=? AND declaration_revision=?',
                          (record.pipeline_id, accepted.previous_input_revision)).fetchone()
    if row is None:
        raise ValueError('accepted revision has no immutable input declaration')
    return TsInput.model_validate_json(row[0])
```

### `_to_output`

来源：[cloudra/tools/Chemtool/ts_search_process.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/ts_search_process.py:70)，行 70–77。

```python
def _to_output(record, *, can_write=True):
    from cloudra.services.ts_pipeline_context import pipeline_database
    if record.pipeline_id:
        view = inspect_process(pipeline_database(), project_id=record.owner_conversation_id,
                               run_id=record.run_id, workspace_dir=record.workspace_dir, can_write=can_write)
    else:
        view = build_process_view(record.model_dump(mode='json'), [], can_write=can_write)
    return TsProcess_output_schema(**view.model_dump())
```

### `resume`

来源：[cloudra/tools/core/ts_process.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/ts_process.py:3626)，行 3626–3630。

```python
def resume(record: TsProcessRecord, request: TsResumeRequest,
           event_sink: Optional[Callable[[str, dict], None]] = None) -> TsProcessRecord:
    """Accept a durable input revision before automatically continuing."""
    from cloudra.tools.core.ts_revision import resume_revised_process
    return resume_revised_process(record, request, event_sink=event_sink)
```

### `plan_input_revision`

来源：[cloudra/tools/core/ts_revision.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/ts_revision.py:288)，行 288–345。

```python
def plan_input_revision(record, request: TsResumeRequest) -> TsRevisionReceipt:
    """Return affected job references; do not mutate record, files or ledger."""
    steps = list(record.job_steps) + ([record.scan_step] if record.scan_step else [])
    if any(step.state in ('running', 'cancel_requested') for step in steps):
        raise ValueError('active compute jobs prevent input revisions; use ts_inspect')
    updated = apply_input_changes(record.input, request.changes)
    differences = _input_revision_differences(record, updated, request.changes)
    failed = _failed_step(record)
    if not differences and failed is None and record.stop_reason is None:
        raise ValueError('no input change or failed attempt to retry; use ts_inspect')
    before_limits, after_limits = record.input.execution.limits, updated.execution.limits
    if before_limits:
        if after_limits is None or before_limits.source != after_limits.source:
            raise ValueError('authorized limits cannot be removed or change source')
        for field in ('max_compute_actions', 'max_model_calls'):
            before, after = getattr(before_limits, field), getattr(after_limits, field)
            if before is not None and (after is None or after > before):
                raise ValueError('input revision cannot raise authorized limits')
    invalidated = set()
    for purpose in _changed_calculations(record, updated):
        invalidated.update(_calculation_dependents(purpose))
    for path in differences:
        if _calculation_change_path(path):
            continue
        if path.startswith(('reaction.reactant_smiles', 'reaction.product_smiles', 'reaction.charge', 'reaction.multiplicity', 'reaction.electronic_character', 'reaction.reaction_center', 'conformers.')):
            invalidated.update(_DEPENDENTS['build'])
        elif path.startswith(('reaction.selected_candidate', 'guess')):
            invalidated.update(_DEPENDENTS['guess'])
        elif path.startswith('ts_optimization'):
            invalidated.update(_DEPENDENTS['ts_opt'])
        elif path.startswith('verification.'):
            field = path.split('.')[1]
            if field.endswith('_endpoint'):
                side = field.removesuffix('_endpoint')
                task = path.split('.')[2]
                if task == 'component_logs':
                    continue
                purpose = side + ('_frequency' if task == 'frequency' else '_opt')
            else:
                purpose = 'irc' if field == 'irc_log' else field
            invalidated.update(_DEPENDENTS[purpose])
    separated_products = bool(updated.verification.product_endpoint.component_logs) or (
        isinstance(updated.reaction.product_smiles, list) and len(updated.reaction.product_smiles) > 1)
    if failed is not None and not (separated_products and failed.purpose in ('product_opt', 'product_frequency')):
        invalidated.update(_DEPENDENTS.get(failed.purpose, {failed.purpose}))
    retained, invalid = [], []
    for step in steps:
        if step.job_id is None and not step.external_source:
            continue
        ref = TsEvidenceReference(declaration_revision=step.source_input_revision,
                                  stage_key=step.stage_key or step.purpose, attempt=1, job_id=step.job_id)
        (invalid if step.purpose in invalidated else retained).append(ref)
    released = [key for purpose, key in record.budget_action_keys.items() if purpose in invalidated or (purpose.startswith('candidate_constraints:') and 'candidate_evaluation' in invalidated)]
    return TsRevisionReceipt(request_key=request.request_key, request_digest=revision_request_digest(request), reason=request.reason,
        previous_revision=request.expected_revision, revision=request.expected_revision + 1,
        previous_input_revision=record.declaration_revision, input_revision=record.declaration_revision + 1,
        changes=differences, retained=retained, invalidated=invalid,
        released_action_keys=released)
```

### `revise_record`

来源：[cloudra/tools/core/ts_revision.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/ts_revision.py:348)，行 348–441。

```python
def revise_record(record, request, receipt):
    """Import explicitly changed sources once; never rewrite caller files."""
    from cloudra.tools.core.ts_process import STAGE_ORDER, TsAttemptHistory
    revised = record.model_copy(deep=True)
    revised.attempt_history.append(TsAttemptHistory(declaration_revision=record.declaration_revision,
        selected_candidate_id=record.selected_candidate_id, job_steps=[*record.job_steps, *([record.scan_step] if record.scan_step else [])], stage_records=record.stage_records,
        input=record.input, terminal=record.terminal, blocked=record.blocked, failed_attempt=record.failed_attempt,
        stop_reason=record.stop_reason, structures=record.structures.model_copy(deep=True),
        provided_guess_binding=record.provided_guess_binding,
        reason=request.reason))
    revised.input = apply_input_changes(record.input, request.changes)
    revised.declaration_revision = receipt.input_revision
    revised.revision = receipt.revision
    _revise_structures(record, revised, request.changes)
    if (_provided_guess_redeclared(request.changes)
            or revised.input.guess is None or revised.input.guess.kind != 'provided'):
        revised.provided_guess_binding = None
    invalid_refs = {(ref.stage_key, ref.job_id) for ref in receipt.invalidated}
    invalid = {step.purpose for step in [*record.job_steps, *([record.scan_step] if record.scan_step else [])]
        if (step.stage_key or step.purpose, step.job_id) in invalid_refs}
    restart = []
    changed_calculations = _changed_calculations(record, revised.input)
    for purpose in changed_calculations:
        restart.append('build' if purpose in ('candidate_opt', 'candidate_evaluation', 'product_seed_opt')
                       else 'guess' if purpose in ('scan', 'path') else 'submit' if purpose == 'ts_opt' else 'refine')
    for path in receipt.changes:
        if _calculation_change_path(path):
            continue
        if path.startswith(('reaction.reactant_smiles', 'reaction.product_smiles', 'reaction.charge', 'reaction.multiplicity', 'reaction.electronic_character')):
            restart.append('declare')
        elif path.startswith('conformers.'):
            restart.append('build')
        elif path.startswith('reaction.selected_candidate'):
            restart.append('map')
        elif path.startswith('reaction.reaction_center'):
            restart.append('build')
        elif path.startswith('guess'):
            restart.append('guess')
        elif path.startswith('ts_optimization'):
            restart.append('submit')
        elif path.startswith('verification.'):
            restart.append('refine')
    failed = _failed_step(record)
    if failed is not None:
        if failed.purpose in ('scan', 'path'):
            restart.append('guess')
        elif failed.purpose in ('candidate_opt', 'candidate_evaluation', 'product_seed_opt'):
            restart.append('build')
        elif failed.purpose == 'ts_opt':
            restart.append('submit')
        else:
            restart.append('refine')
    if not record.is_terminal:
        restart.append(record.stage)
    revised.stage = min(restart, key=STAGE_ORDER.index) if restart else record.stage
    revised.job_steps = [step for step in revised.job_steps if step.purpose not in invalid]
    if revised.scan_step and revised.scan_step.purpose in invalid:
        revised.scan_step = None
    revised.stage_records = [row for row in revised.stage_records if STAGE_ORDER.index(row.stage) < STAGE_ORDER.index(revised.stage)]
    for purpose in invalid:
        revised.budget_action_keys.pop(purpose, None)
        revised.budget_reservations.pop(purpose, None)
    for stage_key, action_key in list(revised.budget_action_keys.items()):
        if action_key in receipt.released_action_keys:
            revised.budget_action_keys.pop(stage_key, None)
            revised.budget_reservations.pop(stage_key, None)
    if STAGE_ORDER.index(revised.stage) <= STAGE_ORDER.index('guess'):
        revised.structures.candidate = None
        revised.path_kind = 'not_attempted'
        revised.job_id, revised.job_input_path = None, ''
    elif 'ts_opt' in invalid or any(path.startswith('ts_optimization') for path in receipt.changes):
        revised.job_id, revised.job_input_path = None, ''
    if STAGE_ORDER.index(revised.stage) <= STAGE_ORDER.index('build'):
        revised.active_attempt_dir, revised.guidance_manifest_path = '', ''
        if (_source_redeclared(record, request.changes, 'reactant')
                or changed_calculations & {'candidate_opt', 'candidate_evaluation'}):
            revised.catalog_id = revised.partition_revision = revised.selected_candidate_id = None
            revised.cards_path = ''
        if _source_redeclared(record, request.changes, 'product') or 'product_seed_opt' in changed_calculations:
            revised.product_seed_candidate_id = None
        if (any(path.startswith(('reaction.', 'conformers.reactant', 'conformers.guidance')) for path in receipt.changes)
                or changed_calculations & {'candidate_opt', 'candidate_evaluation'}):
            revised.optimization_checkpoints = {}
    if failed is not None and failed.purpose == 'candidate_evaluation':
        revised.optimization_checkpoints = {}
    revised.evidence_candidates = [artifact for row in revised.stage_records for artifact in row.artifacts]
    revised.terminal, revised.blocked = None, None
    revised.stop_reason = None
    retained_steps = [*revised.job_steps, *([revised.scan_step] if revised.scan_step else [])]
    revised.waiting_for = record.waiting_for if any(
        record.waiting_for == f'job:{step.job_id}' for step in retained_steps) else ''
    revised.failed_attempt = None
    revised.intervention_count += 1
    return revised
```

### `resume_revised_process`

来源：[cloudra/tools/core/ts_revision.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/ts_revision.py:444)，行 444–485。

```python
def resume_revised_process(record, request, *, event_sink=None):
    """Use the tested existing ledger transaction, then the existing driver."""
    from cloudra.infra.flocks import locked
    from cloudra.services.ts_pipeline_context import pipeline_database, require_pipeline_producer, use_pipeline_database
    from cloudra.services.ts_pipeline_store import commit_input_revision, get_process, get_revision_receipt
    from cloudra.tools.core.ts_pipeline_driver import advance_process
    from cloudra.tools.core.ts_process import TsProcessRecord, _emit
    require_pipeline_producer(record.owner_conversation_id, record.owner_session_id)
    if not record.pipeline_id:
        raise ValueError('durable TS revisions require a ledger-bound run')
    db = pipeline_database()
    with locked(str(Path(record.run_dir) / '.pipeline.lock')), use_pipeline_database(db):
        accepted = get_revision_receipt(db, process_id=record.pipeline_id, request_key=request.request_key)
        if accepted:
            if accepted.request_digest != revision_request_digest(request):
                raise ValueError('revision request key conflict')
            return TsProcessRecord.model_validate(get_process(db, record.pipeline_id)['record'])
        state = get_process(db, record.pipeline_id)
        if state is None or state['record'] is None:
            raise ValueError('process checkpoint missing')
        if state['revision'] != request.expected_revision:
            raise ValueError('stale process revision; use ts_inspect')
        current = TsProcessRecord.model_validate(state['record'])
        if (current.owner_conversation_id, current.owner_session_id) != (record.owner_conversation_id, record.owner_session_id):
            raise ValueError('process owner mismatch')
        current.revision = state['revision']
        from cloudra.tools.core.ts_process import _step_state
        for step in [*current.job_steps, *([current.scan_step] if current.scan_step else [])]:
            step.state = _step_state(current, step)
        if current.waiting_for and all(s.state not in ('ready', 'running', 'cancel_requested') for s in [*current.job_steps, *([current.scan_step] if current.scan_step else [])]):
            current.waiting_for = ''
        if (current.stop_reason is None and _failed_step(current) is None and request.changes.model_fields_set and apply_input_changes(current.input,request.changes) == current.input
                and not _provided_guess_redeclared(request.changes)
                and not any(_source_redeclared(current, request.changes, role) for role in ('reactant', 'product'))):
            return current
        commit_input_revision(db, process_id=record.pipeline_id, request=request)
    # Accepted checkpoint is durable before the driver can submit anything.
    state = advance_process(db, record.pipeline_id)
    current = TsProcessRecord.model_validate(state['record'])
    if event_sink:
        _emit(event_sink, current)
    return current
```

### `advance_process`

来源：[cloudra/tools/core/ts_pipeline_driver.py](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/ts_pipeline_driver.py:17)，行 17–92。

```python
def advance_process(db: ComputeDB, process_id: str) -> dict:
    from cloudra.tools.core.ts_process import TsProcessRecord, advance, save_record
    state = get_process(db, process_id)
    if state is None or state['record'] is None:
        raise ValueError('process checkpoint missing')
    if state['record'].get('format_version') != 7:
        return dict(state, status='isolated', isolation_reason='Unsupported TS input format; existing jobs remain intact')
    directory = state['record']['run_dir']
    os.makedirs(directory, exist_ok=True)
    with locked(os.path.join(directory, '.pipeline.lock')), use_pipeline_database(db):
        state = get_process(db, process_id)
        record = TsProcessRecord.model_validate(state['record'])
        from cloudra.services.exploration_budget_store import settle_process_jobs
        settle_process_jobs(db, process_id)
        if record.is_terminal or (record.blocked and not record.stop_reason):
            return state
        if record.stop_reason and not record.waiting_for:
            return state
        if record.waiting_for:
            from cloudra.services.compute_store import TERMINAL_STATES
            token = record.waiting_for.partition(':')
            if token[0] != 'job' or not token[2].isdigit():
                raise ValueError('invalid waiting job reference')
            with db.connect() as con:
                job = con.execute('SELECT state FROM compute_jobs WHERE id=?', (int(token[2]),)).fetchone()
            if job is None:
                raise ValueError('bound waiting job missing')
            if job[0] not in TERMINAL_STATES:
                return state
            from pathlib import Path

            from cloudra.services.ts_pipeline_store import commit_stage_result, verify_stage_input
            try:
                digest=verify_stage_input(db,int(token[2]))
            except (OSError,ValueError) as exc:
                from cloudra.tools.core.ts_process import _block
                record=_block(record,record.stage,'stage_input_changed',str(exc),needs=['compute_artifacts'])
                save_record(record)
                return get_process(db,process_id)
            with db.connect() as con:
                binding=con.execute('SELECT declaration_revision,stage_key,attempt,evidence FROM ts_pipeline_stages WHERE job_id=?',(int(token[2]),)).fetchone()
                path, engine=con.execute('SELECT path,jobtype FROM compute_jobs WHERE id=?',(int(token[2]),)).fetchone()
            if binding and binding[3] is None:
                artifacts=[path]
                helper_result=str(Path(path).with_suffix('.chem-result.json'))
                if Path(helper_result).is_file():
                    artifacts.append(helper_result)
                state=get_process(db,process_id)
                import hashlib
                from copy import deepcopy

                from cloudra.infra.compute_utils import resolve_log_path
                log_path = Path(resolve_log_path(path, engine, int(token[2])))
                log_digest = hashlib.sha256(log_path.read_bytes()).hexdigest() if log_path.is_file() else None
                frozen_binding = None
                if binding[1] in {'ts_opt', 'frequency', 'irc'} and log_path.is_file():
                    bound_step = next((step for step in record.job_steps if step.job_id == int(token[2])), None)
                    frozen_binding = deepcopy(bound_step.atom_binding) if bound_step else None
                    if frozen_binding:
                        frozen_binding['declaration_revision'] = binding[0]
                        # 频率提交时日志尚不存在；完成后只补日志指纹，不重建已冻结的分子/映射。
                        if binding[1] == 'frequency':
                            frozen_binding['ts_log_sha256'] = log_digest
                committed=commit_stage_result(db,process_id=process_id,expected_revision=state['revision'],
                    stage_key=binding[1],attempt=binding[2],declaration_revision=binding[0],evidence=dict(status=job[0],
                        artifacts=artifacts,input_hash=digest or '',detail='Authoritative execution state: '+job[0]+'. Scientific qualification is a separate stage.',
                        atom_binding=frozen_binding, log_sha256=log_digest if frozen_binding else None))
                if not committed:
                    raise ValueError('stage result checkpoint changed concurrently')
            for step in [*record.job_steps, *([record.scan_step] if record.scan_step else [])]:
                if step.job_id == int(token[2]):
                    step.state = job[0]
            record.waiting_for = ''
        record = advance(record)
        save_record(record)
        return get_process(db, process_id)
```

## 计算执行、结构与构象工具：详细证据

### Cloudra 计算执行与构象工具：系统设计只读审计

检查范围：`scheduler/`、`runtime/monitor.py`、`runtime/remote_compute.py`、`runtime/compute_executor.py`、计算提交与存储、结构构建与构象工具、SSH 传输及锁。

证据性质：以下均是当前工作区源码的静态诊断；没有运行 pytest、没有运行量子化学/CREST/xTB、没有发送取消请求、没有重启服务、没有查询或改变真实作业状态。仅创建本审计文档；没有改动仓库源码。所有“会发生”的结果是沿实际代码推导，不冒充现场执行复现。

本文使用当前源码快照直接摘录。代码段按所讨论请求实际调用顺序排列；每段标注绝对路径与行范围。科学有效性、原生软件正常退出、调度任务完成是不同结论：本文不会把计算账本的 done 说成科学验收通过。

源码摘录时间（UTC）：2026-10-17T23:47:21.093698+00:00

#### 1. SSH 远端科学计算：发出取消就认定已经退出

**具体触发。** 用户取消一条正在跑的 SSH Slurm 作业，或 SSH 直跑 Gaussian/ORCA/xTB 等非 shell 作业。即便网络断开、scancel 命令返回非零，或者 TERM 尚未使真实计算退出，远端执行器也立即确认 cancelled。

**后果。** 界面和中央账本宣称取消完成；调度资源随之释放，而远端实际进程可能仍在运行。SSH 直跑分支还按持久化 PID 发 TERM，PID 本身不构成对当前进程的所有权证明。

**设计根因。** 同一系统有两套取消含义：shell 和本地 Slurm 等真实退出证据；SSH 远端科学计算仍把发送意图当作完成证据。这个分叉来自按 job_type 修补生命周期，计算执行者没有统一承担“我启动的进程已经退出”的确认责任。

**最简单修复。** 删除非 shell 的立即确认分支。SSH Slurm 复用已有的“scancel 请求后继续查终态”行为；SSH 直跑由活 runner 消费请求并在自己拥有的计算退出后写回执。只修改生命周期，不改变化学判据，不新增用户或模型要维护的并发字段。

##### 调用与返回链

**入口：取消 API 转发到中央计算库**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/api_v2/routers/compute.py:69-73`

```python
    @router.post("/api/v2/compute/cancel-all", dependencies=ctx.protected)
    async def cancel_all_compute_jobs() -> dict[str, int]:
        return await acancel_all_compute_jobs(ComputeDB())

    return router
```

**控制面：running 仅改为 cancel_requested，返回请求计数**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/compute_store.py:797-824`

```python
async def acancel_all_compute_jobs(db: ComputeDB) -> dict[str, int]:
    """取消排队作业，并向所有运行中作业发出账本取消请求。

    running → cancel_requested 保留容量占用；只有执行端确认计算退出才能
    落 cancelled。控制面不发信号。中央库不存在时返回全零且不建库。
    """
    counts = {"ready_cancelled": 0, "cancel_requested": 0}
    if not await asyncio.to_thread(_db_ready, db):
        return counts
    now = time.time()

    async def write() -> dict[str, int]:
        async with db.aconnect() as con:
            cur = await con.execute(
                "UPDATE compute_jobs SET state='cancelled', end_timestamp=?, "
                "last_error='cancelled by cancel-all' WHERE state='ready'",
                (now,),
            )
            counts["ready_cancelled"] = cur.rowcount
            cur = await con.execute(
                "UPDATE compute_jobs SET state='cancel_requested' "
                "WHERE state='running'"
            )
            counts["cancel_requested"] = cur.rowcount
            await con.commit()
            return counts

    return await aretry_on_locked(write)
```

**执行器转发：远端工作由 run_remote_compute 负责，返回后读账本送审**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime/compute_executor.py:126-158`

```python
    if kind == "slurm" or kind in REMOTE_KINDS:
        # poller 型作业（本机 Slurm / SSH 远端）：认领进程内轮询即看守，租约随 poll 续
        stop = asyncio.Event()
        renewer = None
        if worker_id:
            renewer = asyncio.create_task(
                _renew_lease(db, task_id, worker_id, stop),
                name=f"compute-lease-{task_id}",
            )
        try:
            if kind == "slurm":
                rc = await run_slurm_compute(task_id, db.path, scheduler=options)
            else:
                rc = await run_remote_compute(task_id, db.path)
            # 作业在 run_*_compute 内到达终态并落库；读回终态入
            # CallReview 收件箱（rev_compute_<id> 去重，非 dag 模式内部跳过）。
            try:
                settled = await aget_compute_job(db, task_id)
                if settled and settled["state"] in ("done", "failed"):
                    from cloudra.dag.controller import enqueue_compute_review

                    await enqueue_compute_review(task_id, settled["state"])
            except Exception:
                logger.exception("could not enqueue compute review for job %s", task_id)
            return rc
        except Exception as exc:
            await _mark_failed(db, task_id, f"{kind} compute failed: {exc}")
            return 1
        finally:
            stop.set()
            if renewer is not None:
                renewer.cancel()
                await asyncio.gather(renewer, return_exceptions=True)
```

**远端执行入口：读取 scheduler/job_type 并恢复句柄**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime/remote_compute.py:416-437`

```python
async def run_remote_compute(
    task_id: int,
    db_path: str,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    transport=None,
) -> int:
    """执行一条已认领的 ssh_local/ssh_slurm 作业；到达终态并落库后返回。"""
    db = ComputeDB.from_path(db_path)
    row = await aget_compute_job(db, task_id)
    if not row:
        raise SshError(f"compute job {task_id} 不存在")
    kind = (row["scheduler"] or "").strip()
    if kind not in REMOTE_KINDS:
        raise SshError(f"compute job {task_id} 不是远端作业: {kind!r}")
    options = _scheduler_options(row)
    endpoint = SshEndpoint.from_connection(options.get("connection") or {})
    transport = transport or SshTransport(endpoint)
    job_type = (row["jobtype"] or "").strip()
    input_file = Path(row["path"]).expanduser()
    remote_dir = endpoint.job_dir(task_id)
    handle = (row["scheduler_job_id"] or "").strip()
```

**错误分支：非 shell 取消操作返回后，立刻确认取消并返回 1**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime/remote_compute.py:458-484`

```python
    workdir = input_file.parent
    poll_seconds = min(max(float(options.get("poll_seconds", 15)), 1), 300)
    last_observed = ""
    empty_after_seen = 0
    pull_failures = 0
    shell_runner = kind == "ssh_local" and job_type == "shell"
    while True:
        current = await aget_compute_job(db, task_id)
        if current and current["state"] in {"cancelled", "cancel_requested"}:
            await asyncio.to_thread(
                _cancel_remote, transport, kind, remote_dir, task_id, handle, job_type
            )
            if not shell_runner or current["state"] == "cancelled":
                await acancel_compute_job(db, task_id)
                return 1
        try:
            if kind == "ssh_slurm":
                state, exit_code = await asyncio.to_thread(
                    _query_slurm_state, transport, handle
                )
            else:
                state, exit_code = await asyncio.to_thread(
                    _query_shell_state, transport, remote_dir, task_id, handle
                )
        except SshError:
            await sleep(poll_seconds)
            continue
```

**取消转换：Slurm 拼 scancel；SSH 直跑读取存储 PID；错误被吞掉**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime/remote_compute.py:242-268`

```python
def _cancel_remote(
    transport, kind: str, remote_dir: str, task_id: int, handle: str, job_type: str = ""
) -> None:
    """显式取消的远端执行侧；shell runner 自己确认整个作业组退出。

    ssh_slurm 走 scancel；ssh_local shell 写请求文件，其他引擎 TERM runner
    与 calculator（pid 文件由 runner 脚本落盘）。只在账本取消后被调用，
    与「任何路径不主动杀未要求取消的计算进程」铁律一致。
    """
    try:
        if kind == "ssh_slurm":
            transport.run(f"scancel {handle}", timeout=30)
        elif job_type == "shell":
            # The live runner kills its owned job group and records actual exit.
            # Repeating a request after an SSH interruption is harmless.
            cancel_file = shlex.quote(f"{remote_dir}/.cloudra-cancel-{task_id}")
            transport.checked(f"touch {cancel_file}", timeout=30)
        else:
            pid = handle[len(_SHELL_HANDLE_PREFIX):]
            pid_file = shlex.quote(f"{remote_dir}/.cloudra-pid-{task_id}")
            transport.run(
                f"kill -TERM $(cat {pid_file} 2>/dev/null) 2>/dev/null; "
                f"kill -TERM {pid} 2>/dev/null; true",
                timeout=30,
            )
    except SshError:
        logger.warning("remote cancel failed for job %s (%s)", task_id, handle, exc_info=True)
```

**传输转发：run 不使用 checked 的返回码检查**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime/remote_compute.py:79-86`

```python
    def __init__(self, endpoint: SshEndpoint) -> None:
        self.endpoint = endpoint

    def run(self, remote_cmd: str, *, timeout: float = 30) -> tuple[int, str, str]:
        return run_remote(self.endpoint, remote_cmd, timeout=timeout)

    def checked(self, remote_cmd: str, *, timeout: float = 30) -> str:
        return run_remote_checked(self.endpoint, remote_cmd, timeout=timeout)
```

**实际 SSH 执行与返回：run_remote 返回非零 rc，不会因此抛异常；checked 才检查 rc**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/infra/ssh_transport.py:70-106`

```python
def ssh_argv(endpoint: SshEndpoint) -> list[str]:
    """ssh 命令前缀（BatchMode 禁交互，10s 连接超时）。"""
    argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    if endpoint.identity_file:
        argv += ["-i", endpoint.identity_file]
    argv += ["-p", str(endpoint.port), endpoint.target]
    return argv


def run_remote(
    endpoint: SshEndpoint, remote_cmd: str, *, timeout: float = 30
) -> tuple[int, str, str]:
    """在远端执行一条命令，返回 ``(rc, stdout, stderr)``；传输失败抛 SshError。"""
    try:
        completed = subprocess.run(
            [*ssh_argv(endpoint), remote_cmd],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SshError(f"ssh to {endpoint.target} failed: {exc}") from exc
    return completed.returncode, completed.stdout, completed.stderr


def run_remote_checked(
    endpoint: SshEndpoint, remote_cmd: str, *, timeout: float = 30
) -> str:
    """远端命令必须 rc=0，否则抛 SshError（带远端 stderr 摘要）。"""
    rc, stdout, stderr = run_remote(endpoint, remote_cmd, timeout=timeout)
    if rc != 0:
        raise SshError(
            f"remote command failed on {endpoint.target} (rc={rc}): "
            f"{(stderr or stdout).strip()[:2000]}"
        )
    return stdout
```

**账本确认：不查执行端，只将 running/cancel_requested 改为 cancelled**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/compute_store.py:916-940`

```python
def cancel_compute_job(db: ComputeDB, task_id: int) -> bool:
    """执行端确认计算退出（或确认尚未启动）后，落 cancelled。

    只覆盖 running / cancel_requested，不得把 done/failed 改成 cancelled。
    """
    def write() -> bool:
        with db.connect() as con:
            cur = con.execute(
                """UPDATE compute_jobs SET state='cancelled',
                scheduler_state='CANCELLED', end_timestamp=?
                WHERE id=? AND state IN ('running', 'cancel_requested')""",
                (time.time(), task_id),
            )
            con.commit()
            return cur.rowcount == 1

    return retry_on_locked(write)


async def acancel_compute_job(db: ComputeDB, task_id: int) -> None:
    """执行端确认取消完成后落 cancelled；发出停止请求本身不算完成。

    只覆盖 running / cancel_requested，不得把 done/failed 改成 cancelled。
    """
    await asyncio.to_thread(cancel_compute_job, db, task_id)
```

**实际调度后果：cancelled 不计入容量占用**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/compute_store.py:473-499`

```python
def _usage_by_node(
    con,
    *,
    now: float,
    default_node_id: str,
    fair_share_mb: Mapping[str, int],
) -> dict[str, list[int]]:
    """租约有效 running 行的**按节点**在用量：``{node_id: [槽位, CPU, 内存MB]}``。

    ``node_id`` 为 NULL 的行归属 ``default_node_id``（旧行升级路径）。不在
    ``fair_share_mb`` 里的节点（已从注册表消失）拿不到公平份额，按声明值或 0
    记账——它的额度本就不存在，认领也不会认到它。
    """
    rows = con.execute(
        """SELECT COALESCE(node_id, ?) AS node, req_cpus, req_memory_mb
           FROM compute_jobs
           WHERE state IN ('running', 'cancel_requested')""",
        (default_node_id,),
    ).fetchall()
    usage: dict[str, list[int]] = {}
    for node, req_cpus, req_mem in rows:
        key = str(node)
        acc = usage.setdefault(key, [0, 0, 0])
        acc[0] += 1
        acc[1] += int(req_cpus or 1)
        acc[2] += int(req_mem if req_mem is not None else fair_share_mb.get(key, 0))
    return usage
```

##### 同系统已经存在的正确对照

以下代码说明这是执行端实现分叉，不能归因于“取消状态设计本来就允许立即终结”。shell 在 runner 消失时也保留请求与容量；本地 Slurm 在 scancel 失败时重试，直到调度终态。

**SSH shell 对照：VANISHED 不证明子进程已退出**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime/remote_compute.py:486-496`

```python
        if shell_runner:
            latest = await aget_compute_job(db, task_id)
            if latest and latest["state"] == "cancel_requested":
                if state == "EXIT":
                    await acancel_compute_job(db, task_id)
                    return 1
                # A vanished runner is not proof that its training children
                # exited. Retain the reservation until the receipt is present.
                if state == "VANISHED":
                    await sleep(poll_seconds)
                    continue
```

**本地 Slurm 对照：请求成功不等于退出，必须等终态确认**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/infra/slurm.py:390-436`

```python
    while True:
        current = await aget_compute_job(db, task_id)
        if current and current["state"] not in {"running", "cancel_requested"}:
            return 0 if current["state"] == "done" else 1
        if current and current["state"] == "cancel_requested" and not cancel_sent:
            try:
                await asyncio.to_thread(cancel_job, str(scheduler_job_id))
            except (SlurmError, OSError, subprocess.TimeoutExpired):
                # Keep the request pending. A later iteration retries scancel;
                # sacct can still independently confirm that the job has exited.
                pass
            else:
                cancel_sent = True
        try:
            state, exit_code = await asyncio.to_thread(query_job, str(scheduler_job_id))
        except (SlurmError, OSError, subprocess.TimeoutExpired):
            await sleep(poll_seconds)
            continue
        # Querying sacct can overlap cancel-all. Only terminal accounting is exit
        # evidence; scancel acceptance or missing accounting rows are not.
        current = await aget_compute_job(db, task_id)
        if not state:
            if last_observed and current and current["state"] == "running":
                empty_after_seen += 1
                if empty_after_seen >= 3:
                    wrote = await afinalize_compute_job(
                        db,
                        task_id,
                        "failed",
                        last_error="Slurm accounting row vanished after "
                        f"{last_observed}",
                    )
                    if not wrote:
                        latest = await aget_compute_job(db, task_id)
                        if latest and latest["state"] == "cancel_requested":
                            await sleep(poll_seconds)
                            continue
                    return 1
            await sleep(poll_seconds)
            continue
        empty_after_seen = 0
        last_observed = state
        await aupdate_scheduler_state(db, task_id, state)
        if state in SLURM_TERMINAL_SUCCESS | SLURM_TERMINAL_FAILURE:
            if current and current["state"] == "cancel_requested":
                await acancel_compute_job(db, task_id)
                return 1
```

#### 2. 缺少原生日志，Slurm/SSH 反而保留“成功”结论

**具体触发。** 作业调度显示 COMPLETED，或 SSH runner 返回 0；原生引擎日志却不存在或不可读。日志解析辅助函数返回 None，调用者保留/生成 done。

**后果。** 一项没有原生正常终止证据的科学计算被记为 done 并返回成功代码，随后作为计算完成结果进入后续通知/审核。这里只是账本假成功，不足以证明 DAG 科学验收已被绕过。

**设计根因。** “调度完成”“脚本退出”“量子化学软件正常终止”各有权威，远端路径却用前两者填补第三者的缺证据。更糟的是，明确失败日志会 failed，完全没有日志却能 done。与本地 guard 的缺日志失败行为不一致。

**最简单修复。** 删除科学计算的缺日志成功回退：没有原生可判定日志时，使用现有失败状态并明确提示缺少终止证据；不添新的科学阈值。shell 保持退出码语义。正常退出后的收敛、频率和 IRC 仍由相应科学证据层判定。

##### 公共入口与日志判定

**执行入口：本机 Slurm 与 SSH 分别转发，收尾结果再入审核**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime/compute_executor.py:126-158`

```python
    if kind == "slurm" or kind in REMOTE_KINDS:
        # poller 型作业（本机 Slurm / SSH 远端）：认领进程内轮询即看守，租约随 poll 续
        stop = asyncio.Event()
        renewer = None
        if worker_id:
            renewer = asyncio.create_task(
                _renew_lease(db, task_id, worker_id, stop),
                name=f"compute-lease-{task_id}",
            )
        try:
            if kind == "slurm":
                rc = await run_slurm_compute(task_id, db.path, scheduler=options)
            else:
                rc = await run_remote_compute(task_id, db.path)
            # 作业在 run_*_compute 内到达终态并落库；读回终态入
            # CallReview 收件箱（rev_compute_<id> 去重，非 dag 模式内部跳过）。
            try:
                settled = await aget_compute_job(db, task_id)
                if settled and settled["state"] in ("done", "failed"):
                    from cloudra.dag.controller import enqueue_compute_review

                    await enqueue_compute_review(task_id, settled["state"])
            except Exception:
                logger.exception("could not enqueue compute review for job %s", task_id)
            return rc
        except Exception as exc:
            await _mark_failed(db, task_id, f"{kind} compute failed: {exc}")
            return 1
        finally:
            stop.set()
            if renewer is not None:
                renewer.cancel()
                await asyncio.gather(renewer, return_exceptions=True)
```

**日志路径解析：主日志与 calculator 捕获日志的实际选择**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/infra/compute_utils.py:366-391`

```python
def resolve_log_path(input_file: str, job_type: str = "gaussian", task_id: int | None = None) -> str:
    """解析计算作业的真实日志路径——query_compute_job 与完成通知统一走这里（GH #20）。

    预测路径（引擎惯例后缀）常与 guard 实际解析的日志不一致：部分引擎不自写
    日志文件（如本机 ORCA 6.1.1 macOS 构建把主输出全部写 stdout、从不落 .out），
    guard 会把 calculator stdout 捕获到 ``.cloudra/calc-<id>.out.log`` 并回退解析它，
    实际解析路径记录在 guard state json 的 ``log_file`` 字段。
    优先级：state json 记录的真实 log_file（文件仍存在）→ calc 落盘文件
    （存在时）→ get_log_path 的纯字符串预测。
    """
    if job_type == 'chem_task':
        return input_file
    if input_file and task_id is not None:
        workdir = Path(input_file).parent
        try:
            recorded = json.loads(
                (workdir / f"state_{task_id}.json").read_text(encoding="utf-8")
            ).get("log_file")
        except (OSError, ValueError):
            recorded = None
        if recorded and Path(recorded).is_file():
            return str(recorded)
        captured = workdir / ".cloudra" / f"calc-{task_id}.out.log"
        if captured.is_file():
            return str(captured)
    return get_log_path(input_file, job_type=job_type)
```

**原生日志路径转换：按输入类型与文件名生成目标**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/infra/compute_utils.py:351-363`

```python
def get_log_path(input_file: str, job_type: str = "gaussian") -> str:
    """根据输入文件路径推导计算软件生成的日志文件路径。

    Gaussian 默认生成与输入文件同名但后缀为 .log 的文件；
    ORCA、CP2K 生成 .out；xtb 主输出由 calculator.sh 重定向到 .out；
    VASP 的日志命名不固定，默认仍按 .out 处理。
    """
    path = Path(input_file)
    if job_type == "chem_task":
        return input_file
    if job_type == "gaussian":
        return str(path.with_suffix(".log"))
    return str(path.with_suffix(".out"))
```

**引擎判定：缺文件或不可读返回 None，而不是确认正常终止**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/infra/slurm.py:275-323`

```python
def _engine_success_from_log(
    job_type: str | None, input_path: str | None, task_id: int | None = None
) -> bool | None:
    """本地 guard 同款文本标记。None = 没有可判定的引擎日志，调用方保持 sacct。"""
    if not input_path:
        return None
    if job_type == 'chem_task':
        from cloudra.runtime.chem_task import read_task_result
        try:
            return read_task_result(str(input_path))[1]
        except (OSError, ValueError, KeyError):
            return False
    from cloudra.infra.compute_utils import resolve_log_path

    log_path = resolve_log_path(
        str(input_path), job_type=job_type or "gaussian", task_id=task_id
    )
    path = Path(log_path)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    kind = (job_type or "").strip().lower()
    if kind == "gaussian":
        from cloudra.tools.core.gaussian_frames import normal_termination

        return normal_termination(text)
    if kind == "orca":
        from cloudra.tools.core import orca_frames

        return orca_frames.normal_termination(text)
    if kind == "cp2k":
        from cloudra.runtime.monitor import _parse_cp2k_log

        parsed = _parse_cp2k_log(path)
        return None if parsed is None else parsed[1]
    if kind == "xtb":
        from cloudra.runtime.monitor import _parse_xtb_log

        parsed = _parse_xtb_log(path)
        return None if parsed is None else parsed[1]
    if kind == "vasp":
        from cloudra.runtime.monitor import _parse_vasp_log

        parsed = _parse_vasp_log(path)
        return None if parsed is None else parsed[1]
    return None
```

##### 本机 Slurm 分支

Slurm 已给终态时先设 done；只有 engine_ok 明确等于 False 才改 failed，None 路径原样落 done。

**Slurm 终态、日志复核、账本落库与返回的完整相关分支**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/infra/slurm.py:430-468`

```python
        empty_after_seen = 0
        last_observed = state
        await aupdate_scheduler_state(db, task_id, state)
        if state in SLURM_TERMINAL_SUCCESS | SLURM_TERMINAL_FAILURE:
            if current and current["state"] == "cancel_requested":
                await acancel_compute_job(db, task_id)
                return 1
            last_error = None if state in SLURM_TERMINAL_SUCCESS else f"Slurm {state} ({exit_code})"
            final = "done" if state in SLURM_TERMINAL_SUCCESS else "failed"
            if state in SLURM_TERMINAL_SUCCESS:
                job_type = current["jobtype"] if current else row["jobtype"]
                if job_type == "shell":
                    if exit_code != "0:0":
                        final = "failed"
                        last_error = f"shell exit code {exit_code or 'unknown'} (Slurm {state})"
                else:
                    engine_ok = await asyncio.to_thread(
                        _engine_success_from_log,
                        job_type,
                        current["path"] if current else row["path"],
                        task_id,
                    )
                    if engine_ok is False:
                        final = "failed"
                        last_error = "engine error termination (Slurm COMPLETED)"
            wrote = await afinalize_compute_job(
                db,
                task_id,
                final,
                last_error=last_error,
            )
            if not wrote:
                latest = await aget_compute_job(db, task_id)
                if latest and latest["state"] == "cancel_requested":
                    await acancel_compute_job(db, task_id)
                    return 1
            # 终态通知由 ComputeNotifyBroker 轮询 compute_jobs 表补投，不再发 IPC
            return 0 if final == "done" else 1
        await sleep(poll_seconds)
```

##### SSH 分支

远端目录拉回成功仅说明传输成功；不能证明里面一定有原生日志。日志判定为 None 后，_terminal_verdict 直接用调度/脚本结果替代。

**SSH 入口：恢复输入类型、路径与句柄**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime/remote_compute.py:416-437`

```python
async def run_remote_compute(
    task_id: int,
    db_path: str,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    transport=None,
) -> int:
    """执行一条已认领的 ssh_local/ssh_slurm 作业；到达终态并落库后返回。"""
    db = ComputeDB.from_path(db_path)
    row = await aget_compute_job(db, task_id)
    if not row:
        raise SshError(f"compute job {task_id} 不存在")
    kind = (row["scheduler"] or "").strip()
    if kind not in REMOTE_KINDS:
        raise SshError(f"compute job {task_id} 不是远端作业: {kind!r}")
    options = _scheduler_options(row)
    endpoint = SshEndpoint.from_connection(options.get("connection") or {})
    transport = transport or SshTransport(endpoint)
    job_type = (row["jobtype"] or "").strip()
    input_file = Path(row["path"]).expanduser()
    remote_dir = endpoint.job_dir(task_id)
    handle = (row["scheduler_job_id"] or "").strip()
```

**进入轮询：区分 ssh_slurm 与 ssh_local 的状态查询**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime/remote_compute.py:458-484`

```python
    workdir = input_file.parent
    poll_seconds = min(max(float(options.get("poll_seconds", 15)), 1), 300)
    last_observed = ""
    empty_after_seen = 0
    pull_failures = 0
    shell_runner = kind == "ssh_local" and job_type == "shell"
    while True:
        current = await aget_compute_job(db, task_id)
        if current and current["state"] in {"cancelled", "cancel_requested"}:
            await asyncio.to_thread(
                _cancel_remote, transport, kind, remote_dir, task_id, handle, job_type
            )
            if not shell_runner or current["state"] == "cancelled":
                await acancel_compute_job(db, task_id)
                return 1
        try:
            if kind == "ssh_slurm":
                state, exit_code = await asyncio.to_thread(
                    _query_slurm_state, transport, handle
                )
            else:
                state, exit_code = await asyncio.to_thread(
                    _query_shell_state, transport, remote_dir, task_id, handle
                )
        except SshError:
            await sleep(poll_seconds)
            continue
```

**终态路径：状态归类、产物拉回、日志调用、终态落库及返回**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime/remote_compute.py:498-577`

```python
        base_error: str | None = None
        if kind == "ssh_slurm":
            if not state:
                if last_observed:
                    empty_after_seen += 1
                    if empty_after_seen >= 3:
                        await afinalize_compute_job(
                            db,
                            task_id,
                            "failed",
                            last_error="Slurm accounting row vanished after "
                            f"{last_observed}",
                        )
                        return 1
                await sleep(poll_seconds)
                continue
            empty_after_seen = 0
            last_observed = state
            await aupdate_scheduler_state(db, task_id, state)
            if state not in SLURM_TERMINAL_SUCCESS | SLURM_TERMINAL_FAILURE:
                await sleep(poll_seconds)
                continue
            if state in SLURM_TERMINAL_FAILURE:
                base_error = f"Slurm {state} ({exit_code})"
        else:
            await aupdate_scheduler_state(
                db, task_id, f"EXIT:{exit_code}" if state == "EXIT" else state
            )
            if state == "RUNNING":
                await sleep(poll_seconds)
                continue
            if state == "VANISHED":
                base_error = (
                    "remote runner vanished before writing its exit file "
                    "(node reboot or SIGKILL)"
                )

        # 终态：拉回全部产物（有界重试），shell 只认退出码，其余引擎复核日志。
        try:
            await asyncio.to_thread(transport.pull_dir, remote_dir, str(workdir))
        except SshError as exc:
            pull_failures += 1
            if pull_failures < _MAX_PULL_ATTEMPTS:
                await sleep(poll_seconds)
                continue
            await afinalize_compute_job(
                db,
                task_id,
                "failed",
                last_error=(
                    f"artifact pull-back failed after {_MAX_PULL_ATTEMPTS} "
                    f"attempts: {exc}"
                )[:500],
            )
            return 1
        if job_type == "shell":
            succeeded = not base_error and exit_code == ("0:0" if kind == "ssh_slurm" else "0")
            final = "done" if succeeded else "failed"
            last_error = None if succeeded else base_error or f"shell exit code {exit_code or 'unknown'}"
        else:
            engine_ok = await asyncio.to_thread(
                _engine_success_from_log, job_type, str(input_file), task_id
            )
            final, last_error = _terminal_verdict(
                kind, state, exit_code, engine_ok, base_error
            )
        wrote = await afinalize_compute_job(db, task_id, final, last_error=last_error)
        if not wrote:
            latest = await aget_compute_job(db, task_id)
            if latest and latest["state"] in {"cancelled", "cancel_requested"}:
                await asyncio.to_thread(
                    _cancel_remote, transport, kind, remote_dir, task_id, handle, job_type
                )
                if shell_runner and state != "EXIT":
                    await sleep(poll_seconds)
                    continue
                await acancel_compute_job(db, task_id)
                return 1
        # 终态通知由 ComputeNotifyBroker 轮询 compute_jobs 表补投，不再发 IPC
        return 0 if final == "done" else 1
```

**结果转换：缺日志 None 被转换为 done**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime/remote_compute.py:387-413`

```python
def _terminal_verdict(
    kind: str, state: str, exit_code: str, engine_ok: bool | None, base_error: str | None
) -> tuple[str, str | None]:
    """终态判定：引擎文本闸门是权威（与本地 guard / Slurm COMPLETED 复核同口径）。

    engine_ok=True → done；False → failed。None（没有可判定日志）时回落调度侧
    信号：ssh_slurm 保持 sacct 结论（同本地 slurm 口径），ssh_local 看 runner
    退出码（0 → done；非 0 / runner 消失 → failed）。
    """
    if engine_ok is True:
        return "done", None
    if engine_ok is False:
        if base_error:
            return "failed", base_error
        reason = (
            "engine error termination (Slurm COMPLETED)"
            if kind == "ssh_slurm"
            else "engine error termination"
        )
        return "failed", reason
    if base_error:
        return "failed", base_error
    if kind == "ssh_slurm":
        return "done", None
    if exit_code == "0":
        return "done", None
    return "failed", f"remote runner exit code {exit_code or 'unknown'}"
```

**最终写入：CAS 保证并发状态，但不验证状态结论的证据**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/compute_store.py:831-852`

```python
async def afinalize_compute_job(
    db: ComputeDB,
    task_id: int,
    state: str,
    *,
    last_error: Optional[str] = None,
    only_running: bool = True,
) -> bool:
    """终态 CAS 落库；only_running=True 时仅覆盖 running（双写竞态防护）。

    返回是否真的写入（CAS 失败说明其他收尾方已写终态）。
    """
    sql = "UPDATE compute_jobs SET state=?, end_timestamp=?, last_error=? WHERE id=?"
    if only_running:
        sql += " AND state='running'"
    async def write() -> bool:
        async with db.aconnect() as con:
            cur = await con.execute(sql, (state, time.time(), last_error, task_id))
            await con.commit()
            return cur.rowcount == 1

    return await aretry_on_locked(write)
```

##### 本地 guard 对照

以下是相同缺日志情形在本地的既有行为。需要统一的是计算结束证据语义，而不是新增一层复杂规则。

**本地解析：没有实际日志目标就返回缺结果**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime/monitor.py:147-155`

```python
    if job_type == 'chem_task':
        from cloudra.runtime.chem_task import read_task_result
        try:
            return await asyncio.to_thread(read_task_result, str(log_path))
        except (OSError, ValueError, KeyError):
            return None, False
    target, _ = await asyncio.to_thread(_resolve_log_target, log_path, fallback_log_path)
    if target is None:
        return None, None
```

**本地收尾：缺解析结果会失败，不能落 done**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime/monitor.py:487-506`

```python
    else:
        data_dic, is_success = await _parse_log(
            log_path, parse_timeout, job_type=job_type,
            fallback_log_path=fallback_log_path, xtb_task=xtb_task,
        )
    if data_dic is None:
        # reason 从"实际应解析的日志"取：推导路径缺失时它可能在落盘回退文件里
        target, _ = await asyncio.to_thread(_resolve_log_target, log_path, fallback_log_path)
        reason = await asyncio.to_thread(_log_tail_reason, target) if target is not None else ""
        await _mark_failed(
            db,
            taskid,
            "guard 在解析窗口内无法完成日志解析"
            + (f"（calculator 退出码 {returncode}）" if returncode else "")
            + (f"；日志尾部：{reason}" if reason else "；日志为空或缺失"),
        )
        return

    state = 'done' if is_success else 'failed'
    fail_reason = ""
```

#### 3. 廉价力场资格被放成 CREST 的启动许可

**具体触发。** 选择 backend=crest。闭壳层分子已成功嵌入真实三维坐标，但 MMFF/UFF 没有覆盖全部原子的参数，或力场迭代未收敛。程序提前拒绝，CREST/xTB 不会获得优化这些坐标的机会。

**后果。** 一个粗略方法的“不支持/未收敛”变成更合适后续方法的禁止条件。不能把没有力场参数解释成没有真实坐标，也不能把“不是力场极小值”解释成“不能作为电子结构计算种子”。

**设计根因。** has_coordinates 混合了两个问题：有没有真实坐标，以及本轮力场是否认可它。共享构建器向调用方只提供总成败，调用方又用总成败决定能否运行不同方法。程序自己的错误文案说这些坐标可作 QM 种子，返回字段却堵住这条路径。

**最简单修复。** CREST 入口只需要真实可用的输入几何，不把 MMFF/UFF 收敛作为启动前提。力场收敛仍决定能否称为力场极小值；原子身份、有限坐标、电子态、真实严重碰撞等检查保留。具体涉及现有科学资格政策的修改需用户确认，本审计未修改任何科学判断。

##### 实际 schema、转发、拒绝与返回

**公开输入：具体文件、电子态、backend 与 mode 的实际字段及默认值**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/conformer_search.py:178-220`

```python
    input_path: Optional[str] = Field(
        default=None,
        description="Input structure file path (xyz/sdf/mol). xyz input infers bond orders via "
                    "rdDetermineBonds. Absolute paths are used as given; relative paths resolve "
                    "against the Agent working directory."
    )
    input_text: Optional[str] = Field(
        default=None,
        description="Structure text (xyz or mol block). If input_path is set, the file is read instead."
    )
    charge: int = Field(
        default=0,
        description="Total molecular charge. Must equal the structure's formal-charge sum; used when "
                    "inferring bond orders from xyz, and passed to CREST as --chrg."
    )
    multiplicity: int = Field(
        default=1,
        description="Spin multiplicity (2S+1). CREST backend: passed to xtb as --uhf = multiplicity - 1. "
                    "Electron-count parity and spin range are checked without selecting a ground state. "
                    "Non-singlet open-shell inputs may use an unoptimized ETKDG seed with unguided "
                    "CREST. The current CREST interface cannot represent open-shell singlets; "
                    "RDKit force-field ensembles and guided force-field searches refuse open-shell states."
    )
    electronic_character: Literal["closed_shell", "open_shell"] | None = Field(
        default=None,
        description="Optional explicit electronic character. Use open_shell for an open-shell singlet "
        "even when the molecular graph carries no localized radical labels; no spin coupling is inferred.",
    )
    backend: Literal["rdkit", "crest"] = Field(
        default="rdkit",
        description="Search backend. rdkit: ETKDGv3 sampling + MMFF/UFF optimization; crest: external CREST (GFN2-xTB, --quick). "
                    "Any mode other than 'conformers' requires backend='crest'."
    )
    mode: Literal["conformers", "nci", "qcg", "protonate", "deprotonate", "tautomerize"] = Field(
        default="conformers",
        description="CREST run type (backend='crest' only). conformers: ordinary search. "
                    "nci: non-covalent complex/aggregate sampling under a wall potential — for hydrogen-bond "
                    "networks and preorganized reactant complexes (intended for multi-component inputs). "
                    "qcg: grow an explicit solvent shell of nsolv solvent_smiles molecules around the solute "
                    "(quantum cluster growth; requires the external xtb-IFF program). "
                    "protonate/deprotonate/tautomerize: protomer/tautomer enumeration of a SINGLE-component "
                    "input; the output may contain pseudo-structures — review every structure before use.",
    )
```

**入口分支：无 regions/ring_order/distance_filters 时转发给 _run_crest**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/conformer_search.py:1252-1290`

```python
        # 路径语义收口：相对路径解析到 agent 工作目录（沙箱），绝对路径保持既有权限语义。
        if user_input.input_path:
            user_input.input_path = resolve_tool_path(self, user_input.input_path)
        out_dir = self._resolve_output_dir(user_input)
        user_input.output_dir = resolve_tool_path(self, out_dir)

        if user_input.catalog_mode == "regions":
            return await asyncio.to_thread(self._run_regions, user_input, user_input.output_dir)

        if user_input.ring_order or user_input.distance_filters:
            from cloudra.tools.core.preorganization import search_guided

            try:
                guided = await asyncio.to_thread(
                    search_guided,
                    structure=self._structure_input(user_input),
                    output_dir=user_input.output_dir,
                    ring_order=user_input.ring_order,
                    distance_filters=[row.model_dump() for row in user_input.distance_filters],
                    charge=user_input.charge, multiplicity=user_input.multiplicity,
                    electronic_character=user_input.electronic_character,
                    backend=user_input.backend, mode=user_input.mode,
                    num_confs=user_input.num_confs, random_seed=user_input.random_seed,
                    rmsd_threshold=user_input.rmsd_threshold, timeout=user_input.timeout,
                )
            except ValueError as exc:
                return ConformerSearch_output_schema(is_success=False, message=f"Invalid ring_order/distance_filters: {exc}")
            return self._guided_output(guided)

        # CREST / RDKit 都是同步 CPU/子进程；必须离开 UI 事件循环，否则 TUI 假死。
        if user_input.backend == "crest":
            return await asyncio.to_thread(self._run_crest, user_input, user_input.output_dir)

        if not _RDKIT_AVAILABLE:
            return ConformerSearch_output_schema(
                is_success=False,
                message="RDKit is not installed. Install it with: pip install 'cloudra[chem]'"
            )
        return await asyncio.to_thread(self._run_rdkit, user_input, user_input.output_dir)
```

**CREST 执行入口：强制 embed+optimize，并按构建总成败提前返回**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/conformer_search.py:996-1024`

```python
    def _run_crest(self, user_input: ConformerSearch_input_schema, out_dir: str, *, candidate_sink=None) -> ConformerSearch_output_schema:
        try:
            # 种子结构由共享构建器产出（embed+optimize），多组分得到组装复合物，
            # 互穿几何绝不会被喂给 CREST/xTB（issue #33 的直接病因）。
            prepared = self._prepare(user_input, out_dir, embed=True, optimize=True,candidate_sink=candidate_sink)
            if prepared.status != "ok" or not prepared.has_coordinates:
                return self._build_failure(prepared)
            if prepared.electronic_state["is_open_shell"] and user_input.multiplicity == 1:
                return ConformerSearch_output_schema(
                    is_success=False,
                    message="The current CREST interface cannot represent a declared open-shell singlet "
                    "through --uhf 0; it has no broken-symmetry or initial-spin declaration. The "
                    "unoptimized MOL/XYZ seed is available for an explicitly chosen QM method and "
                    f"spin-initialization settings. Build artifacts: {prepared.artifact_path}",
                )

            runtype = "default" if user_input.mode == "conformers" else user_input.mode
            multi_fragment = len(prepared.components) > 1
            if runtype in self._SINGLE_COMPONENT_RUNTYPES and multi_fragment:
                return ConformerSearch_output_schema(
                    is_success=False,
                    message=(
                        f"mode='{user_input.mode}' screens protonation states/tautomers of ONE "
                        f"molecule, but this input has {len(prepared.components)} components. "
                        "Run it per component, or use mode='nci'/'conformers' for the complex."
                    ),
                )

            seed_xyz = to_xyz(prepared.mol)
```

**准备转发与错误返回：使用共享构建器，把 status/has_coordinates 的否决返回给调用方**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/conformer_search.py:343-367`

```python
    def _prepare(self, user_input: ConformerSearch_input_schema, out_dir: str,
                 *, embed: bool, optimize: bool, candidate_sink=None) -> PreparedStructure:
        """调用共享构建器解析/构建结构（本工具不再自带解析与 Embed/MMFF 快捷路径）。"""
        return prepare_structure(PreparationRequest(
            structure=self._structure_input(user_input),
            output_dir=self._build_dir(out_dir),
            total_charge=user_input.charge,
            multiplicity=user_input.multiplicity,
            electronic_character=user_input.electronic_character,
            random_seed=user_input.random_seed,
            strategy=BuildStrategy(name="per_component", embed=embed, optimize=optimize),
        ),candidate_sink=candidate_sink)

    @staticmethod
    def _build_failure(prepared: PreparedStructure) -> ConformerSearch_output_schema:
        details = " | ".join(prepared.diagnostics) if prepared.diagnostics else prepared.message
        return ConformerSearch_output_schema(
            is_success=False,
            message=(
                f"Conformer search refused by the shared structure builder "
                f"(build status: {prepared.status}). {prepared.message}"
                + (f" Diagnostics: {details}" if details and details != prepared.message else "")
                + f" Build artifacts: {prepared.artifact_path}"
            ),
        )
```

**构建入口：解析结构、电子态检查、逐组分转发给 _build_component**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/structure_builder.py:752-818`

```python
def prepare_structure(request: PreparationRequest, *, candidate_sink=None) -> PreparedStructure:
    """把请求解析成 ``PreparedStructure``。

    所有可预期失败都返回带显式 ``status`` 的产物（不抛异常、也不返回半成品冒充成功）；
    只有"本函数无法继续"（缺 RDKit、策略名未知）才抛异常。
    """
    if not _RDKIT_AVAILABLE:
        raise RuntimeError(
            "RDKit is not installed. Install it with: pip install 'cloudra[chem]', then retry."
        )
    if request.strategy.name != "per_component":
        raise ValueError(
            f"unknown build strategy {request.strategy.name!r}; only 'per_component' has been "
            "approved (assembly sampling parameters are still awaiting user approval)"
        )
    if request.multiplicity < 1:
        raise ValueError(f"multiplicity must be >= 1 (2S+1), got {request.multiplicity}")

    out_dir = request.output_dir
    os.makedirs(out_dir, exist_ok=True)

    try:
        mol = _parse_input(request.structure, request.total_charge)
    except ValueError as exc:
        return _empty(
            "invalid_input",
            f"Could not build a structure from the request: {exc}",
            out_dir,
        )

    fragments = _fragment_atom_tuples(mol)
    if not fragments:
        return _empty(
            "invalid_input", "The input structure contains no atoms", out_dir,
        )

    state_details = electronic_state_details(
        mol, charge=request.total_charge, multiplicity=request.multiplicity,
        electronic_character=request.electronic_character,
    )
    state_issue = electronic_state_issue(
        mol, charge=request.total_charge, multiplicity=request.multiplicity,
        electronic_character=request.electronic_character,
    )
    if state_issue:
        status, message = state_issue
        return _empty(
            status, message,
            out_dir, mol,
            diagnostics=[
                f"{len(fragments)} component(s) were not built: the electronic state is unsupported"
            ],
            electronic_state=state_details,
        )

    artifacts: list[TrajectoryArtifact] = []
    components: list[BuildComponent] = []
    identities: list[AtomIdentity] = []
    component_paths: list[str] = []
    index_offset = 0

    for position, indices in enumerate(fragments):
        component_id = f"frag{position}"
        component, component_identities = _build_component(
            mol, list(indices), component_id, request, out_dir, artifacts, index_offset, candidate_sink,
            skip_force_field=state_details["requires_spin_aware_geometry"],
        )
```

**组件生成与力场分支：嵌入成功后，缺参数或不收敛被记为失败资格**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/structure_builder.py:560-677`

```python
def _build_component(mol, indices: list[int], component_id: str, request: PreparationRequest,
                     out_dir: str, artifacts: list[TrajectoryArtifact],
                     index_offset: int, candidate_sink=None, *, skip_force_field: bool) -> tuple[BuildComponent, list[AtomIdentity]]:
    """构建单个组分：切分 → 加氢 → （可选）嵌入 → 力场优化（含轨迹）→ 落盘。"""
    submol, old_to_new = _submol_by_input_indices(mol, indices)
    submol_atom_to_input = {new: old for old, new in old_to_new.items()}
    diagnostics: list[str] = []

    formal_charge = sum(a.GetFormalCharge() for a in submol.GetAtoms())

    mol_h, hydrogen_by_index = _add_hydrogens_with_identity(submol, component_id)
    identities = _identity_table(
        mol_h, submol_atom_to_input, hydrogen_by_index, component_id, index_offset,
    )

    component_capture=candidate_sink.for_component(identities) if candidate_sink else None
    parent=None
    single_atom = mol_h.GetNumAtoms() == 1
    embed_status: EmbedStatus = "not_required"
    optimization_status: OptimizationStatus = "not_required"
    engine = ""
    trajectory_id = ""
    final_energy: Optional[float] = None
    xyz_path = ""
    conf_id: Optional[int] = None

    if not request.strategy.embed:
        diagnostics.append(
            "coordinate embedding was not requested (strategy.embed=False); only the structural "
            "resolution (split / AddHs / identity table / charge self-check) was performed"
        )
    elif single_atom:
        # 单原子组分无需调用力场：位置即原点，没有可优化的内部自由度。
        conf = Chem.Conformer(1)
        conf.SetAtomPosition(0, (0.0, 0.0, 0.0))
        mol_h.RemoveAllConformers()
        conf_id = mol_h.AddConformer(conf, assignId=True)
        diagnostics.append(
            "single-atom component: no conformer embedding and no force field were run"
        )
        if skip_force_field:
            optimization_status = "skipped_electronic_state"
            diagnostics.append("single-atom seed: no force-field energy or optimization is claimed")
    else:
        params = AllChem.ETKDGv3()
        params.randomSeed = request.random_seed
        params.clearConfs = True
        params.pruneRmsThresh = -1.0
        embedded = AllChem.EmbedMolecule(mol_h, params)
        if embedded < 0:
            embed_status = "failed"
            mol_h.RemoveAllConformers()
            placeholder = Chem.Conformer(mol_h.GetNumAtoms())
            for atom_index in range(mol_h.GetNumAtoms()):
                placeholder.SetAtomPosition(atom_index, (0.0, 0.0, 0.0))
            conf_id = mol_h.AddConformer(placeholder, assignId=True)
            diagnostics.append(
                f"ETKDGv3 embedding failed for component {component_id} "
                f"(seed={request.random_seed}); the recorded coordinates are placeholders at the "
                "origin and must not be used as a starting geometry"
            )
        else:
            embed_status = "embedded"
            conf_id = embedded
            if component_capture:
                parent=component_capture.capture(mol_h,conf_id,generator="component_ETKDGv3",seed=request.random_seed)
            if not skip_force_field:
                engine = _select_engine(mol_h) or ""
            if skip_force_field:
                optimization_status = "skipped_electronic_state"
                diagnostics.append(
                    "ETKDGv3 seed coordinates are unoptimized: the electronic-state declaration or "
                    "localized radical graph markers require avoiding MMFF94/UFF. No force-field "
                    "energy or convergence is claimed; subsequent optimization must preserve the "
                    "declared electronic state."
                )
            elif not request.strategy.optimize:
                optimization_status = "not_required"
                diagnostics.append("force-field optimization disabled by the approved build strategy")
            elif not engine:
                if component_capture:
                    from cloudra.tools.core.conformer_catalog import Qualification
                    component_capture.capture(mol_h,conf_id,generator="component_force_field_unavailable",parent_id=parent.candidate_id,state="failed",qualification=Qualification(status="rejected",reasons=["missing_parameters"]))
                optimization_status = "missing_parameters"
                diagnostics.append(
                    "no force field covers every atom of this component (MMFF94 and UFF both "
                    "unavailable); coordinates are embedded but NOT optimized"
                )
            else:
                record = _optimize_component(
                    mol_h, conf_id, engine, request.random_seed, request.strategy,
                    component_id, attempt=1, out_dir=out_dir,
                )
                artifacts.append(trajectory_artifact(record))
                trajectory_id = record.trajectory_id
                final_energy = record.final_frame.energy
                optimization_status = record.status
                if component_capture:
                    from cloudra.tools.core.conformer_catalog import EnergyObservation, Qualification
                    energies=[]
                    if final_energy is not None:
                        energies=[EnergyObservation(value=final_energy,unit='kcal/mol',method_fingerprint=engine,
                            species_key=parent.species_key,charge=formal_charge,multiplicity=request.multiplicity,
                            convergence='converged' if record.status=='converged' else 'unconverged',artifact_ref=record.trajectory_id)]
                    component_capture.capture(mol_h,conf_id,generator='component_'+engine,parent_id=parent.candidate_id,
                        state='optimized' if record.status=='converged' else 'failed',energies=energies,
                        qualification=Qualification(status='unknown' if record.status=='converged' else 'rejected',
                            reasons=[] if record.status=='converged' else [record.status],evidence_refs=[record.trajectory_id]))
                if record.status == "not_converged":
                    gradient = record.final_frame.max_gradient
                    gradient_text = "n/a" if gradient is None else f"{gradient:.6g}"
                    diagnostics.append(
                        f"force-field optimization did not converge within "
                        f"{request.strategy.max_optimization_steps} iterations "
                        f"(max gradient {gradient_text})"
                    )
                elif record.status == "failed":
                    diagnostics.append(f"force-field optimization raised: {record.failure}")
```

**力场选择实际实现：MMFF/UFF 是否覆盖全部原子**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/structure_builder.py:469-481`

```python
def _select_engine(mol) -> Optional[str]:
    """选力场引擎：优先 MMFF94，缺参数再试 UFF；两者皆不可用返回 None。"""
    try:
        if AllChem.MMFFHasAllMoleculeParams(mol):
            return MMFF_ENGINE
    except Exception:  # noqa: BLE001 - 力场不可用即视为该引擎不可选
        pass
    try:
        if AllChem.UFFHasAllMoleculeParams(mol):
            return UFF_ENGINE
    except Exception:  # noqa: BLE001
        pass
    return None
```

**力场实际执行与返回：收敛、失败与迭代用尽状态**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/structure_builder.py:503-538`

```python
def _optimize_component(mol, conf_id: int, engine: str, seed: int, strategy: BuildStrategy,
                        component_id: str, attempt: int, out_dir: str) -> TrajectoryRecord:
    """在**同一个** ForceField 实例上逐步优化，并把每一迭代帧流式写入轨迹文件。

    机制与其唯一性见 ``structure_artifacts`` 模块 docstring：本构建下
    ``MinimizeTrajectory`` 的 Snapshot 无 Python 绑定、``Positions()`` 只读，
    因此逐迭代 ``Minimize(maxIts=1)`` 是取到逐迭代快照的唯一手段；实测它给出与一次性
    ``Minimize(maxIts=N)`` 相同终态（dE ≤ 1e-4 kcal/mol）且能量单调下降。
    """
    trajectory_id = f"{component_id}-{engine.lower()}-attempt{attempt}"
    symbols = [a.GetSymbol() for a in mol.GetAtoms()]
    writer = TrajectoryWriter(
        out_dir, trajectory_id, component_id, attempt, engine, symbols, seed,
    )
    ff = _make_force_field(mol, conf_id, engine)
    if ff is None:
        writer.append(0, _positions(mol, conf_id), 0.0, None)
        return writer.finish(
            -2, "failed", failure=f"force field {engine} could not be constructed for this component",
        )

    ff.Initialize()
    writer.append(0, _positions(mol, conf_id), float(ff.CalcEnergy()), _max_gradient(ff))
    try:
        for step in range(1, strategy.max_optimization_steps + 1):
            code = int(ff.Minimize(maxIts=1))
            writer.append(step, _positions(mol, conf_id), float(ff.CalcEnergy()), _max_gradient(ff))
            if code == 0:
                return writer.finish(0, "converged")
    except Exception as exc:  # noqa: BLE001 - 异常前已写入的帧必须保留
        return writer.finish(-3, "failed", failure=f"{type(exc).__name__}: {exc}")

    return writer.finish(
        1, "not_converged",
        notes=[f"reached the iteration limit ({strategy.max_optimization_steps}) without converging"],
    )
```

**组件结果返回：真实 xyz 仍被保存，优化状态与坐标一同返回**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/structure_builder.py:679-707`

```python
    mol_path = os.path.join(out_dir, f"component_{component_id}.mol")
    atomic_write_text(
        mol_path,
        Chem.MolToMolBlock(mol_h, confId=conf_id) if conf_id is not None
        else Chem.MolToMolBlock(mol_h),
    )
    if conf_id is not None:
        xyz_path = os.path.join(out_dir, f"component_{component_id}.xyz")
        atomic_write_text(
            xyz_path,
            _render_xyz(
                mol_h, conf_id, f"component {component_id} (per-component build)", identities,
            ),
        )

    component = BuildComponent(
        component_id=component_id,
        mol=copy_conformer(mol_h, conf_id) if conf_id is not None else mol_h,
        source_atom_indices=list(indices),
        embed_status=embed_status,
        optimization_status=optimization_status,
        engine=engine,
        trajectory_id=trajectory_id,
        final_energy=final_energy,
        mol_path=mol_path,
        xyz_path=xyz_path,
        diagnostics=diagnostics,
    )
    return component, identities
```

**单组分构建结果转换与返回：有坐标但 has_coordinates=False；开壳层跳过力场却允许种子**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/structure_builder.py:950-1031`

```python
        only = components[0]
        if only.embed_status == "failed":
            status = "optimization_failed"
            has_coordinates = False
            message = (
                f"Conformer embedding failed for component {only.component_id}; the "
                "recorded coordinates are placeholders and must not be used as a starting geometry."
            )
        elif only.single_atom:
            status = "ok"
            has_coordinates = True
            message = "Single-atom structure; its coordinate is the origin (no force field needed)."
        elif only.optimization_status in _NON_USABLE_OPTIMIZATION:
            status = "optimization_failed"
            has_coordinates = False
            message = (
                f"Component {only.component_id} did not converge under "
                f"{only.engine or 'any force field'} (or the optimization raised); "
                "its embedded coordinates remain an unqualified seed for a separate quantum-chemistry "
                "optimization, not a force-field minimum. See the recorded trajectory for the last state."
            )
        elif only.optimization_status == "missing_parameters":
            status = "missing_parameters"
            has_coordinates = False
            message = (
                "No force field covers every atom of this structure (MMFF94 and UFF both "
                "unavailable); coordinates were embedded but NOT optimized."
            )
        elif only.optimization_status == "skipped_electronic_state":
            status = "ok"
            has_coordinates = True
            message = (
                "Seed embedded by ETKDGv3; coordinates are unoptimized. "
                "MMFF94/UFF were skipped; subsequent optimization and scientific qualification "
                "must use the declared electronic state."
            )
            diagnostics.extend(only.diagnostics)
        elif only.optimization_status == "not_required":
            status = "missing_parameters"
            has_coordinates = False
            message = (
                "Force-field optimization was disabled by the build strategy, so the structure was "
                "embedded but not optimized."
            )
        else:
            status = "ok"
            has_coordinates = True
            message = "Single component built and optimized; coordinates are ready for downstream use."

    prepared = PreparedStructure(
        status=status,
        message=message,
        has_coordinates=has_coordinates,
        components=components,
        mol=built_mol,
        atom_identities=identities,
        candidate_paths=[],
        component_paths=component_paths,
        trajectory_ids=[a.trajectory_id for a in artifacts],
        trajectory_manifest_path=trajectory_manifest,
        electronic_state=state_details,
        diagnostics=diagnostics,
    )

    prepared.assembly = assembly
    prepared.candidate_paths = assembly_paths

    if status == "ok" and has_coordinates and len(components) == 1:
        xyz_path = os.path.join(out_dir, PREPARED_XYZ_NAME)
        mol_path = os.path.join(out_dir, PREPARED_MOL_NAME)
        atomic_write_text(
            xyz_path,
            _render_xyz(
                prepared.mol, prepared.mol.GetConformer().GetId(),
                "prepared by cloudra structure_builder (per-component build)",
                identities,
            ),
        )
        atomic_write_text(mol_path, Chem.MolToMolBlock(prepared.mol))
        prepared.candidate_paths = [xyz_path, mol_path]

    return _finalize(prepared, out_dir)
```

前面的 _run_crest 在失败分支已经返回，所以没有实际执行 CREST。下面列出被堵住的真实计算路径，确认力场失败并不是 CREST 运行失败。

**如果未被前置拒绝，才将种子转换为 CREST 请求**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/conformer_search.py:1024-1044`

```python
            seed_xyz = to_xyz(prepared.mol)

            solvent_xyz = ""
            if runtype == "qcg":
                solvent_xyz = self._build_qcg_solvent(user_input, out_dir)

            # 用户批准（Task 4 门）：多碎片输入默认加 --noreftopo，只关搜索前的初始拓扑检查。
            # 单组分输入不加该选项（没有片间拓扑可变化，加了只会掩盖真实问题）。
            run = run_crest(CrestRunRequest(
                xyz_text=seed_xyz,
                output_dir=out_dir,
                charge=user_input.charge,
                multiplicity=user_input.multiplicity,
                electronic_character=user_input.electronic_character,
                timeout=user_input.timeout,
                run_label="crest" if runtype == "default" else f"crest_{runtype}",
                noreftopo=multi_fragment,
                runtype=runtype,
                solvent_xyz_text=solvent_xyz,
                nsolv=user_input.nsolv,
            ))
```

**坐标参数转换：只渲染 prepared.mol 当前构象**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/molecule.py:152-158`

```python
def to_xyz(mol, comment: str = "") -> str:
    """Render the default conformer in atom order with eight decimal places."""
    positions = mol.GetConformer().GetPositions()
    lines = [str(mol.GetNumAtoms()), comment]
    for atom, position in zip(mol.GetAtoms(), positions, strict=True):
        lines.append(f"{atom.GetSymbol():<4} {position[0]:>14.8f} {position[1]:>14.8f} {position[2]:>14.8f}")
    return "\n".join(lines) + "\n"
```

**实际命令转换：GFN 方法、输入文件、电荷、自旋与运行模式**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/crest_runner.py:225-263`

```python
def build_crest_command(request: CrestRunRequest) -> list[str]:
    """构造 CREST 命令行。

    电荷与自旋**显式**透传（``--uhf = multiplicity - 1``，与 xtb 通道口径一致），
    绝不依赖 CREST 对带电/开壳层体系的默认推断。qcg 的溶剂文件与 nsolv 是位置性要件，
    缺失即在这里 fail-loud，不留到 CREST 报错。
    """
    if request.multiplicity < 1:
        raise ValueError(f"multiplicity must be >= 1 (2S+1), got {request.multiplicity}")
    if request.electronic_character == 'open_shell' and request.multiplicity == 1:
        raise ValueError('The CREST GFN interface cannot represent a declared open-shell singlet via --uhf 0; supply a capable QM method and initial spin settings.')
    if request.constraint_text and request.runtype not in ("default", "nci"):
        raise ValueError("constraint_text is only supported for default/nci CREST searches")
    method = f"-{request.method.lstrip('-')}"
    if request.runtype == "qcg":
        if not request.solvent_xyz_text.strip():
            raise ValueError("runtype='qcg' requires solvent_xyz_text (the solvent molecule xyz)")
        if request.nsolv < 1:
            raise ValueError(f"runtype='qcg' requires nsolv >= 1, got {request.nsolv}")
        command = ["crest", "input.xyz", "--qcg", "solvent.xyz", "--nsolv", str(request.nsolv), method]
    else:
        if request.solvent_xyz_text.strip() or request.nsolv:
            raise ValueError("solvent_xyz_text/nsolv are only valid with runtype='qcg'")
        command = ["crest", "input.xyz", method]
    if request.quick and request.runtype in ("default", "nci"):
        command.append("--quick")
    command += ["--chrg", str(request.charge), "--uhf", str(request.multiplicity - 1)]
    if request.runtype == "nci":
        command.append("--nci")
    elif request.runtype in ("protonate", "deprotonate", "tautomerize"):
        command.append(f"--{request.runtype}")
    if request.noreftopo:
        # 只关初始拓扑检查；绝不同时加 -notopo（那会关掉 CREGEN 的全部拓扑检查）
        command.append("--noreftopo")
    command += list(request.extra_args)
    if request.constraint_text:
        command += ["--cinp", "constraints.inp"]
    return command

```

**实际启动点：写 input.xyz 并创建 CREST 进程**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/crest_runner.py:467-528`

```python
def run_crest(request: CrestRunRequest) -> CrestRunResult:
    """在持久运行目录里跑一次 CREST，返回分层分类后的结果。

    本函数是同步的（子进程 + 文件 IO）；异步调用方必须经 ``asyncio.to_thread`` 卸载。
    """
    command = build_crest_command(request)
    expected_atoms = _expected_atom_count(request)
    run_dir = next_run_dir(request.output_dir, RUNS_DIR_NAME, request.run_label)

    product_name = RUNTYPE_PRODUCT[request.runtype]
    input_path = os.path.join(run_dir, "input.xyz")
    command_path = os.path.join(run_dir, "command.txt")
    versions_path = os.path.join(run_dir, "versions.txt")
    stdout_path = os.path.join(run_dir, "stdout.log")
    stderr_path = os.path.join(run_dir, "stderr.log")
    conformers_path = os.path.join(run_dir, product_name)

    atomic_write_text(input_path, request.xyz_text)
    if request.constraint_text:
        atomic_write_text(os.path.join(run_dir, "constraints.inp"), request.constraint_text)
    if request.runtype == "qcg":
        atomic_write_text(os.path.join(run_dir, "solvent.xyz"), request.solvent_xyz_text)
    atomic_write_text(command_path, " ".join(command) + "\n")
    atomic_write_text(versions_path, capture_versions(("crest", "xtb"), ("Version", "version", "xTB program")))

    result = CrestRunResult(
        run_dir=run_dir,
        command=command,
        input_path=input_path,
        command_path=command_path,
        versions_path=versions_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        conformers_path=conformers_path,
    )

    if not _which("crest"):
        result.termination_reason = "executable_missing"
        result.diagnostics.append(
            "the 'crest' executable was not found on PATH; nothing was run (install CREST and "
            "retry, or use backend='rdkit')"
        )
        atomic_write_text(stdout_path, "")
        atomic_write_text(stderr_path, "")
        result.artifacts = [
            CrestArtifact(name=name, path=path, size_bytes=size)
            for name, path, size in list_artifact_files(run_dir)
        ]
        result.message = "CREST executable not found; no run was started."
        return result

    timed_out = False
    returncode: Optional[int] = None
    # 独立进程组：超时只能终止**本次运行自己**的进程树（CREST 会再起 xtb 子进程）。
    # 绝不按进程名匹配杀进程，也绝不触碰调度器/guard 拥有的计算。
    proc = subprocess.Popen(
        command, cwd=run_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=request.timeout)
        returncode = proc.returncode
```

**与真正科学验收的区别。** 此问题发生在计算前；删除的是“廉价力场不同意就禁止另一方法尝试”的启动否决，不是允许未收敛力场结果冒充极小值，也不是删除后续 CREST 的原生终止、输出完整性或 TS/IRC 证据标准。

#### 4. 已有 XYZ/MOL 也被强制清除几何、重新嵌入

**具体触发。** 用户传入已有 XYZ/MOL 几何，尤其是预组织的反应复合物、已优化构象、或 QCG 输出的微溶剂簇，想让 CREST 从它继续采样。程序无论来源都使用 embed=True，并在 ETKDG 参数中设 clearConfs=True。多组分还会重新组装。

**后果。** 实际送给 CREST 的 input.xyz 不是用户所提供的坐标。已选构象、反应物相对取向和溶剂氢键排列在计算开始前被静默替换。程序最终仍返回普通 CREST 系综成功结果，不显式提示“输入几何已被重建”。

**设计根因。** 输入归一化把“只有拓扑，需要生成三维结构”与“已经给出三维坐标，需要消费这套坐标”压成一种构建操作。统一构建器保留了原子身份，却没有把几何作为同等重要的输入。可确认的代码事实是几何被重建；此处设计问题针对从给定几何继续计算的任务，不宣称所有从文件生成新系综都必须保留同一构象。

**最简单修复。** 读取到完整有效坐标时直接作为 CREST 种子；只有无坐标的拓扑输入才生成/组装。按输入事实选择路径，不再增加让模型填写的保留几何开关。频率或极小值资格不由“坐标是否保留”推导。

##### 文件输入到实际 input.xyz 的完整相关链

**公开文件字段：XYZ/SDF/MOL 与文本输入**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/conformer_search.py:178-186`

```python
    input_path: Optional[str] = Field(
        default=None,
        description="Input structure file path (xyz/sdf/mol). xyz input infers bond orders via "
                    "rdDetermineBonds. Absolute paths are used as given; relative paths resolve "
                    "against the Agent working directory."
    )
    input_text: Optional[str] = Field(
        default=None,
        description="Structure text (xyz or mol block). If input_path is set, the file is read instead."
```

**工具入口：解析路径并将 crest 请求卸载到执行函数**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/conformer_search.py:1252-1290`

```python
        # 路径语义收口：相对路径解析到 agent 工作目录（沙箱），绝对路径保持既有权限语义。
        if user_input.input_path:
            user_input.input_path = resolve_tool_path(self, user_input.input_path)
        out_dir = self._resolve_output_dir(user_input)
        user_input.output_dir = resolve_tool_path(self, out_dir)

        if user_input.catalog_mode == "regions":
            return await asyncio.to_thread(self._run_regions, user_input, user_input.output_dir)

        if user_input.ring_order or user_input.distance_filters:
            from cloudra.tools.core.preorganization import search_guided

            try:
                guided = await asyncio.to_thread(
                    search_guided,
                    structure=self._structure_input(user_input),
                    output_dir=user_input.output_dir,
                    ring_order=user_input.ring_order,
                    distance_filters=[row.model_dump() for row in user_input.distance_filters],
                    charge=user_input.charge, multiplicity=user_input.multiplicity,
                    electronic_character=user_input.electronic_character,
                    backend=user_input.backend, mode=user_input.mode,
                    num_confs=user_input.num_confs, random_seed=user_input.random_seed,
                    rmsd_threshold=user_input.rmsd_threshold, timeout=user_input.timeout,
                )
            except ValueError as exc:
                return ConformerSearch_output_schema(is_success=False, message=f"Invalid ring_order/distance_filters: {exc}")
            return self._guided_output(guided)

        # CREST / RDKit 都是同步 CPU/子进程；必须离开 UI 事件循环，否则 TUI 假死。
        if user_input.backend == "crest":
            return await asyncio.to_thread(self._run_crest, user_input, user_input.output_dir)

        if not _RDKIT_AVAILABLE:
            return ConformerSearch_output_schema(
                is_success=False,
                message="RDKit is not installed. Install it with: pip install 'cloudra[chem]'"
            )
        return await asyncio.to_thread(self._run_rdkit, user_input, user_input.output_dir)
```

**执行入口：输入文件也强制执行 embed=True,optimize=True**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/conformer_search.py:996-1024`

```python
    def _run_crest(self, user_input: ConformerSearch_input_schema, out_dir: str, *, candidate_sink=None) -> ConformerSearch_output_schema:
        try:
            # 种子结构由共享构建器产出（embed+optimize），多组分得到组装复合物，
            # 互穿几何绝不会被喂给 CREST/xTB（issue #33 的直接病因）。
            prepared = self._prepare(user_input, out_dir, embed=True, optimize=True,candidate_sink=candidate_sink)
            if prepared.status != "ok" or not prepared.has_coordinates:
                return self._build_failure(prepared)
            if prepared.electronic_state["is_open_shell"] and user_input.multiplicity == 1:
                return ConformerSearch_output_schema(
                    is_success=False,
                    message="The current CREST interface cannot represent a declared open-shell singlet "
                    "through --uhf 0; it has no broken-symmetry or initial-spin declaration. The "
                    "unoptimized MOL/XYZ seed is available for an explicitly chosen QM method and "
                    f"spin-initialization settings. Build artifacts: {prepared.artifact_path}",
                )

            runtype = "default" if user_input.mode == "conformers" else user_input.mode
            multi_fragment = len(prepared.components) > 1
            if runtype in self._SINGLE_COMPONENT_RUNTYPES and multi_fragment:
                return ConformerSearch_output_schema(
                    is_success=False,
                    message=(
                        f"mode='{user_input.mode}' screens protonation states/tautomers of ONE "
                        f"molecule, but this input has {len(prepared.components)} components. "
                        "Run it per component, or use mode='nci'/'conformers' for the complex."
                    ),
                )

            seed_xyz = to_xyz(prepared.mol)
```

**准备转发：由输入结构生成统一 PreparationRequest**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/conformer_search.py:343-354`

```python
    def _prepare(self, user_input: ConformerSearch_input_schema, out_dir: str,
                 *, embed: bool, optimize: bool, candidate_sink=None) -> PreparedStructure:
        """调用共享构建器解析/构建结构（本工具不再自带解析与 Embed/MMFF 快捷路径）。"""
        return prepare_structure(PreparationRequest(
            structure=self._structure_input(user_input),
            output_dir=self._build_dir(out_dir),
            total_charge=user_input.charge,
            multiplicity=user_input.multiplicity,
            electronic_character=user_input.electronic_character,
            random_seed=user_input.random_seed,
            strategy=BuildStrategy(name="per_component", embed=embed, optimize=optimize),
        ),candidate_sink=candidate_sink)
```

**文件转换：读入实际内容，按扩展名确定 mol_block/xyz_text**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/conformer_search.py:311-327`

```python
    @staticmethod
    def _structure_input(user_input: ConformerSearch_input_schema) -> StructureInput:
        """把三种输入归一成构建器的声明式来源；来源无法判定即 fail-loud。"""
        if user_input.smiles:
            return StructureInput(kind="smiles", value=user_input.smiles)
        if user_input.input_path:
            if not os.path.isfile(user_input.input_path):
                raise ValueError(f"Input file does not exist: {user_input.input_path}")
            with open(user_input.input_path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
            ext = os.path.splitext(user_input.input_path)[1].lower()
            kind = "mol_block" if ext in (".sdf", ".mol", ".sd") else "xyz_text"
            return StructureInput(kind=kind, value=text)
        if user_input.input_text:
            return StructureInput(kind=_sniff_structure_text(user_input.input_text),
                                  value=user_input.input_text)
        raise ValueError("Must provide one of smiles, input_path, or input_text")
```

**结构解析：MOL/XYZ 原几何被读入 RDKit**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/structure_builder.py:326-353`

```python
def _parse_input(structure: StructureInput, total_charge: int):
    """把入口输入解析成带键级与立体化学的 RDKit Mol；失败抛 ValueError。"""
    if structure.kind == "molecule":
        return Chem.Mol(structure.value)
    if structure.kind == "smiles":
        mol = Chem.MolFromSmiles(structure.value)
        if mol is None:
            raise ValueError(f"Invalid SMILES string: {structure.value}")
        return mol

    if structure.kind == "mol_block":
        mol = Chem.MolFromMolBlock(structure.value, removeHs=False)
        if mol is None:
            raise ValueError("Could not parse the input MOL block")
        return mol

    mol = Chem.MolFromXYZBlock(structure.value)
    if mol is None:
        raise ValueError("Could not parse the input xyz text")
    try:
        rdDetermineBonds.DetermineBonds(mol, charge=total_charge)
    except Exception as exc:  # noqa: BLE001 - 统一转成显式 ValueError
        raise ValueError(
            f"Bond-order inference (rdDetermineBonds) failed for the xyz input: {exc}"
        ) from exc
    if mol.GetNumBonds() == 0 and mol.GetNumAtoms() > 1:
        raise ValueError("No chemical bonds could be inferred from the xyz input")
    return mol
```

**构建转发：将读入的分子拆成组分并送入 _build_component**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/structure_builder.py:752-818`

```python
def prepare_structure(request: PreparationRequest, *, candidate_sink=None) -> PreparedStructure:
    """把请求解析成 ``PreparedStructure``。

    所有可预期失败都返回带显式 ``status`` 的产物（不抛异常、也不返回半成品冒充成功）；
    只有"本函数无法继续"（缺 RDKit、策略名未知）才抛异常。
    """
    if not _RDKIT_AVAILABLE:
        raise RuntimeError(
            "RDKit is not installed. Install it with: pip install 'cloudra[chem]', then retry."
        )
    if request.strategy.name != "per_component":
        raise ValueError(
            f"unknown build strategy {request.strategy.name!r}; only 'per_component' has been "
            "approved (assembly sampling parameters are still awaiting user approval)"
        )
    if request.multiplicity < 1:
        raise ValueError(f"multiplicity must be >= 1 (2S+1), got {request.multiplicity}")

    out_dir = request.output_dir
    os.makedirs(out_dir, exist_ok=True)

    try:
        mol = _parse_input(request.structure, request.total_charge)
    except ValueError as exc:
        return _empty(
            "invalid_input",
            f"Could not build a structure from the request: {exc}",
            out_dir,
        )

    fragments = _fragment_atom_tuples(mol)
    if not fragments:
        return _empty(
            "invalid_input", "The input structure contains no atoms", out_dir,
        )

    state_details = electronic_state_details(
        mol, charge=request.total_charge, multiplicity=request.multiplicity,
        electronic_character=request.electronic_character,
    )
    state_issue = electronic_state_issue(
        mol, charge=request.total_charge, multiplicity=request.multiplicity,
        electronic_character=request.electronic_character,
    )
    if state_issue:
        status, message = state_issue
        return _empty(
            status, message,
            out_dir, mol,
            diagnostics=[
                f"{len(fragments)} component(s) were not built: the electronic state is unsupported"
            ],
            electronic_state=state_details,
        )

    artifacts: list[TrajectoryArtifact] = []
    components: list[BuildComponent] = []
    identities: list[AtomIdentity] = []
    component_paths: list[str] = []
    index_offset = 0

    for position, indices in enumerate(fragments):
        component_id = f"frag{position}"
        component, component_identities = _build_component(
            mol, list(indices), component_id, request, out_dir, artifacts, index_offset, candidate_sink,
            skip_force_field=state_details["requires_spin_aware_geometry"],
        )
```

**拆分转换：子分子原本保留了构象**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/structure_builder.py:374-388`

```python
def _submol_by_input_indices(mol, indices: list[int]):
    """按**给定的输入原子序号顺序**构造子分子，返回 ``(submol, {输入序号: 子分子下标})``。

    在分子副本上删除未选原子，再按请求顺序重排。由 RDKit 保留原子/键属性、
    构象和立体参考，避免逐字段重建时丢失化学信息；输入分子不变。
    """
    old_to_new = {old_index: new_index for new_index, old_index in enumerate(indices)}
    rw = Chem.RWMol(mol)
    for old_index in reversed(range(mol.GetNumAtoms())):
        if old_index not in old_to_new:
            rw.RemoveAtom(old_index)
    retained_order = {old_index: new_index for new_index, old_index in enumerate(sorted(indices))}
    submol = renumber_atoms(rw, [retained_order[index] for index in indices])
    Chem.SanitizeMol(submol)
    return submol, old_to_new
```

**加氢转换：沿用子分子的原子身份映射**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/structure_builder.py:396-423`

```python
def _add_hydrogens_with_identity(submol, component_id: str):
    """加显式氢并返回 ``(加氢后的 mol, {新氢子分子下标: (父子分子下标, 第 k 个氢)})``。

    新增氢的身份是 ``(父重原子的输入序号, 该父原子上的第 k 个氢)``——与 ``AddHs`` 之后的
    数组位置无关。落在原子上的数组下标会随拆分方式改变，不能充当跨反应映射。
    """
    n_before = submol.GetNumAtoms()
    mol_h = Chem.AddHs(submol)
    hydrogen_by_index: dict[int, tuple[int, int]] = {}
    per_parent: dict[int, list[int]] = {}
    for new_index in range(n_before, mol_h.GetNumAtoms()):
        atom = mol_h.GetAtomWithIdx(new_index)
        if atom.GetAtomicNum() != 1:
            raise ValueError(
                f"component {component_id}: atom {new_index} appended by AddHs is not hydrogen "
                f"(symbol={atom.GetSymbol()})"
            )
        neighbors = [n.GetIdx() for n in atom.GetNeighbors()]
        if len(neighbors) != 1:
            raise ValueError(
                f"component {component_id}: the added hydrogen {new_index} has "
                f"{len(neighbors)} neighbours; a stable identity needs exactly one parent"
            )
        per_parent.setdefault(neighbors[0], []).append(new_index)
    for parent_index, hydrogen_indices in per_parent.items():
        for ordinal, new_index in enumerate(sorted(hydrogen_indices), start=1):
            hydrogen_by_index[new_index] = (parent_index, ordinal)
    return mol_h, hydrogen_by_index
```

**决定性覆盖：已有构象也进入 ETKDG clearConfs=True 重新嵌入**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/structure_builder.py:560-608`

```python
def _build_component(mol, indices: list[int], component_id: str, request: PreparationRequest,
                     out_dir: str, artifacts: list[TrajectoryArtifact],
                     index_offset: int, candidate_sink=None, *, skip_force_field: bool) -> tuple[BuildComponent, list[AtomIdentity]]:
    """构建单个组分：切分 → 加氢 → （可选）嵌入 → 力场优化（含轨迹）→ 落盘。"""
    submol, old_to_new = _submol_by_input_indices(mol, indices)
    submol_atom_to_input = {new: old for old, new in old_to_new.items()}
    diagnostics: list[str] = []

    formal_charge = sum(a.GetFormalCharge() for a in submol.GetAtoms())

    mol_h, hydrogen_by_index = _add_hydrogens_with_identity(submol, component_id)
    identities = _identity_table(
        mol_h, submol_atom_to_input, hydrogen_by_index, component_id, index_offset,
    )

    component_capture=candidate_sink.for_component(identities) if candidate_sink else None
    parent=None
    single_atom = mol_h.GetNumAtoms() == 1
    embed_status: EmbedStatus = "not_required"
    optimization_status: OptimizationStatus = "not_required"
    engine = ""
    trajectory_id = ""
    final_energy: Optional[float] = None
    xyz_path = ""
    conf_id: Optional[int] = None

    if not request.strategy.embed:
        diagnostics.append(
            "coordinate embedding was not requested (strategy.embed=False); only the structural "
            "resolution (split / AddHs / identity table / charge self-check) was performed"
        )
    elif single_atom:
        # 单原子组分无需调用力场：位置即原点，没有可优化的内部自由度。
        conf = Chem.Conformer(1)
        conf.SetAtomPosition(0, (0.0, 0.0, 0.0))
        mol_h.RemoveAllConformers()
        conf_id = mol_h.AddConformer(conf, assignId=True)
        diagnostics.append(
            "single-atom component: no conformer embedding and no force field were run"
        )
        if skip_force_field:
            optimization_status = "skipped_electronic_state"
            diagnostics.append("single-atom seed: no force-field energy or optimization is claimed")
    else:
        params = AllChem.ETKDGv3()
        params.randomSeed = request.random_seed
        params.clearConfs = True
        params.pruneRmsThresh = -1.0
        embedded = AllChem.EmbedMolecule(mol_h, params)
```

**覆盖后计算与组件返回：力场优化的是新坐标，写出的组件也是新坐标**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/structure_builder.py:621-707`

```python
        else:
            embed_status = "embedded"
            conf_id = embedded
            if component_capture:
                parent=component_capture.capture(mol_h,conf_id,generator="component_ETKDGv3",seed=request.random_seed)
            if not skip_force_field:
                engine = _select_engine(mol_h) or ""
            if skip_force_field:
                optimization_status = "skipped_electronic_state"
                diagnostics.append(
                    "ETKDGv3 seed coordinates are unoptimized: the electronic-state declaration or "
                    "localized radical graph markers require avoiding MMFF94/UFF. No force-field "
                    "energy or convergence is claimed; subsequent optimization must preserve the "
                    "declared electronic state."
                )
            elif not request.strategy.optimize:
                optimization_status = "not_required"
                diagnostics.append("force-field optimization disabled by the approved build strategy")
            elif not engine:
                if component_capture:
                    from cloudra.tools.core.conformer_catalog import Qualification
                    component_capture.capture(mol_h,conf_id,generator="component_force_field_unavailable",parent_id=parent.candidate_id,state="failed",qualification=Qualification(status="rejected",reasons=["missing_parameters"]))
                optimization_status = "missing_parameters"
                diagnostics.append(
                    "no force field covers every atom of this component (MMFF94 and UFF both "
                    "unavailable); coordinates are embedded but NOT optimized"
                )
            else:
                record = _optimize_component(
                    mol_h, conf_id, engine, request.random_seed, request.strategy,
                    component_id, attempt=1, out_dir=out_dir,
                )
                artifacts.append(trajectory_artifact(record))
                trajectory_id = record.trajectory_id
                final_energy = record.final_frame.energy
                optimization_status = record.status
                if component_capture:
                    from cloudra.tools.core.conformer_catalog import EnergyObservation, Qualification
                    energies=[]
                    if final_energy is not None:
                        energies=[EnergyObservation(value=final_energy,unit='kcal/mol',method_fingerprint=engine,
                            species_key=parent.species_key,charge=formal_charge,multiplicity=request.multiplicity,
                            convergence='converged' if record.status=='converged' else 'unconverged',artifact_ref=record.trajectory_id)]
                    component_capture.capture(mol_h,conf_id,generator='component_'+engine,parent_id=parent.candidate_id,
                        state='optimized' if record.status=='converged' else 'failed',energies=energies,
                        qualification=Qualification(status='unknown' if record.status=='converged' else 'rejected',
                            reasons=[] if record.status=='converged' else [record.status],evidence_refs=[record.trajectory_id]))
                if record.status == "not_converged":
                    gradient = record.final_frame.max_gradient
                    gradient_text = "n/a" if gradient is None else f"{gradient:.6g}"
                    diagnostics.append(
                        f"force-field optimization did not converge within "
                        f"{request.strategy.max_optimization_steps} iterations "
                        f"(max gradient {gradient_text})"
                    )
                elif record.status == "failed":
                    diagnostics.append(f"force-field optimization raised: {record.failure}")

    mol_path = os.path.join(out_dir, f"component_{component_id}.mol")
    atomic_write_text(
        mol_path,
        Chem.MolToMolBlock(mol_h, confId=conf_id) if conf_id is not None
        else Chem.MolToMolBlock(mol_h),
    )
    if conf_id is not None:
        xyz_path = os.path.join(out_dir, f"component_{component_id}.xyz")
        atomic_write_text(
            xyz_path,
            _render_xyz(
                mol_h, conf_id, f"component {component_id} (per-component build)", identities,
            ),
        )

    component = BuildComponent(
        component_id=component_id,
        mol=copy_conformer(mol_h, conf_id) if conf_id is not None else mol_h,
        source_atom_indices=list(indices),
        embed_status=embed_status,
        optimization_status=optimization_status,
        engine=engine,
        trajectory_id=trajectory_id,
        final_energy=final_energy,
        mol_path=mol_path,
        xyz_path=xyz_path,
        diagnostics=diagnostics,
    )
    return component, identities
```

**组分合并：新构建组件组成 built_mol**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/structure_builder.py:825-868`

```python
        components.append(component)
        identities.extend(component_identities)
        component_paths.append(component.mol_path)
        index_offset += component.atom_count

    built_mol = Chem.Mol(components[0].mol)
    for component in components[1:]:
        built_mol = Chem.CombineMols(built_mol, component.mol)

    trajectory_manifest = write_trajectory_manifest(out_dir, artifacts) if artifacts else ""

    atom_count = len(identities)
    invalid_pairs = [
        (left, right) for left, right in request.strategy.reaction_center
        if not (0 <= left < atom_count and 0 <= right < atom_count) or left == right
    ]
    # A reaction center is consumed by this builder only when it assembles multiple
    # embedded fragments. Single-component reaction paths check it after endpoint mapping.
    if invalid_pairs and len(components) > 1 and request.strategy.embed:
        numbering = ", ".join(f"{atom.index}={atom.symbol}" for atom in identities)
        return _finalize(
            PreparedStructure(
                status="invalid_reaction_center",
                message=(
                    f"reaction_center pair(s) {invalid_pairs} are invalid for the built structure "
                    f"with {atom_count} atoms. Indices are 0-based in the full output atom order, "
                    f"including hydrogens; valid indices are 0..{atom_count - 1}, and a pair must "
                    "name two different atoms."
                ),
                components=components,
                mol=built_mol,
                atom_identities=identities,
                component_paths=component_paths,
                trajectory_ids=[artifact.trajectory_id for artifact in artifacts],
                trajectory_manifest_path=trajectory_manifest,
                electronic_state=state_details,
                diagnostics=[f"built atoms (0-based): {numbering}"],
            ),
            out_dir,
        )

    diagnostics: list[str] = []
    assembly: Optional[AssemblyResult] = None
    assembly_paths: list[str] = []
```

**多组分分支：不是保留原输入相对位置，而是重新 assemble 生成候选**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/structure_builder.py:865-941`

```python

    diagnostics: list[str] = []
    assembly: Optional[AssemblyResult] = None
    assembly_paths: list[str] = []
    if len(components) > 1 and not request.strategy.embed:
        # 组装的对象是**已嵌入的**组分坐标（刚性放置要冻结片内几何），因此 embed=False
        # 只做结构解析的调用方拿不到复合物候选；明确报出原因，不做隐式补算。
        status: BuildStatus = "assembly_failed"
        has_coordinates = False
        message = (
            f"{len(components)} connected components detected, but the build strategy requested "
            "embed=False (structure resolution only), so no component has 3D coordinates to "
            "assemble. Request embed=True to get complex candidates."
        )
        diagnostics.append(
            "assembly needs embedded component coordinates; the strategy disabled embedding"
        )
    elif len(components) > 1 and state_details["requires_spin_aware_geometry"]:
        status = "unsupported_spin"
        has_coordinates = False
        message = (
            "Multicomponent force-field assembly cannot represent the electronic-state declaration "
            "or radical-marked graph. Component coordinates are unoptimized seeds; no complex "
            "candidate was produced. Supply an explicit MOL "
            "graph plus XYZ complex geometry through the file conformer input."
        )
        diagnostics.append("MMFF94/UFF complex assembly was not run for this state declaration or graph representation")
    elif len(components) > 1:
        # 组装前闸门：任一组分坐标不可用（嵌入失败/优化未收敛/缺参数）就不进 assemble——
        # 把占位坐标或未收敛几何拼成"复合物"等于交付无意义结构。
        unusable = [component for component in components if not _component_is_usable(component)]
        if unusable:
            details = "; ".join(
                f"{component.component_id} (embed={component.embed_status}, "
                f"optimization={component.optimization_status})"
                for component in unusable
            )
            status = "optimization_failed"
            has_coordinates = False
            message = (
                f"{len(components)} connected components detected, but component(s) "
                f"{details} have no usable coordinates, so assembly was NOT run: a complex "
                "assembled from placeholder or unconverged fragment geometries would be "
                "meaningless. Fix the component builds first."
            )
            diagnostics.append(
                f"assembly refused: {len(unusable)} of {len(components)} component(s) failed the "
                "usability gate (embedded + converged, or single-atom)"
            )
        else:
            # 组装（用户批准的方案 A）：刚性放置采样 + 碰撞剔除 + 力场弛豫；反应中心给出时按
            # 反应模式做约束预优化并条件释放约束。组装参数就是 BuildStrategy.assembly 的默认值。
            assembly = assemble(
                components=[(component.mol, component.mol.GetConformer().GetId()) for component in components],
                output_dir=os.path.join(out_dir, "assembly"),
                parameters=request.strategy.assembly,
                reaction_center=list(request.strategy.reaction_center) or None,
                guided_windows=list(request.strategy.guided_windows) or None,
                seed=request.random_seed, candidate_sink=candidate_sink,
            )
            diagnostics.extend(assembly.diagnostics)
            if assembly.status == "ok":
                status = "ok"
                has_coordinates = True
                built_mol = assembly.candidates[0].mol
                assembly_paths = list(assembly.candidate_paths)
                message = (
                    f"{len(components)} connected components assembled ({assembly.mode} mode): "
                    f"{len(assembly.candidates)} complex candidate(s). {assembly.message}"
                )
            else:
                status = "assembly_failed"
                has_coordinates = False
                message = (
                    f"{len(components)} connected components detected and assembled, but no usable complex "
                    f"candidate was produced (assembly status: {assembly.status}). {assembly.message}"
                )
```

**单组分分支与总结果返回：最终 mol/candidate_paths 来自新建坐标**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/structure_builder.py:950-1031`

```python
        only = components[0]
        if only.embed_status == "failed":
            status = "optimization_failed"
            has_coordinates = False
            message = (
                f"Conformer embedding failed for component {only.component_id}; the "
                "recorded coordinates are placeholders and must not be used as a starting geometry."
            )
        elif only.single_atom:
            status = "ok"
            has_coordinates = True
            message = "Single-atom structure; its coordinate is the origin (no force field needed)."
        elif only.optimization_status in _NON_USABLE_OPTIMIZATION:
            status = "optimization_failed"
            has_coordinates = False
            message = (
                f"Component {only.component_id} did not converge under "
                f"{only.engine or 'any force field'} (or the optimization raised); "
                "its embedded coordinates remain an unqualified seed for a separate quantum-chemistry "
                "optimization, not a force-field minimum. See the recorded trajectory for the last state."
            )
        elif only.optimization_status == "missing_parameters":
            status = "missing_parameters"
            has_coordinates = False
            message = (
                "No force field covers every atom of this structure (MMFF94 and UFF both "
                "unavailable); coordinates were embedded but NOT optimized."
            )
        elif only.optimization_status == "skipped_electronic_state":
            status = "ok"
            has_coordinates = True
            message = (
                "Seed embedded by ETKDGv3; coordinates are unoptimized. "
                "MMFF94/UFF were skipped; subsequent optimization and scientific qualification "
                "must use the declared electronic state."
            )
            diagnostics.extend(only.diagnostics)
        elif only.optimization_status == "not_required":
            status = "missing_parameters"
            has_coordinates = False
            message = (
                "Force-field optimization was disabled by the build strategy, so the structure was "
                "embedded but not optimized."
            )
        else:
            status = "ok"
            has_coordinates = True
            message = "Single component built and optimized; coordinates are ready for downstream use."

    prepared = PreparedStructure(
        status=status,
        message=message,
        has_coordinates=has_coordinates,
        components=components,
        mol=built_mol,
        atom_identities=identities,
        candidate_paths=[],
        component_paths=component_paths,
        trajectory_ids=[a.trajectory_id for a in artifacts],
        trajectory_manifest_path=trajectory_manifest,
        electronic_state=state_details,
        diagnostics=diagnostics,
    )

    prepared.assembly = assembly
    prepared.candidate_paths = assembly_paths

    if status == "ok" and has_coordinates and len(components) == 1:
        xyz_path = os.path.join(out_dir, PREPARED_XYZ_NAME)
        mol_path = os.path.join(out_dir, PREPARED_MOL_NAME)
        atomic_write_text(
            xyz_path,
            _render_xyz(
                prepared.mol, prepared.mol.GetConformer().GetId(),
                "prepared by cloudra structure_builder (per-component build)",
                identities,
            ),
        )
        atomic_write_text(mol_path, Chem.MolToMolBlock(prepared.mol))
        prepared.candidate_paths = [xyz_path, mol_path]

    return _finalize(prepared, out_dir)
```

**向实际计算转发：从 prepared.mol 生成 seed_xyz，而不是原文件坐标**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/conformer_search.py:1024-1044`

```python
            seed_xyz = to_xyz(prepared.mol)

            solvent_xyz = ""
            if runtype == "qcg":
                solvent_xyz = self._build_qcg_solvent(user_input, out_dir)

            # 用户批准（Task 4 门）：多碎片输入默认加 --noreftopo，只关搜索前的初始拓扑检查。
            # 单组分输入不加该选项（没有片间拓扑可变化，加了只会掩盖真实问题）。
            run = run_crest(CrestRunRequest(
                xyz_text=seed_xyz,
                output_dir=out_dir,
                charge=user_input.charge,
                multiplicity=user_input.multiplicity,
                electronic_character=user_input.electronic_character,
                timeout=user_input.timeout,
                run_label="crest" if runtype == "default" else f"crest_{runtype}",
                noreftopo=multi_fragment,
                runtype=runtype,
                solvent_xyz_text=solvent_xyz,
                nsolv=user_input.nsolv,
            ))
```

**坐标参数转换：只渲染 prepared.mol 当前构象**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/molecule.py:152-158`

```python
def to_xyz(mol, comment: str = "") -> str:
    """Render the default conformer in atom order with eight decimal places."""
    positions = mol.GetConformer().GetPositions()
    lines = [str(mol.GetNumAtoms()), comment]
    for atom, position in zip(mol.GetAtoms(), positions, strict=True):
        lines.append(f"{atom.GetSymbol():<4} {position[0]:>14.8f} {position[1]:>14.8f} {position[2]:>14.8f}")
    return "\n".join(lines) + "\n"
```

**运行参数转换：CREST 使用新生成的 input.xyz**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/crest_runner.py:225-263`

```python
def build_crest_command(request: CrestRunRequest) -> list[str]:
    """构造 CREST 命令行。

    电荷与自旋**显式**透传（``--uhf = multiplicity - 1``，与 xtb 通道口径一致），
    绝不依赖 CREST 对带电/开壳层体系的默认推断。qcg 的溶剂文件与 nsolv 是位置性要件，
    缺失即在这里 fail-loud，不留到 CREST 报错。
    """
    if request.multiplicity < 1:
        raise ValueError(f"multiplicity must be >= 1 (2S+1), got {request.multiplicity}")
    if request.electronic_character == 'open_shell' and request.multiplicity == 1:
        raise ValueError('The CREST GFN interface cannot represent a declared open-shell singlet via --uhf 0; supply a capable QM method and initial spin settings.')
    if request.constraint_text and request.runtype not in ("default", "nci"):
        raise ValueError("constraint_text is only supported for default/nci CREST searches")
    method = f"-{request.method.lstrip('-')}"
    if request.runtype == "qcg":
        if not request.solvent_xyz_text.strip():
            raise ValueError("runtype='qcg' requires solvent_xyz_text (the solvent molecule xyz)")
        if request.nsolv < 1:
            raise ValueError(f"runtype='qcg' requires nsolv >= 1, got {request.nsolv}")
        command = ["crest", "input.xyz", "--qcg", "solvent.xyz", "--nsolv", str(request.nsolv), method]
    else:
        if request.solvent_xyz_text.strip() or request.nsolv:
            raise ValueError("solvent_xyz_text/nsolv are only valid with runtype='qcg'")
        command = ["crest", "input.xyz", method]
    if request.quick and request.runtype in ("default", "nci"):
        command.append("--quick")
    command += ["--chrg", str(request.charge), "--uhf", str(request.multiplicity - 1)]
    if request.runtype == "nci":
        command.append("--nci")
    elif request.runtype in ("protonate", "deprotonate", "tautomerize"):
        command.append(f"--{request.runtype}")
    if request.noreftopo:
        # 只关初始拓扑检查；绝不同时加 -notopo（那会关掉 CREGEN 的全部拓扑检查）
        command.append("--noreftopo")
    command += list(request.extra_args)
    if request.constraint_text:
        command += ["--cinp", "constraints.inp"]
    return command

```

**实际输入写入与启动：request.xyz_text 落为 input.xyz，再创建进程**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/crest_runner.py:467-528`

```python
def run_crest(request: CrestRunRequest) -> CrestRunResult:
    """在持久运行目录里跑一次 CREST，返回分层分类后的结果。

    本函数是同步的（子进程 + 文件 IO）；异步调用方必须经 ``asyncio.to_thread`` 卸载。
    """
    command = build_crest_command(request)
    expected_atoms = _expected_atom_count(request)
    run_dir = next_run_dir(request.output_dir, RUNS_DIR_NAME, request.run_label)

    product_name = RUNTYPE_PRODUCT[request.runtype]
    input_path = os.path.join(run_dir, "input.xyz")
    command_path = os.path.join(run_dir, "command.txt")
    versions_path = os.path.join(run_dir, "versions.txt")
    stdout_path = os.path.join(run_dir, "stdout.log")
    stderr_path = os.path.join(run_dir, "stderr.log")
    conformers_path = os.path.join(run_dir, product_name)

    atomic_write_text(input_path, request.xyz_text)
    if request.constraint_text:
        atomic_write_text(os.path.join(run_dir, "constraints.inp"), request.constraint_text)
    if request.runtype == "qcg":
        atomic_write_text(os.path.join(run_dir, "solvent.xyz"), request.solvent_xyz_text)
    atomic_write_text(command_path, " ".join(command) + "\n")
    atomic_write_text(versions_path, capture_versions(("crest", "xtb"), ("Version", "version", "xTB program")))

    result = CrestRunResult(
        run_dir=run_dir,
        command=command,
        input_path=input_path,
        command_path=command_path,
        versions_path=versions_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        conformers_path=conformers_path,
    )

    if not _which("crest"):
        result.termination_reason = "executable_missing"
        result.diagnostics.append(
            "the 'crest' executable was not found on PATH; nothing was run (install CREST and "
            "retry, or use backend='rdkit')"
        )
        atomic_write_text(stdout_path, "")
        atomic_write_text(stderr_path, "")
        result.artifacts = [
            CrestArtifact(name=name, path=path, size_bytes=size)
            for name, path, size in list_artifact_files(run_dir)
        ]
        result.message = "CREST executable not found; no run was started."
        return result

    timed_out = False
    returncode: Optional[int] = None
    # 独立进程组：超时只能终止**本次运行自己**的进程树（CREST 会再起 xtb 子进程）。
    # 绝不按进程名匹配杀进程，也绝不触碰调度器/guard 拥有的计算。
    proc = subprocess.Popen(
        command, cwd=run_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=request.timeout)
        returncode = proc.returncode
```

**CREST 结果返回：原生终止与产物检查后返回帧，不恢复原输入几何**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/crest_runner.py:539-648`

```python
    atomic_write_text(stdout_path, stdout or "")
    atomic_write_text(stderr_path, stderr or "")
    result.returncode = returncode
    result.artifacts = [
        CrestArtifact(name=name, path=path, size_bytes=size)
        for name, path, size in list_artifact_files(run_dir)
    ]
    # 初始优化一旦跑过，CREST 就把逐帧轨迹留在 xtbopt.log；末帧即它真正拿到的几何。
    # 这里记录"输入 → 优化末帧"的连接表差异（片内/片间）供人判断，绝不代替人判断。
    # 只有 default/nci 的产物与输入同原子集合，对比才有意义；protonate/tautomerize/qcg
    # 的产物刻意改变原子数或连接性，跳过对比（xtbopt.log 在这些模式下也未必存在）。
    if request.runtype in ("default", "nci"):
        result.topology_change = _topology_change_report(request, run_dir, input_path)

    if request.noreftopo:
        result.diagnostics.append(
            "--noreftopo was used: the INITIAL topology check before the search was disabled, so this "
            "run would NOT have stopped on an initial-topology change. CREGEN's in-search topology "
            "checks are untouched (-notopo was deliberately NOT passed). Any topology change is still "
            "recorded in topology_change; treat the ensemble accordingly."
        )
    lines = (stdout or "").splitlines()
    # Fortran ERROR STOP（如 QCG 缺 xtb-IFF）写 stderr 而非 stdout，两路都要扫。
    scan_lines = lines + (stderr or "").splitlines()
    hits, marker, stage = _scan_markers(scan_lines)
    result.evidence = hits
    result.stage = stage

    if timed_out:
        result.termination_reason = "timeout"
        result.stage = stage if stage != "not_started" else "search"
        result.message = (
            f"CREST timed out after {request.timeout}s (returncode={returncode}). Increase timeout "
            f"or use backend='rdkit'. Full log: {stdout_path}"
        )
        return result

    if os.path.isfile(os.path.join(run_dir, SENTINEL_NOT_CONVERGED)):
        result.diagnostics.append(
            f"CREST wrote its '{SENTINEL_NOT_CONVERGED}' sentinel in the run directory "
            "(corroborates an optimization failure; the log marker is the primary evidence)"
        )

    if returncode != 0:
        result.termination_reason = marker if marker and marker != "completed" else "unknown_failure"
        if result.termination_reason == "qcg_xtbiff_missing":
            result.diagnostics.append(
                "QCG requires the external xtb-IFF program, which CREST did not find "
                "(https://github.com/grimme-lab/xtbiff); install it or use a non-QCG runtype"
            )
        if result.termination_reason == "engine_crashed":
            result.diagnostics.append(
                "the CREST process was killed by a signal (see the evidence line); this is an "
                "engine-level crash, not a refused or unconverged calculation. Note: on "
                "conda-forge macOS arm64 builds, CREST's QCG GFN-FF preoptimization path is "
                "known to abort (verified 2026-09-21); the default gfn2 grow path works"
            )
        if result.termination_reason == "unknown_failure":
            tail = "\n".join(lines[-15:]) if lines else (stderr or "")[-2000:]
            result.diagnostics.append(
                "CREST failed with no recognised marker; raw log tail follows (no cause is guessed)"
            )
            result.diagnostics.append(tail)
        if os.path.isfile(conformers_path):
            result.diagnostics.append(
                f"a partial {product_name} exists in the run directory; it is kept as evidence "
                "but NOT used, because the process did not exit successfully"
            )
        result.message = (
            f"CREST failed ({result.termination_reason}, stage={result.stage}, "
            f"returncode={returncode}). Full log: {stdout_path}"
        )
        return result

    # returncode == 0：仍要确认正常结束标记 + 产物完整性，"产物在"不构成成功判据。
    if marker != "completed":
        result.termination_reason = "unknown_failure"
        result.diagnostics.append(
            "CREST exited 0 but never printed its normal-termination marker "
            f"({MARKER_NORMAL_TERMINATION!r}); refusing to treat the exit code alone as success"
        )
        result.message = f"CREST did not report normal termination. Full log: {stdout_path}"
        return result

    if request.runtype == "qcg":
        conformers, problem = _parse_qcg_cluster(run_dir, expected_atoms)
    else:
        conformers, problem = _parse_conformers(conformers_path, expected_atoms)
    result.stage = "artifact_check"
    if problem is not None:
        result.termination_reason = "incomplete_artifacts"
        result.diagnostics.append(
            f"{product_name} is unusable: {problem} (the file is kept in the run directory)"
        )
        result.message = (
            f"CREST reported normal termination but its {product_name} output is unusable "
            f"({problem}). Full log: {stdout_path}"
        )
        return result

    result.termination_reason = "completed"
    result.stage = "done"
    result.conformers = conformers
    result.conformer_count = len(conformers)
    result.scientific_success = True
    result.message = (
        f"CREST completed (runtype={request.runtype}): {len(conformers)} structures in "
        f"{product_name}. Run directory: {run_dir}"
    )
    return result
```

**返回适配：接收 CREST 帧、筛选、计算展示数据并保存系综**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/conformer_search.py:1045-1161`

```python
            frames = run.conformers
            if candidate_sink:
                from cloudra.tools.core.conformer_catalog import EnergyObservation
                from cloudra.tools.core.preorganization import load_resolved_graph
                graph=load_resolved_graph(prepared)
                source=run.conformers_path or run.stdout_path or str(os.path.join(run.run_dir,'crest_conformers.xyz'))
                for frame in frames:
                    symbols=frame.symbols or prepared.symbols
                    params={'source_artifact':source,'frame_index':frame.frame_index,'upstream_internal_deleted_choices_unavailable':True}
                    if symbols==[a.GetSymbol() for a in graph.GetAtoms()]:
                        conf=Chem.Conformer(graph.GetNumAtoms())
                        for i,position in enumerate(frame.positions):
                            conf.SetAtomPosition(i,position)
                        graph.RemoveAllConformers()
                        cid=graph.AddConformer(conf,assignId=True)
                        raw=candidate_sink.capture(graph,cid,generator='CREST_returned_frame',parameters=params)
                        # Energy is observed, while geometry optimization evidence
                        # for each returned frame remains unspecified by this adapter.
                        observation=EnergyObservation(value=frame.energy_eh,unit='Ha',method_fingerprint='CREST/returned_energy',
                            species_key=raw.species_key,charge=user_input.charge,multiplicity=user_input.multiplicity,
                            convergence='unknown',artifact_ref=source)
                        candidate_sink.capture(graph,cid,generator='CREST_returned_energy',parent_id=raw.candidate_id,
                            parameters=params,energies=[observation])
                    else:
                        candidate_sink.capture_unresolved_frame(symbols,frame.positions,generator='CREST_returned_frame',
                            parameters=params,energy_hartree=frame.energy_eh)
            if not run.scientific_success:
                details = " | ".join(run.diagnostics) if run.diagnostics else ""
                return ConformerSearch_output_schema(
                    is_success=False,
                    message=(
                        f"CREST backend (mode='{user_input.mode}') did not produce a usable ensemble "
                        f"(termination={run.termination_reason}, stage={run.stage}, "
                        f"returncode={run.returncode}). {run.message}"
                        + (f" Diagnostics: {details}" if details else "")
                        + " A failed or partial run never enters the conformer ranking."
                    ),
                )

            natoms = len(frames[0].positions)
            self._check_filters(user_input, natoms)

            e_min = min(f.energy_eh for f in frames)
            counts = {
                "generated": len(frames),
                "optimized": len(frames),
            }
            frame_rows = []
            for f in frames:
                rel_kcal = (f.energy_eh - e_min) * _EH_TO_KCAL
                import numpy as np
                pos = np.asarray(f.positions, dtype=float)
                frame_rows.append({
                    "frame_id": f.frame_index,
                    "rel_energy_kcal": rel_kcal,
                    "positions": pos,
                    "passes_filters": (self._filter_pass(pos, user_input.distance_filters)
                                       if user_input.distance_filters else True),
                    "boltzmann_pct": 0.0,
                    "rmsd_to_conf0": 0.0,
                })
            rel_by_id = {row["frame_id"]: row["rel_energy_kcal"] for row in frame_rows}
            passes_by_id = {row["frame_id"]: row["passes_filters"] for row in frame_rows}
            within_window = [
                row["frame_id"] for row in frame_rows
                if row["rel_energy_kcal"] <= user_input.energy_window_kcal
            ]
            counts["within_window"] = len(within_window)
            selected_ids = _select_energy_window_candidates(
                [row["frame_id"] for row in frame_rows],
                rel_by_id,
                passes_by_id,
                user_input.energy_window_kcal,
                bool(user_input.distance_filters),
            )
            selected_set = set(selected_ids)
            kept = [row for row in frame_rows if row["frame_id"] in selected_set]
            kept.sort(key=lambda k: k["rel_energy_kcal"])
            for new_id, k in enumerate(kept):
                k["conf_id"] = new_id
            counts["clusters"] = len(kept)
            counts["reactive_rescued"] = sum(
                1 for row in kept
                if row["passes_filters"] and row["rel_energy_kcal"] > user_input.energy_window_kcal
            )
            if not kept:
                return ConformerSearch_output_schema(is_success=False, message="No conformers within the energy window; aborting.")

            if user_input.mode in ("conformers", "nci"):
                from cloudra.tools.core.preorganization import load_resolved_graph
                graph = load_resolved_graph(prepared)
                for candidate in kept:
                    if len(candidate["positions"]) == graph.GetNumAtoms():
                        candidate["ring_shapes"] = describe_structure_rings(graph, candidate["positions"])
            ref_pos = kept[0]["positions"]
            for k in kept:
                k["rmsd_to_conf0"] = _kabsch_rmsd(k["positions"], ref_pos)

            # 拷贝系综到 output_dir（多帧 xyz，注释行带 kcal/mol 相对能量）
            # 元素序列以产物帧为准：protonate/qcg 等模式的产物原子集合与输入不同。
            symbols = frames[0].symbols if frames[0].symbols else prepared.symbols
            xyz_path = os.path.join(out_dir, "confs.xyz")
            chunks = []
            for k in kept:
                lines = [str(natoms), f"conf_id={k['conf_id']} rel_energy_kcal={k['rel_energy_kcal']:.4f}"]
                for sym, p in zip(symbols, k["positions"]):
                    lines.append(f"{sym:<3} {p[0]:>14.6f} {p[1]:>14.6f} {p[2]:>14.6f}")
                chunks.append("\n".join(lines) + "\n")
            atomic_write_text(xyz_path, "".join(chunks))

            extra = (
                "Backend: CREST (GFN2-xTB, --quick). The ensemble was deduplicated by CREST; "
                "no further RMSD clustering was applied. "
                f"CREST run directory (persistent): {run.run_dir}"
            )
            if prepared.electronic_state["requires_spin_aware_geometry"]:
                extra += " The input was an unoptimized ETKDG seed; MMFF94/UFF were skipped for this declared state or graph representation."
```

**工具结果转发：运行模式说明后交给 _finalize，异常返回失败**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/conformer_search.py:1162-1203`

```python
            if runtype == "nci":
                extra = (
                    "Backend: CREST --nci (GFN2-xTB, ellipsoid wall potential): the ensemble samples "
                    "NON-COVALENT arrangements of the input complex — hydrogen-bond networks and aggregate "
                    "geometries — not covalent conformers of a single molecule. "
                    f"CREST run directory (persistent): {run.run_dir}"
                )
            elif runtype == "qcg":
                extra = (
                    f"Backend: CREST --qcg (quantum cluster growth): {user_input.nsolv} explicit "
                    f"{user_input.solvent_smiles} molecule(s) were grown around the solute; the product "
                    "is the grown micro-solvated cluster geometry (solute + solvent shell), NOT a "
                    "bare-solute conformer, and its energy is the GFN-level cluster electronic energy "
                    f"from grow/qcg_energy.dat. To sample alternative shell arrangements, run "
                    f"mode='nci' on this cluster. CREST run directory (persistent): {run.run_dir}"
                )
            elif runtype in self._SINGLE_COMPONENT_RUNTYPES:
                extra = (
                    f"Backend: CREST --{runtype} (automated {'protomer' if runtype != 'tautomerize' else 'tautomer'} "
                    "screening). WARNING: the entries are DIFFERENT CHEMICAL SPECIES (protonation-site or "
                    "tautomer variants), not conformers of one connectivity, and the automated screening may "
                    "include chemically unreasonable pseudo-structures — review EVERY structure chemically "
                    "(protonation site, valence, charge) before using it for any follow-up calculation. "
                    "Relative energies are GFN2-xTB electronic energies of these distinct species. "
                    f"CREST run directory (persistent): {run.run_dir}"
                )
            if multi_fragment:
                extra += (
                    " NOTE: this input has multiple components, so --noreftopo was passed: the initial "
                    "topology check before the search was disabled (CREGEN's in-search topology checks "
                    "were NOT disabled). Any topology change is recorded in the run result's "
                    "topology_change field."
                )
            if counts["reactive_rescued"]:
                extra += (
                    f"{counts['reactive_rescued']} lowest-energy reactive conformer(s) outside the energy window were "
                    "additionally kept to avoid losing reactive conformers in pre-screening; their relative energies still use the global minimum as zero."
                )
            return self._finalize(user_input, kept, counts, xyz_path, extra_message=extra)

        except Exception as e:
            return ConformerSearch_output_schema(is_success=False, message=f"CREST backend failed: {e}")
```

**最终返回：ConformerSearch_output_schema 输出系综路径及成功状态**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Chemtool/conformer_search.py:421-496`

```python
    @staticmethod
    def _boltzmann(rel_energies_kcal: list[float], temperature: float) -> list[float]:
        import numpy as np

        e = np.asarray(rel_energies_kcal, dtype=float)
        w = np.exp(-e / (_KB_KCAL * temperature))
        w = w / w.sum()
        return [float(x * 100.0) for x in w]

    @staticmethod
    def _render_table(rows: list[dict], has_filters: bool) -> str:
        head = f"{'conf_id':>7} {'rel E (kcal/mol)':>16} {'Boltzmann %':>11} {'RMSD to conf0 (Å)':>18}"
        if has_filters:
            head += f" {'pass_filters':>12}"
        lines = [head, "-" * len(head)]
        for r in rows[:10]:
            line = (f"{r['conf_id']:>7} {r['rel_energy_kcal']:>16.3f} "
                    f"{r['boltzmann_pct']:>11.1f} {r['rmsd_to_conf0']:>18.3f}")
            if has_filters:
                line += f" {str(r['passes_filters']):>12}"
            lines.append(line)
        return "\n".join(lines)

    def _finalize(self, user_input: ConformerSearch_input_schema,
                  kept: list[dict], counts: dict, ensemble_path: str,
                  extra_message: str = "") -> ConformerSearch_output_schema:
        """kept：聚类后按能量排序的构象 dict（含 rel_energy_kcal/rmsd/passes_filters）。计算布居并渲染输出。"""
        pops = self._boltzmann([k["rel_energy_kcal"] for k in kept], user_input.temperature)
        for k, p in zip(kept, pops):
            k["boltzmann_pct"] = round(p, 1)

        n_pass = sum(1 for k in kept if k["passes_filters"])
        counts.setdefault("clusters", len(kept))
        counts["retained"] = len(kept)
        counts["passing_filters"] = n_pass

        conformers = [
            {
                "conf_id": k["conf_id"],
                "rel_energy_kcal": round(k["rel_energy_kcal"], 3),
                "boltzmann_pct": k["boltzmann_pct"],
                "rmsd_to_conf0": round(k["rmsd_to_conf0"], 3),
                "passes_filters": k["passes_filters"],
                "rings": ring_summaries(k.get("ring_shapes", [])),
            }
            for k in kept
        ]
        if any(k.get("ring_shapes") for k in kept):
            import json
            path = os.path.join(user_input.output_dir, "ring_shapes.json")
            atomic_write_text(path, json.dumps([
                {"conf_id": k["conf_id"], "rings": k.get("ring_shapes", [])} for k in kept
            ], indent=2) + "\n")
            extra_message += f" Ring geometry descriptors (0-based atoms): {path}."
        table = self._render_table(conformers, bool(user_input.distance_filters))

        message = (
            f"Conformer search complete: {len(kept)} conformers kept after clustering; ensemble written to {ensemble_path}. "
            "Coordinates are not included in context; use the file at ensemble_path for follow-up calculations."
        )
        if user_input.distance_filters:
            message += (
                f"\n{n_pass} conformers pass the distance filters and are reactive conformer candidates; "
                "TS guesses from these conformers are recommended."
            )
        if extra_message:
            message += f"\n{extra_message}"

        return ConformerSearch_output_schema(
            is_success=True,
            table=table,
            conformers=conformers,
            counts=counts,
            ensemble_path=ensemble_path,
            message=message,
        )
```

上述 QCG 结果说明还建议将产物簇再次交给 nci，源码见上一段 1170–1176 行。因此“保留已有几何继续采样”不是只存在于假想使用场景；当前产品文案本身就推荐这条工作流，但后续统一建模会重新生成初始簇。

#### 不应与上述问题一起删除的限制，以及未升级为确诊的问题

- 本地 guard/adopt 以 calc/guard flock 保活。锁持有者仍在运行，就不因观察进程异常而认定计算已死。这是真实执行所有权保护，不是科学近似门槛。
- 队列指定节点已从注册表消失时保持排队，不转投其他机器；注册容量与 cancel_requested 的资源保留应继续存在。
- 虚频数量、IRC 端点关联、真实原子身份和不可变计算证据是科学验收，不能因为工具总成败字段设计差就一并放宽。
- 本文第 3 项不推翻“未收敛的 MMFF/UFF 不能冒充力场极小值”；问题是将该资格扩大成另一种方法启动前的绝对许可。
- 本文第 2 项不推翻“调度结束不等于科学收敛”；它指出缺失原生引擎正常终止证据时仍把计算账本记成功。
- preorganization.py 中 ring_order 缺失的距离窗会取默认 reaction_center_window，随后作为输出硬过滤。这是值得单独确认的科学设计选择，但当前接口明确把它定位为受约束种子，而且没证明它否决已成立的 IRC 端点证据，因此本次没有将它列入四项已确诊问题。
- 发现同步本地提交的容量查询与插入分开执行，但本次没有扩展到并发边界审查，也未将它算入上述科学/生命周期设计问题。
- 没有针对 TS mode、ORCA parser、DAG/Benchmark 再做重复结论；这些由主审计独立负责。

**排除项证据：本地 guard 存活续租，guard 退出则拉起 adopt，不杀计算**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/scheduler/daemon.py:302-342`

```python
            if (row.get("state") or "running") not in {"running", "cancel_requested"}:
                continue
            path = row["path"] or ""
            workdir = os.path.dirname(path)
            if not workdir:
                continue
            lock_path = guard_lock_path(workdir, task_id)
            if is_lock_held(lock_path):
                # guard 活着：续租防重领（租约只剩认领语义，存活以锁为准）
                extend_compute_lease(self.db, task_id, _LEASE_RENEW_AFTER_CHECK)
                continue
            start_ts = float(row.get("start_timestamp") or -1)
            if (
                start_ts > 0
                and (time.time() - start_ts) < _ADOPT_LAUNCH_GRACE_SECONDS
            ):
                continue
            if _adopt_spawn_throttled(lock_path):
                continue  # 60s 内已拉起过 adopt guard，等下轮对账（防崩溃循环轰炸）
            # guard 已死：spawn adopt guard 接管。calc 还在跑它会阻塞等锁；
            # calc 已结束它直接解析收尾；无日志则置 failed。conv_id 从行里取。
            logger.warning(
                "compute job %s: guard lock free, spawning adopt guard", task_id
            )
            try:
                spawn_detached(
                    build_guard_cmd(
                        task_id,
                        path,
                        row["conversation_id"] or "default",
                        self.db.path,
                        job_type=row["jobtype"] or "gaussian",
                        adopt=True,
                    ),
                    guard_log_path(workdir, task_id),
                )
                _record_adopt_spawn(lock_path)
                extend_compute_lease(self.db, task_id, _LEASE_AFTER_ADOPT_SPAWN)
            except Exception:
                logger.exception("could not spawn adopt guard for job %s", task_id)
        return reattach
```

**排除项证据：adopt 先等 calc 锁释放再收尾**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime/monitor.py:750-796`

```python
    """对账接管：guard 已死但作业仍 running 时由调度器拉起。

    不启动新计算：阻塞等 calc 锁释放（内核保证进程死锁必放，无死等），
    然后走与正常 guard 完全相同的解析/落库/通知路径。calc 锁未被持有
    （guard 死在 spawn 前或 calc 已结束）时立即进入解析——日志缺失或
    不可解析则置 failed。全程零 PID 探测。
    """
    log_path = Path(get_log_path(path, job_type=job_type))
    workdir = os.path.dirname(log_path)
    db = ComputeDB.from_path(db_path)

    guard_lock = await asyncio.to_thread(guard_lock_path, workdir, taskid)
    guard_fd = await asyncio.to_thread(try_acquire_lock, guard_lock)
    if guard_fd is None:
        print(f'[guard adopt] task {taskid} 已有 guard 持锁在管，退出')
        return
    try:
        await _register_pid(db, taskid, "guard_pid", os.getpid())
        calc_lock = await asyncio.to_thread(calc_lock_path, workdir, taskid)
        while True:
            calc_fd = await asyncio.to_thread(try_acquire_lock, calc_lock)
            if calc_fd is not None:
                break
            print(f'[guard adopt] calc 锁仍被持有，calculator 还在跑；{_ADOPT_POLL_SECONDS}s 后再探...')
            await asyncio.sleep(_ADOPT_POLL_SECONDS)
        try:
            row = await aget_compute_job(db, taskid)
            if row is None:
                raise RuntimeError(f"compute job {taskid} disappeared before adopt finalization")
            if row["state"] == "cancel_requested":
                await acancel_compute_job(db, taskid)
                return
            if row["state"] != "running":
                return
            xtb_task = XtbParams.from_row(row).task if job_type == "xtb" else None
            output_log = await asyncio.to_thread(_calc_output_log_path, workdir, taskid)
            await _finalize(
                db, taskid, log_path, workdir, parse_timeout, job_type, None,
                fallback_log_path=output_log, xtb_task=xtb_task,
            )
            row = await aget_compute_job(db, taskid)
            if row is not None and row["state"] == "cancel_requested":
                await acancel_compute_job(db, taskid)
        finally:
            os.close(calc_fd)
    finally:
        os.close(guard_fd)
```

**排除项证据：节点不在注册容量表中就留队，不改投**
源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/compute_store.py:609-630`

```python
            for cid, req_cpus, req_mem, node in candidates:
                node_key = str(node)
                limits = caps.get(node_key)
                if limits is None:
                    if node_key not in _warned_unknown_nodes:
                        _warned_unknown_nodes.add(node_key)
                        logger.warning(
                            "compute job %s targets node %r which is not in the node "
                            "registry; leaving it queued (re-register the node or "
                            "cancel the job)",
                            cid,
                            node_key,
                        )
                    continue
                cap_slots, cap_cpus, cap_mem = limits
                used = usage.get(node_key, [0, 0, 0])
                if used[0] + 1 > cap_slots:
                    continue  # 该节点槽位满：后面属于它的作业同样放不下
                r_cpus = int(req_cpus or 1)
                r_mem = int(req_mem if req_mem is not None else fair_share[node_key])
                if used[1] + r_cpus > cap_cpus or used[2] + r_mem > cap_mem:
                    continue  # 该节点放不下，试试后面的小作业
```


## Agent 内核与工具接口：详细证据

### Cloudra 运行时设计审计：三项已确认问题

审计位置：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master`。审计时间：2026-10-18。本文件只记录当前源码证据、设计根因及最小修复方向；未修改仓库源码，未调用真实计算、网络或服务启停，未运行全套测试。唯一动态验证是下文的纯内存角色能力复现，未执行被禁用的 bash。

本报告确认三项：角色工具 deny 被丢弃、他人的项目计算阻断子 Agent 结束、文件工具公开内部并发哈希。方法、基组、虚频、IRC、证据验收标准均不在改动建议范围。

代码块从当前文件按行直接提取；每块给出绝对路径和准确行范围，没有使用省略号代替源码。第一节是后面两项工具问题共享的实际工具调用与结果返回链。为明确限定所讨论的路径，工具执行示例使用系统目前支持的 traditional 协议；JavaScript 工具目录的 deny 暴露问题另外展示。

#### 0. 工具调用和结果返回的共用实际链

模型返回工具调用后，TurnPipeline 按当前协议路由；traditional 调用进入 InvocationService。后者先记录请求、刷新当前 Agent 能力，再依次运行 PolicyStage；允许后交给 LegacyToolExecutor。执行器检查角色权限位、验证 Pydantic 入参，调用 Tool.safe_call；工具输出再转为 ToolResult，InvocationService 持久记录真实结果和结束事件，TurnPipeline 将结果交给 runner，runner 持久加入下一轮上下文。

这里展示同一路径所有中间执行/转交/结果成形环节，后文引用本节，不另复制整套生命周期。

##### 模型输出、协议分支、调用生命周期、结果返回 TurnOutcome

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/turn_pipeline.py:541-665`

```python
        if not response.tool_calls:
            # 无工具调用的纯文本最终回复只是结束*意向*：是否允许结束由 runner
            # 收尾前的统一结束门禁裁决（与显式 stop 同一边界，Task 4A）。
            return TurnOutcome(
                decision="stop", content=response.content, reasoning=response.reasoning
            )

        # 中间轮次的正文（模型在工具调用前后说的话）不能只活在流式气泡里：
        # 落成持久 agent.message_emitted，否则历史轮次的 narration 全被吞掉。
        # stop 轮的正文由 runner 的最终消息承载，这里跳过避免重复。
        # 立刻推到 hub：等整轮工具跑完再 flush 时，前端会先被
        # llm.request_started 清掉流式气泡，内容来不及进时间线。
        if response.content.strip() and not any(
            call.name == self.stop_tool for call in response.tool_calls
        ):
            await self._publish(
                self.event_log.append(
                    "agent.message_emitted",
                    stream="agent",
                    project_id=agent.project_id,
                    session_id=agent.id,
                    run_id=run_id,
                    data={"sender": agent.role_id, "content": response.content},
                )
            )

        exchanges: list[tuple[ToolCall, ToolResult]] = []
        protocol = effective_invocation_protocol(agent)
        if protocol is InvocationProtocol.JAVASCRIPT and response.tool_calls:
            names = [call.name for call in response.tool_calls]
            has_direct = any(is_direct_only(name) for name in names)
            if JS_EXEC_NAME in names and has_direct:
                # Never partially execute a mixed program/control response:
                # every wire call gets matching feedback, nothing runs.
                reason = (
                    "protocol_error[mixed_program_and_controls]: a response "
                    "combining js_exec with direct controls is rejected; "
                    "issue them in separate responses"
                )
                exchanges = [(call, ToolResult(False, reason)) for call in response.tool_calls]
                return TurnOutcome(
                    decision="continue",
                    content=response.content,
                    tool_exchanges=tuple(exchanges),
                    reasoning=response.reasoning,
                )
        # Do not project the assistant tool_calls here.  The runner appends the
        # assistant message and every matching tool result in one durable event
        # only after this turn returns.  Cancellation or a crash therefore
        # cannot expose a half-pair to the next provider request.
        js_programs_run = 0
        for call in response.tool_calls:
            route_error = validate_wire_route(protocol, call.name)
            if route_error is not None:
                # Misrouted calls never execute; the message is model feedback.
                exchanges.append((call, ToolResult(False, route_error)))
                continue
            if protocol is InvocationProtocol.JAVASCRIPT and call.name == JS_EXEC_NAME:
                js_programs_run += 1
                if js_programs_run > 1:
                    exchanges.append((
                        call,
                        ToolResult(
                            False,
                        "protocol_error[multiple_programs]: only one js_exec "
                        "call runs per model response; the first program was "
                        "already processed and this later program was not executed. "
                        "Repair only the unexecuted program; do not replay the first one.",
                        ),
                    ))
                    continue
                result = await self.js_runtime.execute(ctx, call)
                exchanges.append((call, result))
                control = (result.data or {}).get("control_decision")
                if control == "wait_approval":
                    error = (result.data or {}).get("error") or {}
                    return TurnOutcome(
                        decision="wait_approval",
                        message=str(error.get("message") or ""),
                        tool_exchanges=tuple(exchanges),
                        reasoning=response.reasoning,
                    )
                continue
            # The full lifecycle (requested -> policy -> started -> raw result
            # -> post hooks -> finished) lives in the InvocationService; this
            # loop only translates outcomes into turn decisions.
            outcome = await self.invocations.invoke(ctx, call)
            if outcome.decision == "wait_approval":
                return TurnOutcome(
                    decision="wait_approval",
                    message=outcome.error.message if outcome.error else "",
                    blocked_call=outcome.call,
                    tool_exchanges=tuple(exchanges),
                    reasoning=response.reasoning,
                )
            if outcome.error is not None and outcome.error.code == "policy_blocked":
                return TurnOutcome(
                    decision="continue",
                    content=outcome.error.message,
                    message=f"blocked by {outcome.error.stage}",
                    blocked_call=outcome.call,
                    tool_exchanges=tuple(exchanges),
                    reasoning=response.reasoning,
                )
            result = outcome.result
            if result is None:
                # Only wait_approval returns result=None (handled above).
                continue
            exchanges.append((outcome.call, result))
            if outcome.call.name == self.stop_tool:
                # Carry a candidate answer to the runner. A tool receipt is
                # never a final answer or authorization to stop.
                final_text = str(outcome.call.arguments.get("final_answer") or response.content).strip()
                return TurnOutcome(
                    decision="stop",
                    content=final_text,
                    tool_exchanges=tuple(exchanges),
                    reasoning=response.reasoning,
                )
        return TurnOutcome(
            decision="continue",
            content=response.content,
            tool_exchanges=tuple(exchanges),
            reasoning=response.reasoning,
        )
```

##### 实际调用入口：按 Agent 串行执行

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/invocation.py:176-181`

```python
    async def invoke(
        self, ctx: PipelineContext, call: ToolCall, *, execution_id: str | None = None
    ) -> InvocationOutcome:
        lock = self._agent_locks.setdefault(ctx.agent.id, asyncio.Lock())
        async with lock:
            return await self._invoke_admitted(ctx, call, execution_id=execution_id)
```

##### 请求落盘、刷新上下文、绑定调用身份并转入实际执行

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/invocation.py:266-291`

```python
    async def _invoke_admitted(
        self, ctx: PipelineContext, call: ToolCall, *, execution_id: str | None
    ) -> InvocationOutcome:
        # 1. The request is a durable fact before any policy/tool effect.
        draft, effect = decide_invocation(ctx, call, execution_id=execution_id)
        requested = await self._commit(draft)
        call = effect.call
        self._refresh_context(ctx)
        active = True

        async def report(progress):
            if not active:
                raise RuntimeError("cannot report progress after invocation ended")
            await self._commit(self._draft("tool.progress", ctx, {
                **_detach_json(progress.model_dump(mode="json")),
                "tool_call_id": call.id, "tool_name": call.name,
                "execution_id": execution_id, "request_event_id": requested.event_id,
            }))

        scope = InvocationScope(call.id, call.name, execution_id, report, requested.event_id)
        token = set_invocation_scope(scope)
        try:
            return await self._invoke_scoped(ctx, call, execution_id=execution_id)
        finally:
            active = False
            reset_invocation_scope(token)
```

##### 执行前从活 Agent 获取当前设置与能力

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/invocation.py:185-198`

```python
    def _refresh_context(self, ctx: PipelineContext) -> None:
        """Re-derive settings/capabilities from the live agent at admission."""
        if self._agents is None:
            return
        live = self._agents.get(ctx.agent.id)
        if live is None:
            return
        ctx.agent = live
        ctx.settings = live.settings.model_copy(deep=True)
        if live.current_run is not None:
            # The protocol is run-fixed: a mid-run settings change must not
            # leak into the refreshed snapshot.
            ctx.settings.invocation_protocol = live.current_run.invocation_protocol
        ctx.capabilities = live.capabilities
```

##### 完整策略分支、实际执行、结果记录、后处理和返回

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/invocation.py:293-504`

```python
    async def _invoke_scoped(
        self, ctx: PipelineContext, call: ToolCall, *, execution_id: str | None
    ) -> InvocationOutcome:
        agent = ctx.agent
        # 2. Policy gates, in their existing order.
        for stage in self.stages:
            policy = await stage.before_tool(ctx, call)
            if policy.outcome == "block":
                error = InvocationError("policy_blocked", policy.message, "not_started", stage.name)
                await self._commit(
                    self._draft(
                        "tool.blocked",
                        ctx,
                        {
                            "tool_call_id": call.id,
                            "tool_name": call.name,
                            "execution_id": execution_id,
                            "stage": stage.name,
                            "message": policy.message,
                        },
                    )
                )
                await self._commit_finished(
                    ctx,
                    call,
                    execution_id=execution_id,
                    status="blocked",
                    effect_state="not_started",
                    is_success=False,
                    result_summary=policy.message or "blocked by policy",
                    error=error,
                )
                return InvocationOutcome(
                    call=call,
                    result=ToolResult(False, policy.message or "blocked by policy"),
                    error=error,
                )
            if policy.outcome == "ask":
                error = InvocationError("policy_wait", policy.message, "not_started", stage.name)
                await self._commit(
                    self._draft(
                        "tool.approval_requested",
                        ctx,
                        {
                            "tool_call_id": call.id,
                            "tool_name": call.name,
                            "execution_id": execution_id,
                            "message": policy.message,
                        },
                    )
                )
                await self._commit_finished(
                    ctx,
                    call,
                    execution_id=execution_id,
                    status="waiting",
                    effect_state="not_started",
                    is_success=False,
                    result_summary=policy.message or "waiting for approval",
                    error=error,
                )
                return InvocationOutcome(call=call, result=None, decision="wait_approval", error=error)
            if policy.outcome == "warn":
                ctx.emit("agent.warning", {"code": f"{stage.name}.warn", "message": policy.message})

        # 3. Admitted: the started fact is durable before the executor runs.
        await self._commit(
            self._draft(
                "tool.started",
                ctx,
                {
                    "tool_call_id": call.id,
                    "tool_name": call.name,
                    "arguments_summary": call.arguments,
                    "execution_id": execution_id,
                },
            )
        )
        repeat = self._track_tool_call(agent.id, ctx.run_id, call)
        if repeat >= LOOP_DETECTION_THRESHOLD:
            # Soft guard: the call still executes, but the loop is audited and
            # the model is told to change approach on the next turn.
            ctx.emit("loop.detected", {"tool_name": call.name, "repeat": repeat})
            if ctx.notices is not None:
                ctx.notices.push(
                    agent.id,
                    f"[Guard] Loop detected: `{call.name}` has been called {repeat} "
                    "times in a row with identical arguments in this run. Repeating "
                    "the same call will not produce new information — change your "
                    "approach: vary the arguments, use a different tool, or report "
                    "the blocker instead of retrying.",
                )

        # 4. Execute exactly once.
        started_call = time.monotonic()
        try:
            raw = await self.tools.execute(agent, call)
        except asyncio.CancelledError:
            try:
                await self._commit_finished(
                    ctx,
                    call,
                    execution_id=execution_id,
                    status="cancelled",
                    effect_state="unknown",
                    is_success=False,
                    result_summary="interrupted: run cancelled",
                    duration_ms=int((time.monotonic() - started_call) * 1000),
                    error=InvocationError("cancelled", "run cancelled", "unknown"),
                    cancelled=True,
                )
            except EventPersistenceError:
                raise
            except Exception:
                logger.exception("failed to record tool cancellation for %s", call.id)
            raise
        except EventPersistenceError:
            raise
        except Exception as exc:
            error = InvocationError("tool_exception", str(exc), "unknown")
            await self._commit_finished(
                ctx,
                call,
                execution_id=execution_id,
                status="failed",
                effect_state="unknown",
                is_success=False,
                result_summary=f"tool crashed: {exc}",
                duration_ms=int((time.monotonic() - started_call) * 1000),
                error=error,
            )
            return InvocationOutcome(
                call=call,
                result=ToolResult(False, f"tool crashed: {exc}", error=error),
                error=error,
            )
        result = ToolResult(
            is_success=raw.is_success,
            summary=raw.summary,
            data=raw.data,
            duration_ms=int((time.monotonic() - started_call) * 1000),
            error=raw.error,
        )

        if result.error is not None:
            # The executor caught a fault and packaged it as a result: treat
            # it as a terminal unknown-effect failure, not a business result.
            await self._commit_finished(
                ctx,
                call,
                execution_id=execution_id,
                status="failed",
                effect_state=result.error.effect_state,
                is_success=False,
                result_summary=result.summary,
                duration_ms=result.duration_ms,
                error=result.error,
            )
            return InvocationOutcome(call=call, result=result, error=result.error)

        # 5. The raw result is durable before any post-processing hook sees it.
        recorded = await self._commit(
            self._draft(
                "tool.result_recorded",
                ctx,
                {
                    "tool_call_id": call.id,
                    "tool_name": call.name,
                    "execution_id": execution_id,
                    "result": {
                        "is_success": result.is_success,
                        "summary": result.summary,
                        "data": _detach_json(result.data),
                        "duration_ms": result.duration_ms,
                    },
                },
            )
        )

        # 6. Post hooks and artifact registration, exactly once.
        post_error: InvocationError | None = None
        artifact_id: str | None = None
        try:
            for stage in self.stages:
                await stage.after_tool(ctx, call, result)
            artifact_id = await self._register_tool_image(ctx, result)
        except Exception as exc:
            post_error = InvocationError("postprocessing_failed", str(exc), "completed")
            logger.exception("post-tool processing failed for %s", call.id)

        # 7. Durable terminal fact, then resolve the caller.
        image_paths = image_paths_from_tool_result(result)
        await self._commit_finished(
            ctx,
            call,
            execution_id=execution_id,
            status=("failed" if (post_error or not result.is_success) else "completed"),
            effect_state="completed",
            is_success=result.is_success,
            result_summary=result.summary,
            duration_ms=result.duration_ms,
            raw_result_event_id=recorded.event_id,
            error=post_error,
            artifact_id=artifact_id,
            image_paths=image_paths or None,
        )
        return InvocationOutcome(
            call=call,
            result=result,
            error=post_error,
            raw_result_event_id=recorded.event_id,
        )
```

##### 结果结束事件的成形与返回

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/invocation.py:219-264`

```python
    async def _commit_finished(
        self,
        ctx: PipelineContext,
        call: ToolCall,
        *,
        execution_id: str | None,
        status: str,
        effect_state: str,
        is_success: bool,
        result_summary: str,
        duration_ms: int = 0,
        raw_result_event_id: str | None = None,
        error: InvocationError | None = None,
        artifact_id: str | None = None,
        image_paths: list[str] | None = None,
        cancelled: bool = False,
    ):
        data: dict[str, Any] = {
            "tool_call_id": call.id,
            "tool_name": call.name,
            "execution_id": execution_id,
            "status": status,
            "effect_state": effect_state,
            "is_success": is_success,
            "result_summary": result_summary,
            "duration_ms": duration_ms,
            "raw_result_event_id": raw_result_event_id,
            "error": (
                {
                    "code": error.code,
                    "message": error.message,
                    **({"stage": error.stage} if error.stage else {}),
                }
                if error
                else None
            ),
        }
        if artifact_id:
            # The frontend builds the timeline download URL from this id.
            data["artifact_id"] = artifact_id
        if image_paths:
            data["image_path"] = image_paths[0]
            data["image_paths"] = image_paths
        if cancelled:
            data["cancelled"] = True
        return await self._commit(self._draft("tool.finished", ctx, data))
```

##### 实际业务执行器：权限位、输入验证、safe_call、ToolResult 返回

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/adapters.py:1070-1183`

```python
    async def execute(self, agent: AgentSession, call: ToolCall) -> ToolResult:
        from cloudra.runtime_v2.subagent_bridge import NATIVE_TOOL_NAMES, handle_native_tool
        from cloudra.tools import get_tools_lst

        if agent.role_id == "supervisor" and (
            not is_direct_only(call.name) or supervisor_access_for(call.name) != "none"
        ):
            return await self._execute_supervisor(agent, call)

        if call.name in NATIVE_TOOL_NAMES:
            return await handle_native_tool(self.core, agent, call)
        if call.name == "agent_hub":
            from cloudra.runtime_v2.hub_bridge import handle_hub_tool

            return await handle_hub_tool(self.core, agent, call)
        if call.name == "schedule":
            return await self.core.reminders.handle(agent, call)

        if is_retired_tool_name(call.name):
            return ToolResult(
                is_success=False,
                summary=hint_unknown_tool(call.name),
            )

        if call.name == "search":
            source = (call.arguments or {}).get("source") or "web"
            if source == "web" and _native_search_adapter_for(agent.settings) is not None:
                return ToolResult(
                    is_success=False,
                    summary=(
                        "Web search is provided natively by the model. "
                        "Call search with source='arxiv' or source='openalex' instead."
                    ),
                )

        entry = next((e for e in get_tools_lst() if e.tool_name == call.name), None)
        if entry is None:
            return ToolResult(
                is_success=False,
                summary=hint_unknown_tool(call.name),
            )
        project = self.core.require_project(agent.project_id)
        # 工具字段的类型是 ToolActorContext（Protocol），声明了该字段的工具直接
        # 经构造器拿到调用者身份（不再需要 object.__setattr__ 绕过 pydantic 校验）；
        # 不声明它的工具（log_parser 等无状态工具）按原样构造。
        if "subagent" in getattr(entry.cls, "model_fields", {}):
            actor = _LegacyAgentBridge(agent, project.workspace_dir)
            tool = entry.instantiate(subagent=actor)
        else:
            tool = entry.instantiate()
        from cloudra.tools.core.permission_model import check_permission
        if not check_permission(_LegacyAgentBridge(agent, project.workspace_dir).permission_all(), tool.tool_permission_all()):
            return ToolResult(is_success=False, summary="Tool requires permissions absent from this task")
        schema_cls = entry.input_schema or LegacyInputSchema
        try:
            parsed = schema_cls.model_validate(call.arguments)
        except ValidationError as exc:
            return ToolResult(is_success=False, summary=validation_feedback(exc))
        from cloudra.runtime_v2.invocation_context import report_tool_progress
        from cloudra.runtime_v2.schemas import ToolProgress

        await report_tool_progress(ToolProgress(
            phase="executing", message="Validated tool inputs; entering tool execution",
            effective_arguments=parsed.model_dump(mode="json"),
        ))
        token = set_session_yolo(agent.settings.yolo)
        try:
            # v2-native user decisions: destructive-tool approvals and ask_user
            # questions go to the kernel PendingBroker (events + futures)
            # instead of the legacy conversation SQLite / event bus.
            async def _approval(**fields):
                return await self.core.pending.request_approval(agent, **fields)

            async def _interaction(prompt: str) -> str:
                return await self.core.pending.request_interaction(agent, prompt)

            from cloudra.base.tools_class import use_approval_handler
            from cloudra.services.ts_pipeline_context import use_runtime_authority
            from cloudra.tools.Interactool.ask_user import use_input_handler
            with use_approval_handler(_approval), use_input_handler(_interaction), use_runtime_authority(self.core):
                output = await tool.safe_call(parsed, Session(id=agent.id, path=""))
            if not isinstance(output, entry.output_schema):
                raise TypeError(f"Tool {call.name!r} returned an undeclared output schema")
            data = output.model_dump(mode="json")
            is_success = bool(data.get("is_success", True))
            if call.name == "bash":
                is_success = is_success and data.get("exit_code", 1) == 0
            summary = json.dumps(data, ensure_ascii=False, allow_nan=False)
        except Exception as exc:
            # An unexpected safe_call fault is not a business failure: package
            # it as structured tool_exception metadata so the invocation
            # service closes the lifecycle with effect_state=unknown.
            # Validation errors above stay ordinary unsuccessful results.
            from cloudra.runtime_v2.event_writer import EventPersistenceError
            from cloudra.runtime_v2.invocation_types import InvocationError

            # safe_call wraps tool exceptions; a failed durable progress write
            # must retain the runtime's non-retryable persistence semantics.
            cause = exc
            while cause is not None:
                if isinstance(cause, EventPersistenceError):
                    raise cause
                cause = cause.__cause__

            logging.getLogger(__name__).exception("Tool execution failed: %s", call.name)
            message = "Tool execution failed internally. The error was logged; report the tool call instead of inspecting application source."
            return ToolResult(
                is_success=False,
                summary=message,
                error=InvocationError(code="tool_exception", message=message, effect_state="unknown"),
            )
        finally:
            reset_session_yolo(token)
        return ToolResult(is_success=is_success, summary=summary, data=data)
```

##### 工具上下文：绑定项目、工作目录、会话和实际权限

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/adapters.py:981-1001`

```python
    def __init__(self, agent: AgentSession, workspace_dir: str | None) -> None:
        self._runtime_agent = agent
        self.id = agent.id
        self.name = agent.role_id
        # dag_* 工具的 _actor() 依 type=="supervisor" 判 GraphActor.SUPERVISOR
        # （裁决权限的唯一入口）；督导不再是 follower。
        self.type = (
            "coordinator"
            if agent.role_id == "coordinator"
            else "supervisor"
            if agent.role_id == "supervisor"
            else "follower"
        )
        self.conversation_id = agent.project_id
        # workspace_dir=None 的存量项目不能落 None：read/write/bash 会把裸相对
        # 路径解析到进程 cwd，串到别的任务目录（GH #24）——统一兜底到
        # per-project 默认工作区，与 project.create 的缺省推导同一事实源。
        self.working_directory = workspace_dir or str(project_workspace_dir(agent.project_id))
        self.orchestration_mode = agent.settings.orchestration_mode.value
        self.session_id = agent.id
        self._permissions = agent.capabilities.permissions
```

##### 能力权限到工具权限位的转换

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/adapters.py:1003-1019`

```python
    def permission_all(self):
        """Legacy IntFlag projection of the v2 capability permission set."""
        from cloudra.tools.core.permission_model import Permission

        perms = Permission.NONE
        granted = self._permissions
        if granted.read:
            perms |= Permission.READ
        if granted.write:
            perms |= Permission.WRITE
        if granted.manage:
            perms |= Permission.MANAGE
        if granted.script:
            perms |= Permission.SCRIPT
        if granted.destructive:
            perms |= Permission.DESTRUCTIVE
        return perms
```

##### 工具包装器实际调用 tool_call，异常向执行边界传递

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/base/tools_class.py:145-157`

```python
    async def safe_call(self, user_input: input_schema, session: Session) -> output_schema:
        '''
        带有通用异常捕获的工具调用包装器。
        工具执行失败时抛出包含工具名的 RuntimeError，由 runtime_v2 执行边界记录和回传。
        '''
        try:
            return await self.tool_call(user_input, session)
        except Exception as e:
            error_msg = (
                f"[Tool error] {self.tool_name}: {str(e)}. "
                "Fix the arguments or use a different tool, then retry."
            )
            raise RuntimeError(error_msg) from e
```

##### runner 将工具调用与对应结果完整加入会话上下文

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/agent_runner.py:894-941`

```python
    async def _commit_turn_output(self, agent: AgentSession, run_id: str, outcome) -> None:
        """响应消息恰好一次落进会话上下文投影（context.appended）。

        输入（前缀增量/inbox/通知）已在发送前由 ContextBroker.commit_input
        入投影；这里只用同一事件原子追加 assistant tool_calls 与全部匹配的
        tool outputs。run_turn 失败/取消时不调用，不能留下 provider 拒绝的
        半条工具调用；已提交的输入仍留在投影里（它确实进入过请求）。
        """
        entries: list[dict] = []
        tool_calls = [call for call, _ in outcome.tool_exchanges]
        if outcome.blocked_call is not None:
            tool_calls.append(outcome.blocked_call)
        if outcome.content or tool_calls:
            entry: dict = {"role": "assistant", "content": outcome.content}
            if outcome.reasoning:
                entry["reasoning_content"] = outcome.reasoning
            if tool_calls:
                # Structured form; the LLM adapter converts these into the
                # wire format (assistant tool_calls + matching tool messages).
                entry["tool_calls"] = [
                    {"id": call.id, "name": call.name, "arguments": call.arguments}
                    for call in tool_calls
                ]
            entries.append(entry)
        for call, result in outcome.tool_exchanges:
            entries.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": await asyncio.to_thread(self._tool_result_content, agent, result),
                    **({'tool_document_compact_content':result.data['tool_document_compact_content']}
                       if isinstance(result.data, dict) and result.data.get('tool_document_compact_content') else {}),
                    **({'tool_documents':[{'name':doc['name'],'revision':doc['revision']} for doc in result.data.get('documents',[])]}
                       if call.name=='get_tool_docs' and result.is_success else {}),
                    **({'tool_documents': result.data['tool_documents']}
                       if call.name == 'js_exec' and isinstance(result.data, dict)
                       and result.data.get('tool_documents') else {}),
                }
            )
        if outcome.blocked_call is not None:
            entries.append(
                {
                    "role": "tool",
                    "tool_call_id": outcome.blocked_call.id,
                    "content": outcome.message or "blocked by policy",
                }
            )
        await self.core.contexts.append_output(agent=agent, run_id=run_id, messages=entries)
```

#### 1. [P1] 黑名单保存成功，工具能力和执行却完全忽略

**触发与后果：** 通过角色设置配置 `tool_policy={"allow":["*"],"deny":["bash"]}`，之后新建该普通角色（非 Supervisor 特例）的 Agent。角色 GET 和保存结果保留这项黑名单，但工具目录仍出现 bash，实际 PermissionStage 也返回 allow。其他合法权限位和审批仍会照常运行；这里的确定缺陷是用户配置的这个 deny 自身毫无执行效果。

**设计根因：** 角色公开了 allow 和 deny 两套规则，能力投影只复制 allow。通配符随后展开全工具，原来的 deny 信息已经丢失。执行器只有权限类别，没有工具黑名单可以查。这不是模型没按规定调用，而是公开配置与真正执行权限不是同一份事实。

**最小修法：** 没有实际 blacklist 使用需求时，删掉公开 deny，单用 allow；确实需要 blacklist 时，在唯一能力生成点先展开通配符再减去 deny，让目录和执行都消费同一份具体工具集合。不要额外建立独立的一套 deny 守卫。

**现有覆盖缺口：** 源码对 `.tool_policy.deny` 的唯一读取是 get_tool_docs 不许被禁止的特例。runtime 测试未覆盖一般 deny 的目录隐藏和调用拒绝。应回归：同一份 deny 配置在保存、新建 Agent、目录、traditional 调用和 JS 宾客调用上含义一致。

##### 实际公开角色策略 schema

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/schemas.py:171-175`

```python
class ToolPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow: list[str] = Field(default_factory=lambda: ["*"])
    deny: list[str] = Field(default_factory=list)
```

##### HTTP 更新角色入参

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/api_v2/models.py:56-61`

```python
class RolePatch(BaseModel):
    permissions: Optional[dict[str, bool]] = None
    tool_policy: Optional[dict[str, Any]] = None
    can_spawn: Optional[bool] = None
    spawn_roles: Optional[list[str]] = None
    default_settings: Optional[dict[str, Any]] = None
```

##### 入口：PATCH 角色转成 role.update

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/api_v2/routers/roles.py:26-33`

```python
    @router.patch("/api/v2/roles/{role_id}", dependencies=ctx.protected)
    async def patch_role(role_id: str, body: RolePatch) -> CommandResponse:
        command = Command(
            type="role.update",
            target={"role_id": role_id, "project_id": "runtime"},
            payload=_command_payload(body),
        )
        return await ctx.execute(command)
```

##### API 中间层：CommandBus 执行并将结果返回客户端

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/api_v2/context.py:34-56`

```python
    async def execute(self, command: Command) -> CommandResponse:
        try:
            result = await self.bus.execute(command)
        except CommandRejected as exc:
            http_code = {
                "not_found": status.HTTP_404_NOT_FOUND,
                "state_conflict": status.HTTP_409_CONFLICT,
            }.get(exc.code, status.HTTP_400_BAD_REQUEST)
            raise HTTPException(
                status_code=http_code,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
        data = result.data
        if isinstance(data, AgentSession):
            # 命令响应里的 agent 与 GET 端点同形：运行期投影（completion）也带上，
            # 否则前端用响应整体替换 agent 时会丢掉它。
            data = await asyncio.to_thread(agent_dict, self.core, data)
        return CommandResponse(
            command_id=result.command_id,
            accepted=result.accepted,
            event_id=result.event_id,
            data=data,
        )
```

##### CommandBus 入口

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/commands.py:914-916`

```python
    async def execute(self, command: Command) -> CommandResult:
        async with self.core.command_lock:
            return await self._execute_locked(command)
```

##### 命令分派、应用事件和结果返回的完整分支

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/commands.py:918-972`

```python
    async def _execute_locked(self, command: Command) -> CommandResult:
        core = self.core
        cached = core.cached_result(command.command_id)
        if cached is not None:
            return cached
        decider = DECIDERS.get(command.type)
        wrapper = WRAPPERS.get(command.type)
        if decider is None and wrapper is None:
            raise CommandRejected("invalid_request", f"unknown command type {command.type!r}")
        try:
            if command.type == "project.delete":
                from cloudra.persistence.database import ComputeDB
                from cloudra.services.compute_store import (
                    acount_active_compute_job_states,
                    active_jobs_delete_message,
                )

                project_id = _project_id(core, command)
                counts = await acount_active_compute_job_states(ComputeDB(), project_id)
                if counts:
                    raise CommandRejected(
                        "state_conflict",
                        active_jobs_delete_message(counts),
                    )
            if decider is not None:
                # 拍 1：纯 decide（守卫校验在这里抛 CommandRejected）
                if decider is _decide_cancel_agent:
                    # Query history off-loop, then validate the captured event
                    # boundary before making the pure decision atomically.
                    while True:
                        boundary = len(core.event_log)
                        candidates = [agent.model_copy(deep=True) for agent in core.agents.values()]
                        parked = await asyncio.to_thread(lambda: {
                            agent.id for agent in candidates if is_background_parked(core, agent)
                        })
                        if boundary == len(core.event_log):
                            break
                    decision = _decide_cancel_agent(core, command, parked_sessions=parked)
                else:
                    decision = decider(core, command)
                if await self._recover_interrupted_invocations(decision):
                    # Publication may submit a nested message. Re-decide so
                    # that an already reopened session does not get two runs.
                    decision = decider(core, command)
                # 拍 2-4：落日志/发布/持久化 → apply → effects
                result = await self._apply_decision(command, decision)
            else:
                # 薄包装：broker 自带事件流与 future 解析，bus 扫尾发布/持久化
                result = await wrapper(core, command)
                await self._flush()
        except CommandRejected as exc:
            result = await self._reject(command, exc)
        core.remember(command, result)
        await self._maybe_snapshot()
        return result
```

##### role.update 接受并记录 tool_policy

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/commands.py:672-689`

```python
def _decide_update_role(core: RuntimeCore, command: Command) -> Decision:
    role = core.roles.require(command.target.get("role_id", ""))
    payload = command.payload
    allowed = {"default_settings", "permissions", "tool_policy", "can_spawn", "spawn_roles"}
    changes = {key: value for key, value in payload.items() if key in allowed}
    if not changes:
        raise CommandRejected("invalid_request", "no mutable role fields supplied")
    return Decision(
        events=(
            EventDraft(
                "role.updated",
                stream="project",
                project_id=_project_id(core, command),
                data={"role_id": role.role_id, "changes": changes, "actor": command.actor},
            ),
        ),
        result=ResultRef("role", role.role_id),
    )
```

##### 决定落盘、应用事件、执行副作用、解析结果

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/commands.py:1036-1081`

```python
    async def _apply_decision(self, command: Command, decision: Decision) -> CommandResult:
        core = self.core
        envelopes: list[EventEnvelope] = []

        def project(envelope: EventEnvelope) -> None:
            apply_event(core, envelope)
            envelopes.append(envelope)

        try:
            await core.event_writer.commit_and_apply(decision.events, project)
            # 拍 4：副作用（runner/mailbox/文件系统/内存秘密覆盖）
            for effect in decision.effects:
                await _execute_effect(core, effect)
        except EventPersistenceError:
            # spawned 已落盘：返回已创建的 agent 并尽量跑完 effects，
            # 避免 HTTP 500 触发新 command_id 再造一个 coordinator。
            if any(envelope.type == "agent.spawned" for envelope in envelopes):
                persisted = {envelope.type for envelope in envelopes}
                for effect in decision.effects:
                    if (
                        isinstance(effect, DeliverMessage)
                        and "agent.message_injected" not in persisted
                    ):
                        continue
                    try:
                        await _execute_effect(core, effect)
                    except Exception:
                        logger.exception(
                            "spawn effect after partial persist failed for %s",
                            command.command_id,
                        )
                return CommandResult(
                    command_id=command.command_id,
                    accepted=True,
                    event_id=envelopes[-1].event_id,
                    data=self._resolve_result(decision.result),
                )
            raise
        receipt = envelopes[-1] if envelopes else None
        if command.type == "agent.message":
            receipt = next(event for event in envelopes if event.type == "agent.message_injected")
        return CommandResult(
            command_id=command.command_id,
            event_id=receipt.event_id if receipt else "",
            data=self._resolve_result(decision.result),
        )
```

##### 角色事件的实际应用

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/apply.py:139-140`

```python
def _apply_role_updated(core: RuntimeCore, envelope: EventEnvelope) -> None:
    core.roles.update(envelope.data["role_id"], envelope.data["changes"])
```

##### 角色整模型验证保存，deny 本身未丢失

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/roles.py:143-151`

```python
    def update(self, role_id: str, patch: dict) -> RoleProfile:
        role = self.require(role_id)
        # 整模型重校验：patch 里的嵌套 dict（default_settings/permissions/
        # tool_policy）必须落成对应模型实例。裸 model_copy 不校验，会让活
        # core 持 dict 而快照恢复持模型——同一份 role.updated 事件在两条
        # 路径上推出不同形态（等价性门禁实测漂移点）。
        updated = RoleProfile.model_validate({**role.model_dump(mode="json"), **patch})
        self._roles[role_id] = updated
        return updated
```

##### 返回保存后的实际角色对象

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/commands.py:1083-1093`

```python
    def _resolve_result(self, result: Any) -> Any:
        """ResultRef 在 apply+effects 之后解析为活对象；字面量原样返回。"""
        core = self.core
        if isinstance(result, ResultRef):
            if result.kind == "project":
                return core.require_project(result.key)
            if result.kind == "agent":
                return core.require_agent(result.key)
            if result.kind == "role":
                return core.roles.require(result.key)
        return result
```

##### 后续新建 Agent 的实际入口与完整角色解析分支

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/commands.py:276-370`

```python
def _decide_spawn_agent(core: RuntimeCore, command: Command) -> Decision:
    project_id = _project_id(core, command)
    project = core.require_project(project_id)
    payload = command.payload
    role_id = str(payload.get("role_id") or "")
    parent_session_id = payload.get("parent_session_id")
    requested_by_session_id = payload.get("requested_by_session_id")
    requested = EventDraft(
        "agent.spawn_requested",
        stream="project",
        project_id=project_id,
        data={
            "role_id": role_id,
            "parent_session_id": parent_session_id,
            "requested_by_session_id": requested_by_session_id,
            "actor": command.actor,
        },
    )
    try:
        if parent_session_id is not None and requested_by_session_id is not None:
            raise CommandRejected(
                "invalid_request", "a peer requester and a child parent cannot both be set"
            )
        role = core.roles.require(role_id)
        query_sender = "system"
        if requested_by_session_id is not None:
            requester = core.require_agent(requested_by_session_id)
            if requester.project_id != project_id:
                raise CommandRejected("invalid_request", "requesting agent belongs to another project")
            query_sender = requester.role_id
        if parent_session_id is not None:
            parent = core.require_agent(parent_session_id)
            if parent.project_id != project_id:
                raise CommandRejected("invalid_request", "parent agent belongs to another project")
        caller_id = parent_session_id or requested_by_session_id
        if caller_id is not None:
            core.require_agent(caller_id)
        elif command.actor == "agent":
            raise CommandRejected("forbidden", "Agent delegation requires a bound requester identity")
        settings_patch = RuntimeSettingsPatch.model_validate(payload.get("settings") or {})
        settings = core.agent_host.effective_settings(project, role, settings_patch)
        agent = core.agent_host.build(
            project=project,
            role=role,
            parent_session_id=parent_session_id,
            requested_by_session_id=requested_by_session_id,
            display_name=payload.get("display_name"),
            settings=settings,
        )
    except CommandRejected as exc:
        # 拒绝也要留领域审计轨迹：spawn_requested + spawn_rejected 随拒绝落日志。
        raise CommandRejected(
            exc.code,
            exc.message,
            events=(
                requested,
                EventDraft(
                    "agent.spawn_rejected",
                    stream="project",
                    project_id=project_id,
                    data={"code": exc.code, "message": exc.message, "actor": command.actor},
                ),
            ),
        ) from exc
    drafts: list[EventDraft] = [
        requested,
        EventDraft(
            "agent.spawned",
            stream="project",
            project_id=project_id,
            session_id=agent.id,
            data=agent.model_dump(mode="json"),
        ),
    ]
    effects: list[Effect] = []
    if settings.api_key:
        # api_key 是 write-only 秘密，不进事件/快照；活对象在 apply 后由
        # PatchApiKey 补挂内存覆盖（重放/恢复出的 core 回落全局 key，与既有语义一致）。
        effects.append(PatchApiKey(agent.id, settings.api_key))
    query = str(payload.get("query") or "").strip()
    if query:
        message_draft, deliver = _message_drafts(
            project_id=project_id,
            session_id=agent.id,
            sender=query_sender,
            content=query,
            language=payload.get("language"),
        )
        drafts.append(message_draft)
        effects.append(deliver)
        # A capped launch group commits item_dispatched before it starts this
        # child, so its run permit is installed before the first LLM call.
        if payload.get("defer_schedule") is not True:
            effects.append(ScheduleAgent(agent.id))
    return Decision(events=tuple(drafts), effects=tuple(effects), result=ResultRef("agent", agent.id))
```

##### 关键丢失点：仅 allow 进入 AgentCapabilities

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/agent_host.py:357-397`

```python
    def build(
        self,
        *,
        project: Project,
        role: RoleProfile,
        parent_session_id: str | None,
        requested_by_session_id: str | None = None,
        display_name: str | None,
        settings: RuntimeSettings,
    ) -> AgentSession:
        # Supervisor 的工具面是 registry 的 supervisor_access 动态投影
        # （capabilities.supervisor_tool_names），静态 tool_policy 无法表达；
        # 收窄落在这里（能力与线缆投影同源），执行层另有
        # dag/supervisor_tools.py 的路径/动作守卫做第二道闸。
        if role.role_id == "supervisor":
            from cloudra.tools.capabilities import supervisor_tool_names

            tools = supervisor_tool_names()
        else:
            tools = list(role.tool_policy.allow)
        if role.permissions.read:
            if 'get_tool_docs' in role.tool_policy.deny:
                raise CommandRejected('invalid', 'get_tool_docs is required for on-demand tool documentation')
            if '*' not in tools and 'get_tool_docs' not in tools:
                tools.append('get_tool_docs')
        agent = AgentSession(
            id=new_id("as"),
            project_id=project.id,
            role_id=role.role_id,
            display_name=display_name or role.display_name,
            parent_session_id=parent_session_id,
            requested_by_session_id=requested_by_session_id,
            settings=settings,
            capabilities=AgentCapabilities(
                permissions=role.permissions,
                can_spawn=role.can_spawn,
                spawn_roles=list(role.spawn_roles) if role.spawn_roles is not None else None,
                tools=tools,
            ),
        )
        return agent
```

##### 能力通配符展开

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/tool_catalog.py:128-136`

```python
def _resolve_names(tool_names: Iterable[str] | None) -> list[str]:
    """Capability-list resolution: wildcard expands over the registry."""
    supplied = {str(n) for n in (tool_names or []) if n}
    names = supplied - {"*"}
    if "*" in supplied:
        from cloudra.tools import get_tools_lst

        names |= {entry.tool_name for entry in get_tools_lst() if entry.tool_name}
    return sorted(names)
```

##### JS 宾客工具目录：只有能力集合与注册表门禁，无角色 deny

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/tool_catalog.py:139-158`

```python
def guest_tool_names(
    tool_names: Iterable[str] | None,
    *,
    visual_mode: bool = True,
    orchestration_mode: OrchestrationMode | str = OrchestrationMode.STANDARD,
    role_id: str | None = None,
) -> list[str]:
    """Names callable inside a JS program: no direct tools, visual-gated,
    gated by the run's orchestration mode (dag_* tools are hidden in standard
    mode; Supervisor verdict tools outside dag_guided), and filtered by the
    agent's role allowlist projection when role_id is given."""
    gated = frozenset() if visual_mode else visual_tools()
    hidden = _mode_hidden_tools(orchestration_mode) | config_disabled_tools()
    if role_id is not None:
        hidden = hidden | role_hidden_tools(role_id)
    return [
        name
        for name in _resolve_names(tool_names)
        if not is_direct_only(name) and name not in gated and name not in hidden
    ]
```

##### 模型可见工具的协议分支与筛选

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/tool_catalog.py:161-189`

```python
def wire_tool_schemas(agent: AgentSession, tool_names: list[str] | None) -> list[dict]:
    """Protocol- and orchestration-mode-aware wire projection for one LLM request.

    Traditional: the permitted business schemas (unchanged legacy surface).
    Javascript: ``js_exec`` plus the permitted direct tools only. Tools
    that hard-fail under the agent's orchestration mode are never projected.
    """
    from cloudra.runtime_v2.adapters import legacy_tool_schemas  # lazy: import cycle

    if effective_invocation_protocol(agent) is not InvocationProtocol.JAVASCRIPT:
        schemas = legacy_tool_schemas(tool_names)
    else:
        schemas = [js_exec_schema()]
        direct = [name for name in _resolve_names(tool_names) if is_direct_only(name)]
        if direct:
            schemas.extend(legacy_tool_schemas(direct))
    hidden = (
        _mode_hidden_tools(agent.settings.orchestration_mode)
        | _settings_hidden_tools(agent)
        | config_disabled_tools()
        | role_hidden_tools(agent.role_id)
    )
    if not hidden:
        return schemas
    return [
        schema
        for schema in schemas
        if (schema.get("function") or {}).get("name") not in hidden
    ]
```

##### 执行前权限判断：通配符放行且没有 deny

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/policies/permission.py:18-42`

```python
    async def before_tool(self, ctx: PipelineContext, call: ToolCall) -> PolicyResult:
        from cloudra.tools.capabilities import is_dag_compute_entry
        try:
            compute_entry = is_dag_compute_entry(call.name, call.arguments)
        except ValueError as exc:
            return PolicyResult.block(f"Invalid tool arguments: {exc}")
        if compute_entry and not ctx.capabilities.permissions.write:
            return PolicyResult.block("Compute production requires write permission in the current task")
        tools = set(ctx.capabilities.tools)
        if "*" not in tools and call.name not in tools:
            return PolicyResult.block(
                f"tool {call.name!r} is not in this agent's capabilities "
                f"(available: {sorted(tools)})"
            )
        if not ctx.settings.visual_mode and call.name in visual_tools():
            return PolicyResult.block(
                f"tool {call.name!r} requires visual mode, which is off for this agent; "
                "turn it on with /visual to use vision tools"
            )
        if call.name in role_hidden_tools(ctx.agent.role_id):
            return PolicyResult.block(
                f"tool {call.name!r} is restricted to specific roles and is not "
                f"available to role {ctx.agent.role_id!r}"
            )
        return PolicyResult.allow()
```

进入执行器及返回的后续链，见第 0 节 `LegacyToolExecutor.execute → _LegacyAgentBridge.permission_all → Tool.safe_call → InvocationService._invoke_scoped → TurnPipeline → _commit_turn_output` 的完整源码。对具有完整权限的 coordinator，通用权限位不会替代被丢失的工具 deny。

##### 纯内存复现：实际执行的代码与实际输出

以下复现只创建 Pydantic 对象并调用策略函数，没有创建项目目录、读写真实数据库，也没有执行 bash。命令设置了 `PYTHONDONTWRITEBYTECODE=1`。

```python
import asyncio
from types import SimpleNamespace
from cloudra.runtime_v2.agent_host import AgentHost
from cloudra.runtime_v2.events import EventLog
from cloudra.runtime_v2.policies.base import PipelineContext, ToolCall
from cloudra.runtime_v2.policies.permission import PermissionStage
from cloudra.runtime_v2.roles import RoleRegistry
from cloudra.runtime_v2.schemas import Project, RuntimeSettings
from cloudra.runtime_v2.tool_catalog import guest_tool_names
role = RoleRegistry().update('coordinator', {'tool_policy': {'allow': ['*'], 'deny': ['bash']}})
agent = AgentHost(SimpleNamespace(event_log=EventLog())).build(project=Project(id='audit', name='Audit'), role=role, parent_session_id=None, display_name=None, settings=RuntimeSettings())
ctx = PipelineContext(agent=agent, run_id='audit', settings_snapshot=agent.settings, capabilities=agent.capabilities, inbox_messages=[], emit=lambda *_: None)
verdict = asyncio.run(PermissionStage().before_tool(ctx, ToolCall('audit', 'bash', {'command': 'pwd'})))
print({'configured_deny': role.tool_policy.deny, 'capability_tools': agent.capabilities.tools, 'bash_exposed': 'bash' in guest_tool_names(agent.capabilities.tools), 'permission_verdict': verdict.outcome})
```

打印对象原样：

```text
{'configured_deny': ['bash'], 'capability_tools': ['*'], 'bash_exposed': True, 'permission_verdict': 'allow'}
```

#### 2. [P2] 子 Agent 完成自己的任务，也会因他人的计算被禁止结束

**触发与后果：** schedule_mode=true 的 researcher/explorer 等子 Agent 已完成自己的任务，无自己提交的计算、无自己负责的未竟子任务；同项目另一 session 的计算仍 ready/running，或其终态通知未送达。自己的作业查询正确返回零，但 fallback 按整个项目查作业，于是该 Agent 被 continue_work 阻止结束，并被要求创建本来与自己任务无关的 schedule。若再次结束而没有满足该要求，runner 最终以 completion_no_progress 失败；若创建 timer，会产生无关等待和额外模型唤醒。

**设计根因：** 把“项目有未完成计算”当成“你的任务未完成”。同一后台判断中的 Agent 分支已经让非 coordinator 只看自己负责的后代，计算分支却丢失 session 归属，重新扩大到项目。这里没有涉及科学验收标准。

**最小修法：** coordinator 继续进行项目级后台审计；其他角色只看自己实际负责的工作。已有按 session 计数的接口，删掉对普通子 Agent 的项目级计算 fallback，不添加新状态或更多确认握手。

**现有覆盖缺口：** `tests/test_runtime_v2_schedule_stage.py:73-176` 检查自己的作业与自己的终态通知；`tests/test_runtime_v2_completion_gate.py:616-655` 检查 coordinator 等待项目后台。缺少“无自己待办的子 Agent + 他人计算”的回归。本项为当前源码明确的数据作用域推导，未对真实计算执行动态实验。

本条从纯文本完成意向开始讨论；显式 stop 最终也到达同一 runner 边界，入口和相关分支已在第 0 节 TurnPipeline 源码完整展示。

##### 完成入口：纯文本最终回复形成 stop 意向

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/turn_pipeline.py:541-546`

```python
        if not response.tool_calls:
            # 无工具调用的纯文本最终回复只是结束*意向*：是否允许结束由 runner
            # 收尾前的统一结束门禁裁决（与显式 stop 同一边界，Task 4A）。
            return TurnOutcome(
                decision="stop", content=response.content, reasoning=response.reasoning
            )
```

##### runner 完成边界、门禁、继续工作反馈、失败与最终返回路径

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/agent_runner.py:370-500`

```python
                    finally:
                        await self._publish_new_events(cursor)
                        cursor = len(core.event_log)
                # 响应落上下文：完整 assistant/tool 消息（恰好一次；输入已在
                # 发送前经 commit_input 入投影）。
                await self._commit_turn_output(agent, run_id, outcome)
                if outcome.decision == "stop":
                    # 不变量"RUNNING 的下个轮次 drain 收件箱"只在还有下个轮次时
                    # 成立：轮次中途到达的消息（如异步子 agent 终态回报，其 wake
                    # 对 RUNNING 是 no-op）在 stop 收尾后将无人 drain。收件箱非空
                    # 时续跑一轮而不是收尾。
                    if self._inbox_has_pending(agent):
                        continue
                    # 统一运行结束门禁（Task 4A）：显式 stop 与纯文本最终回复
                    # 都在这里裁决；门禁不放行时绝不 finish_run(succeeded)。
                    explicit_stop = any(
                        call.name == self.pipeline.stop_tool
                        for call, _result in outcome.tool_exchanges
                    )
                    stop_arguments = None
                    if explicit_stop:
                        stop_arguments = next(
                            (
                                call.arguments
                                for call, _result in outcome.tool_exchanges
                                if call.name == self.pipeline.stop_tool
                            ),
                            None,
                        )
                    gate, _source = await self._evaluate_completion_gate(
                        agent,
                        run_id,
                        explicit_stop=explicit_stop,
                        stop_arguments=stop_arguments,
                        candidate_answer=outcome.content,
                    )
                    if gate.action == "continue_work":
                        # Keep the candidate private until the completion gate permits delivery.
                        strike, exhausted = self._track_exit_strike(agent, run_id, gate)
                        if exhausted:
                            notice = (
                                f"[Completion gate] Run ended as failed: {self.max_exit_strikes} "
                                f"exit attempts were rejected without new progress (latest: "
                                f"{gate.reason}). The run was NOT marked complete; send a new "
                                "message to resume with fresh instructions."
                            )
                            self._emit_run_message(agent, run_id, notice)
                            await core.agent_host.finish_run(
                                agent,
                                outcome="failed",
                                error=(
                                    f"completion gate: {self.max_exit_strikes} exit attempts "
                                    f"without progress ({gate.reason})"
                                ),
                                failure_kind=RunFailureKind.COMPLETION_NO_PROGRESS,
                            )
                            await self._deliver_completion(agent)
                            break
                        # 缺口/下一步反馈进下一轮（mailbox 投递即持久审计
                        # agent.message_injected + 下一轮 drain 消费）。
                        # 本 run 正在跑、下一轮就会 drain inbox → 不唤醒。
                        await core.dispatcher.commit_and_deliver(
                            to_session_id=agent.id,
                            project_id=agent.project_id,
                            content=self._gate_feedback_text(gate, strike=strike),
                            sender="completion_gate",
                            wake=WakePolicy.NEVER,
                        )
                        continue
                    if gate.action == "wait_review":
                        # 退出审批请求已在门禁内持久化（同 basis 去重复用）且
                        # Supervisor 已按状态表通知；挂起等裁决，不落终态。
                        await core.agent_host.transition(
                            agent,
                            AgentState.WAITING_APPROVAL,
                            reason="wait_review",
                            run_id=run_id,
                        )
                        # 裁决通知/新消息可能恰在判定期间投递：与 wait_approval
                        # 分支同一防 lost-wakeup 握手，迁移后立即复查收件箱。
                        if self._inbox_has_pending(agent):
                            await core.agent_host.transition(
                                agent,
                                AgentState.RUNNING,
                                reason="review_notification_received",
                                run_id=run_id,
                            )
                            continue
                        # 诚实回执（在收件箱复查之后投递，避免自己的反馈触发
                        # 立刻唤醒空转）：stop 工具只确认收到请求，
                        # stop 实际在等 Supervisor 退出裁决——必须把审批回路
                        # 讲清楚，否则 agent 无法区分 接受/待审/被拒 三种结局。
                        await core.dispatcher.commit_and_deliver(
                            to_session_id=agent.id,
                            project_id=agent.project_id,
                            content=self._wait_review_feedback_text(gate),
                            sender="completion_gate",
                            run_id=run_id,
                            wake=WakePolicy.NEVER,
                        )
                        break
                    # wait_background（有可核实唤醒来源的挂起，不是交付）与
                    # allow_final（审计通过/有效批准/agent 声明）才走到收尾。
                    # Task 5 起 schedule stop 不再无条件 compact——压缩触发只有
                    # 手动 compact / 达到上下文预算 / 真实 overflow 三种。
                    # The compute broker marks a terminal job notified only after
                    # its message is delivered. A notice arriving during the gate
                    # must be read before this run becomes a child's first final
                    # result. Top-level agents retain the existing finish/wake
                    # boundary, which starts a fresh run for late user/child input.
                    # Share the target lock with MessageDispatcher so a delivery
                    # cannot slip between this check and finish_run.
                    async with core.dispatcher.target_lock(agent.id):
                        if agent.parent_session_id and self._inbox_has_pending(agent):
                            continue
                        for stage in getattr(self.pipeline, "stages", ()):
                            hook = getattr(stage, "on_run_end", None)
                            if hook is not None:
                                await hook(agent, explicit_stop=explicit_stop)
                        final_answer = gate.final_answer if gate.final_answer is not None else outcome.content
                        if gate.action == "allow_final" and final_answer:
                            self._emit_run_message(agent, run_id, final_answer)
                        elif gate.action == "wait_background":
                            self._emit_run_message(agent, run_id, gate.reason or "Run paused awaiting background work.")
                        await core.agent_host.finish_run(agent, outcome="succeeded")
                        # CommandBus may enqueue outside MessageDispatcher; keep
                        # the existing post-finish wake handshake for that path.
                        if self._inbox_has_pending(agent):
                            await core.agent_host.wake(agent, runner=core.runner)
                    await self._deliver_completion(agent)
                    break
```

##### 中间层：收集各领域裁决，选择实际结论并返回

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/agent_runner.py:700-771`

```python
    async def _evaluate_completion_gate(self, agent: AgentSession, run_id: str, *, explicit_stop: bool, stop_arguments: dict | None, candidate_answer: str = ""):
        """唯一的运行结束判定边界（Task 4A，计划 §6）。

        显式 stop 与无 tool_calls 的纯文本最终回复都流经这里：各 PolicyStage
        的 ``audit_run_end`` 钩子给出本域判定（dag 交付覆盖 / schedule 后台
        事实核查），无意见的 stage 不参与；多域判定取最保守结果
        （wait_background > wait_review > continue_work > allow_final）。
        没有任何门禁意见时按 agent 声明放行——standard 普通问答可结束，但
        如实标注为声明而非已验证完成。判定结论落 ``agent.completion_gate``
        审计事件。返回 (StopGate, source)。
        """
        from cloudra.runtime_v2.policies.base import PipelineContext

        core = self.core
        try:
            project = core.require_project(agent.project_id)
            workspace_dir = project.workspace_dir
        except Exception:
            workspace_dir = None
        ctx = PipelineContext(
            agent=agent,
            run_id=run_id,
            settings_snapshot=agent.settings.model_copy(deep=True),
            capabilities=agent.capabilities,
            inbox_messages=[],
            emit=self.pipeline._emitter(agent, run_id),
            workspace_dir=workspace_dir,
            notices=core.notices,
        )
        verdicts: list[tuple[Any, str]] = []
        for stage in getattr(self.pipeline, "stages", ()):
            hook = getattr(stage, "audit_run_end", None)
            if hook is None:
                continue
            verdict = await hook(
                ctx, explicit_stop=explicit_stop, stop_arguments=stop_arguments, candidate_answer=candidate_answer
            )
            if verdict is not None:
                verdicts.append((verdict, getattr(stage, "name", "unknown")))
        if verdicts:
            rank = {"wait_background": 0, "wait_review": 1, "continue_work": 2, "allow_final": 3}
            gate, source = min(verdicts, key=lambda item: rank.get(item[0].action, 3))
        else:
            from cloudra.dag.stop_audit import StopGate

            gate = StopGate(
                action="allow_final",
                reason=(
                    "no completion gate applies to this agent; the run ends as an "
                    "agent-declared result (not independently verified)"
                ),
                basis="declared",
            )
            source = "declared"
        core.event_log.append(
            "agent.completion_gate",
            stream="agent",
            project_id=agent.project_id,
            session_id=agent.id,
            run_id=run_id,
            data={
                "action": gate.action,
                "source": source,
                "explicit_stop": explicit_stop,
                "reason": gate.reason,
                "request_id": gate.request_id,
                # 收尾依据（结构化）：投影成 UI 的「已验证完成 / 部分交付 /
                # 未独立验证」。绝不由 reason 文本反推。
                "basis": gate.basis,
            },
        )
        return gate, source
```

##### schedule 结束判定的全部相关分支

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/policies/schedule_stage.py:126-163`

```python
    async def audit_run_end(
        self,
        ctx: PipelineContext,
        *,
        explicit_stop: bool,
        stop_arguments: dict[str, Any] | None = None,
        candidate_answer: str = "",
    ):
        """统一结束门禁的 schedule 判定（runner 收尾前；纯文本最终回复与显式
        stop 同边界，计划 §6）。

        唤醒来源必须可核实：有效 reminder（ReminderBroker 事件投影）、未终态
        子 agent（core.agents 投影）、在算作业（compute.db 权威）。模型的
        "有后台脚本在跑"声明不算数——没有可核实唤醒来源就要求先 schedule。
        """
        from cloudra.dag.stop_audit import StopGate

        core = self.core
        if await self._owned_compute_pending(ctx):
            return StopGate(
                action="wait_background",
                reason="this agent's compute jobs are still active; terminal notifications will wake it",
                basis="background_wait",
            )
        if not getattr(ctx.agent.settings, "schedule_mode", False):
            return None
        if core is not None and await asyncio.to_thread(core.reminders.pending, ctx.agent.id):
            return StopGate(
                action="wait_background",
                reason="a schedule reminder is pending; the stop suspends until it fires",
                basis="background_wait",
            )
        if core is not None and await self._verifiable_background_pending(ctx):
            return StopGate(
                action="continue_work",
                reason=BACKGROUND_WITHOUT_WAKEUP_MESSAGE,
            )
        return StopGate(action="allow_final", reason=DECLARED_COMPLETION_REASON, basis="declared")
```

##### 先正确判断自己的作业，coordinator 单独处理

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/policies/schedule_stage.py:165-175`

```python
    async def _owned_compute_pending(self, ctx: PipelineContext) -> bool:
        if self.core is None or ctx.agent.role_id == "coordinator":
            # ComputeNotifyBroker deliberately parks coordinator notices;
            # it cannot use an owned job as an automatic wake source.
            return False
        from cloudra.persistence.database import ComputeDB
        from cloudra.services.compute_store import acount_waitable_compute_jobs_for_session

        return bool(await acount_waitable_compute_jobs_for_session(
            ComputeDB(), ctx.agent.project_id, ctx.agent.id
        ))
```

##### 自己的作业实际 SQL：同时限定项目和 session

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/compute_store.py:390-414`

```python
async def acount_waitable_compute_jobs_for_session(
    db: ComputeDB, conversation_id: str, session_id: str
) -> int:
    """Owned jobs that still owe an agent either execution or a terminal notice.

    A job can become terminal between the agent's stop call and the broker's
    next poll. Until ``notified_at`` is set, the agent must stay parked so it
    cannot report completion before seeing that job's result.
    """
    if not _db_ready(db):
        return 0

    async def read() -> int:
        async with db.aconnect() as con:
            cur = await con.execute(
                "SELECT COUNT(*) FROM compute_jobs "
                "WHERE conversation_id = ? AND session_id = ? AND ("
                "state IN ('ready', 'running', 'cancel_requested') OR "
                "(state IN ('done', 'failed', 'cancelled') AND notified_at IS NULL))",
                (conversation_id, session_id),
            )
            row = await cur.fetchone()
            return int(row[0]) if row else 0

    return await aretry_on_locked(read)
```

##### 后续 fallback：Agent 与计算两条分支作用域不一致

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/policies/schedule_stage.py:177-189`

```python
    async def _verifiable_background_pending(self, ctx: PipelineContext) -> bool:
        from cloudra.dag.stop_audit import has_running_siblings, pending_compute_jobs_exist
        from cloudra.persistence.database import ConversationDB

        core = self.core
        if await asyncio.to_thread(
            has_running_siblings, core, project_id=ctx.agent.project_id, session_id=ctx.agent.id
        ):
            return True
        return await pending_compute_jobs_exist(
            data_dir=ConversationDB(ctx.agent.project_id).data_dir,
            project_id=ctx.agent.project_id,
        )
```

##### Agent 后台分支：非 coordinator 已只看自己负责的后代

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/dag/stop_audit.py:85-160`

```python
def has_running_siblings(core, *, project_id: str, session_id: str) -> bool:
    """Project agents or launch-group items with unfinished work.

    A parked ancestor must not hold its own child open: that would make the
    parent and child wait on each other after both successful run transitions.
    """
    from cloudra.runtime_v2.agent_host import is_background_parked

    # History probes can release the GIL for SQLite. Freeze registry membership
    # and values before probing rather than traversing a live dict across I/O.
    agents = {
        key: agent.model_copy(deep=True) for key, agent in list(core.agents.items())
    }

    def is_descendant(agent) -> bool:
        seen: set[str] = set()
        owner_id = agent.parent_session_id or agent.requested_by_session_id
        while owner_id and owner_id not in seen:
            if owner_id == session_id:
                return True
            seen.add(owner_id)
            owner = agents.get(owner_id)
            owner_id = (
                owner.parent_session_id or owner.requested_by_session_id
                if owner is not None else None
            )
        return False

    terminal = {"succeeded", "failed", "cancelled"}
    current = agents.get(session_id)
    # Coordinator audits the whole project (including legacy unowned agents).
    # A child must only wait on work it owns, never its active parent/siblings.
    project_wide = current is not None and current.role_id == "coordinator"
    scientific_supervision_pending = False
    if any(
        agent.role_id == "supervisor"
        and agent.id != session_id
        and agent.project_id == project_id
        and agent.state.value not in terminal
        for agent in agents.values()
    ):
        from cloudra.runtime_v2.supervision import pending_supervision_counts

        pending = pending_supervision_counts(project_id)
        scientific_supervision_pending = any(
            pending[kind] for kind in ("call_reviews", "open_drafts", "review_requests")
        )
    if any(
        agent.id != session_id
        and agent.project_id == project_id
        # Scientific review still counts as background work. Notebook tidying
        # alone must not hold delivery open.
        and (agent.role_id != "supervisor" or scientific_supervision_pending)
        and (
            (agent.state.value not in terminal and (project_wide or is_descendant(agent)))
            or (is_descendant(agent) and is_background_parked(core, agent))
        )
        for agent in agents.values()
    ):
        return True
    # A capped launch group can have queued items with no child agent yet.
    # Its first child finishes before admission dispatches the next item.
    return any(
        group.project_id == project_id
        and group.state == "running"
        and (group.pending_count or group.running_count)
        and (
            project_wide
            or group.parent_session_id == session_id
            or (
                group.parent_session_id in agents
                and is_descendant(agents[group.parent_session_id])
            )
        )
        for group in core.launch_groups.groups()
    )
```

##### 计算后台分支：只接收项目，没有 session

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/dag/stop_audit.py:66-82`

```python
async def pending_compute_jobs_exist(*, data_dir, project_id: str) -> bool:
    """Whether compute is active or a terminal result still awaits delivery."""
    from cloudra.persistence.database import ComputeDB
    from cloudra.services.compute_store import (
        acount_pending_compute_jobs,
        pending_terminal_jobs,
    )

    db = ComputeDB(data_dir=data_dir)
    if await acount_pending_compute_jobs(db, project_id):
        return True
    # A completed calculation is still background work until its durable
    # result reaches the agent inbox. Never release the delivery gate first.
    return bool(await asyncio.to_thread(
        pending_terminal_jobs, db, window_seconds=0, limit=1,
        conversation_id=project_id,
    ))
```

##### 项目级活跃作业 SQL

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/compute_store.py:368-387`

```python
async def acount_pending_compute_jobs(db: ComputeDB, conversation_id: str) -> int:
    """指定会话的未竟作业数（含待取消）——stop 门禁的挂起判定口径。

    读路径不建库：中央库不存在（从未提交过作业）即 0。
    """
    if not _db_ready(db):
        return 0

    async def read() -> int:
        async with db.aconnect() as con:
            cur = await con.execute(
                "SELECT COUNT(*) FROM compute_jobs "
                "WHERE state IN ('ready', 'running', 'cancel_requested') "
                "AND conversation_id = ?",
                (conversation_id,),
            )
            row = await cur.fetchone()
            return int(row[0]) if row else 0

    return await aretry_on_locked(read)
```

##### 项目级未送达终态通知查询的完整过滤分支

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/compute_store.py:321-365`

```python
def pending_terminal_jobs(
    db: ComputeDB,
    *,
    window_seconds: float,
    limit: int,
    conversation_id: Optional[str] = None,
    conversation_ids: Optional[Sequence[str]] = None,
) -> list[tuple[str, int, str, Optional[str]]]:
    """终态且未通知的作业：(conversation_id, id, state, session_id)。

    ``window_seconds`` 保留给调用方，查询本身不按结束时间截断。读路径
    不建库：中央库文件不存在（从未提交过作业）时返回空，不创建空文件。
    ``conversation_ids`` 限制在已加载项目内扫描，避免未打开项目的积压
    占满 LIMIT、挡住开着的项目。
    """
    if not _db_ready(db):
        return []
    _ = window_seconds
    if conversation_ids is not None and not conversation_ids:
        return []

    def read() -> list[tuple[str, int, str, Optional[str]]]:
        clauses = (
            "state IN ('done','failed','cancelled') "
            "AND notified_at IS NULL"
        )
        params: list[Any] = []
        if conversation_ids is not None:
            placeholders = ",".join("?" * len(conversation_ids))
            clauses += f" AND conversation_id IN ({placeholders})"
            params.extend(conversation_ids)
        elif conversation_id is not None:
            clauses += " AND conversation_id=?"
            params.append(conversation_id)
        with db.connect() as con:
            return [
                (str(r[0]), int(r[1]), str(r[2]), r[3])
                for r in con.execute(
                    f"""SELECT conversation_id, id, state, session_id FROM compute_jobs
                    WHERE {clauses} ORDER BY id LIMIT ?""",
                    (*params, limit),
                ).fetchall()
            ]

    return retry_on_locked(read)
```

##### 返回给模型的强制 schedule 文案

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/policies/schedule_stage.py:52-59`

```python
BACKGROUND_WITHOUT_WAKEUP_MESSAGE = (
    "Verifiable background work is still pending (a sub-agent is not terminal or a "
    "compute job is unfinished) but no wake-up timer or check is scheduled. Call "
    "`schedule` with a read-only check_command + interval_seconds + timeout_seconds "
    "(preferred) or delay_seconds + message so you wake when the work is actually "
    "done, then stop. Re-confirming stop does not mark the goal complete — without "
    "a scheduled wake-up this run cannot end."
)
```

##### 反复退出的实际计数依据

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/agent_runner.py:773-792`

```python
    def _track_exit_strike(self, agent: AgentSession, run_id: str, gate) -> tuple[int, bool]:
        """同状态重复无进展退出的有界计数（刻意易失 per-run shell 状态）。

        指纹 = 判定理由 + 开放缺口集合：缺口变了算有进展、重新计数；同一缺口
        状态反复退出才累计，达到 ``max_exit_strikes`` 返回 exhausted=True。
        """
        report = gate.report
        gaps = []
        if report is not None:
            gaps = [
                *(getattr(report, "unresolved", None) or []),
                *(getattr(report, "inconclusive", None) or []),
            ]
        fingerprint = gate.reason + "|" + ",".join(
            f"{getattr(gap, 'code', '')}:{getattr(gap, 'target_id', '')}" for gap in gaps
        )
        last = self._exit_strikes.get(agent.id)
        strike = last[2] + 1 if last is not None and last[:2] == (run_id, fingerprint) else 1
        self._exit_strikes[agent.id] = (run_id, fingerprint, strike)
        return strike, strike >= self.max_exit_strikes
```

##### 返回下一轮的缺口与终止失败提示

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/agent_runner.py:809-824`

```python
    def _gate_feedback_text(self, gate, *, strike: int) -> str:
        from cloudra.dag.stop_audit import format_gate_gaps

        lines = [f"[Completion gate] This run cannot finish yet: {gate.reason}"]
        gap_lines = format_gate_gaps(gate.report)
        if gap_lines:
            lines.append("Open gaps:")
            lines.extend(gap_lines)
        lines.append(
            "Next: resolve the items above (for DAG deliveries, bind the supporting "
            "evidence and submit it for review with dag_bind_evidence, close the gap, "
            "or re-declare with delivery_disposition='partial'), then stop again. "
            f"Exit attempt {strike}/{self.max_exit_strikes} without new progress; "
            "repeating the same exit without progress ends the run as failed."
        )
        return "\n".join(lines)
```

实际效果已经在本节第一段 runner 源码体现：continue_work 进入重试反馈分支；达到 max_exit_strikes 后落 failed/completion_no_progress；只有 allow_final 路径才发出最终结果。项目内别人的计算在这里足以成为错误否决条件。

#### 3. [P2] 普通文件编辑仍要求模型搬运内部并发哈希

**触发与后果：** edit 必须由模型填写最近一次 read 返回的完整 expected_sha256；省略立即失败。write 将这个字段默认为 missing，所以整文件覆写漏填时，程序把它当成新建并拒绝。模型必须多次调用、复制 64 字符内部摘要，并承担本应由程序绑定的并发身份。错误哈希导致的失败不能简单归因“模型没照说明填”。

**设计根因：** 将内部并发协议穿透为公开 LLM 输入。读工具已经产生真实快照，准备变更也已经记录 before_sha256，应用前还有程序内部再校验，但公开接口仍要求模型在它们之间转抄哈希。当前用户给定 AGENTS 明确要求哈希/摘要由程序生成、绑定、校验。read→prepare 与 prepare→apply 保护不同时间区间，不能称为重复校验；问题是前者的快照绑定被推给模型，而不是并发保护没有必要。

**最小修法：** 删除公开 expected_sha256，程序绑定当前 session 最近读取的目标快照；继续使用原文唯一匹配、PreparedFileChange、应用前比较和原子替换。该建议保留真实并发保护与已有审批，不用另一种公开版本字段替代哈希。

**现有覆盖缺口：** `tests/test_workspace.py:173-188` 与 `tests/test_runtime_v2_adapters.py:676-702` 固化了由调用方显式提供哈希的接口。应让公开调用不含哈希，同时保留“读取后真实文件发生并发变化仍拒绝覆写”的回归。

工具入口和 Pydantic 入参验证、safe_call、最终结果回传见第 0 节。以下按 read → edit/write → prepare → apply → 返回顺序展示业务链；edit 与 write 两条分支均完整展示。

##### read 公开入参

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Searchtool/read.py:23-38`

```python
class Read_input_schema(input_schema):
    path: str = Field(description="File path. Relative paths resolve against the Agent working directory "
                                  "(falling back to the process cwd); absolute paths inside the working "
                                  "directory are accepted. Missing files report every candidate tried.")
    offset: int | None = Field(
        default=None,
        description="1-based start line; omit to start at the first line",
    )
    limit: int | None = Field(
        default=None,
        description="Number of lines to return; omit to read through EOF",
    )
    focus: str = Field(
        default="auto",
        description="Document focus: auto, text, or images (PDFs only)",
    )
```

##### read 公开输出包括哈希

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Searchtool/read.py:41-53`

```python
class Read_output_schema(output_schema):
    is_success: bool = True
    path: str = ""
    kind: str = ""  # "text" | "image" | "document"
    content: str = ""
    sha256: str = ""
    total_lines: int = 0
    offset: int = 1          # 1-based actual start
    limit: int = 0           # lines actually returned; 0 means unused
    image_path: str = ""     # single image (also set when image_paths has one entry)
    image_paths: list[str] = Field(default_factory=list)  # visual injection list; no cap
    images: list[dict] = Field(default_factory=list)  # inventory: {path, page}
    message: str = ""
```

##### read 工作目录解析

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Searchtool/read.py:66-70`

```python
    def _root(self) -> str:
        root = getattr(self.subagent, "working_directory", None)
        if not root:
            root = os.getcwd()
        return root
```

##### read 失败输出

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Searchtool/read.py:72-73`

```python
    def _fail(self, path: str, message: str) -> Read_output_schema:
        return Read_output_schema(is_success=False, path=path, message=message)
```

##### 读取入口与格式分支，文本结果返回

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Searchtool/read.py:75-114`

```python
    async def tool_call(self, user_input: Read_input_schema, session: Session) -> Read_output_schema:
        path = user_input.path
        suffix = Path(path).suffix.lower()
        root = self._root()
        # 存在性兜底：相对路径同时试工作目录与进程 cwd，绝对路径原样；
        # 命中工作区外的候选不读取（read 保持工作区沙箱），但报错要说清它在哪。
        try:
            absolute = Path(resolve_existing_tool_path(self, path))
        except FileNotFoundError as exc:
            return self._fail(path, str(exc))
        try:
            path = absolute.relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            return self._fail(
                path,
                f"File exists at {absolute} but is outside the working directory "
                f"{root}; move it into the working directory first.",
            )
        try:
            if suffix in IMAGE_EXTS:
                absolute = read_image(root, path)
                return Read_output_schema(
                    is_success=True,
                    path=path,
                    kind="image",
                    image_path=absolute,
                    image_paths=[absolute],
                    message=f"Image loaded: {absolute}.",
                )
            if suffix in PDF_EXTS:
                data = await read_pdf(
                    root, path, user_input.offset, user_input.limit, user_input.focus
                )
                return Read_output_schema(is_success=True, kind="document", **data)
            if suffix in OFFICE_EXTS:
                return self._fail(path, "Only PDF documents are supported.")
            data = await read_text(root, path, user_input.offset, user_input.limit)
            return Read_output_schema(is_success=True, kind="text", **data)
        except (OSError, WorkspaceError, ValueError) as exc:
            return self._fail(path, str(exc))
```

##### 文本分页参数转换

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Searchtool/_text.py:14-19`

```python
def offset_limit_to_slice(offset: int | None, limit: int | None) -> tuple[int, int]:
    if offset is not None and offset < 1:
        raise ValueError("offset is 1-based")
    start_0 = 0 if offset is None else offset - 1
    end_0 = -1 if limit is None else start_0 + limit
    return start_0, end_0
```

##### 读取快照、返回完整哈希给模型

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Searchtool/_text.py:22-50`

```python
async def read_text(
    root: str,
    path: str,
    offset: int | None,
    limit: int | None,
) -> dict:
    start_0, end_0 = offset_limit_to_slice(offset, limit)
    service = WorkspaceService(root)
    snapshot, content, total, actual_start, actual_end = await asyncio.to_thread(
        service.read_text,
        path,
        start_0,
        end_0,
    )
    capped = await cap_observation(content, root=root, stem="read")
    message = ""
    if capped != content:
        message = (
            "Full output at .cloudra/tool_output/; page with `read` `offset`/`limit`."
        )
    return {
        "path": snapshot.relative_path,
        "content": capped,
        "sha256": snapshot.sha256,
        "total_lines": total,
        "offset": actual_start + 1,
        "limit": actual_end - actual_start,
        "message": message,
    }
```

##### 实际读取和行切片

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/workspace.py:302-315`

```python
    def read_text(
        self,
        relative_path: str,
        start_line: int = 0,
        end_line: int = -1,
    ) -> tuple[TextSnapshot, str, int, int, int]:
        snapshot = self.snapshot(relative_path)
        lines = snapshot.content.splitlines(keepends=True)
        total_lines = len(lines)
        actual_start = min(max(start_line, 0), total_lines)
        actual_end = total_lines if end_line == -1 else min(max(end_line, 0), total_lines)
        if actual_start > actual_end:
            raise WorkspaceError(f"Invalid slice range: [{actual_start}:{actual_end}]")
        return snapshot, "".join(lines[actual_start:actual_end]), total_lines, actual_start, actual_end
```

##### 真实文件快照与 SHA256 生成

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/workspace.py:271-300`

```python
    def snapshot(self, relative_path: str) -> TextSnapshot:
        absolute_path = self.resolve_path(relative_path)
        if not absolute_path.exists():
            raise WorkspaceError(f"File does not exist: {relative_path}")
        if not absolute_path.is_file():
            raise WorkspaceError(f"Target is not a regular file: {relative_path}")

        raw = absolute_path.read_bytes()
        if len(raw) > self.max_file_bytes:
            raise WorkspaceError(
                f"File is too large to edit as text ({len(raw)} > {self.max_file_bytes} bytes)"
            )
        has_utf8_bom = raw.startswith(codecs.BOM_UTF8)
        body = raw[len(codecs.BOM_UTF8):] if has_utf8_bom else raw
        if b"\x00" in body:
            raise WorkspaceError(f"Target looks like a binary file: {relative_path}")
        try:
            content = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WorkspaceError(f"File is not valid UTF-8 text: {relative_path}") from exc

        return TextSnapshot(
            relative_path=self._relative_label(absolute_path),
            absolute_path=absolute_path,
            content=content,
            sha256=_sha256(raw),
            mode=stat.S_IMODE(absolute_path.stat().st_mode),
            newline=_newline_style(content),
            has_utf8_bom=has_utf8_bom,
        )
```

##### edit 操作 schema

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Writetool/edit.py:22-38`

```python
class EditOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    old_text: str = Field(
        validation_alias=AliasChoices("old_string", "old_str", "old_text"),
        serialization_alias="old_string",
        description="Original text to replace; must match uniquely by default",
    )
    new_text: str = Field(
        validation_alias=AliasChoices("new_string", "new_str", "new_text"),
        serialization_alias="new_string",
        description="Replacement text",
    )
    replace_all: bool = Field(
        default=False,
        description="Whether to replace every match; default false, and the edit is rejected if there are multiple matches",
    )
```

##### edit 必填内部哈希的公开 schema

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Writetool/edit.py:41-44`

```python
class Edit_input_schema(input_schema):
    path: str = Field(description="Target file path relative to the Agent working directory")
    expected_sha256: str = Field(description="Full-file sha256 returned by the latest read call")
    edits: list[EditOperation] = Field(description="Exact text replacements to apply in order")
```

##### write 默认 missing 的公开 schema

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Writetool/write.py:27-33`

```python
class Write_input_schema(input_schema):
    path: str = Field(description="Target file path relative to the Agent working directory")
    content: str = Field(description="Text content to write")
    expected_sha256: str = Field(
        default="missing",
        description="Pass missing for a new file; for overwrite, pass the sha256 returned by read",
    )
```

##### edit/write 到实际 WorkspaceService 的中间转接

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/workspace_mutation.py:42-48`

```python
def workspace_for_tool(tool: Tool) -> WorkspaceService:
    root = getattr(tool.subagent, "working_directory", None)
    if not root:
        import os

        root = os.getcwd()
    return WorkspaceService(root)
```

##### edit 完整业务调用：转换、准备、失败或应用返回

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Writetool/edit.py:66-136`

```python
    async def tool_call(
        self,
        user_input: Edit_input_schema,
        session: Session,
    ) -> Edit_output_schema:
        service = workspace_for_tool(self)
        # 手写坐标守卫：命中时**照常编辑**，把警告附在返回消息里（不硬拦）。
        guard_warning = next(
            (
                warning
                for edit in user_input.edits
                if (warning := handwritten_coord_warning(edit.new_text, path=user_input.path))
            ),
            None,
        )
        edits = [
            TextEdit(
                old_text=edit.old_text,
                new_text=edit.new_text,
                replace_all=edit.replace_all,
            )
            for edit in user_input.edits
        ]
        try:
            change = await asyncio.to_thread(
                service.prepare_edit,
                user_input.path,
                user_input.expected_sha256,
                edits,
            )
        except WorkspaceConflictError as exc:
            await record_preparation_failure(
                self,
                session,
                user_input.path,
                "conflict",
                str(exc),
            )
            return Edit_output_schema(
                is_written=False,
                filepath=user_input.path,
                status="conflict",
                message=str(exc),
            )
        except (OSError, WorkspaceError) as exc:
            await record_preparation_failure(
                self,
                session,
                user_input.path,
                "failed",
                str(exc),
            )
            return Edit_output_schema(
                is_written=False,
                filepath=user_input.path,
                status="failed",
                message=str(exc),
            )

        out = await execute_prepared_change(
            self,
            service,
            change,
            session,
            action="精确编辑文本文件",
            tool_args=user_input.model_dump(mode="json"),
            output_class=Edit_output_schema,
        )
        if guard_warning and out.is_written:
            out.message = f"{guard_warning}\n\n{out.message}"
        return out
```

##### 实际 edit：模型哈希检查、原文唯一匹配、准备变更

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/workspace.py:317-348`

```python
    def prepare_edit(
        self,
        relative_path: str,
        expected_sha256: str,
        edits: Sequence[TextEdit],
    ) -> PreparedFileChange:
        if not edits:
            raise WorkspaceError("At least one text edit is required")
        snapshot = self.snapshot(relative_path)
        if expected_sha256 != snapshot.sha256:
            raise WorkspaceConflictError(
                f"File has changed; re-read before editing. Current sha256={snapshot.sha256}"
            )

        content = snapshot.content
        had_final_newline = _has_final_newline(content)
        for edit in edits:
            old_text = _normalize_newlines(edit.old_text, snapshot.newline)
            new_text = _normalize_newlines(edit.new_text, snapshot.newline)
            if not old_text:
                raise WorkspaceError("old_text must not be empty")
            matches = content.count(old_text)
            if matches == 0:
                raise WorkspaceConflictError("old_text did not match; re-read the target file")
            if not edit.replace_all and matches != 1:
                raise WorkspaceConflictError(
                    f"old_text matched {matches} times; provide more precise context or set replace_all"
                )
            content = content.replace(old_text, new_text, -1 if edit.replace_all else 1)

        content = _preserve_final_newline(content, had_final_newline, snapshot.newline)
        return self._prepare_change(snapshot, content)
```

##### write 完整业务调用：准备、冲突或应用返回

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Writetool/write.py:55-107`

```python
    async def tool_call(self, user_input: Write_input_schema, session: Session) -> Write_output_schema:
        # 手写坐标守卫：命中时**照常写入**，把警告附在返回消息里让模型意识到
        # 行为不当（不硬拦——改 gjf 关键词等正当编辑不该被误伤）。
        guard_warning = handwritten_coord_warning(user_input.content, path=user_input.path)
        service = workspace_for_tool(self)
        try:
            change = await asyncio.to_thread(
                service.prepare_write,
                user_input.path,
                user_input.content,
                user_input.expected_sha256,
            )
        except WorkspaceConflictError as exc:
            await record_preparation_failure(
                self,
                session,
                user_input.path,
                "conflict",
                str(exc),
            )
            return Write_output_schema(
                is_written=False,
                filepath=user_input.path,
                status="conflict",
                message=str(exc),
            )
        except (OSError, WorkspaceError) as exc:
            await record_preparation_failure(
                self,
                session,
                user_input.path,
                "failed",
                str(exc),
            )
            return Write_output_schema(
                is_written=False,
                filepath=user_input.path,
                status="failed",
                message=str(exc),
            )

        out = await execute_prepared_change(
            self,
            service,
            change,
            session,
            action="新建或整文件覆写文本",
            tool_args=user_input.model_dump(mode="json"),
            output_class=Write_output_schema,
        )
        if guard_warning and out.is_written:
            out.message = f"{guard_warning}\n\n{out.message}"
        return out
```

##### 实际 write：已有文件与新文件全部分支

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/workspace.py:350-400`

```python
    def prepare_write(
        self,
        relative_path: str,
        content: str,
        expected_sha256: str,
    ) -> PreparedFileChange:
        absolute_path = self.resolve_path(relative_path)
        if absolute_path.exists():
            snapshot = self.snapshot(relative_path)
            if expected_sha256 == "missing":
                raise WorkspaceConflictError(
                    f"File already exists; read it first and pass sha256={snapshot.sha256}"
                )
            if expected_sha256 != snapshot.sha256:
                raise WorkspaceConflictError(
                    f"File has changed; re-read before overwriting. Current sha256={snapshot.sha256}"
                )
            normalized = _normalize_newlines(content, snapshot.newline)
            normalized = _preserve_final_newline(
                normalized,
                _has_final_newline(snapshot.content),
                snapshot.newline,
            )
            return self._prepare_change(snapshot, normalized)

        if expected_sha256 != "missing":
            raise WorkspaceConflictError(
                "File does not exist; expected_sha256 must be 'missing' when creating a new file"
            )
        normalized = _normalize_newlines(content, "\n")
        after_bytes = _encode_text(normalized, False)
        self._check_output_size(after_bytes)
        diff = _unified_diff(self._relative_label(absolute_path), None, normalized)
        additions, deletions = _diff_counts(diff)
        return PreparedFileChange(
            change_id=uuid4().hex,
            root=self.root,
            relative_path=self._relative_label(absolute_path),
            absolute_path=absolute_path,
            kind="add",
            before_content=None,
            after_content=normalized,
            before_sha256=None,
            after_sha256=_sha256(after_bytes),
            before_mode=None,
            newline="\n",
            has_utf8_bom=False,
            diff=diff,
            additions=additions,
            deletions=deletions,
        )
```

##### 准备变更时程序自己记录 before/after hash

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/workspace.py:402-429`

```python
    def _prepare_change(
        self,
        snapshot: TextSnapshot,
        after_content: str,
    ) -> PreparedFileChange:
        if after_content == snapshot.content:
            raise WorkspaceError("The edit produced no changes")
        after_bytes = _encode_text(after_content, snapshot.has_utf8_bom)
        self._check_output_size(after_bytes)
        diff = _unified_diff(snapshot.relative_path, snapshot.content, after_content)
        additions, deletions = _diff_counts(diff)
        return PreparedFileChange(
            change_id=uuid4().hex,
            root=self.root,
            relative_path=snapshot.relative_path,
            absolute_path=snapshot.absolute_path,
            kind="update",
            before_content=snapshot.content,
            after_content=after_content,
            before_sha256=snapshot.sha256,
            after_sha256=_sha256(after_bytes),
            before_mode=snapshot.mode,
            newline=snapshot.newline,
            has_utf8_bom=snapshot.has_utf8_bom,
            diff=diff,
            additions=additions,
            deletions=deletions,
        )
```

##### 审批、apply、真实失败分支、附属登记与返回

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/workspace_mutation.py:83-219`

```python
async def execute_prepared_change(
    tool: Tool,
    service: WorkspaceService,
    change: PreparedFileChange,
    session: Session,
    action: str,
    tool_args: dict,
    output_class: type[_OutputT],
) -> _OutputT:
    await tool.record_session_event(
        session,
        "file_change_proposed",
        change.event_data("proposed"),
    )
    approved, denial_reason = await tool.ensure_safety(
        session,
        details=_approval_details(action, change),
        tool_args=tool_args,
    )
    if not approved:
        message = denial_reason or (
            "User declined the file change. "
            "Next: explain to the user why the change was needed, adjust the content, "
            "or choose a different approach."
        )
        await tool.record_session_event(
            session,
            "file_change_declined",
            change.event_data("declined", message),
        )
        return output_class(
            is_written=False,
            filepath=change.relative_path,
            status="declined",
            change_id=change.change_id,
            before_sha256=change.before_sha256,
            after_sha256=change.after_sha256,
            diff=change.diff,
            message=message,
        )

    try:
        await asyncio.to_thread(service.apply, change)
    except WorkspaceConflictError as exc:
        message = str(exc)
        await tool.record_session_event(
            session,
            "file_change_failed",
            change.event_data("conflict", message),
        )
        return output_class(
            is_written=False,
            filepath=change.relative_path,
            status="conflict",
            change_id=change.change_id,
            before_sha256=change.before_sha256,
            after_sha256=change.after_sha256,
            diff=change.diff,
            message=message,
        )
    except (OSError, WorkspaceError) as exc:
        message = str(exc)
        await tool.record_session_event(
            session,
            "file_change_failed",
            change.event_data("failed", message),
        )
        return output_class(
            is_written=False,
            filepath=change.relative_path,
            status="failed",
            change_id=change.change_id,
            before_sha256=change.before_sha256,
            after_sha256=change.after_sha256,
            diff=change.diff,
            message=message,
        )

    await tool.record_session_event(
        session,
        "file_change_applied",
        change.event_data("applied"),
    )
    conversation_id = getattr(tool.subagent, "conversation_id", "default")
    from cloudra.persistence.database import ConversationDB
    from cloudra.services import session_store

    try:
        def register() -> None:
            db = ConversationDB(conversation_id)
            # 文件存在 ≠ 表存在（裸 connect 会留下空库文件），v2 agent 也没有
            # legacy session 行——两者都先补齐，ArtifactService 才肯登记。
            session_store.ensure_session_record(
                db, session.id, getattr(tool.subagent, "agent_id", None)
            )
            from cloudra.persistence.artifacts import ArtifactService

            ArtifactService().register_file(
                conversation_id=conversation_id,
                session_id=session.id,
                source=change.absolute_path,
                allowed_root=service.root,
                name=change.relative_path,
            )

        await asyncio.to_thread(register)
    except (OSError, ValueError, sqlite3.Error) as exc:
        await tool.record_session_event(
            session,
            "artifact_registration_failed",
            {
                "path": change.relative_path,
                "message": str(exc),
            },
        )
    session_key = f"{conversation_id}:{session.id}"
    aggregate_diff = turn_diff_tracker.record_applied(session_key, service, change)
    await tool.record_session_event(
        session,
        "turn_diff_updated",
        {
            "change_id": change.change_id,
            "path": change.relative_path,
            "status": "updated",
            "diff": aggregate_diff,
        },
    )
    return output_class(
        is_written=True,
        filepath=change.relative_path,
        status="applied",
        change_id=change.change_id,
        before_sha256=change.before_sha256,
        after_sha256=change.after_sha256,
        diff=change.diff,
        message="File change written atomically",
    )
```

##### 应用前程序内部并发前提校验

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/workspace.py:437-447`

```python
    def _assert_precondition(self, change: PreparedFileChange) -> None:
        if change.before_sha256 is None:
            if change.absolute_path.exists():
                raise WorkspaceConflictError("File was created during approval; re-read it")
            return

        current = self.snapshot(change.relative_path)
        if current.sha256 != change.before_sha256:
            raise WorkspaceConflictError(
                f"File changed during approval; current sha256={current.sha256}"
            )
```

##### 原子替换前再次校验，实际落盘的完整函数

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/workspace.py:449-498`

```python
    def apply(self, change: PreparedFileChange) -> None:
        if change.root != self.root:
            raise WorkspaceError("Change does not belong to the current working directory")
        absolute_path = self.resolve_path(change.relative_path)
        if absolute_path != change.absolute_path:
            raise WorkspaceConflictError("Target path changed during approval")

        self._assert_precondition(change)

        parent = absolute_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        try:
            parent.resolve().relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceConflictError("Parent directory escaped the workspace during approval") from exc

        payload = _encode_text(change.after_content, change.has_utf8_bom)
        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".cloudra-edit-",
                dir=parent,
                delete=False,
            ) as temp_file:
                temp_path = temp_file.name
                temp_file.write(payload)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.chmod(temp_path, change.before_mode if change.before_mode is not None else 0o644)
            # 临时文件写入可能耗时；替换前再检查一次，缩小覆盖并发用户编辑的窗口。
            self._assert_precondition(change)
            os.replace(temp_path, absolute_path)
            temp_path = None
            if hasattr(os, "O_DIRECTORY"):
                try:
                    directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(directory_fd)
                    finally:
                        os.close(directory_fd)
                except OSError:
                    # 替换本身已经完成；部分文件系统不支持目录 fsync。
                    pass
        finally:
            if temp_path is not None:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass
```

##### is_written 转换为外层真实成功状态

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/workspace_mutation.py:22-36`

```python
class WorkspaceMutationOutput(output_schema):
    is_success: bool = Field(default=False, description="Whether the file write completed; derived from is_written")
    is_written: bool = Field(description="Whether the file write completed")
    filepath: str = Field(description="File path relative to the working directory")
    status: Literal["applied", "declined", "conflict", "failed"] = Field(description="File-change outcome")
    change_id: str = Field(default="", description="ID of this file change")
    before_sha256: str | None = Field(default=None, description="File hash before the change")
    after_sha256: str | None = Field(default=None, description="Candidate or post-write file hash")
    diff: str = Field(default="", description="Unified diff of this change")
    message: str = Field(default="", description="Status or error message")

    @model_validator(mode="after")
    def report_write_success(self) -> "WorkspaceMutationOutput":
        self.is_success = self.is_written
        return self
```

工具随后由第 0 节 LegacyToolExecutor.execute 中 `output.model_dump → ToolResult` 返回，InvocationService 记录 raw result 和 tool.finished，TurnPipeline 返回 exchange，runner 把结果加入会话上下文。公开哈希被删后，这条结果链及真正的并发检查都不需要删掉。

#### 4. 明确排除项与记忆归因

没有将“手动 TS/IRC 已开放，但 Guidance 仍要求走 ts_prepare”的策略矛盾列入缺陷。当前源码确实分别写 accepted 和 disabled，不过历史记忆记录了用户明确允许保留强制文案、只开放入口。不能将用户有意保留的策略当成审计发现自动修掉。

此记忆只用于排除误报；上面三项结论均以本次当前源码为依据。

记忆来源：`/Users/cloudrayyy/.codex/memories/MEMORY.md:238-245`。其中第 238 行是用户原指令摘要，第 243-245 行记录手动提交开放与既有科学保护范围。

对应 rollout ID：`01a13e7c-f64a-7c42-bd96-628b93db10bb`。

对应登记位置：`MEMORY.md:220`，rollout 路径为 `/Users/cloudrayyy/.codex/sessions/2026/10/15/rollout-2026-10-15T15-35-39-01a13e7c-f64a-7c42-bd96-628b93db10bb.jsonl`。本次未重读该 rollout 原文，历史意图应按记忆来源说明。


## 启动器、全局记忆、历史 API：详细证据

### Cloudra 控制面、持久化与界面设计审计证据

审计范围：`persistence/`、API v2 控制面及相关启动流程、`frontend/src/`、知识接口。本文保留 3 个经过当前源码确认并已受控复现的问题。没有修改仓库源码、启动/停止任何服务、提交或取消任何量化计算，也没有运行全套测试。

本文中的代码直接摘自当前工作区，标注原始文件与完整行范围；代码块没有人为省略。运行复现只使用临时文件、内存事件日志和 mock 掉的进程/网络边界。源码审计确认的是可触发的软件行为，不声称生产数据已经遭受这些问题。

#### 1. [P1] 实例复用凭“健康 + 页面”认领身份，忽略用户指定的数据库

**实际触发**：8000 已运行一个健康 Cloudra 实例 A；用户使用不同 data_dir，或显式设置 `CLOUDRA_RUNTIME_STORE` 为数据库 B。启动器先探测端口并决定复用 A，之后才读取 B。复用分支跳过 B 的属主检查，也不创建绑定 B 的新进程，最后打开 A 的页面并返回 0。若旧实例挂载另一 checkout 的前端目录，本次 `--rebuild` 也不会重绑它；同一目录内的重建不在这一结论范围。

**系统设计根因**：健康状态、产品类型和实例身份被合并成一个布尔判断。HTTP 2xx 与普通 React `root` 标记只能说明“对端像一个正常 Cloudra”，不能说明它持有用户请求的数据库，也不能说明它正在服务本次构建的前端。

**最小修复方向**：先解析目标 store，再通过已有 store 排他锁属主路径确认是否可复用；仅复用目标 store 的属主。其他健康 Cloudra 只能按端口占用处理。前端目录不一致必须明确报出，不能让“当前构建成功”伪装成“当前页面已更新”。不需要给模型增加任何参数。

##### 1.1 真实调用链与返回

入口 `web` → `_frontend_or_exit` / `_launch_or_exit` → `launch_browser` → `_pinned_runtime` 或 `_find_api_port` → `_runtime_present` → 健康和 SPA 探测 → 回到 `launch_browser` 才解析 store → 复用时跳过属主检查和 `Popen` → 对既有健康 URL 再探测 → 打开 URL → 返回 0。实际 API 静态目录在 `_build_default_v2_app` 中一次性挂载。

下面保留相关转发、参数选择、影响身份判断的分支和结果返回。前端构建函数一并保留，以说明它确实会执行，但不会重绑既有进程。

###### CLI 入口：接收 --rebuild / --skip-build / host / port

源码：[cloudra/cli.py:103-111](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/cli.py:103)

```python
@cli.command(name="web")
@click.option("--host", default=None, help="Web 服务绑定地址（默认 127.0.0.1；绑到非回环地址后可从网络访问）")
@click.option("--port", type=int, default=None, help="Web 服务绑定端口（默认 8000，被占用时自动向后找空闲端口）")
@click.option("--rebuild", is_flag=True, help="强制重新构建前端")
@click.option("--skip-build", is_flag=True, help="复用已有 frontend/dist 构建")
def web(host, port, rebuild, skip_build):
    """启动 Web 前端（API + SPA 单端口服务）。"""
    sys.exit(_launch_or_exit(_frontend_or_exit(), rebuild=rebuild, skip_build=skip_build,
                             host=host, port=port))
```

###### 前端路径转发

源码：[cloudra/cli.py:83-89](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/cli.py:83)

```python
def _frontend_or_exit():
    from cloudra.web_launcher import _frontend_dir
    try:
        return _frontend_dir()
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)
```

###### 启动转发与 CLI 退出码

源码：[cloudra/cli.py:92-100](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/cli.py:92)

```python
def _launch_or_exit(frontend, **kwargs):
    """启动 Web（API+SPA）；启动前的可预期冲突（主库被别家占着、关 token 绑公网）
    以红色提示 + 退出码 1 收场——这些是环境状态，不该甩 traceback 给用户。"""
    try:
        code = launch_browser(frontend, **kwargs)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)
    sys.exit(code)
```

###### 启动主路径：先复用判定，后读取 store，最后返回

源码：[cloudra/web_launcher.py:315-404](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/web_launcher.py:315)

```python
def launch_browser(
    frontend: Path,
    *,
    rebuild: bool,
    skip_build: bool,
    host: str | None = None,
    port: int | None = None,
) -> int:
    _ensure_fd_limit()
    bind_host = (host or "").strip() or _DEFAULT_BIND_HOST
    from cloudra.services.api_token import require_token_for_bind

    require_token_for_bind(bind_host)
    probe_host = _probe_host(bind_host)
    if port is not None:
        api_port, reused_runtime = _pinned_runtime(bind_host, port)
    else:
        api_port, reused_runtime = _find_api_port(8000, "CLOUDRA_API_PORT", bind_host)
    if not _is_loopback_bind(bind_host):
        print(
            f"[cloudra] warning: binding to non-loopback address {bind_host} — the API is "
            "reachable from the network and the bearer token is the only access control",
            flush=True,
        )
    from cloudra.persistence import paths

    store_path = os.environ.get(
        "CLOUDRA_RUNTIME_STORE",
        str(paths.runtime_db_path()),
    )
    if not reused_runtime:
        # 主库被别家持有时，换端口也起不来（app 的排他 flock）：在拉起子进程、
        # 清除关停 marker 之前就 fail loud，既不留下 doomed 进程也不误启守护。
        _refuse_owned_store(store_path, bind_host=bind_host, probe_host=probe_host)
    _ensure_frontend(frontend, rebuild=rebuild, skip_build=skip_build)
    # 显式启动清除 `cloudra stop` 的持久关停 marker，否则 ensure 拒绝拉起。
    from cloudra.services.daemon_supervisor import clear_daemons_shutdown

    clear_daemons_shutdown()
    ensure_daemons()
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    repo_root = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = f"{repo_root}:{existing_pythonpath}" if existing_pythonpath else repo_root
    env["CLOUDRA_RUNTIME_STORE"] = store_path
    env["CLOUDRA_FRONTEND_SERVE_DIR"] = str(frontend / "dist")
    # 绑定地址传给 app（Host 校验白名单据此放开；绑回环时保持原白名单）。
    env["CLOUDRA_API_BIND_HOST"] = bind_host
    runtime = None
    if reused_runtime:
        print(f"[cloudra] reusing existing Cloudra runtime on port {api_port}", flush=True)
    else:
        print(f"[cloudra] starting web server on {bind_host}:{api_port}...", flush=True)
        runtime = subprocess.Popen(
            _uvicorn_argv(api_port, bind_host),
            env=env,
            # 固定子进程 cwd：`python -m` 会把 cwd 放到 sys.path 最前面，
            # cwd 下一个无 __init__.py 的 `cloudra` 目录会把已安装包遮蔽成
            # namespace 包（__version__ 缺失、子模块却能被 editable finder
            # 加载，报 "unknown location"）。frontend 目录已校验存在且不
            # 含 cloudra 子目录，是确定无遮蔽的工作目录。
            cwd=frontend,
        )
    try:
        _wait_healthy(f"http://{probe_host}:{api_port}/api/v2/runtime/health")
        from cloudra.services.api_token import resolve_api_token

        token = resolve_api_token()
        shown_url = _ui_url(probe_host, api_port, token)
        print(f"[cloudra] web UI: {shown_url}", flush=True)
        if bind_host in _WILDCARD_BIND_HOSTS:
            # 通配绑定常常是「服务在远端、浏览器在别处」（SSH/局域网）：
            # 控制台里的回环 URL 在那台机器上打不开，把对外地址一并给出。
            reachable = _primary_address()
            if reachable:
                print(
                    f"[cloudra] reachable from other machines: "
                    f"{_ui_url(reachable, api_port, token)}",
                    flush=True,
                )
        if os.environ.get("CLOUDRA_NO_BROWSER", "").strip().lower() not in {"1", "true", "yes"}:
            webbrowser.open(shown_url)
        if runtime is None:
            return 0
        return runtime.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        if runtime is not None:
            _terminate_runtime(runtime)
```

###### 显式端口分支

源码：[cloudra/web_launcher.py:171-176](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/web_launcher.py:171)

```python
def _pinned_runtime(bind_host: str, port: int) -> tuple[int, bool]:
    """显式指定的端口：不扫描邻近端口，占用而不可复用时交给 uvicorn 在绑定
    阶段报错（而不是悄悄换端口）。"""
    if not _may_reuse_runtime(bind_host):
        return port, False
    return port, _runtime_present(_probe_host(bind_host), port)
```

###### 默认及环境端口分支

源码：[cloudra/web_launcher.py:179-199](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/web_launcher.py:179)

```python
def _find_api_port(preferred: int, env_name: str, bind_host: str) -> tuple[int, bool]:
    """Return (port, reused_existing_runtime).

    A runtime is only reused when it both serves the API and the built SPA on
    the same port; otherwise we start a fresh single-port runtime on a free
    port so the frontend never points at a stale or foreign server.
    """
    probe_host = _probe_host(bind_host)
    reuse = _may_reuse_runtime(bind_host)
    env_value = os.environ.get(env_name)
    if env_value:
        port = int(env_value)
        return port, reuse and _runtime_present(probe_host, port)
    if _port_is_bindable(bind_host, preferred):
        return preferred, False
    if reuse and _runtime_present(probe_host, preferred):
        return preferred, True
    for port in range(preferred + 1, preferred + 100):
        if _port_is_bindable(bind_host, port):
            return port, False
    raise RuntimeError(f"no free port near {preferred}; set {env_name} explicitly")
```

###### 探测地址转换

源码：[cloudra/web_launcher.py:121-131](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/web_launcher.py:121)

```python
def _probe_host(bind_host: str) -> str:
    """本机侧探测/访问用的地址。

    通配绑定（0.0.0.0/::）在回环上同样可达，用回环探测；绑具体网卡地址时
    回环上根本没有监听，必须用该地址本身。IPv6 字面量加方括号才能拼进 URL。
    """
    if bind_host in _WILDCARD_BIND_HOSTS:
        return "127.0.0.1"
    if ":" in bind_host:
        return f"[{bind_host}]"
    return bind_host
```

###### 回环判断

源码：[cloudra/web_launcher.py:134-135](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/web_launcher.py:134)

```python
def _is_loopback_bind(bind_host: str) -> bool:
    return bind_host in _LOOPBACK_BIND_HOSTS
```

###### 是否允许探测复用

源码：[cloudra/web_launcher.py:138-145](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/web_launcher.py:138)

```python
def _may_reuse_runtime(bind_host: str) -> bool:
    """能否复用已在跑的实例。

    通配绑定不能：探测走回环，而回环探测分辨不出对端绑的是 127.0.0.1 还是
    0.0.0.0——复用会让 `--host 0.0.0.0` 静默失效（用户以为已对外可访问，
    实际只绑在回环上）。回环/具体地址的探测地址就是绑定地址本身，判定可信。
    """
    return bind_host not in _WILDCARD_BIND_HOSTS
```

###### 空闲端口检查

源码：[cloudra/web_launcher.py:148-155](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/web_launcher.py:148)

```python
def _port_is_bindable(bind_host: str, preferred: int) -> bool:
    family = socket.AF_INET6 if ":" in bind_host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((bind_host, preferred))
        except OSError:
            return False
        return True
```

###### 把健康和页面合并为可复用

源码：[cloudra/web_launcher.py:166-168](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/web_launcher.py:166)

```python
def _runtime_present(probe_host: str, port: int) -> bool:
    """同端口既提供 API 又提供已构建 SPA，才算可复用的 Cloudra 实例。"""
    return _runtime_is_healthy(probe_host, port) and _runtime_serves_spa(probe_host, port)
```

###### 健康探测转发

源码：[cloudra/web_launcher.py:158-159](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/web_launcher.py:158)

```python
def _runtime_is_healthy(probe_host: str, port: int) -> bool:
    return api_is_healthy(probe_host, port)
```

###### SPA 探测转发

源码：[cloudra/web_launcher.py:162-163](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/web_launcher.py:162)

```python
def _runtime_serves_spa(probe_host: str, port: int) -> bool:
    return api_serves_spa(probe_host, port)
```

###### 探测目标及页面标记

源码：[cloudra/services/runtime_ownership.py:23-26](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/runtime_ownership.py:23)

```python
_HEALTH_PATH = "/api/v2/runtime/health"
# SPA 挂载点（frontend/index.html 的 #root）：同端口既供 API 又供已构建前端，
# 才构成「可复用实例」的必要条件，与 web_launcher._runtime_present 一致。
_SPA_MARKER = '<div id="root"></div>'
```

###### 健康探测实际只判断 HTTP 状态

源码：[cloudra/services/runtime_ownership.py:45-53](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/runtime_ownership.py:45)

```python
def api_is_healthy(probe_host: str, port: int, *, timeout: float = 1.0) -> bool:
    """``/api/v2/runtime/health`` 是否 2xx。"""
    try:
        with urllib.request.urlopen(
            f"http://{probe_host}:{port}{_HEALTH_PATH}", timeout=timeout
        ) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False
```

###### SPA 探测实际只判断普通 root 标记

源码：[cloudra/services/runtime_ownership.py:56-63](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/runtime_ownership.py:56)

```python
def api_serves_spa(probe_host: str, port: int, *, timeout: float = 1.0) -> bool:
    """同一端口是否提供已构建的前端（可复用性的必要条件）。"""
    try:
        with urllib.request.urlopen(f"http://{probe_host}:{port}/", timeout=timeout) as resp:
            body = resp.read(4096).decode("utf-8", "ignore")
            return 200 <= resp.status < 300 and _SPA_MARKER in body
    except Exception:
        return False
```

###### 健康响应：不携带 store 身份

源码：[cloudra/services/api_v2/routers/runtime.py:28-30](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/api_v2/routers/runtime.py:28)

```python
    @router.get("/api/v2/runtime/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}
```

###### 目标 store 属主检查：只在不复用时调用

源码：[cloudra/web_launcher.py:202-221](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/web_launcher.py:202)

```python
def _refuse_owned_store(store_path: str, *, bind_host: str, probe_host: str) -> None:
    """主库已有属主时拒绝另起实例——端口是否空闲无关。

    app 启动阶段用排他 flock 保证「一个 store 一个属主」，所以另起实例必然在
    启动时撞锁退出；必须在拉起 uvicorn 之前指出占用者，否则用户只看到一句
    "database is already in use"（launchd 自启实例占着主库、它的前端目录又已
    失效时正是这种局面：既不可复用，也不能另起）。归属判定仍以 flock 为准，
    lsof 只用来把 PID/端口查出来。
    """
    lock_path = runtime_api_lock_path(store_path)
    # 持锁者必然创建过锁文件；文件不在（含 data_dir 尚未建立）就是没人持锁，
    # 不能顺手把 data_dir 建出来。
    if not lock_path.is_file() or not is_lock_held(str(lock_path)):
        return
    owner = find_store_owner(store_path, probe_host=probe_host)
    raise RuntimeError(
        describe_store_conflict(
            store_path, owner, reuse_allowed=_may_reuse_runtime(bind_host)
        )
    )
```

###### 当前 checkout 的前端构建，不会重绑旧进程

源码：[cloudra/web_launcher.py:102-118](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/web_launcher.py:102)

```python
def _ensure_frontend(frontend: Path, *, rebuild: bool = False, skip_build: bool = False) -> None:
    dist = frontend / "dist"
    if skip_build:
        if not (dist / "index.html").is_file():
            raise RuntimeError("--skip-build was requested but frontend/dist is missing")
        return
    _check_node(frontend)
    if not (frontend / "node_modules").is_dir():
        print("[cloudra] installing frontend dependencies...", flush=True)
        subprocess.run(_npm_argv() + ["install", "--no-audit", "--no-fund"], cwd=frontend, check=True)
    stale = _frontend_source_newer_than_dist(frontend)
    if rebuild or not (dist / "index.html").is_file() or stale:
        if stale and not rebuild and (dist / "index.html").is_file():
            print("[cloudra] frontend source changed — rebuilding...", flush=True)
        else:
            print("[cloudra] building frontend...", flush=True)
        subprocess.run(_npm_argv() + ["run", "build"], cwd=frontend, check=True)
```

###### 决定是否重构建的实际来源

源码：[cloudra/web_launcher.py:84-99](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/web_launcher.py:84)

```python
def _frontend_source_newer_than_dist(frontend: Path) -> bool:
    dist_index = frontend / "dist" / "index.html"
    if not dist_index.is_file():
        return True
    dist_mtime = dist_index.stat().st_mtime
    for root in (frontend / "src", frontend / "public"):
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.stat().st_mtime > dist_mtime:
                return True
    for name in ("index.html", "vite.config.ts", "package.json"):
        path = frontend / name
        if path.is_file() and path.stat().st_mtime > dist_mtime:
            return True
    return False
```

###### 返回前的探测仍只判断健康状态

源码：[cloudra/web_launcher.py:224-234](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/web_launcher.py:224)

```python
def _wait_healthy(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                if 200 <= resp.status < 300:
                    return
        except Exception:
            pass
        time.sleep(0.25)
    raise RuntimeError(f"runtime did not become healthy at {url}")
```

###### 最终浏览器 URL 构造

源码：[cloudra/web_launcher.py:275-279](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/web_launcher.py:275)

```python
def _ui_url(url_host: str, api_port: int, token: str | None) -> str:
    """访问 URL；认证开启时把 token 放 fragment 里（fragment 不进 HTTP 请求，
    前端启动时读入 sessionStorage 后从地址栏抹掉）。"""
    url = f"http://{url_host}:{api_port}"
    return f"{url}/#token={token}" if token is not None else url
```

###### 既有进程的前端目录在创建应用时绑定

源码：[cloudra/services/api_v2/app.py:543-549](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/api_v2/app.py:543)

```python
        restore_core(core, core.store)
    # Optional single-port browser mode: serve the built SPA from the same
    # uvicorn process.  Static mount is added last so /api/* routes win.
    serve_dir = os.environ.get("CLOUDRA_FRONTEND_SERVE_DIR", "").strip()
    if serve_dir and Path(serve_dir, "index.html").is_file():
        app.mount("/", StaticFiles(directory=serve_dir, html=True), name="frontend")
    return app
```

##### 1.2 已执行的受控复现

复现中模拟“8000 有健康 Cloudra A”，同时给本次启动指定 `/tmp/audit-requested-other-runtime.db` 和另一个 checkout 的前端目录。进程启动、真实网络探测、浏览器和守护行为全部被 mock，不产生服务副作用。调用真实 `launch_browser(..., rebuild=True, skip_build=False)`。

实际输出：

```text
[cloudra] reusing existing Cloudra runtime on port 8000
return = 0
started_requested_runtime = False
checked_requested_runtime_ownership = False
```

复现证明：请求目标 store 不参与复用决策，且整个启动仍报告成功。它没有证明生产实例正在使用错误数据库，也未读取生产项目内容。

#### 2. [P2] 全局记忆压缩用旧副本覆盖整文件，删除期间另一项目成功保存的经验

**实际触发**：项目 A 的 `update_memory` 触发超过默认 4000 字阈值的自动压缩，通过异步 LLM 调用等待返回期间，项目 B 调用同一工具并成功追加一条经验。A 结束等待后，直接用自己的旧副本生成新文件，覆盖 B 的新条目。归档用的同样是 A 的旧副本，因此 B 的经验甚至不在这次归档中。两个工具调用仍都返回成功。

**系统设计根因**：所有项目写同一个全局文件，每次工具调用新建 manager，却用“读整文件 → 异步处理 → 覆盖整文件”实现共享知识更新。异步调用期间可发生合法更新，覆盖时没有保护新增内容。

**最小修复方向**：压缩结果只替换本次读取的前缀；提交时通过文件锁保护重读和写入，把压缩期间新增的条目拼回。不能把等待前的旧副本直接覆盖当前权威文件。另一种更简单的减法是先取消自动破坏性整文件覆盖，持久记录保留完整，再单独处理提示词长度。

##### 2.1 真实调用链与返回

工具注册 → `LegacyToolExecutor.execute`（按 schema 解析并实例化）→ `Tool.safe_call` → `UpdateMemory.tool_call` → `get_memory_manager` → `MemoryManager.__init__` / `_resolve_path` → `paths.memory_path` → `append_lesson` → `_compress_memory` → `_llm_compress`（真实网络 await 或 fallback）→ 旧副本归档和覆盖 → 工具返回 `is_success=True` → 执行器返回 `ToolResult`。

本问题不依赖模型压缩得好不好；只要 await 期间有另一条合法写入，就存在覆盖。下列执行器代码同时保留原有角色分支、schema 转换、异常和返回路径，未用伪代码替代。

###### 实际工具注册

源码：[cloudra/tools/registry.py:550-556](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/registry.py:550)

```python
    ToolRegistration(
        module='cloudra.tools.Writetool.update_memory',
        class_name='UpdateMemory',
        tool_name='update_memory',
        runtime_profiles=frozenset({'desktop', 'android'}),
        summary='Update the project memory through its authorized workflow.',
    ),
```

###### 当前运行内核的实例化、参数转换、调用及结果返回

源码：[cloudra/runtime_v2/adapters.py:1070-1183](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/adapters.py:1070)

```python
    async def execute(self, agent: AgentSession, call: ToolCall) -> ToolResult:
        from cloudra.runtime_v2.subagent_bridge import NATIVE_TOOL_NAMES, handle_native_tool
        from cloudra.tools import get_tools_lst

        if agent.role_id == "supervisor" and (
            not is_direct_only(call.name) or supervisor_access_for(call.name) != "none"
        ):
            return await self._execute_supervisor(agent, call)

        if call.name in NATIVE_TOOL_NAMES:
            return await handle_native_tool(self.core, agent, call)
        if call.name == "agent_hub":
            from cloudra.runtime_v2.hub_bridge import handle_hub_tool

            return await handle_hub_tool(self.core, agent, call)
        if call.name == "schedule":
            return await self.core.reminders.handle(agent, call)

        if is_retired_tool_name(call.name):
            return ToolResult(
                is_success=False,
                summary=hint_unknown_tool(call.name),
            )

        if call.name == "search":
            source = (call.arguments or {}).get("source") or "web"
            if source == "web" and _native_search_adapter_for(agent.settings) is not None:
                return ToolResult(
                    is_success=False,
                    summary=(
                        "Web search is provided natively by the model. "
                        "Call search with source='arxiv' or source='openalex' instead."
                    ),
                )

        entry = next((e for e in get_tools_lst() if e.tool_name == call.name), None)
        if entry is None:
            return ToolResult(
                is_success=False,
                summary=hint_unknown_tool(call.name),
            )
        project = self.core.require_project(agent.project_id)
        # 工具字段的类型是 ToolActorContext（Protocol），声明了该字段的工具直接
        # 经构造器拿到调用者身份（不再需要 object.__setattr__ 绕过 pydantic 校验）；
        # 不声明它的工具（log_parser 等无状态工具）按原样构造。
        if "subagent" in getattr(entry.cls, "model_fields", {}):
            actor = _LegacyAgentBridge(agent, project.workspace_dir)
            tool = entry.instantiate(subagent=actor)
        else:
            tool = entry.instantiate()
        from cloudra.tools.core.permission_model import check_permission
        if not check_permission(_LegacyAgentBridge(agent, project.workspace_dir).permission_all(), tool.tool_permission_all()):
            return ToolResult(is_success=False, summary="Tool requires permissions absent from this task")
        schema_cls = entry.input_schema or LegacyInputSchema
        try:
            parsed = schema_cls.model_validate(call.arguments)
        except ValidationError as exc:
            return ToolResult(is_success=False, summary=validation_feedback(exc))
        from cloudra.runtime_v2.invocation_context import report_tool_progress
        from cloudra.runtime_v2.schemas import ToolProgress

        await report_tool_progress(ToolProgress(
            phase="executing", message="Validated tool inputs; entering tool execution",
            effective_arguments=parsed.model_dump(mode="json"),
        ))
        token = set_session_yolo(agent.settings.yolo)
        try:
            # v2-native user decisions: destructive-tool approvals and ask_user
            # questions go to the kernel PendingBroker (events + futures)
            # instead of the legacy conversation SQLite / event bus.
            async def _approval(**fields):
                return await self.core.pending.request_approval(agent, **fields)

            async def _interaction(prompt: str) -> str:
                return await self.core.pending.request_interaction(agent, prompt)

            from cloudra.base.tools_class import use_approval_handler
            from cloudra.services.ts_pipeline_context import use_runtime_authority
            from cloudra.tools.Interactool.ask_user import use_input_handler
            with use_approval_handler(_approval), use_input_handler(_interaction), use_runtime_authority(self.core):
                output = await tool.safe_call(parsed, Session(id=agent.id, path=""))
            if not isinstance(output, entry.output_schema):
                raise TypeError(f"Tool {call.name!r} returned an undeclared output schema")
            data = output.model_dump(mode="json")
            is_success = bool(data.get("is_success", True))
            if call.name == "bash":
                is_success = is_success and data.get("exit_code", 1) == 0
            summary = json.dumps(data, ensure_ascii=False, allow_nan=False)
        except Exception as exc:
            # An unexpected safe_call fault is not a business failure: package
            # it as structured tool_exception metadata so the invocation
            # service closes the lifecycle with effect_state=unknown.
            # Validation errors above stay ordinary unsuccessful results.
            from cloudra.runtime_v2.event_writer import EventPersistenceError
            from cloudra.runtime_v2.invocation_types import InvocationError

            # safe_call wraps tool exceptions; a failed durable progress write
            # must retain the runtime's non-retryable persistence semantics.
            cause = exc
            while cause is not None:
                if isinstance(cause, EventPersistenceError):
                    raise cause
                cause = cause.__cause__

            logging.getLogger(__name__).exception("Tool execution failed: %s", call.name)
            message = "Tool execution failed internally. The error was logged; report the tool call instead of inspecting application source."
            return ToolResult(
                is_success=False,
                summary=message,
                error=InvocationError(code="tool_exception", message=message, effect_state="unknown"),
            )
        finally:
            reset_session_yolo(token)
        return ToolResult(is_success=is_success, summary=summary, data=data)
```

###### 工具通用转发与异常返回边界

源码：[cloudra/base/tools_class.py:145-157](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/base/tools_class.py:145)

```python
    async def safe_call(self, user_input: input_schema, session: Session) -> output_schema:
        '''
        带有通用异常捕获的工具调用包装器。
        工具执行失败时抛出包含工具名的 RuntimeError，由 runtime_v2 执行边界记录和回传。
        '''
        try:
            return await self.tool_call(user_input, session)
        except Exception as e:
            error_msg = (
                f"[Tool error] {self.tool_name}: {str(e)}. "
                "Fix the arguments or use a different tool, then retry."
            )
            raise RuntimeError(error_msg) from e
```

###### 模型实际填写的输入 schema

源码：[cloudra/tools/Writetool/update_memory.py:20-35](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Writetool/update_memory.py:20)

```python
class UpdateMemory_input_schema(input_schema):
    lesson: str = Field(
        description=(
            "The lesson or skill reminder to record. Keep it concise, specific, and reusable, e.g.: "
            "'Before a Gaussian TS search, run a relaxed scan and save the guess geometry;' "
            "'When parsing a VASP OUTCAR, prefer the MAGMOM column to judge magnetism.'"
        )
    )
    source: str = Field(
        default="",
        description="Source of the lesson, e.g. a sub-agent name, session_id, or task description."
    )
    skill_name: str = Field(
        default="",
        description="Optional skill category tag, e.g. 'dft-calculation', 'literature-search'."
    )
```

###### 工具实际返回的输出 schema

源码：[cloudra/tools/Writetool/update_memory.py:38-41](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Writetool/update_memory.py:38)

```python
class UpdateMemory_output_schema(output_schema):
    is_success: bool = Field(default=True, description="Whether the memory write succeeded")
    result: str = Field(description="Memory-update result")
    word_count: int = Field(default=0, description="Estimated word count of the current MEMORY.md")
```

###### 工具调用新建 manager 并返回成功

源码：[cloudra/tools/Writetool/update_memory.py:55-87](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/Writetool/update_memory.py:55)

```python
    async def tool_call(
        self,
        user_input: UpdateMemory_input_schema,
        session: Session
    ) -> UpdateMemory_output_schema:
        from cloudra.tools.core.memory_scope_guard import find_project_specific_fragments

        fragments = find_project_specific_fragments(user_input.lesson)
        if fragments:
            return UpdateMemory_output_schema(
                is_success=False,
                result=(
                    "Rejected: MEMORY.md is global and injected into every project's Coordinator, "
                    "so lessons must be project-agnostic. These fragments look project-specific: "
                    + "; ".join(fragments)
                    + ". Rewrite the lesson in generic, reusable terms (no absolute paths, project "
                    "names, or job IDs) and call update_memory again."
                ),
            )
        conv_id = getattr(self.subagent, 'conversation_id', None) if self.subagent else None
        manager = get_memory_manager(conversation_id=conv_id)

        result = await manager.append_lesson(
            lesson=user_input.lesson,
            source=user_input.source,
            skill_name=user_input.skill_name,
        )

        return UpdateMemory_output_schema(
            is_success=True,
            result=result,
            word_count=manager._count_words(manager.load()),
        )
```

###### 每次构造新的 manager

源码：[cloudra/persistence/memory.py:207-209](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/memory.py:207)

```python
def get_memory_manager(conversation_id: Optional[str] = None) -> MemoryManager:
    """工厂函数，获取 MemoryManager 实例。"""
    return MemoryManager(conversation_id=conversation_id)
```

###### 自动压缩默认阈值

源码：[cloudra/persistence/memory.py:25-31](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/memory.py:25)

```python

# 默认记忆字数上限（中文字符按 1 个计，英文单词按 1 个计）。
# 超过此阈值时触发自动压缩。
DEFAULT_MEMORY_WORD_LIMIT = 4000

# 压缩后保留的最大字数
DEFAULT_COMPRESSED_WORD_LIMIT = 2000
```

###### 记录 conversation，但解析路径不按项目隔离

源码：[cloudra/persistence/memory.py:37-48](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/memory.py:37)

```python
    def __init__(
        self,
        conversation_id: Optional[str] = None,
        word_limit: int = DEFAULT_MEMORY_WORD_LIMIT,
        compressed_word_limit: int = DEFAULT_COMPRESSED_WORD_LIMIT,
    ):
        self.conversation_id = conversation_id or "default"
        self.word_limit = max(100, word_limit)
        self.compressed_word_limit = max(100, compressed_word_limit)
        self.memory_path = self._resolve_path()
        # LLM 传输层客户端缓存：压缩是低频操作，但没必要每次新建连接池
        self._llm_client: Optional[LLMClient] = None
```

###### 所有项目解析到全局 MEMORY.md

源码：[cloudra/persistence/memory.py:50-54](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/memory.py:50)

```python
    def _resolve_path(self) -> Path:
        """解析记忆文件路径。默认使用全局记忆，跨会话共享。"""
        path = paths.memory_path(data_dir=get_config().data_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
```

###### 全局权威文件路径

源码：[cloudra/persistence/paths.py:118-120](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/paths.py:118)

```python
def memory_path(data_dir: Optional[PathLike] = None) -> Path:
    """全局长期记忆文件（MEMORY.md）路径。"""
    return _root(data_dir) / "memory" / "MEMORY.md"
```

###### 路径根目录转发

源码：[cloudra/persistence/paths.py:23-24](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/paths.py:23)

```python
def _root(override: Optional[PathLike]) -> Path:
    return Path(override) if override is not None else _resolve_data_dir()
```

###### 默认数据根目录解析

源码：[cloudra/persistence/paths.py:16-20](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/paths.py:16)

```python
def _resolve_data_dir() -> Path:
    """从全局配置惰性解析数据根目录。"""
    from cloudra.infra.config import get_config

    return Path(get_config().data_dir)
```

###### 读取前的存在性判断

源码：[cloudra/persistence/memory.py:56-58](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/memory.py:56)

```python
    def exists(self) -> bool:
        """记忆文件是否存在。"""
        return self.memory_path.exists()
```

###### 读取当前整文件

源码：[cloudra/persistence/memory.py:60-68](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/memory.py:60)

```python
    def load(self) -> str:
        """加载记忆文件内容；不存在时返回空字符串。"""
        if not self.exists():
            return ""
        try:
            return self.memory_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[MemoryManager] 读取 MEMORY.md 失败: {e}")
            return ""
```

###### 阈值计算

源码：[cloudra/persistence/memory.py:70-78](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/memory.py:70)

```python
    def _count_words(self, text: str) -> int:
        """估算字数：中文字符 + 英文单词分别计数。"""
        if not text:
            return 0
        # 中文字符
        cn_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        # 英文单词：连续字母/数字序列
        en_words = len(re.findall(r"[a-zA-Z0-9]+", text))
        return cn_chars + en_words
```

###### 读改写追加与触发自动压缩

源码：[cloudra/persistence/memory.py:80-121](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/memory.py:80)

```python
    async def append_lesson(
        self,
        lesson: str,
        source: str = "",
        skill_name: str = "",
    ) -> str:
        """追加一条经验到 MEMORY.md，并在超限时自动压缩。

        Args:
            lesson: 经验/技能提醒的具体内容。
            source: 来源，例如子 Agent 名称、session_id、任务描述。
            skill_name: 可选的技能分类标签。

        Returns:
            操作结果描述。
        """
        if not lesson or not lesson.strip():
            return "没有可记录的内容。"

        current_text = self.load()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        skill_tag = f" [{skill_name}]" if skill_name else ""

        entry = (
            f"\n## Lesson{skill_tag} ({timestamp})\n\n"
            f"- **Source**: {source or 'Coordinator'}\n"
            f"- **Lesson**: {lesson.strip()}\n"
        )

        if not current_text.strip():
            current_text = "# Cloudra Coordinator Memory\n\n" + entry
        else:
            current_text = current_text.rstrip() + "\n" + entry

        self.memory_path.write_text(current_text, encoding="utf-8")

        word_count = self._count_words(current_text)
        if word_count > self.word_limit:
            await self._compress_memory()
            return f"已记录经验并触发记忆压缩（原字数 {word_count}）。"

        return f"已记录经验（当前记忆字数 {word_count}）。"
```

###### await 后用旧副本归档和覆盖

源码：[cloudra/persistence/memory.py:123-149](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/memory.py:123)

```python
    async def _compress_memory(self) -> None:
        """当记忆超过字数上限时，调用 LLM 压缩为核心原则。"""
        current_text = self.load()
        if not current_text.strip():
            return

        compressed = await self._llm_compress(current_text)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        new_content = (
            "# Cloudra Coordinator Memory\n\n"
            f"_（以下内容由历史经验自动压缩生成，更新时间：{timestamp}）_\n\n"
            f"{compressed.strip()}\n"
        )

        # 保留原始记忆的归档副本
        archive_path = self.memory_path.with_suffix(".archive.md")
        archive_entry = (
            f"\n\n# Archived memory before {timestamp}\n\n{current_text}"
        )
        with open(archive_path, "a", encoding="utf-8") as f:
            f.write(archive_entry)

        self.memory_path.write_text(new_content, encoding="utf-8")
        print(
            f"[MemoryManager] MEMORY.md 已自动压缩并归档到 {archive_path}"
        )
```

###### LLM 等待及各返回分支

源码：[cloudra/persistence/memory.py:151-189](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/memory.py:151)

```python
    async def _llm_compress(self, text: str) -> str:
        """调用 FOLLOWER 配置的大模型把记忆压缩成核心原则。"""
        from cloudra.infra.codex_auth import is_codex_url

        cfg = get_config().follower
        model = cfg.model
        base_url = cfg.url
        api_key = cfg.key

        if not model or not base_url or (not api_key and not is_codex_url(base_url)):
            # 未配置 LLM 时做简单的启发式截断
            return self._fallback_compress(text)

        prompt = (
            "你正在维护一个 AI 科研助手的长期记忆库。以下内容是 Coordinator 在多次任务中"
            "积累的经验、技能提醒和失败教训。请把它们压缩成一份精简的“核心原则”列表，"
            "保留最重要的判断标准、常用工具组合、常见陷阱和最佳实践。"
            "去掉具体的时间戳和重复内容，用条目式输出。总字数控制在 {limit} 字以内。\n\n"
            "--- 原始记忆 ---\n\n{text}\n\n"
            "--- 核心原则 ---"
        ).format(limit=self.compressed_word_limit, text=text[:12000])

        try:
            if self._llm_client is None:
                self._llm_client = LLMClient(api_key=api_key, base_url=base_url)
            response = await self._llm_client.create(
                model=model,
                messages=[
                    {"role": "system", "content": "你是一个专门整理科研助手长期记忆的助手。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=1.0,  # 大量模型只接受 temperature=1
                max_tokens=2000,
            )
            result = response.choices[0].message.content
            return result.strip() if result else self._fallback_compress(text)
        except Exception as e:
            print(f"[MemoryManager] LLM 压缩失败: {e}，使用启发式压缩。")
            return self._fallback_compress(text)
```

###### 压缩失败或未配置时的返回分支

源码：[cloudra/persistence/memory.py:191-204](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/persistence/memory.py:191)

```python
    def _fallback_compress(self, text: str) -> str:
        """未配置 LLM 时的启发式压缩：只保留最近的条目。"""
        lines = text.splitlines()
        # 保留标题和最近约 compressed_word_limit 字的内容
        kept = []
        total = 0
        for line in reversed(lines):
            w = self._count_words(line)
            if total + w > self.compressed_word_limit:
                break
            kept.append(line)
            total += w
        kept.reverse()
        return "\n".join(kept) if kept else "（记忆内容已压缩）"
```

##### 2.2 已执行的确定性复现

仅使用临时目录的 `MEMORY.md`，不实例化生产配置；两个真实 `MemoryManager` 方法共享这个临时文件。A 的压缩替身在读取旧文本后停在一个 `asyncio.Event`，模拟真实 LLM 等待；随后 B 正常调用 `append_lesson`。确认 B 已写入，再放行 A。

实际结果：

```text
second_call_result = 已记录经验（当前记忆字数 272）。
lesson_b_before_compaction_finishes = True
lesson_b_after_compaction_finishes = False
first_call_result = 已记录经验并触发记忆压缩（原字数 254）。
```

阈值在复现中缩小以避免大文本，交错顺序和覆盖逻辑均为当前真实方法。复现验证了确定的数据丢失，不依赖真实 API 或模型输出措辞，也不声称生产记忆已经丢失。

#### 3. [P2] transcript 先截最后 500 条所有事件，再筛消息，可能把非空对话返回为空

**实际触发**：一条用户提问之后产生至少 500 条工具/状态事件，再读取 `/api/v2/agents/{session_id}/transcript`。接口未指定消息类型和上限，沿用 `query_session` 的 `limit=500, tail=True`；用户提问先被窗口截掉，之后才筛选消息，因此成功返回 `messages=[]`。响应没有游标、截断标志或警告，无法区分“没有对话”和“查询窗口没有覆盖对话”。

**系统设计根因**：用于最近事件展示的隐含默认窗口，被当作对话记录查询。筛选顺序使工具噪声决定用户消息是否存在于响应，消息是否仍然持久化完全不影响接口结论。

**最小修复方向**：在事件查询层先限定 `agent.message_injected` 和 `agent.message_emitted`。完整 transcript 用现有事件迭代器读取或导出；如果确实只提供一页，应明确提供游标和截断语义，不能静默丢掉旧对话。

##### 3.1 真实调用链与返回

FastAPI transcript handler → `require_agent` → worker 内 `EventLog.query_session`（默认 500、tail）→ `_query` → `_read_snapshot`（缓存/持久前缀选择）→ 必要时 `RuntimeStore.read_events` → `RuntimeStore.iter_events`（数据库过滤/排序）→ `_query` 最终截取最后 500 条 → handler 再筛消息 → 普通 JSON 成功返回。

下面保留查询中的真实缓存和存储分支。内存复现不触发持久层，生产持久层也有相同默认截断结果。

###### HTTP 入口：取窗口之后才筛选消息

源码：[cloudra/services/api_v2/routers/agents.py:38-55](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/api_v2/routers/agents.py:38)

```python
    @router.get("/api/v2/agents/{session_id}/transcript", dependencies=ctx.protected)
    async def agent_transcript(session_id: str) -> dict[str, Any]:
        agent = ctx.core.require_agent(session_id)
        messages = []
        events = await asyncio.to_thread(ctx.core.event_log.query_session, session_id)
        for event in events:
            if event.type in {"agent.message_injected", "agent.message_emitted"}:
                data = event.data
                messages.append(
                    {
                        "message_id": data.get("message_id"),
                        "sender": data.get("sender"),
                        "content": data.get("content"),
                        "event_id": event.event_id,
                        "created_at": event.created_at.isoformat(),
                    }
                )
        return {"session_id": session_id, "agent_id": agent.role_id, "messages": messages}
```

###### 存在性校验与 agent 返回

源码：[cloudra/runtime_v2/core.py:405-409](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/core.py:405)

```python
    def require_agent(self, session_id: str) -> AgentSession:
        agent = self.agents.get(session_id)
        if agent is None:
            raise CommandRejected("not_found", f"unknown agent session {session_id!r}")
        return agent
```

###### query_session 默认窗口和转发

源码：[cloudra/runtime_v2/events.py:362-374](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/events.py:362)

```python
    def query_session(
        self,
        session_id: str,
        *,
        run_id: str | None = None,
        after_session_seq: int = 0,
        before_session_seq: int | None = None,
        types: Iterable[str] | None = None,
        limit: int | None = 500,
        tail: bool = True,
    ) -> list[EventEnvelope]:
        return self._query(session_id=session_id, run_id=run_id, after_session_seq=after_session_seq,
                           before_session_seq=before_session_seq, types=types, limit=limit, tail=tail)
```

###### 缓存/持久数据合并及最终截断

源码：[cloudra/runtime_v2/events.py:424-438](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/events.py:424)

```python
    def _query(self, *, limit, tail, **filters) -> list[EventEnvelope]:
        wanted = filters.get("types")
        filters["types"] = frozenset(wanted) if wanted is not None else None
        store, older, resident = self._read_snapshot(filters)
        extra = [event for event in resident if self._matches(event, filters)]
        if tail and limit is not None and len(extra) >= limit:
            return extra[-limit:]
        durable = []
        if older is not None:
            missing = limit - len(extra) if tail and limit is not None else limit
            durable = store.read_events(limit=missing, tail=tail, **older)
        matched = durable + extra
        if limit is None:
            return matched
        return matched[-limit:] if tail else matched[:limit]
```

###### 缓存与持久前缀的完整选择分支

源码：[cloudra/runtime_v2/events.py:376-422](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/events.py:376)

```python
    def _read_snapshot(self, filters):
        """Pin a lazy resident suffix and bound only the older, uncached prefix."""
        with self._lock:
            store = self._store
            resident = islice(iter(self._events), len(self._events))
            if store is None or self._base_index == 0:
                return store, None, resident
            cached_durable = self._events[:self._durable_count - self._base_index]
            older = dict(filters)
            session_id = filters.get("session_id")
            project_id = filters.get("project_id")
            if project_id is None and filters.get("after_seq", 0):
                boundaries = dict(self._durable_projects)
                for event in cached_durable:
                    if event.project_id in boundaries:
                        boundaries[event.project_id] = min(boundaries[event.project_id], event.seq - 1)
                if max(boundaries.values(), default=0) <= filters["after_seq"]:
                    return store, None, resident
            if session_id is not None:
                boundary = self._durable_sessions.get(session_id, 0)
                for event in cached_durable:
                    if event.session_id == session_id and event.session_seq is not None:
                        boundary = min(boundary, event.session_seq - 1)
                        break
                before = filters.get("before_session_seq")
                boundary = min(boundary, before) if before is not None else boundary
                if boundary <= max(0, filters.get("after_session_seq", 0)):
                    return store, None, resident
                # Session sequences pin the prefix without a global row OFFSET.
                older["before_session_seq"] = boundary
            elif project_id is not None:
                boundary = self._durable_projects.get(project_id, 0)
                for event in cached_durable:
                    if event.project_id == project_id:
                        boundary = min(boundary, event.seq - 1)
                        break
                before = filters.get("before_seq")
                boundary = min(boundary, before) if before is not None else boundary
                if boundary <= filters.get("after_seq", 0):
                    return store, None, resident
                older["before_seq"] = boundary
            else:
                boundaries = dict(self._durable_projects)
                for event in cached_durable:
                    boundaries[event.project_id] = min(boundaries[event.project_id], event.seq - 1)
                older["before_seqs"] = boundaries
        return store, older, resident
```

###### 实际事件匹配条件

源码：[cloudra/runtime_v2/events.py:440-451](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/events.py:440)

```python
    @staticmethod
    def _matches(event, filters) -> bool:
        return (
            (filters.get("project_id") is None or event.project_id == filters["project_id"])
            and (filters.get("session_id") is None or event.session_id == filters["session_id"])
            and (filters.get("run_id") is None or event.run_id == filters["run_id"])
            and event.seq > filters.get("after_seq", 0)
            and (filters.get("before_seq") is None or event.seq <= filters["before_seq"])
            and (event.session_seq or 0) > filters.get("after_session_seq", -1)
            and (filters.get("before_session_seq") is None or (event.session_seq or 0) <= filters["before_session_seq"])
            and (filters.get("types") is None or event.type in filters["types"])
        )
```

###### 持久读取转发与顺序恢复

源码：[cloudra/runtime_v2/persistence.py:456-458](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/persistence.py:456)

```python
    def read_events(self, *, tail: bool = False, **filters) -> list[EventEnvelope]:
        events = list(self.iter_events(tail=tail, **filters))
        return list(reversed(events)) if tail else events
```

###### 数据库查询执行与事件返回

源码：[cloudra/runtime_v2/persistence.py:344-454](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/persistence.py:344)

```python
    def iter_events(
        self, *, project_id: str | None = None, session_id: str | None = None,
        run_id: str | None = None,
        after_seq: int = 0, before_seq: int | None = None,
        after_session_seq: int = -1, before_session_seq: int | None = None,
        types: Iterable[str] | None = None, stop_index: int | None = None,
        start_index: int = 0,
        last_seqs: dict[str, int] | None = None,
        before_seqs: dict[str, int] | None = None,
        limit: int | None = None, tail: bool = False,
    ) -> Iterator[EventEnvelope]:
        """Stream a fixed history prefix; callers consume in a worker thread.

        Payloads are decoded one at a time, including large raw tool outputs.
        SQL pagination limits allocations before JSON decoding.
        """
        if stop_index is not None and stop_index <= 0:
            return
        conditions, params = [], []
        for column, value in (("project_id", project_id), ("session_id", session_id), ("run_id", run_id)):
            if value is not None:
                conditions.append(f"{column} = ?")
                params.append(value)
        conditions.append("seq > ?")
        params.append(after_seq)
        if before_seq is not None:
            conditions.append("seq <= ?")
            params.append(before_seq)
        if session_id is not None and after_session_seq >= 0:
            conditions.append("session_seq > ?")
            params.append(after_session_seq)
        if before_session_seq is not None:
            conditions.append("session_seq <= ?")
            params.append(before_session_seq)
        if types is not None:
            wanted = tuple(types)
            if not wanted:
                return
            conditions.append("type IN (" + ",".join("?" for _ in wanted) + ")")
            params.extend(wanted)
        if last_seqs:
            # A missing project postdates the snapshot and is replayed from 0.
            conditions.append("(" + " OR ".join(
                ["(project_id = ? AND seq > ?)" for _ in last_seqs]
                + ["project_id NOT IN (" + ",".join("?" for _ in last_seqs) + ")"]
            ) + ")")
            for key, seq in last_seqs.items():
                params.extend((key, seq))
            params.extend(last_seqs)
        if before_seqs is not None:
            boundaries = [(key, seq) for key, seq in before_seqs.items() if seq > 0]
            if not boundaries:
                return
            conditions.append("(" + " OR ".join(
                "(project_id = ? AND seq <= ?)" for _ in boundaries
            ) + ")")
            for key, seq in boundaries:
                params.extend((key, seq))
        order = "DESC" if tail else "ASC"
        # Match pagination to the existing ordered scope indexes. Global
        # replay alone uses rowid to preserve causality across projects.
        column = "session_seq" if session_id is not None else "seq" if project_id is not None else "rowid"
        column_index = {"session_seq": 6, "seq": 5, "rowid": 10}[column]
        with self._connect() as con:
            upper_rowid = con.execute("SELECT COALESCE(MAX(rowid), 0) FROM events").fetchone()[0]
            if stop_index is not None:
                row = con.execute("SELECT rowid FROM events ORDER BY rowid LIMIT 1 OFFSET ?", (stop_index - 1,)).fetchone()
                if row is not None:
                    upper_rowid = row[0]
            lower_rowid = 0
            if start_index > 0:
                row = con.execute("SELECT rowid FROM events ORDER BY rowid LIMIT 1 OFFSET ?", (start_index - 1,)).fetchone()
                if row is None:
                    return
                lower_rowid = row[0]
        conditions.append("rowid <= ?")
        params.append(upper_rowid)
        conditions.append("rowid > ?")
        params.append(lower_rowid)
        position = None
        remaining = limit
        while remaining is None or remaining > 0:
            page_limit = min(500, remaining) if remaining is not None else 500
            cursor_condition = "" if position is None else f" AND {column} {'<' if tail else '>'} ?"
            sql = (
                "SELECT event_id, stream, project_id, session_id, run_id, seq, session_seq, type, data, created_at, rowid "
                "FROM events WHERE " + " AND ".join(conditions)
                + cursor_condition
                + f" ORDER BY {column} {order} LIMIT ?"
            )
            # Close before yielding: successive pages may be consumed by
            # different asyncio worker threads. Cap bytes as well as row count.
            rows, page_bytes = [], 0
            with self._connect() as con:
                page_params = [*params, *([position] if position is not None else []), page_limit]
                cursor = con.execute(sql, page_params)
                while len(rows) < page_limit:
                    row = cursor.fetchone()
                    if row is None:
                        break
                    rows.append(row)
                    page_bytes += len(row[8])
                    if page_bytes >= 512 * 1024:
                        break
            if not rows:
                break
            position = rows[-1][column_index]
            for row in rows:
                yield self._envelope(row)
            if remaining is not None:
                remaining -= len(rows)
```

###### 数据库行转成实际事件字段

源码：[cloudra/runtime_v2/persistence.py:289-296](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/persistence.py:289)

```python
    @staticmethod
    def _envelope(row) -> EventEnvelope:
        return EventEnvelope.model_validate({
            "event_id": row[0], "stream": row[1], "project_id": row[2],
            "session_id": row[3], "run_id": row[4], "seq": row[5],
            "session_seq": row[6], "type": row[7],
            "data": json.loads(row[8]), "created_at": row[9],
        })
```

###### 持久查询连接边界

源码：[cloudra/runtime_v2/persistence.py:237-246](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/persistence.py:237)

```python
    @contextlib.contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=30.0)
        try:
            con.execute("PRAGMA busy_timeout=30000;")
            con.execute("PRAGMA synchronous=NORMAL;")
            with con:
                yield con
        finally:
            con.close()
```

##### 3.2 已执行的最小复现

使用真实 `EventLog` 和真实 router endpoint；日志先追加一条 `agent.message_injected`（内容为 `Original research question`），再追加 500 条 `tool.finished`。调用真实 transcript handler，另以 `types={消息类型}, limit=None` 读取权威日志作对照。

实际输出：

```text
authoritative_message_count = 1
returned_message_count = 0
response_keys = ['session_id', 'agent_id', 'messages']
```

没有启动 HTTP 服务或 Agent，没有读取生产数据库。这个 API 在真实前端不是当前聊天懒加载的主入口，因此本条不能扩张成“当前聊天界面已丢全部历史”；它确认的是公开 transcript 接口本身会无提示遗漏对话。

#### 审计边界及记忆来源

当前 SSE 有界缓存、历史懒加载和完成状态展示已核对，没有把过去已修问题作为现存问题重复报告。相对路径向 server cwd 回退未列入确认项：该行为在当前代码中有明确契约，`read` 另有工作区约束；本文不靠这个候选凑数。

本次用于确定审计方向的历史记忆仅有：

- `MEMORY.md:140-147`：此前 SSE/历史窗口修复及其限制；对应 rollout ID `01a14503-8ed0-7091-8c84-e274892b3d84`。
- `MEMORY.md:1192-1198`：源代码、生成 dist、实际服务目录需分开判断；对应 rollout ID `01a10703-e48e-7b60-b980-7e6199fd98f3`。

三个确认问题的结论均来自本次当前源码和上述受控复现，不把记忆中的旧实例状态当作当前生产事实。

## 知识检索补扫

### 知识检索补充审计：来源故障被标成可用

**触发与后果。** 已注册 chem-kb 等知识来源，但本次查询抛异常，例如数据库不可读或正文数据损坏。来源异常被记录后丢弃，Agent 最终仍收到 `is_success=True`、`library=[]`、`sources_status.library="available"`。知识库文件缺失也会返回空结果，随后同样被标为 available。Agent 无法分清“检索成功但没有命中”和“该来源根本没有被成功检索”。

**根因。** 聚合层只返回命中列表，丢掉本次来源执行状态；展示层再用“是否注册过 provider”推断当前可用性。注册事实不是查询成功证据。

**最小修复。** 保留其他来源成功返回的结果，同时把故障来源的本次错误传回；不要因一个来源失败而让全部检索失败，也不要把故障来源标为 available。无需增加模型要填写的协议字段。

**边界。** 这是来源状态失真，不是科学证据放行，也没有证明它绕过 TS/IRC 或 DAG 验收。本次仅摘录当前源码；未运行真实检索、外部请求或生产数据库操作，未改仓库源码。下面按入口、调用、错误处理、结果返回顺序列出相关代码。

#### 1. AgentHub 搜索入口：keyword 转换后实际调用知识检索

源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/hub_bridge.py:453-472`

```python
async def _search(core, author: AgentSession, args: dict[str, Any]) -> ToolResult:
    keyword = str(args.get("keyword") or "").strip()
    limit = int(args.get("limit") or 20)
    scanned = await asyncio.to_thread(_posts, core, author.project_id, limit=_SEARCH_SCAN_LIMIT)
    scored = []
    for post in scanned:
        score = max(
            _fuzzy_score(keyword, post["topic"]),
            _fuzzy_score(keyword, post["content"]) * 0.9,
        )
        if score >= _FUZZY_FLOOR:
            post["score"] = round(score, 3)
            scored.append((score, post["seq"], post))
    scored.sort(key=lambda item: (-item[0], -item[1]))
    posts = [post for _, _, post in scored[:limit]]
    # The library layer: registered knowledge providers (GraphRAG plugins)
    # are queried on every hub search — same tool, no extra interface.
    from cloudra.runtime_v2.knowledge import render_library_hits, search_library

    library = await search_library(keyword, limit=5)
```

#### 2. 来源执行与吞错：失败来源被跳过，返回值只有命中列表

源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/knowledge.py:131-161`

```python
async def search_library(query: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """Query every registered provider; merge, rank, and cap the hits.

    A broken provider is logged and skipped — it must never break a hub
    search.  Sync providers run in a worker thread (never block the loop).
    """
    hits: list[dict[str, Any]] = []
    for provider in list(_providers):
        name = str(getattr(provider, "name", type(provider).__name__))
        try:
            if asyncio.iscoroutinefunction(getattr(provider, "search", None)):
                raw = await provider.search(query, limit=limit)
            else:
                raw = await asyncio.to_thread(provider.search, query, limit=limit)
            if inspect.isawaitable(raw):
                raw = await raw
        except Exception:
            logger.exception("knowledge provider %s search failed", name)
            continue
        for item in raw or []:
            entry = _normalize(item, name)
            if entry is not None:
                hits.append(entry)
    hits.sort(
        key=lambda e: (
            _LEVEL_RANK.get(e["evidence_level"], 3),
            e["falsified"],
            -e["score"],
        )
    )
    return hits[:limit]
```

#### 3. 返回状态：只按注册情况标 available，再把空 library 包装返回

源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/hub_bridge.py:497-530`

```python
    forum_line = (
        f"Keyword '{keyword}' fuzzy-matched {len(posts)} post(s) (scanned the latest {len(scanned)})."
        if posts
        else f"Keyword '{keyword}' had no forum hits."
    )
    sources_status = {
        "project_posts": "available",
        "library": "available" if _providers_present() else (
            "no_hits" if not library else "available"
        ),
        "skills": "available" if matched_skills else "no_hits",
    }

    summary_parts = [forum_line]
    if matched_skills:
        skill_lines = []
        for sk in matched_skills:
            skill_lines.append(
                f"- **{sk['name']}**: {sk['description']}\n"
                f"  -> Load via: `get_skill(skill_name=\"{sk['name']}\")`"
            )
        summary_parts.append("Matched Domain Skills:\n" + "\n".join(skill_lines))

    if library:
        summary_parts.append(f"Library hits ({len(library)}):\n{render_library_hits(library)}")

    summary = "\n\n".join(summary_parts)
    return _ok(summary, posts=posts, library=library, skills=matched_skills, sources_status=sources_status)


def _providers_present() -> bool:
    from cloudra.runtime_v2.knowledge import registered_providers

    return bool(registered_providers())
```

#### 4. 最终工具结果：无条件成功

源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/hub_bridge.py:181-182`

```python
def _ok(summary: str, **data: Any) -> ToolResult:
    return ToolResult(is_success=True, summary=summary, data={"is_success": True, "message": summary, **data})
```

#### 5. 同一错误状态的缺库分支

即使没有抛异常，已注册来源的数据库缺失也不会传回故障状态。实际执行路径如下；知识图谱命中与正文读取依旧只产生结果列表，没有来源状态回传。

#### 5.1 chem-kb 入口与结果返回：没有图谱匹配就返回空列表

源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/knowledge/plugin.py:25-59`

```python
    def search(self, query: str, *, limit: int = 5) -> list[KnowledgeEntry]:
        if limit < 1:
            return []
        matches = store.search_sources(knowledge_graph_db_path(), query)
        if not matches:
            return []
        sources = content.load_sources()
        preferred = "en" if _ascii_dominant(query) else "zh"
        entries: list[KnowledgeEntry] = []
        for match in matches:
            rows = sources.get(match["source"], [])
            sections: dict[str, dict] = {}
            for row in sorted(rows, key=lambda row: (
                row.get("lang", "zh") != preferred,
                row.get("lang", "zh") != "zh",
            )):
                sections.setdefault(row["card_id"], row)
            ordered = sorted(sections.values(), key=lambda row: int(row["card_id"].rsplit(":", 1)[1]))
            if not ordered:
                continue
            first = ordered[0]
            body = "\n\n".join(f"## {row['heading']}\n\n{row['content']}" for row in ordered)
            if first.get("file"):
                body = f"Knowledge file: 知识卡片/{first['file']}\n\n{body}"
            tags = list(dict.fromkeys(tag for row in ordered for tag in flatten_tags(row.get("tags"))))
            entries.append(KnowledgeEntry(
                title=first.get("fm_title") or first.get("topic") or first["heading"],
                content=body,
                source=match["source"],
                score=match["score"],
                tags=tags,
            ))
            if len(entries) >= limit:
                break
        return entries
```

#### 5.2 来源搜索：只读连接不存在就返回空列表

源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/knowledge/store.py:371-421`

```python
def search_sources(db_path: PathLike, query: str) -> list[dict[str, Any]]:
    """Use directly matched graph entities as an index to all their distinct sources.

    Match each query keyword independently, including short terms such as TS.
    Rank by distinct keyword coverage per source, then by summed keyword scores;
    multiple entities matching one keyword never add extra coverage.
    Only entity names/English names/SMILES qualify, not incidental property text.
    Collect all keyword matches before ranking sources; limit documents in the caller.
    Neighbour-only sources are not matches; the caller loads and limits documents.
    """
    separated = query.translate(str.maketrans({mark: " " for mark in ",，;；、"}))
    tokens = list(dict.fromkeys(
        token.strip(".。:：!?！？\"'“”‘’（）()[]【】").casefold()
        for token in separated.split()
    ))
    tokens = [token for token in tokens if token]
    if not tokens:
        return []
    con = _open_ro(db_path)
    if con is None:
        return []
    try:
        con.row_factory = sqlite3.Row
        sources: dict[str, dict[str, Any]] = {}
        for token in tokens:
            seeds, _ = _match_seeds(con, token, cap=-1)
            token_sources: dict[str, float] = {}
            for seed in seeds:
                names = (seed["label"], _label_en(seed["props"]) or "", seed["smiles"] or "")
                if not any(_keyword_in_name(token, name) for name in names):
                    continue
                score = _bm25_score(seed["r"], seed["n_sources"] or 1)
                rows = con.execute(
                    "SELECT DISTINCT source FROM kg_relations WHERE src_id = ? OR dst_id = ? ORDER BY source",
                    (seed["id"], seed["id"]),
                ).fetchall()
                for row in rows:
                    source = row["source"]
                    if source:
                        token_sources[source] = max(token_sources.get(source, 0.0), score)
            for source, score in token_sources.items():
                hit = sources.setdefault(source, {"source": source, "matches": 0, "relevance": 0.0})
                hit["matches"] += 1
                hit["relevance"] += score
        return sorted(
            ({"source": hit["source"], "score": hit["matches"] + hit["relevance"] / (1 + hit["relevance"])}
             for hit in sources.values()),
            key=lambda hit: (-hit["score"], hit["source"]),
        )
    finally:
        con.close()
```

#### 5.3 实际只读连接：数据库文件缺失返回 None

源码：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/knowledge/store.py:103-110`

```python
def _open_ro(db_path: PathLike) -> Optional[sqlite3.Connection]:
    p = Path(db_path)
    if not p.exists():
        return None
    con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True, timeout=60.0)
    con.execute("PRAGMA busy_timeout=60000")
    con.execute("PRAGMA synchronous=NORMAL")
    return con
```

这两个分支最终都回到第 3、4 步：聚合器返回空命中，工具却因来源已经注册而称其 available。修复应让成功、无命中、故障三个事实在来源状态上可区分，其他来源的正常命中继续保留。

## Benchmark 补扫

### Benchmark 关键验收链补充审计

时间：2026-10-18。范围：除本轮 IRC 方向证明修复之外，补扫 DAG 文件科学检查、证据绑定、交付物校验及 Benchmark 三层评分。本文只保留下面两项有当前源码和临时 fixture 实证的问题。没有修改仓库源码，没有启动服务、提交/取消计算或调用 LLM，没有运行全套测试。

本文不修改方法、基组、频率、IRC 或评分权重，不自行认定新的科学阈值。大日志问题保留资源/内存限制；空图问题只记录当前得分和交付语义，不指定新分值。

#### 1. 工程扫描预算被当成科学上“没有证据”，正常大日志会进入零证据倒扣

**可触发条件**：交付图通过 `properties.evidence_log` 明确绑定正确、正常终止的原生 Opt/Freq 日志，但文件超过共享 `MAX_SCAN_BYTES=20MiB`。扫描器把这个文件保留为已分类 EvidenceFile，随后证据绑定、频率自洽和能垒取证都直接排除它。最终可能按“没有任何 accessible 物种绑定证据/unsupported claims”倒扣，而不是表达“工程扫描预算不足，本次未完成验收”。

**设计根因**：同一个布尔条件混合了资源预算和科学真实性。预算导致“不读取”，后续却解释成“没有可用正常终止证据”，并流入科学自洽失败及零证据处罚。显式证据路径不会绕开这个判断，因而不是自动发现遗漏一个未引用文件。

**最小修复方向**：保留内存限制，用流式、分段或末尾必要信息读取来验证显式绑定日志；暂不能处理时把工程不可评估作为独立的 incomplete/基础设施原因返回。不能仅把预算失败叫作 unsupported claims。本文不建议取消限制，也不决定 incomplete 应换成多少分。

##### 1.1 已执行复现及严格限定

使用仓库现成原生 Gaussian 水优化/频率 fixture `tests/fixtures/gaussian/water_opt_freq_g16.out`。创建两个临时沙箱：一个保持原始字节；另一个在既有行边界插入空白，使文件超过扫描预算，原有坐标、能量、频率和终止标记字节保留。两份图都显式声明同一个水物种，并绑定各自 `water.log`。

真实 `normal_log(path)`（不施加 Benchmark 工程上限）对两份都返回 True。真实 `audit_integrity` 和 `score_sandbox` 结果：

| 输入 | 字节数 | 正常终止及频率几何一致 | 显式绑定 | 自洽 | final |
| --- | ---: | --- | --- | --- | ---: |
| 原生 fixture | 92,872 | True | True | True | 1.0 |
| 仅加空白，越过扫描预算 | 21,064,393 | True | False | False | -1.0 |

超限样本 notes 包括 `unbound nodes (no matching evidence file)`、`no evidence bound to this node`、`unsupported claims; penalty applied`，没有返回本次工程扫描未完成的状态。

这是一份仅用于证明分支的临时扩展 fixture，不声称生产日志已经遭遇误罚。测试没有改变科学阈值，也没有把合成内容充当新的计算结果。

##### 1.2 真实执行与返回链

`BenchmarkRunner.score_sandbox` → `audit_integrity` → 定位/加载交付 JSON → `scan_evidence_files`（文件分类和字节数）→ `bind_graph_to_evidence`（显式路径也要求大小在预算内）→ 返回 unbound；runner 再调用 `audit_self_consistency` → `_LogProbe`（重复施加预算）→ 返回未覆盖；再调用 `collect_barrier_evidence`（同一预算）和 `score_accuracy`；最后 runner 的零证据分支返回 `-no_evidence_penalty`。

下面是所讨论路径完整相关函数，包含中间转换、分支和返回，没有用省略号替代源码。第 2 项共用这条评分入口。

##### 任务级图比较配置转发

来源：[cloudra/benchmark/runner.py:332-342](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/runner.py:332)

```python
    def _ged_config_for(self, task: TaskSpec) -> GedConfig:
        """Per-task GED 参数：stereo 是否计代价按 rubric.graph_similarity 的
        stereo_tier_rule，其余全用 runner 默认（per-task 数值覆盖已取消）。"""
        return replace(
            self.ged_config,
            # hard 档立体化学计代价；easy/normal 忽略立体（stereo_free）
            stereo_free=(
                task.rubric.graph_similarity.stereo_tier_rule
                == "easy_normal_stereo_free"
            ),
        )
```

##### 完整评分入口、三层转发和最终返回

来源：[cloudra/benchmark/runner.py:344-497](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/runner.py:344)

```python
    def score_sandbox(self, task: TaskSpec, sandbox: Path) -> RunResult:
        """按交付物评分：图（JSON）+ 日志，不读任何散文。"""
        res = RunResult(
            task_id=task.task_id,
            sandbox=str(sandbox),
            orchestration_mode=task.prompt.orchestration_mode.value,
        )
        ged_config = self._ged_config_for(task)

        integ: IntegrityReport = audit_integrity(sandbox, task.rubric.integrity, ged_config)
        res.notes.extend(integ.notes)

        # 逐节点绑定质量图并入图分：未绑定的 accessible 节点按代价 1.0 记账，
        # 质子化变体部分扣；accessible=false 节点不参与绑定、不在图里，
        # q 缺省 1.0 正好不罚（标志一致性由 graph_similarity 单独把关）。
        binding_quality = {b.node_id: b.quality for b in integ.node_bindings}
        if integ.delivered_graph is not None:
            ged: GedResult = mechanism_similarity(
                integ.delivered_graph,
                task.gold.mechanism_graph,
                ged_config,
                binding_quality=binding_quality,
            )
            res.graph_score = ged.score
        else:
            res.graph_score = 0.0
            res.notes.append("no delivered graph to compare")

        sc: SelfConsistencyReport = audit_self_consistency(
            integ.delivered_graph,
            integ.node_bindings,
            integ.evidence_files,
            sandbox,
            task.rubric.self_consistency,
            charge=task.system.charge,
            integrity_rubric=task.rubric.integrity,
            ged_config=ged_config,
        )
        res.selfconsistency_passed = sc.passed
        res.notes.extend(sc.notes)

        # 自洽回捞（2026-09-25 用户裁决）：gold 边被交付步覆盖、但覆盖它的
        # 交付步全部自洽不合格 → 该 gold 边赢下的图分覆盖贡献倒扣（违规交付
        # 边剔出交付图后重算 GED——同一 gold 边另有自洽合格的覆盖步时保留
        # 覆盖；有效不可达/accessible=false 的交付边本就被自洽豁免，不会进
        # 倒扣集）。不在 gold 子图里的额外交付边自洽不合格只落自洽层零分，
        # 不倒扣图分——gold 边出错与其他边出错严重程度不同。
        if integ.delivered_graph is not None and res.graph_score > 0.0:
            failed_edges = {
                c.element_id
                for c in sc.checks
                if c.kind == "edge" and not c.covered
            }
            if failed_edges:
                remove: set[str] = set()
                for g_edge in task.gold.mechanism_graph.edges:
                    covering = _covering_delivered_edge_ids(
                        g_edge,
                        task.gold.mechanism_graph,
                        integ.delivered_graph,
                        ged_config,
                        task.rubric.integrity.match_threshold,
                    )
                    failing = [e for e in covering if e in failed_edges]
                    if covering and len(failing) == len(covering):
                        remove.update(failing)
                        for eid in sorted(failing):
                            res.notes.append(
                                f"edge {eid}: selfconsistency failed, graph "
                                f"credit for gold edge {g_edge.id} clawed back"
                            )
                if remove:
                    pruned = GoldMechanismGraph(
                        nodes=list(integ.delivered_graph.nodes),
                        edges=[
                            e
                            for e in integ.delivered_graph.edges
                            if e.id not in remove
                        ],
                    )
                    res.graph_score = mechanism_similarity(
                        pruned,
                        task.gold.mechanism_graph,
                        ged_config,
                        binding_quality=binding_quality,
                    ).score

        barriers: BarrierEvidence = collect_barrier_evidence(sandbox)
        res.notes.extend(barriers.notes)
        # hard 档定性选择性：gold.selectivity 带 favored_channel 时替代 accuracy
        # 槽位（composite 的 accuracy 权重给选择性分；barrier spread 数值不评分）
        acc_fail_loud = False
        selectivity = task.gold.selectivity
        if selectivity is not None and selectivity.favored_channel:
            sel_score, sel_note = score_qualitative_selectivity(
                integ.delivered_graph, selectivity
            )
            res.accuracy_score = sel_score
            res.notes.append(sel_note)
        else:
            acc: AccuracyReport = score_accuracy(
                evidence=barriers,
                gold=task.gold,
                rubric=task.rubric.accuracy,
                delivered_graph=integ.delivered_graph,
                cfg=ged_config,
                match_threshold=task.rubric.integrity.match_threshold,
            )
            res.accuracy_score = acc.final_score
            res.notes.extend(acc.notes)
            acc_fail_loud = acc.fail_loud

        rub = task.rubric.integrity
        if not integ.graph_parseable:
            # 图缺失/不可解析 = 不可能有任何证据支撑 -> 零证据倒扣
            res.final_score = -rub.no_evidence_penalty
            res.notes.append(
                "no parseable mechanism graph -> no evidence possible; penalty applied"
            )
            return res
        accessible_species = [
            n
            for n in integ.delivered_graph.nodes
            if n.accessible and n.role is not NodeRole.TRANSITION_STATE
        ]
        evidenced = {b.node_id for b in integ.node_bindings if b.quality > 0.0}
        if accessible_species and not any(
            n.id in evidenced for n in accessible_species
        ):
            # 有 accessible 物种声明但无一绑到证据 = 无证据支撑的机理声明，
            # 比没交付更糟 -> 倒扣；全部节点都声明 accessible=false 是合法
            # 交付（纯不可达声明），不触发本条
            res.final_score = -rub.no_evidence_penalty
            res.notes.append(
                "no evidence bound to any accessible species node -> "
                "unsupported claims; penalty applied"
            )
            return res
        if acc_fail_loud:
            # fail-loud 短路：声明无据/不一致 -> 自洽与 accuracy 分量清零，
            # final 只保留图分
            res.final_score = round(W_GRAPH * res.graph_score, 4)
            res.notes.append(
                "accuracy fail-loud (unsupported or inconsistent declared "
                "barriers); final keeps the graph component only"
            )
            return res
        res.final_score = round(
            W_GRAPH * res.graph_score
            + W_SELFCONSISTENCY * (1.0 if res.selfconsistency_passed else 0.0)
            + W_ACCURACY * res.accuracy_score,
            4,
        )
        return res
```

##### 当前权重常量，本文不修改

来源：[cloudra/benchmark/runner.py:79-87](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/runner.py:79)

```python

# composite 权重（2026-09-25 用户裁决）：final = 0.1·图 + 0.3·自洽 + 0.6·accuracy。
# 机理不对时 accuracy 层也会惩罚，图份额不该高；自洽层保持全有或全无（布尔）。
# accuracy 双来源核对 fail-loud 时自洽/accuracy 分量清零、只保留图分
# （final = W_GRAPH·graph）；图不可解析或没有任何 accessible 物种节点绑到
# 证据时倒扣 -rubric.integrity.no_evidence_penalty。
W_GRAPH = 0.1
W_SELFCONSISTENCY = 0.3
W_ACCURACY = 0.6
```

##### 完整性入口和绑定结果返回

来源：[cloudra/benchmark/integrity.py:485-532](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/integrity.py:485)

```python
def audit_integrity(
    sandbox: Path,
    rubric: Optional[IntegrityRubric] = None,
    cfg: Optional[GedConfig] = None,
) -> IntegrityReport:
    """审计入口：只产出报告（图可解析性 + 逐节点绑定质量），不判通过与否。
    零证据倒扣与证据加权扣分都在 runner/graph_similarity 侧按报告事实计算。"""
    rubric = rubric or IntegrityRubric()
    report = IntegrityReport(graph_found=False, graph_parseable=False)

    graph_path = find_graph_json(sandbox)
    if graph_path is None:
        report.notes.append("mechanism_graph.json not found in sandbox")
        return report
    report.graph_found = True
    report.graph_path = str(graph_path.relative_to(sandbox))

    graph = load_delivered_graph(graph_path)
    if graph is None:
        report.notes.append("mechanism_graph.json present but not parseable")
        return report
    report.graph_parseable = True
    report.delivered_graph = graph

    # 兜底发现的交付图文件自身排除出证据扫描：其内嵌 SMILES 不构成计算证据
    report.evidence_files = scan_evidence_files(sandbox, exclude=graph_path)
    report.node_bindings = bind_graph_to_evidence(
        graph,
        report.evidence_files,
        cfg,
        match_threshold=rubric.match_threshold,
        partial_quality=rubric.protonation_partial_quality,
        sandbox=sandbox,
    )

    report.binding_quality = (
        sum(b.quality for b in report.node_bindings) / len(report.node_bindings)
    ) if report.node_bindings else 0.0
    bound = [b for b in report.node_bindings if b.matched]
    partial = [b.node_id for b in bound if b.quality < 1.0]
    if partial:
        report.notes.append(
            f"partial-credit binds (protonation/charge-state variants): {partial}"
        )
    unbound = [b.node_id for b in report.node_bindings if not b.matched]
    if unbound:
        report.notes.append(f"unbound nodes (no matching evidence file): {unbound}")
    return report
```

##### 交付文件定位

来源：[cloudra/benchmark/integrity.py:157-170](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/integrity.py:157)

```python
def find_graph_json(sandbox: Path) -> Optional[Path]:
    """Locate the agent-maintained mechanism_graph.json at the sandbox root,
    falling back to any *.json that parses to a mechanism graph shape."""
    direct = sandbox / "mechanism_graph.json"
    if direct.is_file():
        return direct
    for p in sorted(sandbox.rglob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if isinstance(data, dict) and "nodes" in data and "edges" in data:
            return p
    return None
```

##### 交付 JSON 转换和模型返回

来源：[cloudra/benchmark/integrity.py:173-197](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/integrity.py:173)

```python
def load_delivered_graph(path: Path) -> Optional[GoldMechanismGraph]:
    """Parse a delivered graph JSON into GoldMechanismGraph.

    交付侧宽松加载（Postel）：agent 多写的键（energy/metadata 等）忽略、
    边缺 id 自动补；gold 侧仍由 strict schema 约束。端点引用完整性由
    GoldMechanismGraph 的 validator 把关：悬空 from/to/via → 校验失败、
    返回 None（不可解析），不再静默造幽灵节点进图比较。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    try:
        nodes = [_DeliveredNode.model_validate(n) for n in data.get("nodes", [])]
        edges = [_DeliveredEdge.model_validate(e) for e in data.get("edges", [])]
        return GoldMechanismGraph(
            nodes=[MechanismNode(**n.model_dump()) for n in nodes],
            edges=[
                MechanismEdge(**(e.model_dump() | {"id": e.id or f"e{i}"}))
                for i, e in enumerate(edges)
            ],
        )
    except Exception:
        return None
```

##### 交付节点字段规范化

来源：[cloudra/benchmark/integrity.py:54-85](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/integrity.py:54)

```python
class _DeliveredNode(MechanismNode):
    """交付侧节点：Postel 宽松加载（GH #29）。

    常规图节点字段（``type``、字符串 ``smiles``）在字段校验前规范化到本系统
    的 schema（``role``、``smiles: list[str]``）；多写的键忽略。组分列表形态
    （``["C=O","CN"]``）由 schema 校验器折叠成点连接络合物单条，无需在此
    特判。"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    @model_validator(mode="before")
    @classmethod
    def _normalize_delivery_fields(cls, data):
        if not isinstance(data, dict):
            return data
        data = dict(data)
        # role 缺失，或 role 是自由文本（不是合法 NodeRole 枚举值）而 type 能映射
        # 时，以 type 的映射值为 role；自由文本并进 label，不丢信息。role 本身
        # 是合法枚举值时不动；type 也映射不了则留原样，让校验 fail-loud。
        alias = _NODE_TYPE_ALIASES.get(str(data.get("type") or "").strip().lower())
        if alias is not None and data.get("role") not in {r.value for r in NodeRole}:
            free_text = str(data["role"]).strip() if data.get("role") is not None else ""
            if free_text:
                label = str(data.get("label") or "").strip()
                data["label"] = f"{label} | {free_text}" if label else free_text
            data["role"] = alias
        smiles = data.get("smiles")
        if isinstance(smiles, str):
            data["smiles"] = [smiles]
        elif smiles is None:
            data["smiles"] = []
        return data
```

##### 交付边字段规范化

来源：[cloudra/benchmark/integrity.py:88-107](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/integrity.py:88)

```python
class _DeliveredEdge(MechanismEdge):
    """交付侧边：忽略多写的键，id 可缺省（加载时补）。

    Postel 规范化：常规图论字段 ``source``/``target`` 映射到 ``from``/``to``。"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_delivery_fields(cls, data):
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "from" not in data and "source" in data:
            data["from"] = data["source"]
        if "to" not in data and "target" in data:
            data["to"] = data["target"]
        return data
```

##### 交付/Gold 共用图结构和引用校验

来源：[cloudra/benchmark/schema.py:139-181](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/schema.py:139)

```python
class GoldMechanismGraph(BaseModel):
    """机理图（gold 参考与交付图共用形状）。

    端点引用完整性：每条边的 from/to 必须指向已声明节点 id；via 非空时必须
    指向已声明的 transition_state 角色节点——违反即 ValidationError（gold
    侧 fail-loud；交付侧加载随之失败，不再静默造幽灵节点进图比较）。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    nodes: list[MechanismNode]
    edges: list[MechanismEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def _edge_references_declared(self) -> "GoldMechanismGraph":
        roles = {n.id: n.role for n in self.nodes}
        for e in self.edges:
            for endpoint in (e.from_node, e.to_node):
                if endpoint not in roles:
                    raise ValueError(
                        f"edge {e.id}: endpoint {endpoint!r} is not a declared node"
                    )
            if e.via and roles.get(e.via) is not NodeRole.TRANSITION_STATE:
                raise ValueError(
                    f"edge {e.id}: via {e.via!r} is not a declared "
                    "transition_state node"
                )
        return self

    def edge_effectively_accessible(self, edge: MechanismEdge) -> bool:
        """边的有效可达性：``edge.accessible`` 且经由的 TS 节点（``via``）也可达。

        gold 只在节点上标 ``accessible=false``（边从不标），交付侧按协议句可以把
        不可达标在节点或边上——两侧同口径折叠成「有效可达性」再判定：经由不可达
        TS 的步在允许方法下同样算不了，视同不可达边；``via`` 为空的边不做端点
        检查。图分的标志一致性闸门、accuracy 的无参考边 1.0/0.0 规则、自洽的边
        豁免三处统一走这个口径，不得各抄一份。"""
        if not edge.accessible:
            return False
        if edge.via is None:
            return True
        via = next((n for n in self.nodes if n.id == edge.via), None)
        # validator 已保证 via 指向已声明的 TS 节点；防御性分支按不可达计
        return bool(via is not None and via.accessible)
```

##### 共享预算以及实际 EvidenceFile 字段

来源：[cloudra/benchmark/integrity.py:112-124](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/integrity.py:112)

```python
# 超过该大小的文件只做类型分类、不整读扫 SMILES，也不进 Layer 2 的帧解析
# （两层共享同一上限：超大文件在 Layer 1 没贡献绑定，cclib 整读只会拖住评分器）
MAX_SCAN_BYTES = 20 * 1024 * 1024

# `smiles:` 注释行是交付协议的一部分（query 明确要求证据文件携带）。
# 容忍 JSON/YAML 引号与注释前缀："smiles": "X"、smiles: 'X'、# smiles: X。
# 注意不能把 [ ] 排除在捕获集外——离子/ bracket SMILES（[F-]、[OH3+]）依赖它们。
@dataclass
class EvidenceFile:
    path: str
    smiles_found: list[str] = field(default_factory=list)
    kind: str = ""  # 'gaussian'|'orca'|'xyz'|'json'|'unknown'
    size: int = 0   # 字节数；Layer 2 据此跳过超过 MAX_SCAN_BYTES 的文件
```

##### 预算只保留分类，但清空文本取证

来源：[cloudra/benchmark/integrity.py:243-284](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/integrity.py:243)

```python
def scan_evidence_files(sandbox: Path, exclude: Optional[Path] = None) -> list[EvidenceFile]:
    files: list[EvidenceFile] = []
    for p in sorted(sandbox.rglob("*")):
        if not p.is_file():
            continue
        try:
            p.resolve().relative_to(sandbox.resolve())
        except ValueError:
            continue
        if p.suffix.lower() not in _EVIDENCE_SUFFIXES:
            continue
        if p.name == "mechanism_graph.json":
            continue
        # 兜底发现加载的交付图（如 sub/my_graph.json）同样不得计入证据——
        # 否则图文件内嵌的 SMILES 会自绑，零计算证据也能过 Layer 1
        if exclude is not None and p == exclude:
            continue
        kind = _classify(p)
        try:
            size = p.stat().st_size
            if size > MAX_SCAN_BYTES:
                text = ""  # 超大日志不整读；保留分类结果，SMILES 扫描跳过
            else:
                text = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        # 机理图形状的 JSON（顶层 nodes+edges）一律不是证据：交付图的多份改名
        # 拷贝若算证据，其内嵌 SMILES 会让图节点绑定到自己，零计算证据过 Layer 1
        if p.suffix.lower() == ".json" and text:
            try:
                data = json.loads(text)
            except Exception:
                data = None
            if isinstance(data, dict) and "nodes" in data and "edges" in data:
                continue
        files.append(EvidenceFile(
            path=str(p.relative_to(sandbox)),
            smiles_found=_smiles_in_text(text),
            kind=kind,
            size=size,
        ))
    return files
```

##### 实际文件类型识别

来源：[cloudra/benchmark/integrity.py:287-309](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/integrity.py:287)

```python
def _classify(p: Path) -> str:
    s = p.suffix.lower()
    if s in (".gjf", ".com"):
        return "gaussian"
    if s == ".inp":
        return "orca"
    if s == ".xyz":
        return "xyz"
    if s == ".json":
        return "json"
    if s in (".log", ".out"):
        # sniff engine by content header（只读头部，不整读）
        try:
            with p.open("r", encoding="utf-8", errors="replace") as fh:
                head = fh.read(2000)
        except Exception:
            return "unknown"
        if "Entering Gaussian System" in head or "Gaussian" in head:
            return "gaussian"
        if "O   R   C   A" in head or "ORCA" in head:
            return "orca"
        return "log"
    return "unknown"
```

##### 显式 evidence_log 也被预算排除

来源：[cloudra/benchmark/integrity.py:354-477](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/integrity.py:354)

```python
def bind_graph_to_evidence(
    graph: GoldMechanismGraph,
    files: list[EvidenceFile],
    cfg: Optional[GedConfig] = None,
    match_threshold: float = 0.2,
    partial_quality: float = 0.7,
    *,
    sandbox: Path,
) -> list[NodeBinding]:
    """Bind each declared species to matching evidence for its complete identity.

    A dot-connected entry requires whole-complex geometry. Multiple entries
    describe separated species and each needs its own matching evidence.
    Inaccessible nodes are exempt; TS nodes retain explicit evidence lineage.
    """
    cfg = cfg or GedConfig()
    sandbox = Path(sandbox)
    available = files
    from cloudra.dag.file_science import _geometry_species
    verified = []
    for evidence in files:
        identities = []
        if evidence.size <= MAX_SCAN_BYTES and (evidence.kind == 'xyz' or normal_log(sandbox / evidence.path, max_scan_bytes=MAX_SCAN_BYTES)):
            for identity in evidence.smiles_found:
                try:
                    if _geometry_species(str(sandbox / evidence.path), identity):
                        identities.append(identity)
                except (ValueError, RuntimeError) as exc:
                    # Dependency failures must not become missing molecular evidence.
                    if isinstance(exc, RuntimeError) and isinstance(exc.__cause__, ImportError):
                        raise
                    continue
        verified.append(replace(evidence, smiles_found=identities))
    files = verified
    bindings: list[NodeBinding] = []
    by_id: dict[str, NodeBinding] = {}
    ts_ids = {n.id for n in graph.nodes if n.role == NodeRole.TRANSITION_STATE}

    # pass 1: accessible 物种节点（TS 节点第二趟按边端点判定）
    for node in graph.nodes:
        if not node.accessible:
            continue  # 不可达声明不要求证据
        nb = NodeBinding(node_id=node.id)
        by_id[node.id] = nb
        bindings.append(nb)
        if node.id in ts_ids:
            continue
        if 'evidence_log' in node.properties:
            raw = node.properties['evidence_log']
            try:
                path = (sandbox / raw).resolve() if isinstance(raw, str) else None
                relative = str(path.relative_to(sandbox.resolve())) if path is not None else None
                evidence = next((item for item in available if item.path == relative
                                 and item.kind in {'gaussian', 'orca'} and item.size <= MAX_SCAN_BYTES), None)
                if evidence and node.smiles and normal_log(path, max_scan_bytes=MAX_SCAN_BYTES):
                    identities = next(item.smiles_found for item in files if item.path == relative)
                    identities = list(identities)
                    identities.extend(identity for identity in node.smiles if _geometry_species(str(path), identity))
                    candidate = replace(evidence, smiles_found=list(dict.fromkeys(identities)))
                    qualities = [_species_file_qualities(identity, [candidate], cfg, match_threshold, partial_quality)[0]
                                 for identity in node.smiles]
                    if all(quality > 0 for quality in qualities):
                        nb.bound_files, nb.matched, nb.quality = [relative], True, min(qualities)
            except (ValueError, RuntimeError, OSError) as exc:
                if isinstance(exc, RuntimeError) and isinstance(exc.__cause__, ImportError):
                    raise
                pass
            continue  # A bad explicit reference must never select other history.
        if not node.smiles:
            # 物种节点不带 SMILES = 只有声明没有可取证内容，不予绑定；
            # 否则 agent 把 SMILES 全留空即可零证据通过本层。
            continue
        all_species_matched = True
        node_quality = 1.0
        for species_smiles in node.smiles:
            q, qpaths = _species_file_qualities(
                species_smiles, files, cfg, match_threshold, partial_quality
            )
            if qpaths:
                nb.bound_files.extend(qpaths)
            else:
                all_species_matched = False
            node_quality = min(node_quality, q)
        nb.bound_files = sorted(set(nb.bound_files))
        nb.matched = all_species_matched and bool(nb.bound_files)
        nb.quality = node_quality if nb.matched else 0.0

    # pass 2: TS nodes — 仅当某条边经由它且两端物种都已绑定证据；
    # accessible=false 的 TS 不在 by_id 里，自然跳过
    for ts_id in ts_ids:
        nb = by_id.get(ts_id)
        if nb is None:
            continue
        node = next(n for n in graph.nodes if n.id == ts_id)
        if 'evidence_log' in node.properties:
            raw = node.properties['evidence_log']
            try:
                path = (sandbox / raw).resolve() if isinstance(raw, str) else None
                relative = str(path.relative_to(sandbox.resolve())) if path is not None else None
                if any(f.path == relative and f.kind in {'gaussian', 'orca'} and f.size <= MAX_SCAN_BYTES for f in available) and normal_log(path, max_scan_bytes=MAX_SCAN_BYTES):
                    endpoint_quality = max((min(by_id[e.from_node].quality, by_id[e.to_node].quality)
                                            for e in graph.edges if e.via == ts_id and e.from_node in by_id and e.to_node in by_id), default=0.0)
                    nb.bound_files, nb.matched, nb.quality = [relative], True, endpoint_quality
            except (ValueError, OSError):
                pass
            continue
        for e in graph.edges:
            if e.via != ts_id:
                continue
            a, b = by_id.get(e.from_node), by_id.get(e.to_node)
            if a is not None and b is not None and a.matched and b.matched:
                nb.matched = True
                nb.quality = min(a.quality, b.quality)
                from cloudra.benchmark.barrier_evidence import (
                    _declared_node_energy_hartree,
                    _identify_by_declared_energy,
                )
                declared = _declared_node_energy_hartree(node)
                candidates = [f.path for f in available if f.kind in {'gaussian', 'orca'}
                              and f.size <= MAX_SCAN_BYTES]
                selected = _identify_by_declared_energy(sandbox, candidates, declared) if declared is not None else None
                nb.bound_files = [selected] if selected else []
                break
    return bindings
```

##### 工程预算转换成布尔结果

来源：[cloudra/tools/core/irc_evidence.py:184-190](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/irc_evidence.py:184)

```python
def _within_scan_limit(path: Path, max_scan_bytes: Optional[int]) -> bool:
    if max_scan_bytes is None:
        return True
    try:
        return path.stat().st_size <= max_scan_bytes
    except OSError:
        return False
```

##### 预算失败与非正常终止共用 False

来源：[cloudra/tools/core/irc_evidence.py:193-205](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/irc_evidence.py:193)

```python
def normal_log(path, *, max_scan_bytes=None) -> bool:
    """Native normally terminated QM evidence within the caller's read limit."""
    path = Path(path)
    if not path.is_file() or not _within_scan_limit(path, max_scan_bytes):
        return False
    engine = qm_engine.detect_qm_engine(str(path))
    parser = {'orca': orca_frames, 'gaussian': gaussian_frames}.get(engine)
    text = path.read_text(errors='replace')
    if parser is None or not parser.normal_termination(text):
        return False
    if engine == 'orca' and 'ORCA finished by error termination' in text:
        return False
    return frequency_geometry_matches(path)
```

##### normal_log 返回前的真实频率与几何一致性检查

来源：[cloudra/tools/core/irc_evidence.py:208-225](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/tools/core/irc_evidence.py:208)

```python
def frequency_geometry_matches(path) -> bool:
    """The last spectrum must belong to the final geometry in the native log."""
    engine = qm_engine.detect_qm_engine(str(path))
    text = Path(path).read_text(errors='replace')
    frequency_marker = 'VIBRATIONAL FREQUENCIES' if engine == 'orca' else 'Frequencies --'
    frequency_index = text.rfind(frequency_marker)
    if frequency_index < 0:
        return True  # No frequency claim; probe_log still returns n_imag=None.

    def geometry(region):
        if engine == 'orca':
            return parse_xyz(orca_frames.final_xyz_from_text(region))
        blocks = gaussian_frames.std_orientation_frames(region)
        coords = blocks[-1] if blocks else gaussian_frames._parse_last_input_orientation(region)
        return parse_xyz(gaussian_frames._coords_to_xyz(
            [row[0] for row in coords], [row[1:] for row in coords])) if coords else None

    return same_geometry(geometry(text), geometry(text[:frequency_index]))
```

##### 自洽覆盖判断、空集合判定及完整返回

来源：[cloudra/benchmark/selfconsistency.py:233-426](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/selfconsistency.py:233)

```python
def audit_self_consistency(
    graph: Optional[GoldMechanismGraph],
    bindings: list[NodeBinding],
    evidence_files: list[EvidenceFile],
    sandbox: Path,
    rubric: Optional[SelfConsistencyRubric] = None,
    charge: int = 0,
    *,
    integrity_rubric: Optional[IntegrityRubric] = None,
    ged_config: Optional[GedConfig] = None,
) -> SelfConsistencyReport:
    rubric = rubric or SelfConsistencyRubric()
    integrity_rubric = integrity_rubric or IntegrityRubric()
    report = SelfConsistencyReport()
    if not (rubric.ts_first_order_saddle or rubric.irc_connects_endpoints):
        report.passed = True
        report.notes.append("self-consistency checks disabled by rubric; passthrough")
        return report
    if graph is None:
        report.notes.append("no delivered graph; self-consistency not assessable")
        return report

    files_by_path = {f.path: f for f in evidence_files}
    probe = _LogProbe(sandbox, files_by_path)
    qm_paths = [f.path for f in evidence_files if f.kind in {'gaussian', 'orca'}
                and f.size <= MAX_SCAN_BYTES]
    bmap = {b.node_id: b for b in bindings}
    species_covered: dict[str, bool] = {}
    edge_checks: dict[str, ElementCheck] = {}

    # 物种节点：极小值证据须覆盖整络合物或每个分开交付的组分。
    for node in graph.nodes:
        if node.role == NodeRole.TRANSITION_STATE:
            continue
        chk = ElementCheck(element_id=node.id, kind="species")
        report.checks.append(chk)
        if not node.accessible:
            chk.declared_inaccessible = True
            chk.covered = True
            chk.notes.append("declared inaccessible; evidence not required")
        else:
            b = bmap.get(node.id)
            chk.bound = bool(b and b.matched)
            if not chk.bound:
                chk.notes.append("no evidence bound to this node")
            else:
                minimum_witnesses = {
                    p: witness for p in b.bound_files
                    for witness in (probe.minimum_witness(p, qm_paths),)
                    if witness is not None
                }
                if len(node.smiles) > 1 or any("." in species for species in node.smiles):
                    # Recheck component coverage using verified bound anchors;
                    # replacing anchors with Freq paths loses explicit references.
                    minimum_files = [files_by_path[p] for p in minimum_witnesses]
                    minimum_binding = bind_graph_to_evidence(
                        GoldMechanismGraph(nodes=[node], edges=[]), minimum_files,
                        ged_config,
                        match_threshold=integrity_rubric.match_threshold,
                        partial_quality=integrity_rubric.protonation_partial_quality,
                        sandbox=sandbox,
                    )[0]
                    chk.covered = minimum_binding.matched
                    if chk.covered:
                        chk.evidence_used.extend(dict.fromkeys(
                            path for anchor in minimum_binding.bound_files
                            for path in (anchor, minimum_witnesses[anchor])
                        ))
                    else:
                        chk.notes.append("verified minima do not cover every declared species; a complex needs its own minimum")
                else:
                    for p, witness in minimum_witnesses.items():
                        chk.covered = True
                        chk.evidence_used.extend(dict.fromkeys([p, witness]))
                        break
                if not chk.covered and not chk.notes:
                    chk.notes.append(
                        "no verified minimum (frequency block with zero "
                        "imaginary frequencies) among bound evidence"
                    )
        species_covered[node.id] = chk.covered

    # 边：TS 步查一阶鞍点 + IRC 方向区间证明（各按 rubric 开关），任一合格证据即覆盖
    for edge in graph.edges:
        chk = ElementCheck(element_id=edge.id, kind="edge")
        report.checks.append(chk)
        edge_checks[edge.id] = chk
        if not graph.edge_effectively_accessible(edge):
            # 有效不可达（边自身 accessible=false，或经由的 TS 节点不可达）视同
            # declared_inaccessible 豁免——与图分/accuracy 同一口径
            # （schema.edge_effectively_accessible）
            chk.declared_inaccessible = True
            chk.covered = True
            chk.notes.append(
                "effectively inaccessible (the edge or its via transition state); "
                "evidence not required"
            )
            continue
        if edge.via is None:
            endpoints_bound = all(
                (bmap.get(nid) is not None and bmap[nid].matched)
                for nid in (edge.from_node, edge.to_node)
            )
            chk.bound = endpoints_bound
            chk.covered = species_covered.get(edge.from_node, False) and (
                species_covered.get(edge.to_node, False)
            )
            if not chk.covered:
                chk.notes.append("no TS node on this edge; endpoint species not both covered")
            continue
        pool: set[str] = set()
        for nid in (edge.via, edge.from_node, edge.to_node):
            b = bmap.get(nid)
            if b and b.matched:
                pool.update(b.bound_files)
        ts_binding = bmap.get(edge.via)
        ts_files = list(ts_binding.bound_files) if ts_binding and ts_binding.matched else []
        # IRC logs are candidates only; the native starting geometry must match
        # the selected TS. Endpoint annotations do not establish that lineage.
        pool.update(qm_paths)
        chk.bound = bool(ts_files)
        if not ts_files:
            chk.notes.append(
                f"no evidence explicitly associated with TS {edge.via}; declare its evidence_log or energy_hartree"
            )
            continue
        saddle_ok = not rubric.ts_first_order_saddle
        irc_ok = not rubric.irc_connects_endpoints
        for p in sorted(ts_files):
            witness = probe.ts_witness(p, pool)
            if not saddle_ok and witness is not None:
                saddle_ok = True
                chk.evidence_used.extend(dict.fromkeys([p, witness]))
                break
        if not irc_ok:
            from_binding = bmap.get(edge.from_node)
            to_binding = bmap.get(edge.to_node)
            from_files = (
                list(from_binding.bound_files)
                if from_binding and from_binding.matched else []
            )
            to_files = (
                list(to_binding.bound_files)
                if to_binding and to_binding.matched else []
            )
            proof = _strict_irc_proof(probe, sorted(pool), from_files, to_files, charge,
                ts_files=ts_files,
                product_smiles=next(node.smiles for node in graph.nodes if node.id == edge.to_node),
                reactant_smiles=next(node.smiles for node in graph.nodes if node.id == edge.from_node))
            if proof is not None:
                irc_ok = True
                saddle_ok = True
                chk.evidence_used, details = proof
                chk.notes.extend(details)
        chk.covered = saddle_ok and irc_ok
        if not saddle_ok:
            chk.notes.append(
                "no first-order saddle (exactly one imaginary frequency) "
                "among bound evidence"
            )
        if not irc_ok:
            chk.notes.append(
                "no same-TS bidirectional IRC whose outer frames are connected by native "
                "converged optimization logs to the declared verified endpoint minima"
            )

    # TS 节点随边覆盖：至少一条 accessible 的边经由它且被覆盖；否则必须自我声明豁免
    for node in graph.nodes:
        if node.role != NodeRole.TRANSITION_STATE:
            continue
        chk = ElementCheck(element_id=node.id, kind="transition_state")
        report.checks.append(chk)
        covering = [
            e.id for e in graph.edges
            if e.via == node.id and e.accessible and edge_checks[e.id].covered
        ]
        if covering:
            chk.bound = True
            chk.covered = True
        elif not node.accessible:
            chk.declared_inaccessible = True
            chk.covered = True
            chk.notes.append("declared inaccessible; evidence not required")
        else:
            b = bmap.get(node.id)
            chk.bound = bool(b and b.matched)
            chk.notes.append("no accessible edge through this TS is covered")

    report.passed = all(c.covered for c in report.checks)
    for c in report.checks:
        if not c.covered:
            for n in c.notes:
                report.notes.append(f"{c.kind} {c.element_id}: {n}")
    return report
```

##### 自洽探针重复排除超限日志

来源：[cloudra/benchmark/selfconsistency.py:115-133](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/selfconsistency.py:115)

```python
    def _parse(self, rel_path: str) -> tuple[Optional[int], Optional[tuple]]:
        """(虚频数, 末帧几何)。虚频数 None = 无频率块/文件不可解析。"""
        if rel_path not in self._cache:
            result: tuple[Optional[int], Optional[tuple]] = (None, None)
            f = self._files.get(rel_path)
            if (
                f is not None
                and f.kind in ("gaussian", "orca")
                and f.size <= MAX_SCAN_BYTES
                and normal_log(self._sandbox / rel_path, max_scan_bytes=MAX_SCAN_BYTES)
            ):
                path = self._sandbox / rel_path
                frames, _irc_meta = _frames_for(path)
                freqs = _freqs_for(path, frames)
                n_imag = len(_imag_freqs(freqs)) if freqs else None
                geometry = _last_geometry(path, frames)
                result = (n_imag, geometry)
            self._cache[rel_path] = result
        return self._cache[rel_path]
```

##### 虚频数转发

来源：[cloudra/benchmark/selfconsistency.py:135-136](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/selfconsistency.py:135)

```python
    def n_imag(self, rel_path: str) -> Optional[int]:
        return self._parse(rel_path)[0]
```

##### 末帧几何转发

来源：[cloudra/benchmark/selfconsistency.py:138-140](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/selfconsistency.py:138)

```python
    def last_geometry(self, rel_path: str) -> Optional[tuple]:
        """末帧几何 (symbols, positions)；无坐标帧返回 None。"""
        return self._parse(rel_path)[1]
```

##### 最小值证据查询和返回

来源：[cloudra/benchmark/selfconsistency.py:150-157](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/selfconsistency.py:150)

```python
    def minimum_witness(self, anchor, pool):
        """Verify the bound geometry, never substitute a historical minimum."""
        from cloudra.tools.core.irc_path import same_geometry
        if self.n_imag(anchor) == 0:
            return anchor
        geometry = self.last_geometry(anchor)
        return next((p for p in sorted(pool) if self.n_imag(p) == 0 and
                     same_geometry(geometry, self.last_geometry(p))), None)
```

##### 独立能垒取证入口和返回，继续使用同一工程预算

来源：[cloudra/benchmark/barrier_evidence.py:249-434](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/barrier_evidence.py:249)

```python
def collect_barrier_evidence(sandbox: Path | str) -> BarrierEvidence:
    """从交付图 + 绑定日志推出逐步能垒（不做任何散文解析）。"""
    sandbox = Path(sandbox)
    report = BarrierEvidence()
    graph_path = find_graph_json(sandbox)
    if graph_path is None:
        report.notes.append("no delivered mechanism graph; no barrier evidence")
        return report
    graph: Optional[GoldMechanismGraph] = load_delivered_graph(graph_path)
    if graph is None:
        report.notes.append(f"delivered graph unparseable: {graph_path.name}")
        return report
    report.graph_found = True

    files = scan_evidence_files(sandbox, exclude=graph_path)
    from cloudra.benchmark.integrity import bind_graph_to_evidence

    bindings = {b.node_id: b for b in bind_graph_to_evidence(graph, files, sandbox=sandbox)}
    log_paths = [f.path for f in files if f.kind in _SCORING_ENGINES and f.size <= MAX_SCAN_BYTES]
    by_id = {node.id: node for node in graph.nodes}

    for edge in graph.edges:
        if edge.via is None:
            report.notes.append(f"edge {edge.id}: no transition-state node (`via`)")
            continue
        base_node = by_id.get(edge.from_node)
        ts_node = by_id.get(edge.via)
        ts_node_name = getattr(ts_node, "name", "") if ts_node is not None else ""
        if base_node is None:
            report.notes.append(f"edge {edge.id}: unknown base node {edge.from_node}")
            continue
        if len(base_node.smiles) > 1:
            report.notes.append(
                f"edge {edge.id}: separated source species have no single complex energy reference; "
                "component energies are not substituted for it"
            )
            continue
        base_binding = bindings.get(edge.from_node)
        base_candidates = list(base_binding.bound_files) if base_binding else []
        if not base_candidates:
            report.notes.append(
                f"edge {edge.id}: base node {edge.from_node} has no bound evidence"
            )
            continue
        # TS 证据：从两端点绑定文件的并集里按内容找一阶鞍点；多步题优先用
        # 文件名携带该步 TS 身份（edge id / TS 节点 id / 步名）的那一个——
        # 这是确定性偏好，不是猜谜；无法唯一确定时记 note 说明所用文件。
        ts_binding = bindings.get(edge.via)
        ts_candidates = list(ts_binding.bound_files) if ts_binding else []
        saddles = [
            p for p in sorted(set(ts_candidates)) if _frequency_supported(sandbox, p, log_paths, 1)
        ]
        if not saddles:
            report.notes.append(
                f"edge {edge.id}: no first-order saddle log bound to TS "
                f"{edge.via}; barrier not derivable from evidence"
            )
            continue
        all_saddles = list(saddles)
        # TS 日志指认：节点声明的 energy_hartree 直接钉住交付的是哪一份鞍点
        # 日志（同物种/同节点可绑定多份）；无声明或未命中时退回名字/路径序。
        declared_ts_energy = _declared_node_energy_hartree(ts_node)
        matched_ts = _identify_by_declared_energy(sandbox, saddles, declared_ts_energy)
        if matched_ts is not None:
            if len(saddles) > 1:
                report.notes.append(
                    f"edge {edge.id}: {len(saddles)} saddle logs bound to TS "
                    f"{edge.via}; using {matched_ts} (matches the node's declared "
                    "energy_hartree)"
                )
            saddles = [matched_ts]
        elif declared_ts_energy is not None:
            report.notes.append(
                f"edge {edge.id}: TS {edge.via} declares energy_hartree "
                f"{declared_ts_energy:.6f} but no bound saddle log matches it; "
                "barrier not derivable from the declared evidence"
            )
            continue
        if len(saddles) > 1:
            tokens = [t.lower() for t in (edge.id, edge.via, ts_node_name) if t]
            preferred = [
                p for p in saddles if any(t in Path(p).name.lower() for t in tokens)
            ]
            report.notes.append(
                f"edge {edge.id}: several saddle logs {saddles}; "
                + (f"using {preferred[0]} (name matches the step)" if preferred
                   else f"using {saddles[0]} (deterministic first by path)")
            )
            saddles = preferred or saddles
        ts_path = saddles[0]

        # 全部合法组合（TS 日志 × 起点极小值日志）都要留给评分侧：交付声明的
        # 是一个构象、而参考答案对应另一个已算好的构象时，只有看到全部组合
        # 才能区分"指认/答案定义差异"与"无据声明"。
        saddle_energies: dict[str, float] = {}
        for candidate in all_saddles:
            energy, _reason = _engine_energy_kcal(sandbox, candidate)
            if energy is not None:
                saddle_energies[candidate] = energy
        ts_energy = saddle_energies.get(ts_path)
        if ts_energy is None:
            _energy, ts_reason = _engine_energy_kcal(sandbox, ts_path)
            report.notes.append(f"edge {edge.id}: {ts_reason}")
            continue

        # 起点最小值的选择：节点声明的 energy_hartree 优先指认交付的是哪份
        # 极小值日志（同一中间体的不同构象都是合法极小值）；无声明或未命中时
        # 退回启发式——鞍点连通的是它正下方**最浅**的那个阱（拿更深的远端极小值
        # 当起点会把别的阱的稳定化能错算进能垒）。
        minima = [
            p for p in base_candidates if _frequency_supported(sandbox, p, log_paths, 0)
        ]
        minima_energies: dict[str, float] = {}
        for candidate in minima:
            energy, _reason = _engine_energy_kcal(sandbox, candidate)
            if energy is not None:
                minima_energies[candidate] = energy
        below: list[tuple[float, str]] = [
            (energy, path)
            for path, energy in sorted(minima_energies.items())
            if energy < ts_energy
        ]
        if not below:
            report.notes.append(
                f"edge {edge.id}: no bound minimum of {edge.from_node} lies "
                "below the saddle; barrier not derivable from evidence"
            )
            continue
        report.alternatives[edge.id] = [
            StepBarrier(
                edge_id=edge.id,
                ts_path=ts_candidate,
                base_path=base_candidate,
                base_node_id=edge.from_node,
                barrier_kcal_mol=ts_e - base_e,
                declared_kcal_mol=edge.barrier_kcal_mol,
            )
            for ts_candidate, ts_e in sorted(saddle_energies.items())
            for base_candidate, base_e in sorted(minima_energies.items())
            if base_e < ts_e
        ]
        declared_base_energy = _declared_node_energy_hartree(base_node)
        matched_base = None
        if declared_base_energy is not None:
            matched_base = _identify_by_declared_energy(sandbox, [path for _, path in below], declared_base_energy)
        if matched_base is not None:
            base_energy, base_path = next(
                (energy, path) for energy, path in below if path == matched_base
            )
            if len(below) > 1:
                report.notes.append(
                    f"edge {edge.id}: {len(below)} minima of {edge.from_node} below "
                    f"the saddle; using {base_path} (matches the node's declared "
                    "energy_hartree)"
                )
        else:
            if declared_base_energy is not None:
                report.notes.append(
                    f"edge {edge.id}: {edge.from_node} declares energy_hartree "
                    f"{declared_base_energy:.6f} but no bound minimum matches it; "
                    "barrier not derivable from the declared evidence"
                )
                continue
            below.sort(key=lambda item: (-item[0], item[1]))
            base_energy, base_path = below[0]
            if len(below) > 1:
                report.notes.append(
                    f"edge {edge.id}: several minima of {edge.from_node} below the "
                    f"saddle; using {base_path} (highest-energy minimum below the "
                    "saddle — the basin the saddle connects to)"
                )

        report.steps.append(
            StepBarrier(
                edge_id=edge.id,
                ts_path=ts_path,
                base_path=base_path,
                base_node_id=edge.from_node,
                barrier_kcal_mol=ts_energy - base_energy,
                declared_kcal_mol=edge.barrier_kcal_mol,
            )
        )

    if not report.steps:
        report.notes.append("no step barrier could be derived from the delivered logs")
    return report
```

##### 能量几何与频率支持的实际转发

来源：[cloudra/benchmark/barrier_evidence.py:188-200](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/barrier_evidence.py:188)

```python
def _frequency_supported(sandbox, path, candidates, expected):
    """A separate Freq can support an energy log only at the same geometry."""
    from cloudra.tools.core.irc_evidence import frames_for, last_geometry
    from cloudra.tools.core.irc_path import same_geometry
    resolved = _resolve_in_sandbox(sandbox, path)
    if resolved is None or not normal_log(resolved, max_scan_bytes=MAX_SCAN_BYTES):
        return False
    if _imaginary_frequency_count(sandbox, path) == expected:
        return True
    source = last_geometry(resolved, frames_for(resolved)[0])
    return any(_imaginary_frequency_count(sandbox, other) == expected and
               same_geometry(source, last_geometry(sandbox / other, frames_for(sandbox / other)[0]))
               for other in candidates)
```

##### 频率计数继续施加预算

来源：[cloudra/benchmark/barrier_evidence.py:165-185](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/barrier_evidence.py:165)

```python
def _imaginary_frequency_count(sandbox: Path, rel_path: str) -> Optional[int]:
    """证据文件里的虚频个数（判定它物理上是不是一阶鞍点）；不可判定返回 None。"""
    path = _resolve_in_sandbox(sandbox, rel_path)
    if path is None or not normal_log(path, max_scan_bytes=MAX_SCAN_BYTES):
        return None
    engine, frames = _frames_for(sandbox, rel_path)
    if engine not in _SCORING_ENGINES:
        return None
    if engine == "orca":
        # cclib 对 ORCA 6.1 日志裸抛 IndexError——走带文本回退的统一入口
        path = _resolve_in_sandbox(sandbox, rel_path)
        if path is None or not path.is_file():
            return None
        from cloudra.tools.core import orca_frames

        freqs = orca_frames.frequencies_with_text_fallback(str(path))
    else:
        freqs = _last_frequencies(frames)
    if not freqs:
        return None
    return sum(1 for f in freqs if f < 0)
```

##### 正常终止及预算检查之后才提取原生能量

来源：[cloudra/benchmark/barrier_evidence.py:124-162](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/barrier_evidence.py:124)

```python
def _engine_energy_kcal(sandbox: Path, rel_path: str) -> tuple[Optional[float], str]:
    """证据日志 → 最终能量（kcal/mol）。(值, 原因) —— 原因非空即不可用。

    ORCA 走文本权威能量行（cclib 对外部势/ExtOpt 日志常失败）；Gaussian 走
    帧记录的 cclib 能量。两者都不读任何散文。
    """
    from cloudra.tools.core import gaussian_frames, orca_frames
    from cloudra.tools.core.qm_engine import detect_qm_engine

    path = _resolve_in_sandbox(sandbox, rel_path)
    if path is None:
        return None, (
            f"{rel_path}: evidence reference escapes this task's sandbox; "
            "relative evidence references never cross tasks"
        )
    if not path.is_file():
        return None, f"{rel_path}: evidence file missing"
    if not normal_log(path, max_scan_bytes=MAX_SCAN_BYTES):
        return None, f'{rel_path}: normally terminated evidence within the scan limit required'
    engine = detect_qm_engine(str(path))
    if engine not in _SCORING_ENGINES:
        return None, (
            f"{rel_path}: engine {engine or 'unknown'} output does not count as "
            "evidence (ORCA/Gaussian log formats only)"
        )
    text = _read_text(path)
    if not text.strip():
        return None, f"{rel_path}: empty log"
    if engine == "orca":
        energy = orca_frames.final_energy_hartree(text)
    else:
        energy = None
        for frame in reversed(gaussian_frames.extract_frames(str(path))):
            if frame.scf_energy_hartree is not None:
                energy = frame.scf_energy_hartree
                break
    if energy is None:
        return None, f"{rel_path}: no final energy in the {engine} log"
    return float(energy) * HARTREE_TO_KCAL_MOL, ""
```

##### 准确度核对和返回；空图无 step 的路径也在此

来源：[cloudra/benchmark/accuracy.py:273-481](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/accuracy.py:273)

```python
def score_accuracy(
    *,
    evidence: "BarrierEvidence",
    gold: GoldSpec,
    rubric: AccuracyRubric | None = None,
    delivered_graph: Optional[GoldMechanismGraph] = None,
    cfg=None,
    match_threshold: float = 0.2,
) -> AccuracyReport:
    """评分边集合 = 全部 gold 边：带参考值的边逐边核对（"声明得到日志支撑"），
    再对 gold 比、按 gold 边 weight 加权平均；不带参考值的 accessible 边记 1.0、
    不可达边记 0.0。gold.reference_properties 非空时走性质锚点模式（与能垒模式
    互斥）。"""
    rubric = rubric or AccuracyRubric()
    rds = evidence.rds()
    rep = AccuracyReport(
        enabled=rubric.enabled,
        sigma_kcal=rubric.sigma_kcal_mol,
        log_barrier_kcal=rds.barrier_kcal_mol if rds is not None else None,
        declared_barrier_kcal=rds.declared_kcal_mol if rds is not None else None,
        rds_edge_id=rds.edge_id if rds is not None else "",
    )

    if not rubric.enabled:
        rep.gaussian_score = 1.0
        rep.final_score = 1.0
        rep.notes.append("accuracy disabled for this task; scored 1.0 (computable but not graded)")
        return rep
    if gold.reference_properties:
        return _score_properties(delivered_graph, gold.reference_properties, rep)
    scored_edges = list(gold.mechanism_graph.edges)
    if not scored_edges:
        rep.gaussian_score = 1.0
        rep.final_score = 1.0
        rep.notes.append("gold mechanism graph carries no edges; accuracy not scored")
        return rep

    # 逐边核对：缺失计该边零分，声明/日志冲突才触发 fail-loud。
    from cloudra.benchmark.graph_similarity import GedConfig

    cfg = cfg or GedConfig()
    gold_nodes = {n.id: n for n in gold.mechanism_graph.nodes}
    # 全零权重无法归一：退回逐边等权（避免除零；正常题库不出现）
    equal_fallback = sum(e.weight for e in scored_edges) <= 0
    if equal_fallback:
        rep.notes.append(
            "all scored-edge weights are zero; falling back to equal weighting"
        )
    weights = {e.id: (1.0 if equal_fallback else e.weight) for e in scored_edges}
    weight_total = sum(weights.values())
    edge_signatures = [
        (e.from_node, e.to_node, frozenset(e.bond_changes.pairs()))
        for e in scored_edges
    ]

    failures: list[str] = []
    weighted_sum = 0.0
    graded_weight = 0.0        # 已交付双来源参考边的权重和（高斯/定义差异罚分）
    graded_score_sum = 0.0     # Σ w·g（带参考值边）
    uncapped_penalty = 0.0     # 缺证据、缺声明或标答不可达边的零分记账
    for edge, signature in zip(scored_edges, edge_signatures):
        if edge.barrier_kcal_mol is None:
            if gold.mechanism_graph.edge_effectively_accessible(edge):
                rep.edge_scores[edge.id] = 1.0
                weighted_sum += weights[edge.id] * 1.0
                rep.notes.append(
                    f"edge {edge.id}: accessible but the gold reference carries no "
                    "reference barrier; scored 1.0"
                )
            else:
                rep.edge_scores[edge.id] = 0.0
                uncapped_penalty += weights[edge.id]
                rep.notes.append(
                    f"edge {edge.id}: effectively inaccessible in the gold "
                    "reference (the edge itself or its via transition state is "
                    "declared accessible=false); no accuracy score (0.0)"
                )
            continue
        step = _find_matching_step(
            edge, gold_nodes, evidence.steps, delivered_graph, cfg, match_threshold,
            require_channel=edge.channel is not None and edge_signatures.count(signature) > 1,
        )
        if step is None:
            rep.edge_scores[edge.id] = 0.0
            uncapped_penalty += weights[edge.id]
            rep.notes.append(
                f"gold edge {edge.id} carries a reference barrier but no delivered "
                "step matches its endpoint species; scored 0"
            )
            continue
        if step.edge_id != edge.id:
            rep.notes.append(
                f"gold edge {edge.id} matched delivered step {step.edge_id} "
                "by endpoint species"
            )
        if step.declared_kcal_mol is None:
            rep.edge_scores[edge.id] = 0.0
            uncapped_penalty += weights[edge.id]
            rep.notes.append(
                "delivered mechanism_graph.json declares no barrier_kcal_mol on "
                f"step edge {edge.id}; scored 0"
            )
            continue
        graded_weight += weights[edge.id]
        declared = step.declared_kcal_mol
        # 该边全部合法组合（TS 日志 × 起点极小值日志；含策略选中的那组）。
        # 声明支撑得住哪一组、哪一组能对上参考，决定这条边怎么算分：
        # 支撑得住 → 正常数值路径；支撑不住但证据里有能对参考的 → 答案定义/
        # 构象指认差异（小扣分，不是科学错误）；两者皆无 → 无据声明 fail-loud。
        candidates = evidence.alternatives.get(step.edge_id) or [step]
        sigma_eff = _effective_sigma(rubric, edge.barrier_kcal_mol)
        supported = [
            c for c in candidates
            if abs(declared - c.barrier_kcal_mol) <= rubric.sigma_kcal_mol
        ]
        matches_ref = [
            c for c in candidates
            if abs(c.barrier_kcal_mol - edge.barrier_kcal_mol) <= sigma_eff
        ]

        if supported:
            same_as_ref = any(
                (c.ts_path, c.base_path) in {(m.ts_path, m.base_path) for m in matches_ref}
                for c in supported
            )
            if matches_ref and not same_as_ref:
                rep.edge_scores[edge.id] = _DEFINITION_MISMATCH_EDGE_SCORE
                weighted_sum += weights[edge.id] * _DEFINITION_MISMATCH_EDGE_SCORE
                graded_score_sum += weights[edge.id] * _DEFINITION_MISMATCH_EDGE_SCORE
                ref = min(
                    matches_ref,
                    key=lambda c: (abs(c.barrier_kcal_mol - edge.barrier_kcal_mol),
                                   c.ts_path, c.base_path),
                )
                rep.notes.append(
                    f"edge {edge.id}: declared {declared:.3f} is supported by "
                    f"{supported[0].ts_path} / {supported[0].base_path}, but the "
                    f"delivered evidence also contains a combination consistent "
                    f"with the reference ({ref.barrier_kcal_mol:.3f} vs gold "
                    f"{edge.barrier_kcal_mol:.3f}, {ref.ts_path} / {ref.base_path}) "
                    "-> answer-definition mismatch, scored "
                    f"{_DEFINITION_MISMATCH_EDGE_SCORE}"
                )
                continue
            chosen = step if step in supported else min(
                supported,
                key=lambda c: (abs(declared - c.barrier_kcal_mol), c.ts_path, c.base_path),
            )
            g = gaussian_barrier_score(chosen.barrier_kcal_mol, edge.barrier_kcal_mol, sigma_eff)
            rep.edge_scores[edge.id] = g
            weighted_sum += weights[edge.id] * g
            graded_score_sum += weights[edge.id] * g
            rep.notes.append(
                f"edge {edge.id}: log-derived {chosen.barrier_kcal_mol:.3f} vs gold "
                f"{edge.barrier_kcal_mol:.3f} (sigma {sigma_eff:.1f}) -> {g:.4f} "
                f"(weight {weights[edge.id]})"
            )
            continue

        if matches_ref:
            ref = min(
                matches_ref,
                key=lambda c: (abs(c.barrier_kcal_mol - edge.barrier_kcal_mol),
                               c.ts_path, c.base_path),
            )
            rep.edge_scores[edge.id] = _DEFINITION_MISMATCH_EDGE_SCORE
            weighted_sum += weights[edge.id] * _DEFINITION_MISMATCH_EDGE_SCORE
            graded_score_sum += weights[edge.id] * _DEFINITION_MISMATCH_EDGE_SCORE
            rep.notes.append(
                f"edge {edge.id}: declared {declared:.3f} is not supported by any "
                "delivered log combination, but the evidence contains one "
                f"consistent with the reference ({ref.barrier_kcal_mol:.3f} vs gold "
                f"{edge.barrier_kcal_mol:.3f}, {ref.ts_path} / {ref.base_path}) "
                "-> answer-definition mismatch, scored "
                f"{_DEFINITION_MISMATCH_EDGE_SCORE}"
            )
            continue

        rep.edge_scores[edge.id] = 0.0
        failures.append(
            "declared vs log-derived barrier disagreement on edge "
            f"{edge.id} beyond sigma {rubric.sigma_kcal_mol}: declared "
            f"{declared:.3f} vs logs {step.barrier_kcal_mol:.3f}"
        )

    if failures:
        # fail-loud：参考边的声明/日志冲突且证据对不上参考 -> 置结构化标记、本层
        # accuracy 记 0（不给部分分，也不套 max_penalty_fraction 封顶），
        # composite 的短路由 runner 按 fail_loud 执行。
        rep.notes.extend(f"{note}; scored 0" for note in failures)
        rep.fail_loud = True
        rep.gaussian_score = 0.0
        rep.capped_penalty = 1.0
        rep.final_score = 0.0
        return rep

    rep.gaussian_score = weighted_sum / weight_total
    # max_penalty_fraction 只封顶带参考值边的罚分（高斯偏离/定义差异——兜合法的
    # 方法学差异）；缺失和标答不可达边按零分直接记账、不参与封顶，避免未完成
    # 或不可达边被数值容差保底抬分。
    graded_penalty = (graded_weight - graded_score_sum) / weight_total
    capped_graded = min(graded_penalty, rubric.max_penalty_fraction)
    rep.capped_penalty = capped_graded + uncapped_penalty / weight_total
    rep.final_score = 1.0 - rep.capped_penalty
    if graded_penalty > rubric.max_penalty_fraction:
        rep.notes.append(
            f"numeric penalty {graded_penalty:.3f} capped at {rubric.max_penalty_fraction}"
        )
    return rep
```

##### 现有测试固化了“超限按未覆盖判负”

来源：[tests/test_benchmark.py:2546-2562](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/tests/test_benchmark.py:2546)

```python
def test_selfconsistency_skips_oversized_logs(tmp_path, monkeypatch):
    """2c：超过共享上限的 QM 日志两层都不整读——绑定了超限文件的元素按
    未覆盖判负（用 monkeypatch 缩小上限模拟）。"""
    from cloudra.benchmark import selfconsistency as sc_mod

    big = tmp_path / "ts_opt.log"
    big.write_text(" Entering Gaussian System\n" + "x" * 100)
    monkeypatch.setattr(sc_mod, "MAX_SCAN_BYTES", 10)
    graph = _sc_graph(R={"accessible": False}, P={"accessible": False})
    files = [EvidenceFile(path="ts_opt.log", kind="gaussian", size=big.stat().st_size)]
    bindings = [
        NodeBinding(node_id="TS", bound_files=["ts_opt.log"], matched=True, quality=1.0),
    ]
    rep = sc_mod.audit_self_consistency(graph, bindings, files, tmp_path)
    edge = _checks_by_id(rep)["E1"]
    assert not edge.covered  # 超限文件不可解析，不构成可用证据
    assert rep.passed is False
```

#### 2. 空交付图获得“自洽通过”及 0.3，零证据处罚没有覆盖缺交付

**可触发条件**：交付文件只有 `{"nodes": [], "edges": []}`，没有任何计算日志；Gold 是正常的非空机理图，且目标边带参考能垒。图 schema 接受空列表，加载结果是“可解析交付图”。自洽检查未生成任何 ElementCheck，末尾 `all([])` 返回 True。runner 的零证据处罚只在 accessible_species 非空时检查，因此空图绕过。准确度按缺目标边记 0，最终保留 0.3 自洽贡献。

**设计根因**：合法的“全部元素明确不可达”与“根本没有交付任何元素”共用“没有 accessible 物种”的分支。自洽层空集合的数学真值被当作科学验收通过，再进入加权分数。这与真实已交付部分证据通过、保留部分分不同。

**限定与最小修复方向**：确认的是当前空图 `selfconsistency_passed=True`、final=0.3，并非声称其他非空部分交付也应清零。应先明确缺交付和显式不可达的语义；空图应走哪个结果/扣分由用户决定。本文不新增评分阈值、不改既定权重，也不替用户选择最终分值。

##### 2.1 已执行复现

在 TemporaryDirectory 写入唯一文件 `mechanism_graph.json={"nodes": [], "edges": []}`。Gold 含 R、TS、P 和一条 `barrier_kcal_mol=10.0` 的目标边。使用真实 TaskSpec 和 `score_sandbox`；runner 通过 `__new__` 构造，只注入 GedConfig，避免创建 BenchmarkDB。没有调用 backend 或运行 Agent。

实际输出：

```text
graph = 0.0
selfconsistency = True
accuracy = 0.0
final = 0.3
notes = [
  "no step barrier could be derived from the delivered logs",
  "gold edge E carries a reference barrier but no delivered step matches its endpoint species; scored 0"
]
```

##### 2.2 最短完整链及源码位置

共用第 1 节已经完整列出的 `score_sandbox → audit_integrity → load_delivered_graph → GoldMechanismGraph → audit_self_consistency → collect_barrier_evidence → score_accuracy → score_sandbox`。

关键分支为：图 schema 的 `nodes: list` 没有非空条件，加载返回空图对象；`audit_self_consistency` 的三个元素循环全部不执行，`report.passed = all(c.covered for c in report.checks)` 返回 True；`collect_barrier_evidence` 的边循环不执行，返回 steps=[]；`score_accuracy` 对 Gold 参考边没有 matching step，记 0；runner 的 `if accessible_species and ...` 不进入，然后照常加权。

图结构分的中间转发与实际返回如下。空图没有任何候选节点，匹配返回所有 Gold 节点缺失，图结构分为 0；该层没有把空图变成缺交付状态。

##### 图结构评分公开转发

来源：[cloudra/benchmark/graph_similarity.py:429-441](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/graph_similarity.py:429)

```python
def mechanism_similarity(
    agent: GoldMechanismGraph,
    gold: GoldMechanismGraph,
    cfg: Optional[GedConfig] = None,
    binding_quality: Optional[dict[str, float]] = None,
) -> GedResult:
    """Score agent mechanism against gold (subgraph coverage; extras free).
    Returns GedResult with score in [0, 1] (1 = gold fully covered) plus a
    human-readable edit script. `binding_quality` 是 integrity 的逐节点绑定
    质量图（交付节点 id → [0,1]）；缺省 None 不做证据加权（诊断/旧测试等
    无绑定信息的调用方不受影响）。"""
    cfg = cfg or GedConfig()
    return _subgraph_similarity(agent, gold, cfg, binding_quality)
```

##### 覆盖代价和图结构分返回

来源：[cloudra/benchmark/graph_similarity.py:355-421](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/graph_similarity.py:355)

```python
def _subgraph_similarity(
    agent: GoldMechanismGraph,
    gold: GoldMechanismGraph,
    cfg: GedConfig,
    binding_quality: Optional[dict[str, float]] = None,
) -> GedResult:
    """Subgraph coverage: every gold element must be covered by the delivered
    graph; extra delivered elements are free. Polynomial in practice (gold
    graphs are small), so no size guard is needed.

    证据加权：binding_quality（交付节点 id → 绑定质量，来自 integrity 报告）
    存在时，匹配的 accessible 交付节点有效代价 = 1 - (1 - subst_cost)·q——
    q=0（未绑定）等同未覆盖，部分绑定（质子化变体）部分扣。accessible=false
    的交付节点不参与绑定、不在字典里，q 缺省 1.0 正好不罚（标志一致性已由
    _node_subst_checked 单独把关）。"""
    ga, gg = _lift(agent), _lift(gold)
    gold_nodes = list(gg.nodes)
    agent_nodes = list(ga.nodes)

    def cost_of(g: str, a: str) -> float:
        cost = _node_subst_checked(gg.nodes[g], ga.nodes[a], cfg)
        if binding_quality:
            q = binding_quality.get(a, 1.0)
            cost = 1.0 - (1.0 - cost) * q
        return cost

    def edge_cost_of(asn: dict[str, Optional[str]]) -> float:
        total = 0.0
        grouped: dict[tuple[str, str], list[dict]] = {}
        for u, v, gattrs in gg.edges(data=True):
            mu, mv = asn.get(u), asn.get(v)
            if mu is None or mv is None:
                total += cfg.edge_insert_cost
            else:
                grouped.setdefault((mu, mv), []).append(gattrs)
        for (mu, mv), gold_edges in grouped.items():
            delivered_edges = list(ga.get_edge_data(mu, mv, default={}).values())
            matching = nx.Graph()
            for i, gattrs in enumerate(gold_edges):
                for j, aattrs in enumerate(delivered_edges):
                    cost = _edge_subst_checked(aattrs, gattrs, cfg)
                    if cost < cfg.edge_insert_cost:
                        matching.add_edge(("g", i), ("a", j), weight=cfg.edge_insert_cost - cost)
            covered = nx.max_weight_matching(matching, weight="weight")
            gain = sum(matching[u][v]["weight"] for u, v in covered)
            total += len(gold_edges) * cfg.edge_insert_cost - gain
        return total

    assignment = _assign_gold_nodes(gold_nodes, agent_nodes, cost_of, edge_cost_of)

    distance = edge_cost_of(assignment)
    for g in gold_nodes:
        a = assignment.get(g)
        distance += cost_of(g, a) if a is not None else cfg.node_insert_cost

    max_distance = (
        cfg.node_insert_cost * gg.number_of_nodes()
        + cfg.edge_insert_cost * gg.number_of_edges()
    )
    score = 1.0 - (distance / max_distance) if max_distance > 0 else 1.0
    score = max(0.0, min(1.0, score))
    return GedResult(
        score=score,
        distance=float(distance),
        max_distance=float(max_distance),
        edit_script=_describe_edits(ga, gg),
    )
```

##### 交付/Gold 图转换

来源：[cloudra/benchmark/graph_similarity.py:216-247](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/graph_similarity.py:216)

```python
def _lift(graph: GoldMechanismGraph) -> nx.MultiDiGraph:
    """Fold TS nodes into edges: node attribute 'smiles'; edge attribute
    'bond_changes' (frozenset) and 'has_ts' bool. TS nodes carry no SMILES in
    the gold reference, so they are not compared as species; their presence /
    correctness is encoded on the edge.

    MultiDiGraph：同一对物种间可能有多条基元步边（双通道机理），普通
    DiGraph 会互相覆盖丢边。边的 accessible 属性折叠为「有效可达性」
    （schema.GoldMechanismGraph.edge_effectively_accessible：边自身 AND
    经由的 TS 节点）——gold 把不可达标在 TS 节点上、交付标在边上，lift 后
    同口径可比。"""
    g = nx.MultiDiGraph()
    ts_ids = {n.id for n in graph.nodes if n.role.value == "transition_state"}
    signatures = [
        (e.from_node, e.to_node, frozenset(e.bond_changes.pairs()))
        for e in graph.edges
    ]
    for n in graph.nodes:
        if n.id in ts_ids:
            continue
        g.add_node(n.id, smiles=tuple(sorted(n.smiles)), accessible=n.accessible)
    for e, signature in zip(graph.edges, signatures):
        g.add_edge(
            e.from_node,
            e.to_node,
            bond_changes=e.bond_changes.pairs(),
            has_ts=bool(e.via),
            accessible=graph.edge_effectively_accessible(e),
            channel=e.channel,
            require_channel=e.channel is not None and signatures.count(signature) > 1,
        )
    return g
```

##### 空候选集合的实际匹配返回

来源：[cloudra/benchmark/graph_similarity.py:295-352](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/graph_similarity.py:295)

```python
def _assign_gold_nodes(
    gold_nodes: list[str],
    agent_nodes: list[str],
    cost_of,
    edge_cost_of=None,
) -> dict[str, Optional[str]]:
    """Injective gold->agent node assignment minimizing total cost.

    目标是节点替换代价 + （完整指派下的）边代价之和：退化机理（R/P 同
    SMILES）里节点代价并列的指派有多个，边连通性必须参与 tie-break，否则
    交叉指派会把真实存在的边判成缺失。未匹配的 gold 节点等价于"缺失"（按
    插入代价记账）。候选 = 替换代价严格小于 1.0 的节点（等于 1.0 与缺失同价
    且对边评估无意义）。候选组合在预算内全量 DFS，超预算退回贪心（仅按节点
    代价）。"""
    candidates: dict[str, list[tuple[float, str]]] = {}
    for g in gold_nodes:
        cands = sorted(
            (c, a) for a in agent_nodes if (c := cost_of(g, a)) < 1.0
        )
        candidates[g] = cands
    budget = 1
    for g in gold_nodes:
        budget *= max(1, len(candidates[g]))
    if budget <= _ASSIGNMENT_DFS_BUDGET:
        best_cost = math.inf
        best: dict[str, Optional[str]] = {}

        def dfs(i: int, used: set[str], total: float, cur: dict[str, Optional[str]]) -> None:
            nonlocal best_cost, best
            if total >= best_cost:
                return  # 边代价非负：节点部分已不优即可剪枝
            if i == len(gold_nodes):
                full = total + (edge_cost_of(cur) if edge_cost_of is not None else 0.0)
                if full < best_cost:
                    best_cost, best = full, dict(cur)
                return
            g = gold_nodes[i]
            for cost, a in candidates[g]:
                if a in used:
                    continue
                cur[g] = a
                dfs(i + 1, used | {a}, total + cost, cur)
            cur[g] = None  # 缺失
            dfs(i + 1, used, total + 1.0, cur)
            cur.pop(g)

        dfs(0, set(), 0.0, {})
        return best
    used: set[str] = set()
    assignment: dict[str, Optional[str]] = {}
    for g in sorted(gold_nodes, key=lambda g: candidates[g][0][0] if candidates[g] else math.inf):
        pick = next(((c, a) for c, a in candidates[g] if a not in used), None)
        if pick is not None:
            assignment[g] = pick[1]
            used.add(pick[1])
        else:
            assignment[g] = None
    return assignment
```

##### 缺失元素诊断返回

来源：[cloudra/benchmark/graph_similarity.py:444-475](/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/benchmark/graph_similarity.py:444)

```python
def _describe_edits(ga: nx.MultiDiGraph, gg: nx.MultiDiGraph) -> list[str]:
    """Human-readable structural diff. Agent 与 gold 的节点 id 命名空间不同，
    按 id 做差永远得到"全 removed/missing"，因此按物种 SMILES 多重集与
    （端点 SMILES + 键变化）描述的步骤多重集来描述差异。"""
    def species(multigraph):
        return sorted(tuple(sorted(attrs.get("smiles", ()))) for _, attrs in multigraph.nodes(data=True))

    def steps(multigraph):
        return sorted(
            (
                tuple(sorted(multigraph.nodes[u].get("smiles", ()))),
                tuple(sorted(multigraph.nodes[v].get("smiles", ()))),
                tuple(sorted(attrs.get("bond_changes", frozenset()))),
                # TS 折叠进边后，"是否经由 TS" 必须进 diff 键，否则缺 TS 的交付
                # 分数扣了、诊断文本却显示无差异
                bool(attrs.get("has_ts")),
            )
            for u, v, attrs in multigraph.edges(data=True)
        )

    out = []
    sa, sg = species(ga), species(gg)
    for s in sorted(set(sa) - set(sg)):
        out.append(f"species_removed:{list(s)}")
    for s in sorted(set(sg) - set(sa)):
        out.append(f"species_missing:{list(s)}")
    ea, eg = steps(ga), steps(gg)
    for e in sorted(set(ea) - set(eg)):
        out.append(f"step_removed:{e}")
    for e in sorted(set(eg) - set(ea)):
        out.append(f"step_missing:{e}")
    return out
```

#### 3. 本次实际执行的完整复现脚本与原始输出

脚本仅调用只读评分和探针函数，对 TemporaryDirectory 中的副本操作；实际 Fixture 从仓库读取，不修改源文件。未初始化 BenchmarkDB，未使用真实项目数据目录。

```python
import json
import tempfile
from pathlib import Path

from cloudra.benchmark.graph_similarity import GedConfig
from cloudra.benchmark.integrity import MAX_SCAN_BYTES, audit_integrity
from cloudra.benchmark.runner import BenchmarkRunner
from cloudra.benchmark.schema import TaskSpec
from cloudra.tools.core.irc_evidence import normal_log

runner = BenchmarkRunner.__new__(BenchmarkRunner)
runner.ged_config = GedConfig()

def task(graph):
    return TaskSpec.model_validate({
        'task_id': 'AUDIT_ONLY', 'tier': 'easy',
        'prompt': {'query': 'Temporary controlled audit; no agent is run.'},
        'system': {'reactants': ['O']},
        'gold': {'mechanism_graph': graph},
    })

with tempfile.TemporaryDirectory(prefix='cloudra-benchmark-audit-') as directory:
    root = Path(directory)
    empty = root / 'empty'
    empty.mkdir()
    (empty / 'mechanism_graph.json').write_text('{"nodes": [], "edges": []}')
    reference = {
        'nodes': [
            {'id': 'R', 'role': 'reactant', 'smiles': ['O']},
            {'id': 'TS', 'role': 'transition_state', 'smiles': []},
            {'id': 'P', 'role': 'product', 'smiles': ['O']},
        ],
        'edges': [{'id': 'E', 'from': 'R', 'to': 'P', 'via': 'TS', 'barrier_kcal_mol': 10.0}],
    }
    result = runner.score_sandbox(task(reference), empty)
    print('empty_graph', json.dumps({
        'graph': result.graph_score, 'selfconsistency': result.selfconsistency_passed,
        'accuracy': result.accuracy_score, 'final': result.final_score,
        'notes': result.notes,
    }))

    fixture = Path('tests/fixtures/gaussian/water_opt_freq_g16.out').read_bytes()
    offset = fixture.index(b'\n', 4096) + 1
    for label, content in [
        ('native', fixture),
        ('padded', fixture[:offset] + b'\n' * (MAX_SCAN_BYTES + 1) + fixture[offset:]),
    ]:
        sandbox = root / label
        sandbox.mkdir()
        path = sandbox / 'water.log'
        path.write_bytes(content)
        graph = {'nodes': [{'id': 'R', 'role': 'reactant', 'smiles': ['O'],
                            'properties': {'evidence_log': 'water.log'}}], 'edges': []}
        (sandbox / 'mechanism_graph.json').write_text(json.dumps(graph))
        integrity = audit_integrity(sandbox)
        result = runner.score_sandbox(task(graph), sandbox)
        print(label, json.dumps({
            'bytes': path.stat().st_size,
            'native_normal_and_same_frequency_geometry': normal_log(path),
            'within_benchmark_scan_limit': path.stat().st_size <= MAX_SCAN_BYTES,
            'explicit_binding': integrity.node_bindings[0].matched,
            'selfconsistency': result.selfconsistency_passed, 'final': result.final_score,
            'notes': result.notes,
        }))
```

原始输出：

```text
empty_graph {"graph": 0.0, "selfconsistency": true, "accuracy": 0.0, "final": 0.3, "notes": ["no step barrier could be derived from the delivered logs", "gold edge E carries a reference barrier but no delivered step matches its endpoint species; scored 0"]}
native {"bytes": 92872, "native_normal_and_same_frequency_geometry": true, "within_benchmark_scan_limit": true, "explicit_binding": true, "selfconsistency": true, "final": 1.0, "notes": ["no step barrier could be derived from the delivered logs", "gold mechanism graph carries no edges; accuracy not scored"]}
padded {"bytes": 21064393, "native_normal_and_same_frequency_geometry": true, "within_benchmark_scan_limit": false, "explicit_binding": false, "selfconsistency": false, "final": -1.0, "notes": ["unbound nodes (no matching evidence file): ['R']", "species R: no evidence bound to this node", "no step barrier could be derived from the delivered logs", "gold mechanism graph carries no edges; accuracy not scored", "no evidence bound to any accessible species node -> unsupported claims; penalty applied"]}
```

#### 4. 补扫结论和未扩大项

除此两项，本次补扫没有再确认新的“启发式硬否决正确证据”或“吞异常后科学通过”问题。检查过文件证据快照/绑定、几何身份、TS 优化与频率配对、DAG 交付文件校验、自洽覆盖、Gold-edge 回捞、能垒双来源核对和部分交付计分路径。

没有把科学判断本身或现有阈值偏好当作软件 bug；未把 RDKit 的潜在感知失败、未复现的数值误判或缺失依赖当作确认问题。没有对本轮 IRC 修复重复立项。

本补充报告未采用历史记忆中的运行状态作为证据。所有结论以当前源码及上述临时 fixture 输出为准。

## 前端补扫

### Cloudra 前端与 API 设计审计补充

范围：当前前端显示、表单回调、HTTP 命令结果与最终消费对象。2026-10-18 只读源码检查；未启动服务、浏览器或真实作业，未修改仓库源码。除明确标出的纯内存命令验证外，以下行为是沿当前实际源码推导，不冒充 UI 现场复现。

确认三项此前运行时报告未覆盖的问题：侧栏操作改错项目、输入框写当前 B 却发送给 A 的交互等待、创建被拒绝却显示创建成功。以下按实际请求顺序列出短源码链；共享命令传递/返回源码集中在第 0 节，后续不重复全文。

#### 0. 共用 HTTP 与命令接受/拒绝返回契约

HTTP request 仅对非 2xx 抛错；CommandBus 遇到 CommandRejected 将其变成 accepted=false 的普通返回值；ApiContext 不把这种返回值自动改为错误 HTTP。因而每个前端命令调用都必须消费 accepted，或在共同层统一处理。此处只是说明现有协议，不建议增加新的确认门。

##### HTTP request 与已有 assertAccepted：检查存在，但未统一使用

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/api.ts:45-91`

```typescript

export class ApiError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${runtimeUrl}${path}`, {
    ...init,
    headers: {
      ...(init?.headers ? {} : { 'Content-Type': 'application/json' }),
      ...(init?.headers as Record<string, string> | undefined),
      ...authHeaders(),
    },
  });
  if (!resp.ok) {
    let code = resp.status === 401 ? 'unauthorized' : 'http_error';
    let message = resp.status === 401 ? '需要 API token（用启动时打印的 #token= URL 打开）' : resp.statusText;
    try {
      const body = await resp.json();
      code = body.detail?.code ?? code;
      message = body.detail?.message ?? body.detail ?? message;
    } catch {
      /* keep defaults */
    }
    throw new ApiError(code, String(message));
  }
  return (await resp.json()) as T;
}

interface CommandResponse<T> {
  command_id: string;
  accepted: boolean;
  event_id: string;
  data: T;
}

function assertAccepted<T>(resp: CommandResponse<T>, fallback: string): CommandResponse<T> {
  if (resp.accepted === false) {
    const err = (resp.data as { error?: { message?: string } } | null)?.error;
    throw new ApiError('rejected', err?.message ?? fallback);
  }
  return resp;
}
```

##### API 中间转发和 CommandResponse 返回

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/api_v2/context.py:34-56`

```python
    async def execute(self, command: Command) -> CommandResponse:
        try:
            result = await self.bus.execute(command)
        except CommandRejected as exc:
            http_code = {
                "not_found": status.HTTP_404_NOT_FOUND,
                "state_conflict": status.HTTP_409_CONFLICT,
            }.get(exc.code, status.HTTP_400_BAD_REQUEST)
            raise HTTPException(
                status_code=http_code,
                detail={"code": exc.code, "message": exc.message},
            ) from exc
        data = result.data
        if isinstance(data, AgentSession):
            # 命令响应里的 agent 与 GET 端点同形：运行期投影（completion）也带上，
            # 否则前端用响应整体替换 agent 时会丢掉它。
            data = await asyncio.to_thread(agent_dict, self.core, data)
        return CommandResponse(
            command_id=result.command_id,
            accepted=result.accepted,
            event_id=result.event_id,
            data=data,
        )
```

##### CommandBus 入口

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/commands.py:914-916`

```python
    async def execute(self, command: Command) -> CommandResult:
        async with self.core.command_lock:
            return await self._execute_locked(command)
```

##### 命令执行、CommandRejected 转返回值的完整分支

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/commands.py:918-972`

```python
    async def _execute_locked(self, command: Command) -> CommandResult:
        core = self.core
        cached = core.cached_result(command.command_id)
        if cached is not None:
            return cached
        decider = DECIDERS.get(command.type)
        wrapper = WRAPPERS.get(command.type)
        if decider is None and wrapper is None:
            raise CommandRejected("invalid_request", f"unknown command type {command.type!r}")
        try:
            if command.type == "project.delete":
                from cloudra.persistence.database import ComputeDB
                from cloudra.services.compute_store import (
                    acount_active_compute_job_states,
                    active_jobs_delete_message,
                )

                project_id = _project_id(core, command)
                counts = await acount_active_compute_job_states(ComputeDB(), project_id)
                if counts:
                    raise CommandRejected(
                        "state_conflict",
                        active_jobs_delete_message(counts),
                    )
            if decider is not None:
                # 拍 1：纯 decide（守卫校验在这里抛 CommandRejected）
                if decider is _decide_cancel_agent:
                    # Query history off-loop, then validate the captured event
                    # boundary before making the pure decision atomically.
                    while True:
                        boundary = len(core.event_log)
                        candidates = [agent.model_copy(deep=True) for agent in core.agents.values()]
                        parked = await asyncio.to_thread(lambda: {
                            agent.id for agent in candidates if is_background_parked(core, agent)
                        })
                        if boundary == len(core.event_log):
                            break
                    decision = _decide_cancel_agent(core, command, parked_sessions=parked)
                else:
                    decision = decider(core, command)
                if await self._recover_interrupted_invocations(decision):
                    # Publication may submit a nested message. Re-decide so
                    # that an already reopened session does not get two runs.
                    decision = decider(core, command)
                # 拍 2-4：落日志/发布/持久化 → apply → effects
                result = await self._apply_decision(command, decision)
            else:
                # 薄包装：broker 自带事件流与 future 解析，bus 扫尾发布/持久化
                result = await wrapper(core, command)
                await self._flush()
        except CommandRejected as exc:
            result = await self._reject(command, exc)
        core.remember(command, result)
        await self._maybe_snapshot()
        return result
```

##### 事件落盘与应用、结果返回

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/commands.py:1036-1081`

```python
    async def _apply_decision(self, command: Command, decision: Decision) -> CommandResult:
        core = self.core
        envelopes: list[EventEnvelope] = []

        def project(envelope: EventEnvelope) -> None:
            apply_event(core, envelope)
            envelopes.append(envelope)

        try:
            await core.event_writer.commit_and_apply(decision.events, project)
            # 拍 4：副作用（runner/mailbox/文件系统/内存秘密覆盖）
            for effect in decision.effects:
                await _execute_effect(core, effect)
        except EventPersistenceError:
            # spawned 已落盘：返回已创建的 agent 并尽量跑完 effects，
            # 避免 HTTP 500 触发新 command_id 再造一个 coordinator。
            if any(envelope.type == "agent.spawned" for envelope in envelopes):
                persisted = {envelope.type for envelope in envelopes}
                for effect in decision.effects:
                    if (
                        isinstance(effect, DeliverMessage)
                        and "agent.message_injected" not in persisted
                    ):
                        continue
                    try:
                        await _execute_effect(core, effect)
                    except Exception:
                        logger.exception(
                            "spawn effect after partial persist failed for %s",
                            command.command_id,
                        )
                return CommandResult(
                    command_id=command.command_id,
                    accepted=True,
                    event_id=envelopes[-1].event_id,
                    data=self._resolve_result(decision.result),
                )
            raise
        receipt = envelopes[-1] if envelopes else None
        if command.type == "agent.message":
            receipt = next(event for event in envelopes if event.type == "agent.message_injected")
        return CommandResult(
            command_id=command.command_id,
            event_id=receipt.event_id if receipt else "",
            data=self._resolve_result(decision.result),
        )
```

##### 返回实际项目/Agent/角色对象

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/commands.py:1083-1093`

```python
    def _resolve_result(self, result: Any) -> Any:
        """ResultRef 在 apply+effects 之后解析为活对象；字面量原样返回。"""
        core = self.core
        if isinstance(result, ResultRef):
            if result.kind == "project":
                return core.require_project(result.key)
            if result.kind == "agent":
                return core.require_agent(result.key)
            if result.kind == "role":
                return core.roles.require(result.key)
        return result
```

##### 实际拒绝响应：accepted=false，而非重新抛出

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/commands.py:1095-1126`

```python
    async def _reject(self, command: Command, exc: CommandRejected) -> CommandResult:
        """拒绝路径：先落异常携带的领域审计草稿，再落 command.rejected。

        （顺带修复旧行为：spawn_requested/spawn_rejected 等拒绝轨迹此前只进
        内存日志、从不发布/持久化，重启即丢。）
        """
        core = self.core
        appended: list[EventEnvelope] = []
        for draft in exc.events:
            before_append = len(core.event_log)
            appended.append(self._append_draft(draft))
            await self._persist_appended(keep=before_append)
        before_append = len(core.event_log)
        appended.append(
            core.record(
                "command.rejected",
                stream="project",
                project_id=_project_id(core, command),
                data={
                    "command_type": command.type,
                    "code": exc.code,
                    "message": exc.message,
                },
            )
        )
        await self._persist_appended(keep=before_append)
        return CommandResult(
            command_id=command.command_id,
            accepted=False,
            event_id=appended[-1].event_id,
            data={"error": {"code": exc.code, "message": exc.message}},
        )
```

##### 实际公开响应 schema

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/api_v2/models.py:157-161`

```python
class CommandResponse(BaseModel):
    command_id: str
    accepted: bool
    event_id: str
    data: Any = None
```

##### HTTP 入参到命令载荷的转换

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/api_v2/models.py:164-165`

```python
def _command_payload(body: BaseModel) -> dict[str, Any]:
    return body.model_dump(exclude_unset=True)
```

#### 1. [P1] 点击项目 P 的更改按钮，实际改的是当前项目 Q

**精确触发：** 当前选中 Q，侧栏还显示另一个项目 P。直接点 P 行的“更改”按钮并在文件夹选择器确认新目录。按钮显式 stopPropagation，所以点击不会先切换到 P。按钮标题和选择器初始目录来自 P，用户指定的操作对象明确是 P。

**实际后果：** 回调没有携带 p.id，而 changeWorkspace 读取 activeProject.id，因此发出的 PATCH 是 Q；后端按该 URL 真的更新 Q 的 workspace_dir，P 不变。若所选值碰巧等于 Q 的现目录，函数会提前返回，P 仍未被修改。这不是网络竞态；当前点击链稳定丢失了目标项目身份。

**设计根因：** 单项列表操作用全局当前选中对象执行，渲染身份和写入身份分裂。

**最小修法：** 让 changeWorkspace 接收被点项目的 id，并由 P 的按钮传 p.id；成功返回只更新这个 id。无需新确认状态或更多守卫。

注意中文按钮实际文案是“更改”，英文为 Rename；此发现依据按钮绑定的具体项目与最终 PATCH 对象，不把文案翻译当作缺陷。

##### 当前全局选中的项目与 Agent

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/App.tsx:273-276`

```tsx
  const interactions = attention.get(activeProjectId ?? '')?.interactions ?? [];
  const activeProject = projects.find((p) => p.id === activeProjectId) ?? null;
  const activeAgent = agents.find((a) => a.id === activeAgentId) ?? null;
  // Visual mode gates the composer attach button; defaults to on.
```

##### 当前中文按钮文案

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/i18n.tsx:20-25`

```tsx
    sidebarNoProjectsHint: '暂无项目，请在上方新建',
    sidebarArchivedCount: (count: number) => `已归档项目 (${count})`,
    sidebarRestore: '恢复',
    sidebarArchive: '归档',
    sidebarRename: '更改',
    sidebarGlobalSettings: '全局设置',
```

##### 项目行按钮：标题/初始路径是 P，点击不切换项目，回调却未携带 P.id

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/App.tsx:2018-2052`

```tsx
                      {list.map((p) => {
                        const isActive = p.id === activeProjectId;
                        return (
                          <div
                            key={p.id}
                            className={`project-node ${isActive ? 'active' : ''}`}
                          >
                            <div
                              className="project-node-header"
                              onClick={() => selectProject(p.id)}
                              title={`选择项目: ${p.name}`}
                            >
                              <div className="project-node-title">
                                {isActive && <span className="active-dot" />}
                                <span className="project-title-text">{p.name}</span>
                                {p.name.startsWith('benchmark:') && (
                                  <span className="badge sm bm-tag">BM</span>
                                )}
                              </div>
                              <div className="project-node-actions">
                                <button
                                  type="button"
                                  className="btn ghost sm mini-icon-btn"
                                  title={`${t.sidebarRename} "${p.name}"`}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    openPathPicker({
                                      title: `${t.sidebarRename} ${p.name}`,
                                      initialPath: p.workspace_dir ?? undefined,
                                      onSelect: (newDir) => void changeWorkspace(newDir),
                                    });
                                  }}
                                >
                                  {t.sidebarRename}
                                </button>
```

##### 路径选择器中间层保存原回调

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/App.tsx:363-377`

```tsx
  const openPathPicker = useCallback(
    (options: {
      title?: string;
      initialPath?: string;
      onSelect: (path: string) => void;
    }) => {
      setPathPicker({
        isOpen: true,
        title: options.title,
        initialPath: options.initialPath,
        onSelect: options.onSelect,
      });
    },
    [],
  );
```

##### 保存的回调转交真实 PathPickerModal

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/App.tsx:2833-2840`

```tsx
        <PathPickerModal
          isOpen={pathPicker.isOpen}
          title={pathPicker.title}
          initialPath={pathPicker.initialPath}
          extraShortcuts={extraPickerShortcuts}
          onSelect={pathPicker.onSelect}
          onClose={() => setPathPicker((prev) => ({ ...prev, isOpen: false }))}
        />
```

##### 用户确认选择后调用该 onSelect

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/PathPickerModal.tsx:415-433`

```tsx
          <div className="modal-actions">
            <button type="button" className="btn ghost sm" onClick={onClose}>
              Cancel
            </button>
            <button
              type="button"
              className="btn primary sm path-confirm-btn"
              disabled={!selectedPath && !currentPath}
              onClick={() => {
                const finalPath = selectedPath || currentPath;
                if (finalPath) {
                  onSelect(finalPath);
                  onClose();
                }
              }}
            >
              Select This Folder
            </button>
          </div>
```

##### 实际写操作错误读取 activeProject.id，并按此更新界面

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/App.tsx:1001-1012`

```tsx
  async function changeWorkspace(dir: string) {
    if (!activeProject) return;
    const value = dir.trim() || null;
    if (value === (activeProject.workspace_dir ?? null)) return;
    try {
      const resp = await api.patchProject(activeProject.id, { workspace_dir: value });
      setProjects((prev) => prev.map((p) => (p.id === activeProject.id ? resp.data : p)));
      pushToast('ok', value ? `Workspace → ${value}` : 'Workspace cleared');
    } catch (e) {
      reportError(e);
    }
  }
```

##### 最终 HTTP PATCH URL 使用函数收到的项目 id

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/api.ts:112-117`

```typescript
  patchProject: (projectId: string, patch: Record<string, unknown>) =>
    request<CommandResponse<Project>>(`/api/v2/projects/${projectId}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),
  archiveProject: (projectId: string) =>
```

##### API 按 URL 项目 id 消费 workspace 修改

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/api_v2/routers/projects.py:41-48`

```python
    @router.patch("/api/v2/projects/{project_id}", dependencies=ctx.protected)
    async def patch_project(project_id: str, body: ProjectPatch) -> CommandResponse:
        command = Command(
            type="project.update",
            target={"project_id": project_id},
            payload=_command_payload(body),
        )
        return await ctx.execute(command)
```

##### 实际项目修改 schema

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/api_v2/models.py:16-20`

```python
class ProjectPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    workspace_dir: Optional[str] = None
    archived: Optional[bool] = None
    settings: Optional[dict[str, Any]] = None
```

##### 实际更新决策按目标 id 取项目、归一化路径并记录修改

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/commands.py:185-237`

```python
def _decide_update_project(core: RuntimeCore, command: Command) -> Decision:
    project = core.require_project(_project_id(core, command))
    payload = command.payload
    changes: dict[str, Any] = {}
    for field in ("name", "workspace_dir", "archived"):
        if field in payload:
            changes[field] = payload[field]
    effects: list[Effect] = []
    if changes.get("workspace_dir"):
        changes["workspace_dir"] = _normalize_workspace(changes["workspace_dir"])
        effects.append(EnsureDir(changes["workspace_dir"]))
    drafts: list[EventDraft] = []
    if changes:
        # dict(changes) 冻结事件负载：settings 合并走独立事件，绝不能让
        # 后续的本地变更漏进已落日志的 envelope（旧代码的引用泄漏曾让
        # project.updated 的 data 混入 ProjectSettings 对象，落盘即崩）。
        drafts.append(
            EventDraft(
                "project.updated",
                stream="project",
                project_id=project.id,
                data={"changes": dict(changes), "actor": command.actor},
            )
        )
    if "settings" in payload:
        # decide 侧校验：非法 settings 必须在事件落日志之前抛错。
        settings_changes = dict(payload["settings"])
        benchmark_task_id = project.settings.benchmark_task_id
        if benchmark_task_id is not None:
            if settings_changes.get("benchmark_task_id", benchmark_task_id) != benchmark_task_id:
                raise CommandRejected("invalid_request", "Benchmark task identity cannot be changed")
            settings_changes["benchmark_task_id"] = benchmark_task_id
            settings_changes.setdefault("method_policy", project.settings.method_policy.model_dump(mode="json")
                if project.settings.method_policy is not None else None)
        new_settings = ProjectSettings.model_validate(settings_changes)
        drafts.append(
            EventDraft(
                "project.settings_changed",
                stream="project",
                project_id=project.id,
                data={"changes": settings_changes, "actor": command.actor},
            )
        )
        # 事件驱动督导（Task 4）：切回 dag_guided 沿补一次待办通知——退出
        # guided 期间生产端通知口是关闭的，积压在持久化信箱里；只在迁移沿
        # 触发（guided→guided 重写不重复通知）。shell 侧的 reconcile 按
        # 状态表补通知：failed/cancelled 的 supervisor 不复活、待办不清空。
        if (
            new_settings.orchestration_mode is OrchestrationMode.DAG_GUIDED
            and project.settings.orchestration_mode is not OrchestrationMode.DAG_GUIDED
        ):
            effects.append(ReconcileSupervision(project.id))
    return Decision(events=tuple(drafts), effects=tuple(effects), result=ResultRef("project", project.id))
```

##### 最终生效对象由事件 project_id 决定

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/apply.py:105-109`

```python
def _apply_project_updated(core: RuntimeCore, envelope: EventEnvelope) -> None:
    project = core.require_project(envelope.project_id)
    project = project.model_copy(update=envelope.data.get("changes", {}))
    project.updated_at = envelope.created_at
    core.projects[project.id] = project
```

其后的命令成功返回路径是第 0 节 `_apply_decision → _resolve_result → ApiContext.execute → request`。前端 changeWorkspace 随后用同一个 activeProject.id 替换项目并显示 Workspace 成功通知。

#### 2. [P1] 普通输入框显示“Reply to B”，实际消耗的是 A 的等待回答

**精确触发：** 同项目 A=small_mol 正在 ask_user，用户当前选择 B=researcher，二者 session 和 role 均不同。用户没有点 A 的“在此回答”或跳转按钮，而在当前普通 composer 输入给 B 的内容并 Send。A 不是当前 Agent，所以普通 composer 会显示；placeholder 却把当前 B 的名字与项目第一个 pending 问题拼在一起。

**最终消费：** sendMessage 把项目全部 interactions 给路由器；路由器只要列表不空就返回第一个 interaction_id，没有接收 activeAgentId 的能力。前端 POST 该 id，服务端从 pending 项取回 A 的 session_id，落 interaction.responded 并直接 resolve A 的等待 future。不会向 B 发送普通消息。

**为什么不是明确选择回答 A：** 专用 InteractionPrompt 当前已经有“其他 Agent 正在问”的提示条、明确显示真实 A，且要求点“在此回答”才展开答题框；这条正确交互路径不在缺陷范围。本项只针对旁边的普通 composer：它未经过这个明确选择，却全项目自动劫持为回答 A，并显示 B 名字。

**设计根因：** 项目收件箱、当前会话输入框各自维护一套发送目标规则，真正请求目标由列表顺序决定，显示目标由 activeAgent 决定。

**最小修法：** 普通 composer 只为当前 session 的 pending 交互改成回复模式；其他 Agent 的问题继续交由已有明确选择的 InteractionPrompt/AttentionDock。禁止用角色名替代已存在的 session_id 判断，避免同角色多实例继续混淆。

现有 `frontend/src/composerSend.test.ts` 把“选中了 Agent 仍劫持为任意 pending”写成断言；测试没有传 session 归属，未覆盖 B 显示/A 消费。

##### 项目级问题列表与回答 HTTP 接口

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/api.ts:293-298`

```typescript
  interactions: (projectId: string) => request<Array<Record<string, unknown>>>(`/api/v2/projects/${projectId}/interactions`),
  respondInteraction: (projectId: string, interactionId: number | string, response: string) =>
    request<Record<string, unknown>>(`/api/v2/projects/${projectId}/interactions/${interactionId}/response`, {
      method: 'POST',
      body: JSON.stringify({ response }),
    }),
```

##### 服务端列表只有显式传 session_id 时才过滤

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/api_v2/routers/pending.py:44-52`

```python
    @router.get("/api/v2/projects/{project_id}/interactions", dependencies=ctx.protected)
    async def list_interactions(
        project_id: str, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        ctx.core.require_project(project_id)
        rows = ctx.core.pending.list_pending_interactions(project_id)
        if session_id is not None:
            rows = [row for row in rows if row["session_id"] == session_id]
        return rows
```

##### 问题载入后原样存入项目 attention，不按当前 session 过滤

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/App.tsx:402-438`

```tsx
  const refreshProjectPending = useCallback((projectId: string, changed = false): Promise<ProjectPending | undefined> => {
    if (!projectsRef.current.some((project) => project.id === projectId && !project.archived)) return Promise.resolve(undefined);
    const existing = pendingLoadsRef.current.get(projectId);
    if (existing) {
      if (changed) pendingDirtyRef.current.add(projectId);
      return existing;
    }
    const promise: Promise<ProjectPending | undefined> = Promise.resolve().then(async () => {
      let latest: ProjectPending | undefined;
      do {
        pendingDirtyRef.current.delete(projectId);
        try {
          const [approvals, interactions] = await Promise.all([
            api.approvals(projectId), api.interactions(projectId),
          ]);
          const project = projectsRef.current.find((item) => item.id === projectId && !item.archived);
          if (!project || pendingLoadsRef.current.get(projectId) !== promise) return;
          // A committed change arrived while HTTP was running. Do not publish
          // its older snapshot; callers share the follow-up request as well.
          if (pendingDirtyRef.current.has(projectId)) continue;
          const pending = { name: project.name, approvals, interactions };
          latest = pending;
          setAttention((prev) => new Map(prev).set(projectId, pending));
        } catch {
          // Keep the last visible pending state; the next fallback retries.
        }
      } while (pendingDirtyRef.current.has(projectId) && projectsRef.current.some((item) => item.id === projectId && !item.archived));
      return latest;
    }).finally(() => {
      if (pendingLoadsRef.current.get(projectId) === promise) {
        pendingLoadsRef.current.delete(projectId);
        pendingDirtyRef.current.delete(projectId);
      }
    });
    pendingLoadsRef.current.set(projectId, promise);
    return promise;
  }, []);
```

##### 取项目全部 interactions；B 无自己待办时 hasActiveAgentDecision=false

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/App.tsx:273-292`

```tsx
  const interactions = attention.get(activeProjectId ?? '')?.interactions ?? [];
  const activeProject = projects.find((p) => p.id === activeProjectId) ?? null;
  const activeAgent = agents.find((a) => a.id === activeAgentId) ?? null;
  // Visual mode gates the composer attach button; defaults to on.
  const visualOn = activeProject
    ? (activeAgent?.settings.visual_mode ?? activeProject.settings.defaults?.visual_mode ?? true) !== false
    : false;

  const hasActiveAgentDecision = Boolean(
    interactions.find(
      (ixn) =>
        (activeAgent?.id && String(ixn.session_id) === String(activeAgent.id)) ||
        (activeAgent?.role_id && String(ixn.agent_id) === String(activeAgent.role_id))
    ) ||
    approvals.find(
      (appr) =>
        (activeAgent?.id && String(appr.session_id) === String(activeAgent.id)) ||
        (activeAgent?.role_id && (String(appr.agent_name) === String(activeAgent.role_id) || String(appr.agent_name) === String(activeAgent.display_name)))
    ) ||
    ((interactions.length > 0 || approvals.length > 0) && !activeAgent)
```

##### 正确专用卡片：实际问题拥有者与当前会话区分，专用答案按 itemId 发送

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/InteractionPrompt.tsx:112-143`

```tsx

  // Resolve asking agent name & object
  const sessionId = currentItem.data.session_id;
  const rawAgentId = isApproval ? approvalData?.agent_name : interactionData?.agent_id;
  const askingAgent =
    agents.find((a) => a.id === sessionId) ||
    agents.find((a) => a.role_id === rawAgentId || a.display_name === rawAgentId);
  const agentDisplayName =
    askingAgent?.display_name || askingAgent?.role_id || String(rawAgentId || 'Agent');

  // Check if current item belongs to active viewed agent
  const isCurrentAgent =
    !activeAgent ||
    (sessionId && sessionId === activeAgent.id) ||
    (rawAgentId && (rawAgentId === activeAgent.role_id || rawAgentId === activeAgent.display_name));

  // Parsed data for interaction
  const parsedInteraction = !isApproval
    ? parseInteractionDetails(interactionData?.prompt ?? interactionData?.message ?? interactionData?.question)
    : null;

  // Handlers for interaction
  const handleSendAnswer = async (responseValue?: string) => {
    if (sending || isApproval) return;
    const finalAnswer = (responseValue !== undefined ? responseValue : answerDraft).trim();
    if (!finalAnswer && !parsedInteraction?.defaultAnswer) return;
    const submission = finalAnswer || parsedInteraction?.defaultAnswer || '';
    if (!(await onRespond(itemId, submission)) || selectedKeyRef.current !== selectedKey) return;
    setAnswerDraft('');
    setShowRejectInput(false);
    setRejectReason('');
  };
```

##### 专用卡片其他 Agent 必须明确选择的分支条件

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/InteractionPrompt.tsx:171-172`

```tsx
  // If item is for another agent and user hasn't clicked "Reply Here", render an alert ribbon above composer
  if (!isCurrentAgent && !forceInlineReply) {
```

##### 专用卡片显示 A 并提供明确的跳转/在此回答按钮

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/InteractionPrompt.tsx:209-241`

```tsx
    if (parsedInteraction) {
      return (
        <div className="interaction-dock-banner" data-testid="interaction-other-agent-banner">
          <div className="interaction-dock-banner-left">
            <span className="interaction-pulse-beacon" />
            <span className="interaction-banner-badge">{agentDisplayName}</span>
            <span className="interaction-banner-text">
              {t.interactionOtherAgentAsking(agentDisplayName)}: “{parsedInteraction.question.slice(0, 70)}
              {parsedInteraction.question.length > 70 ? '…' : ''}”
            </span>
          </div>
          <div className="interaction-dock-banner-actions">
            {askingAgent && onSelectAgent && (
              <button
                type="button"
                className="btn ghost sm interaction-jump-btn"
                onClick={() => onSelectAgent(askingAgent.id)}
              >
                {t.interactionJumpToAgent} →
              </button>
            )}
            <button
              type="button"
              className="btn green sm interaction-reply-here-btn"
              onClick={() => setForceInlineReply(true)}
            >
              {t.interactionAnswerHere}
            </button>
          </div>
        </div>
      );
    }
  }
```

##### 专用卡片与普通 composer 并存；B 无待办时普通 composer 显示

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/App.tsx:2493-2512`

```tsx
          {(interactions.length > 0 || approvals.length > 0) && (
            <InteractionPrompt
              key={activeProjectId}
              interactions={interactions}
              approvals={approvals}
              activeAgent={activeAgent}
              agents={agents}
              onRespond={handleRespondInteraction}
              onDecide={handleDecideApproval}
              onSelectAgent={(agentId: string) => void selectAgent(agentId)}
              onToggleYolo={(yoloVal: boolean) => toggleProjectYolo(yoloVal)}
              isYolo={activeProject?.settings.defaults?.yolo === true}
              sending={sending}
              t={t}
              isCollapsed={interactionCollapsed}
              onToggleCollapse={(c: boolean) => setInteractionCollapsed(c)}
            />
          )}
          {(!hasActiveAgentDecision || interactionCollapsed) && (
            <div className="composer">
```

##### 有任意 pending 时，普通输入框仍使用当前 B 的名称

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/App.tsx:2579-2591`

```tsx
              placeholder={
                !activeProject
                  ? 'Select or create a project first…'
                  : interactions.length > 0
                    ? `Reply to ${activeAgent?.display_name ?? 'agent'}: ${short(cleanPromptText(interactions[0].prompt ?? interactions[0].message), 60)}…`
                    : activeAgent
                      ? activeAgent.state === 'failed' || activeAgent.state === 'cancelled'
                        ? `Message ${activeAgent.display_name} — this reopens it with a fresh run…`
                        : `Guide ${activeAgent.display_name}…`
                      : 'Describe the task for the coordinator…'
              }
              disabled={!activeProject}
            />
```

##### 普通 Send 按钮调用 sendMessage

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/App.tsx:2629-2637`

```tsx
              {activeAgent && activeAgent.state === 'running' && (
                <button className="btn ghost sm" onClick={() => cancelAgent()}>Cancel</button>
              )}
              <button className="btn primary sm" onClick={sendMessage} disabled={!draft.trim() || !activeProject || sending}>
                {sending ? 'Sending…' : 'Send'}
              </button>
            </div>
          </div>
          )}
```

##### sendMessage 传入全项目列表，未传当前 session 身份

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/App.tsx:1129-1143`

```tsx
  async function sendMessage() {
    const target = resolveComposerSendTarget({
      draft,
      sending,
      hasProject: Boolean(activeProject),
      hasAgent: Boolean(activeAgent),
      interactions,
    });
    if (target.kind === 'noop' || !activeProject) return;
    const content = draft.trim();
    const pendingId = `pending-${++pendingMessageSeqRef.current}`;
    const images = pendingImages.map((p) => p.path);
    const imageArtifactIds = pendingImages.map((p) => p.artifactId);
    setSending(true);
    try {
```

##### 完整路由函数：列表第一个问题压过普通 Agent 消息

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/composerSend.ts:1-42`

```typescript
/** Composer send routing: pending ask_user hijacks Send away from messages. */

export type PendingInteraction = {
  interaction_id?: string | number;
  id?: string | number;
};

export type ComposerSendTarget =
  | { kind: 'slash'; command: string }
  | { kind: 'respond'; interactionId: string | number }
  | { kind: 'spawn_coordinator' }
  | { kind: 'message' }
  | { kind: 'noop'; reason: 'empty' | 'busy' | 'no_project' };

/**
 * Decide where a composer Send goes. Mirrors App.tsx sendMessage branching
 * (slash commands are detected here but handled by the caller).
 */
export function resolveComposerSendTarget(opts: {
  draft: string;
  sending: boolean;
  hasProject: boolean;
  hasAgent: boolean;
  interactions: PendingInteraction[];
}): ComposerSendTarget {
  const content = opts.draft.trim();
  if (!content) return { kind: 'noop', reason: 'empty' };
  if (!opts.hasProject) return { kind: 'noop', reason: 'no_project' };
  if (opts.sending) return { kind: 'noop', reason: 'busy' };
  if (content.startsWith('/')) {
    return { kind: 'slash', command: content };
  }
  if (opts.interactions.length > 0) {
    const first = opts.interactions[0];
    const ixnId = first.interaction_id ?? first.id;
    if (ixnId !== undefined && ixnId !== null && String(ixnId) !== '') {
      return { kind: 'respond', interactionId: ixnId };
    }
  }
  if (!opts.hasAgent) return { kind: 'spawn_coordinator' };
  return { kind: 'message' };
}
```

##### respond 分支消费自动选择的 interactionId，随后立即返回

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/App.tsx:1227-1234`

```tsx
        // Unknown slash: fall through to message/spawn so the agent can see it.
      }
      if (target.kind === 'respond') {
        if (await handleRespondInteraction(target.interactionId, content)) {
          if (activeProjectIdRef.current === activeProject.id) setDraft((current) => current === draft ? '' : current);
        }
        return;
      }
```

##### 处理回答：按该 id 提交并报告成功

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/App.tsx:1030-1057`

```tsx
  const handleRespondInteraction = async (interactionId: string | number, answer: string): Promise<boolean> => {
    if (!activeProject || decisionSendingRef.current) return false;
    const projectId = activeProject.id;
    decisionSendingRef.current = true;
    setSending(true);
    try {
      await api.respondInteraction(projectId, interactionId, answer);
    } catch (err: unknown) {
      reportError(err);
      return false;
    } finally {
      decisionSendingRef.current = false;
      setSending(false);
    }
    const revision = ++pendingRevisionRef.current;
    pushToast('ok', t.interactionSentToast || 'Response sent to agent');
    removePendingItem(projectId, 'interactions', interactionId);
    void refreshProjectPending(projectId, true);
    const selection = agentSelectionVersionRef.current;
    const through = maxSeqRef.current;
    // The mutation succeeded. A failed refresh must not suggest resubmission.
    void api.listAgents(projectId).then((sessions) => {
      if (activeProjectIdRef.current !== projectId || pendingRevisionRef.current !== revision
          || agentSelectionVersionRef.current !== selection || maxSeqRef.current !== through) return;
      setAgents(dedupeAgents(sessions));
    }).catch(() => undefined);
    return true;
  };
```

##### API 回答入口：只传 project 和 interaction_id，没有 B 信息

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/api_v2/routers/pending.py:54-71`

```python
    @router.post("/api/v2/projects/{project_id}/interactions/{interaction_id}/response", dependencies=ctx.protected)
    async def respond_interaction(
        project_id: str,
        interaction_id: str,
        body: InteractionResponse,
    ) -> dict[str, Any]:
        result = await ctx.bus.execute(
            Command(
                type="interaction.respond",
                target={"project_id": project_id},
                payload={"interaction_id": interaction_id, "response": body.response},
            )
        )
        if not result.accepted:
            error = (result.data or {}).get("error", {})
            http_code = 404 if error.get("code") == "not_found" else 400
            raise HTTPException(status_code=http_code, detail=error.get("message", "response rejected"))
        return result.data
```

##### 命令中间转发：interaction_id 决定目标

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/commands.py:745-754`

```python
async def _respond_interaction(core: RuntimeCore, command: Command) -> CommandResult:
    project_id = _project_id(core, command)
    core.require_project(project_id)
    payload = command.payload
    record = await core.pending.respond_interaction(
        project_id,
        str(payload.get("interaction_id") or ""),
        str(payload.get("response") or ""),
    )
    return CommandResult(command_id=command.command_id, event_id=await asyncio.to_thread(_last_event_id, core), data=record)
```

##### 最终消费：读取 A 的 session，落盘后 resolve A 的 future，返回 A 的 session_id

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/pending.py:273-296`

```python
    async def respond_interaction(self, project_id: str, interaction_id: str, response: str) -> dict[str, Any]:
        pending = self._interactions.get(project_id, {}).get(interaction_id)
        if pending is None:
            raise CommandRejected("not_found", f"no pending interaction {interaction_id!r}")
        session_id = pending["session_id"] or ""
        envelope = await self._emit(
            "interaction.responded",
            project_id=project_id,
            session_id=session_id,
            data={"interaction_id": interaction_id, "response": response},
            publish=False,  # the command bus flushes new events after the handler
        )
        # The response must be durable before any parked waiter resolves.
        await self.core.event_writer.flush()
        future = self._waiters.get(interaction_id)
        if future is not None and not future.done():
            future.set_result(response)
        return {
            "interaction_id": interaction_id,
            "session_id": session_id,
            "response": response,
            "state": "responded",
            "responded_at": envelope.created_at.isoformat(),
        }
```

##### 现有测试固化全项目劫持，却没有会话归属场景

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/composerSend.test.ts:45-58`

```typescript
  { kind: 'slash', command: '/compact' },
);

// Pending ask_user hijacks Send even when an agent is selected.
assert.deepEqual(
  resolveComposerSendTarget({
    draft: 'ethanol',
    sending: false,
    hasProject: true,
    hasAgent: true,
    interactions: [{ interaction_id: 'ixn_1', id: 99 }],
  }),
  { kind: 'respond', interactionId: 'ixn_1' },
);
```

#### 3. [P2] 创建请求被拒绝，前端仍显示 Project created

**精确触发：** 在项目创建的工作区文本框输入相对路径，例如 relative-folder。UI 和 ProjectCreate schema 允许任意字符串进入请求，后端 _normalize_workspace 按现有规则明确拒绝相对路径。

**最终结果：** CommandBus 返回 accepted=false 和 invalid_request，项目数量不变；API 路由仍按 create endpoint 的 201 状态返回 CommandResponse。前端 request 只看 resp.ok，createProject 没调用已经存在的 assertAccepted；App 把错误对象当成 Project，读取不存在的 data.id，最后照常显示 Project created 并清空表单。

**设计根因：** accepted 是应用层真实结论，但 HTTP 成功和业务成功没有统一处理；只有 spawn/send/cancel 等部分 API 包装调用 assertAccepted，其他同类命令只依赖 2xx。无需增加另一套判断，复用现有共同接受检查即可。

**最小修法：** 对所有 CommandResponse 在同一层执行已有 accepted 检查，或由 API 一致地把拒绝返回为错误 HTTP；不要继续每个 UI action 自己解释接受状态。另一个同源问题是 App.createProject 将成功创建后的 listProjects 刷新放在同一成功条件里：若仅刷新失败，会显示错误且保留表单，使用户误以为创建没发生；应按已有交互提交处理方式，将刷新失败与写入成功分开。

此项不声称科学计算已经执行或被验收；这是纯项目创建的错误成功回执。

##### 实际可输入任意工作区路径的项目创建 UI

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/App.tsx:1886-1933`

```tsx
        <div className="left-sidebar-content">
          {/* New Project Creator Bar */}
          <div className="new-project-bar">
            <div className="new-project-row">
              <input
                className="input"
                value={newProject}
                onChange={(e) => setNewProject(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && createProjectAndSelect()}
                placeholder={t.sidebarNewProjectPlaceholder}
                style={{ height: 28, fontSize: 12, flex: 1 }}
              />
              <button
                type="button"
                className="btn primary sm"
                style={{ height: 28, padding: '0 10px' }}
                onClick={createProjectAndSelect}
                disabled={!newProject.trim()}
                title="新建项目"
              >
                +
              </button>
            </div>
            <div className="new-project-ws-row">
              <input
                className="input ws-path"
                value={newProjectWs}
                onChange={(e) => setNewProjectWs(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && createProjectAndSelect()}
                placeholder={t.sidebarNewProjectWsPlaceholder}
                title="项目工作区路径：机理计算文件与日志落盘目录"
                list="workspace-dirs"
              />
              <button
                type="button"
                className="btn ghost sm ws-browse-btn"
                title="浏览选择工作区文件夹"
                onClick={() =>
                  openPathPicker({
                    title: '选择项目工作区文件夹',
                    initialPath: newProjectWs,
                    onSelect: (p) => setNewProjectWs(p),
                  })
                }
              >
                {t.sidebarBrowseWs}
              </button>
            </div>
```

##### 创建请求、刷新、成功通知和表单清空完整路径

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/App.tsx:959-987`

```tsx
  async function createProject(name: string, workspaceDir?: string) {
    const resp = await api.createProject(name, workspaceDir);
    const list = await api.listProjects(true);
    setProjects(list);
    setActiveProjectId(resp.data.id);
    pushToast('ok', `Project "${name}" created`);
  }

  async function createProjectAndSelect() {
    const name = newProject.trim();
    if (!name) return;
    try {
      await createProject(name, newProjectWs.trim() || undefined);
      setNewProject('');
      setNewProjectWs('');
    } catch (e) {
      reportError(e);
    }
  }

  async function submitInlineCreate() {
    if (!inlineCreate || !inlineCreate.name.trim()) return;
    try {
      await createProject(inlineCreate.name.trim(), inlineCreate.ws.trim() || undefined);
      setInlineCreate(null);
    } catch (e) {
      reportError(e);
    }
  }
```

##### 创建包装未使用 assertAccepted

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/frontend/src/api.ts:105-111`

```typescript
  listProjects: (includeArchived = false) =>
    request<Project[]>(`/api/v2/projects${includeArchived ? '?include_archived=true' : ''}`),
  createProject: (name: string, workspace_dir?: string) =>
    request<CommandResponse<Project>>('/api/v2/projects', {
      method: 'POST',
      body: JSON.stringify({ name, workspace_dir }),
    }),
```

##### 公开入参：workspace_dir 无绝对路径约束

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/api_v2/models.py:10-13`

```python
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    workspace_dir: Optional[str] = None
    settings: dict[str, Any] = Field(default_factory=dict)
```

##### 创建 HTTP 路由固定 201 并转发 CommandResponse

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/services/api_v2/routers/projects.py:32-35`

```python
    @router.post("/api/v2/projects", dependencies=ctx.protected, status_code=status.HTTP_201_CREATED)
    async def create_project(body: ProjectCreate) -> CommandResponse:
        command = Command(type="project.create", payload=_command_payload(body))
        return await ctx.execute(command)
```

##### 创建决策在事件/目录动作产生前验证路径

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/commands.py:155-182`

```python
def _decide_create_project(core: RuntimeCore, command: Command) -> Decision:
    payload = command.payload
    name = str(payload.get("name") or "").strip()
    if not name:
        raise CommandRejected("invalid_request", "project name is required")
    project_id = new_id("prj")
    settings = ProjectSettings.model_validate(payload.get("settings") or {})
    effects: list[Effect] = []
    if payload.get("workspace_dir"):
        workspace_dir = _normalize_workspace(payload["workspace_dir"])
    else:
        # 未提供时默认 per-project 工作区：workspace_dir=None 会让下游
        # 文件/bash 工具的相对路径解析到进程 cwd，串到别的任务目录（GH #24）。
        workspace_dir = str(project_workspace_dir(project_id))
    effects.append(EnsureDir(workspace_dir))
    project = Project(id=project_id, name=name, workspace_dir=workspace_dir, settings=settings)
    return Decision(
        events=(
            EventDraft(
                "project.created",
                stream="project",
                project_id=project_id,
                data=project.model_dump(mode="json"),
            ),
        ),
        effects=tuple(effects),
        result=ResultRef("project", project_id),
    )
```

##### 实际拒绝相对工作区路径

来源：`/Users/cloudrayyy/Desktop/Desktop_Archive/Projects/Cloudra-mechanism-agent-master/cloudra/runtime_v2/commands.py:96-110`

```python
def _normalize_workspace(raw: Any) -> str:
    """Pure workspace validation/normalization; creation is an EnsureDir effect.

    A relative path would silently resolve against the server process cwd
    downstream (tools compose it with the workspace and produce nonsense
    nested paths), so reject it here instead; `~` is expanded.  The missing
    directory is created by the shell (EnsureDir), not here.
    """
    p = Path(str(raw)).expanduser()
    if not p.is_absolute():
        raise CommandRejected(
            "invalid_request",
            f"workspace_dir must be an absolute path (got {raw!r})",
        )
    return str(p)
```

拒绝随后沿第 0 节 `CommandBus._execute_locked → _reject → ApiContext.execute` 返回普通 CommandResponse；HTTP request 对 201 不抛错，最终进入 App.createProject 的无条件成功通知。

##### 纯内存复核

调用真实 CommandBus，使用无 store 的 RuntimeCore；无目录创建或真实项目落盘。

```python
import asyncio
from cloudra.runtime_v2.commands import CommandBus
from cloudra.runtime_v2.core import RuntimeCore
from cloudra.runtime_v2.schemas import Command
async def main():
    core = RuntimeCore(strict_events=True)
    result = await CommandBus(core).execute(Command(type='project.create', payload={'name': 'Audit UI receipt', 'workspace_dir': 'relative-folder'}))
    print({'accepted': result.accepted, 'data': result.data, 'projects': len(core.projects)})
asyncio.run(main())
```

实际打印：

```text
{'accepted': False, 'data': {'error': {'code': 'invalid_request', 'message': "workspace_dir must be an absolute path (got 'relative-folder')"}}, 'projects': 0}
```
#### 检查边界

以上三个结论均依据当前源码；没有读取额外记忆文件，没有假设用户明确选择回答 A 是错误，也没有将请求收到、脚本结束、科学验收混为一谈。没有做仓库修复或真实 UI/服务变更。
