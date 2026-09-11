# ORCA NEB-TS 日志与逐图像边文件（真实运行）

一次真实的 **HCN → HNC** NEB-TS 运行的产物（本机 ORCA 6.1.1）：

```
orca neb.inp        # ! NEB-TS B3LYP def2-SVP TightSCF, %neb NEB_End_XYZFile/NImages 8
```

- `neb.out` —— 从完整主输出里**截取**的关键行（关键字回显 `NAME = neb.inp` 与
  `! NEB-TS ...`、逐迭代 CI-NEB 收敛表、`Converged TS will be written to ...
  neb_NEB-TS_converged.xyz`）。**为了体积截取过，不是全文**。
- `neb_im0.xyz` / `neb_im4.xyz` / `neb_im8.xyz` —— 逐图像几何边文件（真实文件，未改动）。
  注释行形如 `Coordinates from ORCA-job neb_im8 E -93.031209778059`，能量单位 **Eh**。

## 为什么这些边文件重要

NEB 的**逐图像几何不在主输出里**，只有迭代表；几何在每个图像一个的
`<作业名>_im<N>.xyz` 里。所以"日志里读不到几何"不等于"作业没有几何"——
`orca_frames.extract_frames` 会去读这些边文件，读不到时用
`frames_unavailable_reason()` 给出**具体原因**，而不是静默返回空列表。

`NAME = neb.inp` 这一行是关键：harness 把主输出捕获成 `.cloudra/calc-<id>.out.log`，
日志名与 ORCA 作业名无关，靠这条记录才能找到边文件所在的目录与作业名。
