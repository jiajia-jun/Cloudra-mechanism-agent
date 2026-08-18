#Requires -Version 5.1
<#
.SYNOPSIS
    Cloudra Windows 一键安装脚本。

.DESCRIPTION
    1. 查找 Python 3.10+
    2. 创建 .venv 虚拟环境
    3. 安装 cloudra[all,gui]
    4. 把 venv Scripts 目录加入用户 PATH
    5. 初始化 cloudra config

    Python 端安装完成后，如需 Web 前端，再运行 cloudra 或 .\web.ps1。
#>

$ErrorActionPreference = "Stop"

$ProjectName = "cloudra"
$MinPython = [Version]"3.10"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$VenvDir = Join-Path $ScriptDir ".venv"

function Write-Info { param([string]$Message) Write-Host "[INFO] $Message" -ForegroundColor Cyan }
function Write-Ok { param([string]$Message) Write-Host "[OK] $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "[WARN] $Message" -ForegroundColor Yellow }
function Write-Err { param([string]$Message) Write-Host "[ERROR] $Message" -ForegroundColor Red }

function Find-Python {
    foreach ($cmd in @("python", "python3", "py")) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found) { return $found.Source }
    }
    # 检查之前下载过的 standalone Python
    $standalone = Join-Path $ScriptDir ".python\python\python.exe"
    if (Test-Path $standalone) { return $standalone }
    return $null
}

function Get-PythonVersion {
    param([string]$Python)
    $verStr = & $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
    return [Version]$verStr
}

function Install-StandalonePython {
    $os = "windows"
    if ([Environment]::Is64BitOperatingSystem) {
        $arch = "x86_64"
        $triple = "x86_64-pc-windows-msvc"
    } else {
        $arch = "i686"
        $triple = "i686-pc-windows-msvc"
    }
    $targetDir = Join-Path $ScriptDir ".python"

    Write-Info "未检测到系统 Python，正在从 python-build-standalone 下载独立运行时 (${triple})..."
    Write-Info "下载目录: $targetDir（无需管理员权限）"

    $apiUrl = "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"
    try {
        $response = Invoke-WebRequest -Uri $apiUrl -UseBasicParsing
        $release = $response.Content | ConvertFrom-Json
        $asset = $release.assets | Where-Object { $_.name -match "^cpython-3\.13.*${triple}-install_only\.tar\.gz$" } | Select-Object -First 1
    } catch {
        Write-Err "无法获取独立 Python 下载链接: $_"
        return $null
    }

    if (-not $asset) {
        Write-Err "无法找到 ${triple} 的独立 Python 下载链接"
        return $null
    }

    New-Item -ItemType Directory -Force -Path $targetDir | Out-Null
    $tmpTar = Join-Path $env:TEMP "cloudra-python.tar.gz"
    try {
        Write-Info "下载独立 Python..."
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $tmpTar -UseBasicParsing
        Write-Info "解压独立 Python..."
        & tar -xzf $tmpTar -C $targetDir
    } catch {
        Write-Err "下载或解压独立 Python 失败: $_"
        return $null
    } finally {
        Remove-Item -Path $tmpTar -Force -ErrorAction SilentlyContinue
    }

    $pyCmd = Join-Path $targetDir "python\python.exe"
    if (-not (Test-Path $pyCmd)) {
        Write-Err "独立 Python 解压后未找到可执行文件: $pyCmd"
        return $null
    }
    return $pyCmd
}

$Python = Find-Python
if (-not $Python) {
    Write-Info "未找到 Python 解释器。"
    $Auto = Read-Host "是否自动下载独立 Python 3.10+ 到项目目录（无需管理员权限）？[Y/n]"
    if ($Auto -eq "" -or $Auto -match "^[Yy]") {
        $Python = Install-StandalonePython
        if (-not $Python) {
            Write-Err "请手动安装 Python 3.10+ 后重试：https://www.python.org/downloads/"
            exit 1
        }
    } else {
        Write-Err "未找到 Python 解释器，请先安装 Python 3.10+"
        Write-Err "下载地址：https://www.python.org/downloads/"
        exit 1
    }
}

$PythonVersion = Get-PythonVersion -Python $Python
Write-Info "检测到 Python: $Python (v$PythonVersion)"

if ($PythonVersion -lt $MinPython) {
    Write-Err "需要 Python >= $MinPython，当前为 $PythonVersion"
    exit 1
}
Write-Ok "Python 版本符合要求"

# 创建虚拟环境
if (Test-Path $VenvDir) {
    Write-Warn "虚拟环境已存在: $VenvDir"
} else {
    Write-Info "创建虚拟环境: $VenvDir"
    & $Python -m venv $VenvDir
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"

# 升级 pip
Write-Info "升级 pip..."
& $VenvPython -m pip install --upgrade pip

# 安装 cloudra（默认带完整工具链 + GUI）
$Extras = "all,gui"
Write-Info "安装 ${ProjectName}（完整工具链 + GUI）..."
& $VenvPython -m pip install -e "$ScriptDir[$Extras]"

# 把 venv Scripts 加入用户 PATH
$ScriptsDir = Join-Path $VenvDir "Scripts"
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$ScriptsDir*") {
    Write-Info "把 cloudra 命令加入用户 PATH..."
    [Environment]::SetEnvironmentVariable("Path", "$UserPath;$ScriptsDir", "User")
    $env:Path += ";$ScriptsDir"
    Write-Ok "PATH 已更新"
} else {
    Write-Ok "PATH 中已存在 $ScriptsDir"
}

# 迁移旧 .env（如果存在）
$EnvFile = Join-Path $ScriptDir ".env"
if (Test-Path $EnvFile) {
    Write-Warn "检测到旧的 .env 配置文件: $EnvFile"
    Write-Warn "cloudra 现在优先使用 YAML 配置文件（%USERPROFILE%\.config\cloudra\config.yaml）"
    $Migrate = Read-Host "是否将 .env 中的 LLM 配置迁移到 cloudra config？[Y/n]"
    if ($Migrate -eq "" -or $Migrate -match "^[Yy]") {
        Write-Info "读取 .env 并准备迁移..."
        $Lines = Get-Content $EnvFile
        foreach ($Line in $Lines) {
            if ($Line -match '^(COORDINATOR|FOLLOWER)_(MODEL|URL|KEY)=(.+)$') {
                $Key = ($Line -split '=', 2)[0].ToLower().Replace('_', '.')
                $Value = ($Line -split '=', 2)[1]
                & $VenvPython -m cloudra config set $Key $Value 2>$null
            }
        }
        Write-Ok "迁移完成"
        Write-Warn "建议备份后删除 $EnvFile"
    }
}

# 初始化配置
Write-Info "初始化 cloudra 配置..."
& $VenvPython -m cloudra config init

# 验证
Write-Info "验证安装..."
try {
    $Version = & $VenvPython -m cloudra --version
    Write-Ok "cloudra 安装成功: $Version"
} catch {
    Write-Err "cloudra 命令无法执行，请检查安装日志"
    exit 1
}

Write-Ok "安装完成！"
Write-Info "推荐使用 Web 前端（需要 Node.js >= 18）："
Write-Host "  cloudra                    # 构建并启动 Web 服务（默认打开浏览器）"
Write-Host "  cloudra web --skip-build   # 复用已构建的前端"
Write-Host "  `$env:CLOUDRA_NO_BROWSER=1; cloudra   # 仅启动服务，不自动打开浏览器"
