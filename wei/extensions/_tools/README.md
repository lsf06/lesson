# `_tools`：让微课在这台机器上跑起来的辅助设施

本目录**不属于任何微课主线**，只解决两件事：没有读卡器怎么给 SD 卡放模型（`sdcard_seed/`），以及这台 Windows 开发机上路径太长导致的构建失败（`fix_esp_video_long_path.ps1` 与“短构建目录”）。

> 实测环境：Windows + ESP-IDF v5.4.4、ESP32-S3-EYE。仓库位于很深的目录，`extensions` 这一层本身就有 90 个字符：

```text
E:\study\lsf\daima\ganzhi\esi-mvp-code-main\esi-mvp-code-main\esi-mvp-code-main\extensions   (90 字符)
```

| 工具 / 做法 | 解决什么问题 | 何时要跑 |
|---|---|---|
| `sdcard_seed/` | 板上自己往 microSD 写模型和样例图，免读卡器 | 新卡、卡被格式化、或模型换版本后跑一次 |
| `fix_esp_video_long_path.ps1` | 托管组件 `espressif/esp_video` 因路径过长装不进去 | 首次构建猫狗工程前跑一次（幂等，可重复跑） |
| `idf.py -B <短路径>` | Windows MAX_PATH(260) 导致 `03_live_catdog_assignment` 编译中途失败 | 该工程**每次**构建 / 烧录都要带 |

## 1. `sdcard_seed/`：把开发板当读卡器用

`sdcard_seed` 会往卡上写这三个文件（`03_catdog_static_infer` 只用前两个）：

```text
/sdcard/models/s3/catdog_mobilenet_v2.espdl   （分类模型，约 2.2 MB）
/sdcard/images/sample.jpg                     （默认测试图）
/sdcard/images/dog.jpg                        （额外样例，手动实验用；静态推理工程不使用）
```

没有读卡器时，用这块板子自己写卡。这个独立工程把模型和两张 JPEG 用 `EMBED_FILES` 嵌进自己的固件（不会在仓库里再存一份 2.4 MB 的二进制），上电后走**和 BSP 完全相同的 SDMMC 引脚**（`bsp_storage.c` 的 slot 0、1-bit、CLK=GPIO39 / CMD=GPIO38 / D0=GPIO40）把三个文件写进卡，再逐个回读做 SHA-256 校验后才报成功；`format_if_mount_failed` 打开，空白卡或非 FAT 卡会被自动格式化。

```powershell
cd extensions\_tools\sdcard_seed
idf.py set-target esp32s3
idf.py -p <PORT> build flash monitor
```

看到校验通过（每个文件打印写入字节数与 SHA-256 比对结果）后按 `Ctrl+]` 退出。这个工程的构建根目录只有 115 字符、构建树里最长文件 252 字符（都在上限内），**不需要** `-B` 短构建目录。

它**不依赖** `espressif__esp32_s3_eye` / `esp_video`，只用 `fatfs`、`sdmmc`、`esp_driver_sdmmc`、`mbedtls`（见 `main/CMakeLists.txt`），所以不受下面第 2 节的长路径问题影响。

## 2. `fix_esp_video_long_path.ps1`：esp_video 装不进去

托管组件管理器会把每个依赖从缓存**复制**到 `<工程>\managed_components\<组件>`。本仓库里这个目标前缀已经约 132 字符，而 `espressif/esp_video` 内部路径最长约 150 字符——复制时超出 Windows 的路径上限，结果是目录写了一半、`.component_hash` 标记文件没生成；下一次构建管理器判定“组件不存在”，构建失败。

脚本用**目录联接（junction）**手工完成一次安装：

1. 从 `dependencies.lock` 读出该组件的期望哈希；
2. 把组件从管理器缓存复制到一个短路径目录（默认 `%USERPROFILE%\ev_video_component`，可用 `-ShortRoot` 改）；
3. 写好管理器用来比对的 `.component_hash`；
4. 把 `<工程>\managed_components\espressif__esp_video` 变成指向那个短目录的 junction。

之后管理器的校验通过（`IDF_COMPONENT_STRICT_CHECKSUM` 默认为 False，加上哈希文件一致），**不再重复复制**；编译则通过 junction 照常读到源码。

```powershell
# 默认处理 03_catdog_static_infer 和 03_live_catdog_assignment 两个工程
powershell -ExecutionPolicy Bypass -File extensions\_tools\fix_esp_video_long_path.ps1

# 只处理一个工程，并指定短路径根
powershell -ExecutionPolicy Bypass -File extensions\_tools\fix_esp_video_long_path.ps1 `
    -Project extensions\03_catdog_static_infer -ShortRoot C:\ev
```

脚本是幂等的：已经装好的工程会跳过，不会覆盖一个完整的 `managed_components` 条目。注意 junction 是“目录快捷方式”，用资源管理器删除或移动 `managed_components\espressif__esp_video` 可能会**删掉目标目录里的真实文件**，需要重装时用 `-Force`。

> 本机现状：两个工程的 junction 目前指向 `%USERPROFILE%\ev_video`（当初手工建的，早于脚本默认值 `%USERPROFILE%\ev_video_component`）。因为哈希文件齐备、校验通过，脚本会直接跳过这两个工程，不会新建目录；想统一位置就 `-Force -ShortRoot ...` 重新建。

## 3. `03_live_catdog_assignment` 必须用短构建目录

两个猫狗工程的构建根目录只差 3 个字符，就决定了成不成功：

| 工程 | 构建根目录 | 同一个 `.obj.d` 依赖文件的全路径 |
|---|---|---|
| `03_catdog_static_infer` | 119 字符 | 258 字符 ✔（构建树实测最长 256 字符） |
| `03_live_catdog_assignment` | 122 字符 | 261 字符 ✘（超过可用的 259 字符） |

越界时如果直接 `idf.py build`，日志末尾是这种“看着像缺文件、其实是路径太长”的报错（编译引导加载程序时写不出 `.obj.d` 依赖文件）：

```text
...\components\bootloader_support\bootloader_flash\src\bootloader_flash_config_esp32s3.c:308:1:
fatal error: opening dependency file
esp-idf\bootloader_support\CMakeFiles\__idf_bootloader_support.dir\bootloader_flash\src\bootloader_flash_config_esp32s3.c.obj.d:
No such file or directory
```

**规避方法**：把构建目录放到短路径下（`-B`），`sdkconfig` 仍留在工程根目录，配置不会丢：

```powershell
cd extensions\03_live_catdog_assignment
idf.py -B E:\esi_build\projB build
idf.py -B E:\esi_build\projB -p <PORT> flash monitor
```

两个注意点：

- **别手工移动已生成的构建目录**。`build.ninja` / `CMakeCache.txt` 里存的是绝对路径，移动后 ninja 会去旧路径找文件而失败；换目录必须删掉新目录并重新 configure（`idf.py -B <新目录> build` 会自动重新配置）。
- 短路径目录名保持简短（`E:\esi_build\projB`），路径里不要有空格或中文；用 `subst`/junction 映射盘符也能达到同样效果。（仓库里 `09_audio_resource_budget`、`10_state_machine_test` 也是用 `-B build/<子目录>` 隔离多组构建，思路一致，只是它们的工程路径更短、不需要挪出仓库。）