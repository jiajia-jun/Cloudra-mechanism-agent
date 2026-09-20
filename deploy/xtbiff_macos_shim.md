# xtb-IFF macOS arm64 安装（Docker shim）

xtb-IFF（CREST QCG 的依赖）闭源、官方只发布 Linux x86-64 静态二进制
（<https://github.com/grimme-lab/xtbiff/releases/tag/v1.1>），macOS arm64 无法原生安装。
本机方案（2026-09-21）：Docker + Rosetta amd64 模拟。

```bash
# 1. 取官方二进制并构建最小镜像
mkdir xtbiff-img && cd xtbiff-img
curl -sL https://github.com/grimme-lab/xtbiff/releases/download/v1.1/xtbiff.tar.xz | tar -xf -
printf 'FROM scratch\nCOPY xtbiff /usr/local/bin/xtbiff\nENTRYPOINT ["/usr/local/bin/xtbiff"]\n' > Dockerfile
docker build --platform linux/amd64 -t xtbiff:1.1 .

# 2. PATH shim（~/bin 已在 PATH；CREST 以相对文件名在 cwd 调用 xtbiff，故挂载 cwd）
cat > ~/bin/xtbiff <<'EOF'
#!/bin/bash
exec docker run --rm --platform linux/amd64 -v "$PWD:/work" -w /work xtbiff:1.1 "$@"
EOF
chmod +x ~/bin/xtbiff
```

前置条件：Docker Desktop 运行中。daemon 不在时 shim 直接报错退出（fail-loud）。

## 现状警告（2026-09-21 实测）

xtbiff shim 本身可用（standalone 调用正常）。conda-forge 的 macOS arm64 CREST 在 QCG 的
**GFN-FF 预优化路径**实测 SIGABRT（2.12；3.0.2 更早在 "Setting up backup calculator"
SIGSEGV），而 **gfn2 的 grow 路径正常**——`conformer_search` 的 qcg 模式默认即 gfn2，
只跑 grow（产物 `grow/cluster.xyz` + `grow/qcg_energy.dat` 能量），本机可用。
CREST 的第二阶段 ensemble 生成在 macOS 上同样崩溃（且成本高），刻意不纳入 qcg 模式；
想要溶剂壳排布系综，对 grow 产物再跑 `mode="nci"`（同一套 NCI-MTD 机制）。
nci / protonate / deprotonate / tautomerize 不受影响，本机原生可用。
引擎崩溃会被分类为 `engine_crashed` 如实报错。
