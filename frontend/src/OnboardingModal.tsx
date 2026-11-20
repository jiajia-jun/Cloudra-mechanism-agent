import { useState } from 'react';
import EnvironmentDiagnosticsPanel from './EnvironmentDiagnosticsPanel';
import { useI18n } from './i18n';
import { ONBOARDING_STARTERS, type OnboardingStarter } from './onboardingState';
import type { RuntimeDiagnostics } from './types';

interface OnboardingModalProps {
  onClose: (dontShowAgain: boolean) => void;
  onOpenSettings: () => void;
  onPickStarter: (starter: OnboardingStarter, dontShowAgain: boolean) => void;
}

const TOTAL_STEPS = 3;

export default function OnboardingModal({
  onClose,
  onOpenSettings,
  onPickStarter,
}: OnboardingModalProps) {
  const { lang } = useI18n();
  const [step, setStep] = useState(0);
  const [dontShowAgain, setDontShowAgain] = useState(true);
  const [diagReport, setDiagReport] = useState<RuntimeDiagnostics | null>(null);

  const llmCheck = diagReport?.checks.find((c) => c.id === 'llm_config');

  const stepTitles = lang === 'zh'
    ? ['欢迎来到 Cloudra', '本机与集群环境自检', '挑一个起点立刻开工']
    : ['Welcome to Cloudra', 'Environment Self-Check', 'Pick a Starter Workflow'];

  return (
    <div className="modal-backdrop" onClick={() => onClose(dontShowAgain)}>
      <div className="modal onboarding-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <div className="modal-title">{stepTitles[step]}</div>
            <div className="onboarding-stepper" aria-label="Onboarding progress">
              {stepTitles.map((title, idx) => (
                <button
                  key={title}
                  type="button"
                  className={`onboarding-step-pill ${idx === step ? 'active' : idx < step ? 'done' : ''}`}
                  onClick={() => setStep(idx)}
                >
                  <span>{idx + 1}. {title}</span>
                </button>
              ))}
            </div>
          </div>
          <button
            type="button"
            className="btn ghost sm"
            onClick={() => onClose(dontShowAgain)}
            title={lang === 'zh' ? '跳过引导' : 'Skip'}
          >
            ✕
          </button>
        </div>

        <div className="onboarding-body">
          {step === 0 && (
            <div className="onboarding-step-content">
              <p className="onboarding-lead">
                {lang === 'zh'
                  ? 'Cloudra 把多智能体协作、分子三维编辑和独立保活的计算调度器揉在同一个工作台里。花一分钟认一下路，马上就能上手。'
                  : 'Cloudra combines multi-agent research, 3D molecular editing, and a crash-isolated compute scheduler in one workbench. Here is a quick 1-minute tour.'}
              </p>

              <div className="onboarding-cards">
                <div className="onboarding-card">
                  <div className="onboarding-card-title">
                    {lang === 'zh' ? '1. 对话与智能体协作' : '1. Dialogue & Multi-Agent Runs'}
                  </div>
                  <p>
                    {lang === 'zh'
                      ? '用自然语言下达机理探索、文献调研或脚本任务；主控 Agent 会拆解步骤、调用工具并在必要时向你确认。'
                      : 'Describe mechanism studies, literature reviews, or analysis tasks in natural language; the coordinator plans, runs tools, and asks before critical decisions.'}
                  </p>
                </div>

                <div className="onboarding-card">
                  <div className="onboarding-card-title">
                    {lang === 'zh' ? '2. 控制台与机理证据图' : '2. Console & Mechanism Evidence'}
                  </div>
                  <p>
                    {lang === 'zh'
                      ? '切换顶部“控制台”可查看结构产物、计算作业队列、智能体论坛，以及每个物种和过渡态背后绑定的原始计算日志。'
                      : 'Switch to Console in the top bar to inspect structures, compute queues, AgentHub discussions, and verifiable QM log evidence behind every species and TS.'}
                  </p>
                </div>

                <div className="onboarding-card">
                  <div className="onboarding-card-title">
                    {lang === 'zh' ? '3. 独立分子工作台（Alt+M）' : '3. Molecular Workbench (Alt+M)'}
                  </div>
                  <p>
                    {lang === 'zh'
                      ? '按 Alt+M 或点击结构预览即可进入三维画布：从空白建模、MMFF/UFF 预优化、看虚频振动和 IRC 轨迹，还能直接标注视图发给 Agent。'
                      : 'Press Alt+M or click any structure preview to edit 3D molecules, run force-field preoptimization, inspect imaginary modes and IRC paths, and send annotated views to agents.'}
                  </p>
                </div>
              </div>

              <div className="onboarding-llm-callout">
                <div>
                  <strong>
                    {lang === 'zh' ? '第一步建议：先确认大模型已连接' : 'First step: verify your LLM connection'}
                  </strong>
                  <div className="onboarding-callout-sub">
                    {lang === 'zh'
                      ? '支持 OpenAI 兼容 API（DeepSeek / OpenRouter 等）以及 ChatGPT / Codex 账号直接登录。'
                      : 'Supports OpenAI-compatible APIs (DeepSeek, OpenRouter, etc.) as well as ChatGPT / Codex login.'}
                  </div>
                </div>
                <button type="button" className="btn outline sm" onClick={onOpenSettings}>
                  {lang === 'zh' ? '打开全局设置' : 'Open Global Settings'}
                </button>
              </div>
            </div>
          )}

          {step === 1 && (
            <div className="onboarding-step-content">
              <p className="onboarding-lead">
                {lang === 'zh'
                  ? '下面是 Cloudra 自动扫描到的本机与配置状态。标注“可选未装”的软件不会影响你先使用对话、文献调研或远程集群计算。'
                  : 'Here is a live check of your local runtime and configured backends. Items marked Optional do not block chat, literature workflows, or remote clusters.'}
              </p>
              <EnvironmentDiagnosticsPanel
                compact
                onOpenSettings={onOpenSettings}
                onReportLoaded={setDiagReport}
              />
              {llmCheck && llmCheck.status !== 'ready' && (
                <div className="onboarding-note">
                  {lang === 'zh'
                    ? '提示：配完模型后点右上角“重新检测”即可确认绿灯。'
                    : 'Tip: after configuring a model in Global Settings, click Re-check above to confirm.'}
                </div>
              )}
            </div>
          )}

          {step === 2 && (
            <div className="onboarding-step-content">
              <p className="onboarding-lead">
                {lang === 'zh'
                  ? '选一个最接近你现在手头活的起点，我会帮你把推荐模式和开场描述直接填好，你改几个字就能开跑。'
                  : 'Choose a starter close to what you want to do—Cloudra will prefill a tailored prompt so you can tweak and run immediately.'}
              </p>

              <div className="onboarding-starters">
                {ONBOARDING_STARTERS.map((starter) => (
                  <button
                    key={starter.id}
                    type="button"
                    className="onboarding-starter-card"
                    onClick={() => onPickStarter(starter, dontShowAgain)}
                  >
                    <div className="onboarding-starter-head">
                      <span className="onboarding-starter-title">
                        {lang === 'zh' ? starter.titleZh : starter.titleEn}
                      </span>
                      <span className="onboarding-mode-tag">{starter.mode}</span>
                    </div>
                    <div className="onboarding-starter-desc">
                      {lang === 'zh' ? starter.descZh : starter.descEn}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="onboarding-footer">
          <label className="onboarding-checkbox">
            <input
              type="checkbox"
              checked={dontShowAgain}
              onChange={(e) => setDontShowAgain(e.target.checked)}
            />
            <span>
              {lang === 'zh'
                ? '下次不再自动弹出（随时可在侧边栏“更多 → 使用引导与体检”重新打开）'
                : 'Do not auto-open next time (reopen anytime from Sidebar → More)'}
            </span>
          </label>

          <div className="onboarding-nav">
            {step > 0 && (
              <button
                type="button"
                className="btn outline sm"
                onClick={() => setStep((s) => Math.max(0, s - 1))}
              >
                {lang === 'zh' ? '上一步' : 'Back'}
              </button>
            )}
            {step < TOTAL_STEPS - 1 ? (
              <button
                type="button"
                className="btn primary sm"
                onClick={() => setStep((s) => Math.min(TOTAL_STEPS - 1, s + 1))}
              >
                {lang === 'zh' ? '下一步' : 'Next'}
              </button>
            ) : (
              <button
                type="button"
                className="btn primary sm"
                onClick={() => onClose(dontShowAgain)}
              >
                {lang === 'zh' ? '直接进入工作台' : 'Enter Workbench'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
