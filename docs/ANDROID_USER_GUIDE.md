# Cloudra Android 使用教程

这是 Cloudra Android 的使用说明。Android APK 只负责界面、审批、文件授权和设备能力；模型调用、Agent、化学工具、数据库与计算任务都在电脑或服务器上运行。手机不需要填写模型 API Key。

## 先准备服务器

进入源码目录并确认配置可用：

```bash
cd /home/yyy2333/Cloudra/program/CLOUDRA
source .venv/bin/activate
cloudra config init
```

`config init` 中填写 Coordinator/Follower 的模型、API 地址和 Key。随后生成一个足够长的 Server Token，例如：

```bash
openssl rand -hex 32
```

保存输出，但不要把它写进仓库。用这个 token 启动局域网服务器：

```bash
export CLOUDRA_API_TOKEN='刚才生成的字符串'
export CLOUDRA_API_HOST='0.0.0.0'
export CLOUDRA_API_PORT='8000'
.venv/bin/python -m cloudra.api
```

这个终端需要保持运行。服务器上的 `CLOUDRA_API_TOKEN` 必须和稍后手机输入的 Server Token 完全相同。不要把 `0.0.0.0:8000` 暴露到公网；公网使用时应放在 HTTPS 反向代理和防火墙后面。

先在服务器本机检查：

```bash
curl http://127.0.0.1:8000/api/health
```

正常会返回 `status: ok` 和版本号。接着找出服务器的局域网 IP，例如 `192.168.1.23`，再用手机浏览器访问：

```text
http://192.168.1.23:8000/api/health
```

手机能看到响应后再配置 App。若源码运行在 WSL2 中，必须确保 Windows 防火墙允许 8000 端口，并让局域网流量能够转发到 WSL；最简单的判断仍是上面的手机浏览器测试。浏览器打不开时，App 也不会神奇地绕过网络问题。

传统 NAT 模式的 WSL2 可先在 WSL 中查看地址：

```bash
hostname -I
```

然后在“管理员 PowerShell”中把 `<WSL_IP>` 换成上一步的第一个地址：

```powershell
netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=8000 connectaddress=<WSL_IP> connectport=8000
New-NetFirewallRule -DisplayName "Cloudra API 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
```

手机里的 Server 地址使用 Windows 电脑的局域网 IP，而不是 WSL IP。WSL 的 NAT 地址可能在重启后变化，届时需要删除并重建 `portproxy`：

```powershell
netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=8000
```

这条防火墙规则只应在可信的 Private 局域网使用；Server Token 仍然必须设置。

## 安装 APK

当前 ARM64 测试包位于：

```text
build/apk/cloudra-android.apk
```

可以把它传到手机后点击安装，或在已开启 USB 调试的电脑上运行：

```bash
adb install -r build/apk/cloudra-android.apk
```

安装前可核对文件：

```bash
sha256sum build/apk/cloudra-android.apk
```

当前包使用 Android Debug 证书，只用于开发和上机测试。以后换成生产证书时，Android 会把它视为不同签名；若覆盖安装提示签名冲突，需要先备份 App 数据再卸载旧包。正式发布包必须通过 `cloudra android audit-apk` 的证书指纹门禁。

## 第一次连接

打开 Cloudra，进入“服务器连接”对话框，然后填写：

- Cloudra Server 地址：例如 `http://192.168.1.23:8000`；不要填 `0.0.0.0` 或手机自己的 `127.0.0.1`。
- Server Token：服务器启动时设置的 `CLOUDRA_API_TOKEN`。
- 如果使用上述局域网 HTTP 地址，勾选“允许局域网明文 HTTP（仅开发环境）”。
- 点击“连接”。

Token 成功后会进入 Android Keystore，不会写入 `remote-state.json`，输入框也不会回显已保存的 token。连接完成后选择服务器提供的“节点 / 工作区”。默认单机部署通常显示 `node-local / default`。

现在可以新建对话并发送指令。Agent 在服务器执行；手机断网、切后台或重启后，重新打开同一服务器会根据持久 event cursor 继续同步，而不是重新执行已应用命令。工具需要人工批准时，手机会展示批准或拒绝界面。服务器生成的 Artifact 可从“服务器产物”中下载，下载授权是短期 token，不会暴露服务器数据目录。

## 启用手机 Device Runtime

如果希望 Agent 读取 App 私有工作区、调用系统文件选择器、相机或分享面板，在“服务器连接”中启用：

```text
保持 Android 设备 Runtime 后台在线（显示常驻通知）
```

首次启用会自动完成一次性配对，并请求通知权限。通知存在表示前台服务正在维持设备连接。Android 可能仍会因省电策略终止后台进程；若设备频繁离线，请在系统的电池设置中允许 Cloudra 后台运行，然后重新打开 App。

设备写操作不会静默执行。`device.workspace.apply_patch`、配置修改、文档写入、相机和分享都会在手机本地显示目标与预览；拒绝权限或内容在批准前发生变化时，服务器会收到结构化失败结果，不会强行覆盖文件。

## 授权手机文档目录

App 私有工作区不等于手机“下载”或其他公共目录。需要让 Agent 操作一个现有目录时，进入设备能力页面，选择“授权文档目录”，然后在 Android 系统选择器中选定目录。Cloudra 只持久保留这个目录的 Storage Access Framework 授权，不能越出所选目录。

撤销时使用设备能力页面中的“撤销文档目录授权”。撤销后 `device.documents.*` 会从可用能力中消失；App 私有工作区不受影响。

## 多服务器、节点与 Slurm

App 可以保存多个服务器。在服务器对话框的“已注册服务器”中切换，然后选择该服务器提供的节点和工作区。每个服务器的 Token、设备身份和 event cursor 都独立隔离。

服务器使用多节点注册表时：

```bash
export CLOUDRA_NODE_REGISTRY_FILE=/absolute/path/to/nodes.json
```

格式参考 [`deploy/node-registry.example.json`](../deploy/node-registry.example.json)。注册表中的工作区路径必须已经存在。`scheduler.type=slurm` 的节点会让 `submit_compute_job` 使用 `sbatch`，并通过 `sacct` 跟踪状态；服务器需要能找到 `sbatch`、`sacct` 和 `scancel`。当前 Slurm 适配仍应先在实际集群的小任务队列验证，不要第一次就提交昂贵计算。

## 移除服务器与丢失手机

在 Android 的服务器连接对话框点击“移除此服务器”，会清除该服务器对应的 Server Token、设备 Token、本地设备身份和 event cursor。在线且当前正连接该服务器时，App 还会先请求服务器撤销设备。离线移除只保证本机凭据被删除，因此之后仍应在服务器执行：

```bash
cloudra devices list --all
cloudra devices revoke DEVICE_ID
```

手机丢失时直接在服务器执行上述撤销命令。撤销会立刻使旧 Device Token 失效，并取消该设备尚未结束的工具调用。设备找回后也必须重新配对。

## 备份、升级与恢复

升级前在服务器运行：

```bash
cloudra backup create /安全目录/cloudra-pre-upgrade.zip
cloudra backup verify /安全目录/cloudra-pre-upgrade.zip
```

恢复演练必须使用空目录：

```bash
cloudra backup restore /安全目录/cloudra-pre-upgrade.zip /临时空目录/cloudra-restore
```

备份会使用 SQLite 在线快照并校验每个文件的 SHA-256。恢复命令不会覆盖非空目录。更完整的生产运维说明见 [`PHASE8_OPERATIONS.md`](PHASE8_OPERATIONS.md)。

## 常见问题

“连接被拒绝”通常表示 API 没有监听 `0.0.0.0`、IP/端口写错、Windows/服务器防火墙拦截，或手机和服务器不在可互通的网络。先用手机浏览器打开 `/api/health`。

HTTP 401 表示 Server Token 不一致。重新输入 token，或在服务器确认当前进程的 `CLOUDRA_API_TOKEN`。不要把 token 拼进 URL。

HTTP 426 表示 App 与服务器控制协议版本不兼容，应同时更新 APK 和服务器源码。

HTTP 409 且提示 node/workspace 时，说明注册表已变化；重新打开服务器连接并选择仍然存在的节点与工作区。

设备显示 offline 时，确认常驻通知仍存在、通知权限已允许、系统没有限制后台电池使用，然后关闭再启用 Device Runtime。重新安装或清除 App 数据后需要重新配对。

安装后白屏或闪退时，保留出错时间并导出：

```bash
adb logcat -c
adb logcat | grep -i -E 'cloudra|python|flet|AndroidRuntime'
```

把安装报错、截图或这段 logcat 发回来即可继续定位。不要在日志中公开 Server Token 或模型 API Key。
