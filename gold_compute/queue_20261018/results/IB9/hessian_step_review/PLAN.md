# 一次小步长/数值Hessian最低点诊断

起点 ../tight_review/tight_optfreq.xyz（833原生NAME最终结构），气相完整11原子CH2N2+乙烯q0m1，GFN2-XTB/SCC/占据保持不变。不是新TS/IRC。
假说：tight梯度尚有两软负曲率，检查BFGS近似Hessian与较大允许步长的影响，不宣称它们已被证明是原因。

依据researcher官方核查：ORCA6.1 manual optimizations.html，MaxStep每个内部坐标分量默认0.3au，Trust负数为固定半径。此次MaxStep0.1、Trust−0.1；不是Å。Calc_Hess仅初始，NumHess请求数值，Recalc_Hess1意图每周期。官方该组说明标TS additional control，minimum兼容尚未证实；必须由839实际日志确认，若未触发则报告未验证，不试第二配置。外接GFN支持gradient/optimization/numerical frequency。
https://www.faccts.de/docs/orca/6.1/manual/contents/structurereactivity/optimizations.html
https://www.faccts.de/docs/orca/6.1/manual/contents/modelchemistries/semiempirical.html

已通过公开submit提交job839，输入review.inp，普通Opt+NumFreq，无约束。沿用833全部tight阈值，不扩大budget/改strict。结果验收：正常/优化真实收敛、实际步长与Hessian重算次数/间隔、全频率、身份和模式。无零虚频也保留，不说minimum不存在或报Gold。单体742/745参考继续有效。
