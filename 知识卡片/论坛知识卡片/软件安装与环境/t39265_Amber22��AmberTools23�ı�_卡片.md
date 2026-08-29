---
key: t39265
title: Amber22��AmberTools23�ı���
url: http://bbs.keinsci.com/thread-39265-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2023
cards: 27
---

# Amber22��AmberTools23�ı��� — 知识卡片

## 1. 操作系统与基础环境准备

本教程适用于CentOS 7、Ubuntu 20.04及CentOS 8 Stream系统。安装过程建议使用root权限，默认Shell为bash，软件通常安装在/opt目录下。对于CentOS 8 Stream/RockyLinux 8系统，使用dnf命令；CentOS 7使用yum命令；Ubuntu系统使用apt命令。
- 不同的Linux发行版使用不同的包管理器。
- 安装前需备份镜像文件以备后续使用。

---

## 2. 常用依赖库安装

编译计算化学软件需要安装g++、gfortran、tcl-devel、bzip2-devel、zlib、libzip-devel、cmake3等基础库。推荐使用包管理器直接安装，例如`dnf install -y bzip2-devel cmake3 gcc-gfortran gcc-c++ lzip tcl-devel zlib libzip-devel epel-release cmake3`。若软件提供开发版或静态/动态库，需安装对应的-devel或-dev包。
- 基础工具和库文件是编译源码的前提。
- CentOS 7自带的gcc 4.8.5版本较旧，建议升级。

---

## 3. GCC版本升级与编译

若系统自带GCC版本过旧，可下载GCC 8.5.0源码进行编译安装。编译前需在contrib目录下运行download_prerequisites脚本下载gmp、mpfr、mpc、isl等依赖，或手动安装isl。编译命令包含`--with-isl=xxxxxx`参数以指定isl路径。
- 旧版本GCC可能无法满足新软件的编译需求。
- 编译GCC需提前准备其依赖的数学库。

---

## 4. CMake版本升级

若系统自带的CMake版本不符合要求，可从官网下载最新版本的二进制安装包。解压后需将安装目录添加至PATH环境变量中。教程中提到的CMake特定版本要求为3.22.2。
- 较新的软件通常需要较新版本的CMake。
- 配置PATH环境变量后即可使用新版CMake。

---

## 5. Environment Modules安装与配置

强烈建议安装Environment Modules以管理环境变量。下载源码后，使用`./configure --prefix=xxxxxx`、`make`及`make install`进行安装。安装后需在.bashrc中添加source命令以初始化module功能。
- Environment Modules用于灵活切换不同版本软件的环境变量。
- 初始化配置后需重新登录终端生效。

---

## 6. 编写Modulefile文件

为特定软件编写modulefile文件需使用Tcl语言，并放置在$MODULEPATH指定的目录中（如/opt/Modules/modulefiles）。文件中常用命令包括`module load`加载依赖、`setenv`设置环境变量、`prepend-path`添加路径。例如，设置`prepend-path PATH $prefix/bin`相当于`export PATH=$prefix/bin:$PATH`。
- Modulefile定义了软件加载时的环境变量行为。
- `prereq`命令可用于检查依赖模块是否已加载。

---

## 7. GCC Modulefile示例

GCC 9.5.0的modulefile示例中，设置了PATH、INCLUDE、LD_LIBRARY_PATH、LIBRARY_PATH等环境变量，并指定了CC、FC、CXX编译器路径。该文件依赖gmp、mpfr、mpc、isl等模块，并使用`module load`和`prereq`确保依赖顺序。
- 示例展示了如何完整配置一个编译器的模块文件。
- 正确设置库路径和头文件路径对编译至关重要。

---

## 8. Open MPI安装注意事项

编译Open MPI 4.1.1时，必须使用与后续编译Amber等软件相同的GCC版本。如果已用旧版本GCC编译了Open MPI，更换GCC版本后需重新编译Open MPI以避免兼容性问题。
- Open MPI与编译器版本强相关。
- 混用不同编译器编译的库可能导致运行错误。

---

## 9. FFTW 3.3.10 编译脚本

FFTW 3.3.10的编译涉及多次configure以支持不同的精度和特性，包括float、long-double、quad-precision以及sse、avx、avx2、avx512指令集。脚本通过`--enable-shared`、`--enable-threads`、`--enable-openmp`等参数配置，并使用`make -j`进行并行编译。
- FFTW需针对不同精度和指令集分别编译。
- 使用脚本可自动化重复的配置与编译过程。

---

## 10. FFTW Modulefile配置

FFTW的modulefile设置了bin、lib路径以及C/C++头文件路径。路径前缀通常设定为安装目录，如`/opt/fftw/3.3.10`。
- 该配置确保系统能找到FFTW的库文件和头文件。
- 正确配置LD_LIBRARY_PATH可解决运行时库找不到的问题。

---

## 11. Intel OneAPI BaseKit与HPCKit安装

在Linux下可通过配置yum源安装Intel OneAPI。创建`/etc/yum.repos.d/oneAPI.repo`文件并添加仓库信息后，执行`dnf makecache`和`dnf install intel-basekit intel-hpckit`即可。MKL和Intel MPI包含在安装包中。
- Intel OneAPI提供了Intel编译器和数学库。
- 使用官方源可简化安装流程。

---

## 12. Intel OneAPI Modulefile配置

Intel软件的modulefile需使用`source-sh`命令加载环境脚本，路径通常为`/opt/intel/oneapi/compiler/latest/env/vars.sh intel64`。MKL库在加载intel64后可能还需加载llp64接口。
- `source-sh`命令能正确处理Intel脚本中的环境变量设置。
- 根据需求选择MKL接口类型。

---

## 13. Anaconda3安装与模块化

下载Anaconda3安装脚本并按提示执行，安装目录建议设为`/opt/anaconda3`。安装时可选择不写入.bashrc，而是通过modulefile使用`source-sh bash $prefix/bin/activate`来激活环境。
- 使用Module管理Anaconda环境可避免干扰系统环境。
- Anaconda提供了Python及大量科学计算包。

---

## 14. MPI4Py编译与安装

安装MPI4Py 3.1.4前需已安装Open MPI。解压后编辑`mpi.cfg`，在`[openmpi]`字段设置`mpi_dir`为OpenMPI的实际安装路径。使用`python setup.py build --mpi=openmpi`和`python setup.py install --prefix=...`进行编译安装。
- MPI4Py需明确指定OpenMPI的路径。
- RockyLinux 8.8可能需要将/lib64下的动态库链接到OpenMPI的lib目录以解决依赖。

---

## 15. MPI4Py Modulefile配置

MPI4Py的modulefile主要需设置`PYTHONPATH`，将安装路径下的`python3.11/site-packages`添加进去。例如`prepend-path PYTHONPATH $prefix/lib/python3.11/site-packages:$PYTHONPATH`。
- 配置PYTHONPATH使Python能加载MPI4Py模块。
- 路径中的Python版本号需根据实际情况调整。

---

## 16. Boost库编译与MPI支持

安装Boost 1.82.0前需确保已安装Open MPI。运行`./bootstrap.sh`初始化，并在生成的`project-config.jam`中添加`using mpi : /opt/openmpi/4.11.1/bin/mpicxx ;`以启用MPI支持。最后使用`./b2`命令进行编译安装。
- Boost默认不编译MPI支持，需手动配置。
- 注意配置语句末尾的分号不可省略。

---

## 17. Nvidia显卡驱动禁用nouveau

安装Nvidia驱动前需禁用系统自带的nouveau驱动。在`/etc/modprobe.d/blacklist.conf`等配置文件中添加`blacklist nouveau`和`options nouveau modeset=0`，并在`/etc/default/grub`的`GRUB_CMDLINE_LINUX`中添加`rd.driver.blacklist=nouveau nouveau.modeset=0`。
- 禁用nouveau是安装Nvidia闭源驱动的必要步骤。
- 修改grub配置后需重新生成grub.cfg。

---

## 18. Nvidia驱动安装步骤

更新initramfs镜像后，切换到tty终端运行`init 3`进入文本模式。执行`./NVIDIA*.run --no-opengl-files`安装驱动，`--no-opengl-files`参数可防止与GNOME的OpenGL库冲突。安装完成后运行`init 5`返回图形界面。
- 在文本模式下安装驱动可避免图形服务干扰。
- 根据提示选择32位兼容性和X配置选项。

---

## 19. CUDA安装与Modulefile

下载CUDA runfile文件并按提示安装，默认选项即可。CUDA的modulefile需设置`/usr/local/cuda-12.1`下的bin、include和lib64路径至环境变量。
- CUDA提供了GPU计算所需的库和编译器。
- 模块文件中可注明该模块仅适用于GPU节点。

---

## 20. Amber编译环境依赖

编译Amber前需加载一系列模块，包括cmake、gcc、fftw、openmpi、anaconda、mpi4py、boost、intel mkl及cuda。通过`module load`和`prereq`确保所有依赖版本正确且顺序加载。
- Amber依赖复杂的数学库、MPI库及Python环境。
- 严格的环境依赖检查是编译成功的关键。

---

## 21. Amber源码修改与补丁

在编译Amber前，需在`CMakeLists.txt`文件前部添加`add_compile_definitions(THRUST_IGNORE_CUB_VERSION_CHECK)`。若需更新Amber，可在Bug Fixes页面下载补丁，使用`./update_amber --apply-patch=update.xxx`命令应用。
- 添加编译定义可绕过特定版本检查错误。
- 官方补丁可修复已知Bug。

---

## 22. Miniconda 下载与依赖配置

编译时设置 `-DDOWNLOAD_MINICONDA=FALSE` 可跳过 Miniconda 下载过程。需同时确保存在 `-DMINICONDA_USE_PY3` 配置，并启用 `-DTRUST_SYSTEM_LIBS=TRUE` 以及 `-DOPENMP=TRUE`。若需支持并行计算，将 `-DMPI` 设置为 TRUE。

---

## 23. 编译与安装命令

配置完成后，依次执行 `./run_cmake` 进行配置，接着运行 `make -j 8` 进行8线程编译。最后执行 `make install` 完成软件安装。此过程可编译出支持 MPI 和 OpenMP 的版本。

---

## 24. 禁用 OpenMP 与 MPI 配置

若将 `-DOPENMP` 设置为 FALSE，程序将只使用单线程，适用于仅需串行计算的场景。是否开启 MPI 需根据需求将对应参数设为 TRUE 或 FALSE。

---

## 25. CUDA 版本编译参数

编译 GPU 版本需添加 `-DCUDA=TRUE` 并指定 CUDA 路径，参数格式为 `-DCUDA_TOOLKIT_ROOT_DIR=/usr/local/cuda-??.?`。其中 `??.?` 需替换为实际安装的 CUDA 版本号。

---

## 26. NVLink 支持配置

若计算环境使用 NVLink 技术，需在编译参数中加入 `-DNCCL=TRUE`。配置完成后，按照标准流程执行编译命令即可生成支持 GPU 的版本。

---

## 27. 环境变量 Modulefile 配置

编译完成后，可编写 modulefile 文件以管理环境变量。需设置 prefix 路径（如 `/opt/amber/22`），并使用 `source-sh bash $prefix/amber.sh` 加载环境。加载对应 module 后即可使用 Amber。
