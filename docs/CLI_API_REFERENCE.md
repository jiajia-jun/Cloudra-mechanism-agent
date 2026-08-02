# CLI and API entry points

这里整理的是 Cloudra 的命令行入口与 API 端点速查，不展开研究背景。项目设计、验证范围等说明请参考仓库 README；Android 端的完整操作流程见 [`ANDROID_USER_GUIDE.md`](ANDROID_USER_GUIDE.md)。

## CLI

```text
cloudra --version
cloudra                       # Linux TUI；Windows/Android 默认 GUI
cloudra gui
cloudra run "TASK" [--new] [--conv-id ID] [--dry-run] [--yolo]

cloudra config init
cloudra config show
cloudra config get KEY
cloudra config set KEY VALUE

cloudra history [--limit N]
cloudra logs CONVERSATION_ID
cloudra sessions [--state STATE]
cloudra skills

cloudra devices list [--all]
cloudra devices revoke DEVICE_ID [--yes]

cloudra backup create ARCHIVE.zip
cloudra backup verify ARCHIVE.zip
cloudra backup restore ARCHIVE.zip EMPTY_DIRECTORY

cloudra android audit-apk APP.apk \
  --expected-cert-sha256 FINGERPRINT
```

各命令的具体参数以安装版本输出的 `cloudra COMMAND --help` 为准。模型 Key 等敏感配置建议通过环境变量传入；`config show` 会做脱敏处理，不要把真实 Key 写进文档或 issue 里。

## API server

```bash
export CLOUDRA_API_TOKEN='a-long-random-secret'
export CLOUDRA_API_HOST='127.0.0.1'   # 局域网访问时显式改为 0.0.0.0
export CLOUDRA_API_PORT='8000'
cloudra-api
```

`GET /api/health` 是公开的健康检查端点。其余控制与运维接口需携带 `Authorization: Bearer <Server Token>`。Android 客户端访问 `/api/v1` 时，还要在请求头里带上协议版本、客户端版本和节点路由；不要省略这些字段让服务器去猜。

服务启动后，打开 `/docs` 即可查看由当前代码自动生成的 OpenAPI 文档。主要资源路径如下：

- `/api/v1/profile`、`/api/v1/nodes`、`/api/v1/workspaces`；
- `/api/v1/conversations` 与其 Session、消息和 event stream；
- interactions、approvals、artifacts 及短期下载 token；
- pairing、devices、heartbeat 和 device tool invocation；
- `/api/operations/status` 的低基数运维状态。

写入类命令需要稳定的 `Idempotency-Key`。客户端重试同一逻辑操作时复用原来的 key；若把同一个 key 用于不同的 payload、节点或工作区，会得到冲突而不是静默覆盖。

开发服务器默认只监听 loopback。如果要让公网访问，必须通过 HTTPS 反向代理、私网组网或其他受控隧道；不要把允许明文 HTTP 的开发配置直接暴露到互联网。
