# Cloudra Phase 7 Android 真机矩阵

这份记录用于构建后的 APK，源码级 pytest 不能替代它。每次候选 APK 都要记录
APK SHA-256、Android 版本、厂商 ROM、测试日期和结果；未填写的格子就是未验证，
不能在发布说明里写成“已支持”。

## 设备覆盖

最低覆盖一个模拟器和两台真机，其中至少一台为非原生 Android 厂商 ROM：

| 设备 | Android / ROM | APK SHA-256 | 日期 | 结果 |
|---|---|---|---|---|
| 模拟器 | 待填写 | 待填写 | 待填写 | 未运行 |
| 真机 A | 待填写 | 待填写 | 待填写 | 未运行 |
| 真机 B（厂商 ROM） | 待填写 | 待填写 | 待填写 | 未运行 |

## 必测路径

先连接测试服务器并启用 Device Runtime。确认 Server Token 与 device token
没有出现在 `remote-state.json`、`device-state.json`、logcat 或通知文本里，
通知栏明确显示 Runtime 的连接状态。

随后依次验证：

- 熄屏、切到后台 15 分钟再返回，Runtime 通知仍存在，服务器设备状态在线。
- 切换 Wi-Fi、蜂窝网络和飞行模式；断网时通知显示中断，恢复网络后自动 hello，
  未确认的 result/outbox 只提交一次；服务器确认后 `device-state.json` 不再保留
  文件选择或相机返回的 base64，只留下幂等摘要。
- 拒绝通知权限；Runtime 启动结果明确为 `permission_denied`，App 内状态和系统
  活跃服务入口仍能说明它是否运行。
- 用 SAF 授权一个文档树，读写一个小文件，重启 App 后不重新选择目录仍可访问；
  在系统设置撤销 grant 后，调用返回 `not_authorized` 或
  `permission_denied`，不能沿用缓存 URI；重新选择另一个树后旧 grant 必须释放。
- 在 SAF 写入审批弹窗打开时从其他 App 修改文件，批准后必须返回 `conflict`，
  不能覆盖新内容。
- 对文件选择器、相机和分享面板分别测试批准、取消、系统能力不存在和权限拒绝。
  相机当前返回本次拍摄的 JPEG 缩略图；分享的最终目标必须仍由用户在系统面板选择。
- 从后台审批通知点按进入 App，必须落回 Cloudra 并显示对应的本地审批；拒绝和
  Android 返回键都要让服务器调用进入终态，不能永久卡在等待中。
- 用系统“强行停止”终止 App。Foreground Service 通知必须消失，服务器在
  heartbeat 超时后标记设备离线；重新启动 App 后从 Keystore 恢复凭据并重新
  hello，不能宣称被杀期间仍在线。
- 分别开启系统省电、厂商自启动/后台限制的允许与禁止状态。记录厂商实际行为；
  Cloudra 不承诺绕过 OEM 强杀，只承诺通知、离线检测和下次启动恢复语义真实。

最后跑大 diff、1 MiB 边界文件、长流式输出和同一 `tool_call_id` result 丢包重放。
任何一项失败都保留 logcat、服务器 Session event 和 APK SHA-256，修复后重新跑
整条路径，不只重测单点。
