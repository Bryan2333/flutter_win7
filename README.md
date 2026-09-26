# flutter_win7

Windows 7 SP1 x64 上可用的 Flutter 引擎 `flutter_windows.dll`（基于 Flutter 3.41.9），
让 Flutter 桌面程序在 Win7 上能正常加载运行。

官方引擎 DLL 静态导入了 9 个 Windows 8+ 的 API，在 Win7 上 `LoadLibrary` 直接失败。
这个版本用 [YY-Thunks](https://github.com/Chuyu-Team/YY-Thunks) 把它们改成运行时动态解析 +
降级实现，并额外修掉 4 个导入表之外的差异（BoringSSL 随机数、Skia DirectWrite、
ANGLE 系统库加载、Win10 以下改用软件合成器）。

## 使用

1. 在 [Releases](../../releases) 里下载对应模式的包：

   | 包 | 用途 |
   | --- | --- |
   | `...-release-x64.zip` | 常规发布（`flutter build windows`） |
   | `...-profile-x64.zip` | profile 构建 |
   | `...-debug-x64.zip` | debug（需要装了 Visual Studio 的机器，debug 运行库不随包分发） |

2. 解压后，把 `flutter_windows.dll`（建议连 `flutter_windows.dll.lib` 一起）覆盖到 Flutter SDK 对应目录，
   然后照常构建 app：

   | 包 | 覆盖到 |
   | --- | --- |
   | release | `<flutter>/bin/cache/artifacts/engine/windows-x64-release/` |
   | profile | `<flutter>/bin/cache/artifacts/engine/windows-x64-profile/` |
   | debug | `<flutter>/bin/cache/artifacts/engine/windows-x64/` |

`...-x64.zip` 里的 `.pdb` 用于崩溃栈符号化，不影响运行，可以不部署。

## app 侧链接

引擎 DLL 之外，`runner.exe` 与各插件 DLL 需各自去除 Win8+ 静态导入。
在 `windows/CMakeLists.txt` 顶部（插件目录之前）加入：

```cmake
if(WIN32 AND CMAKE_CXX_COMPILER_ID MATCHES "MSVC" AND CMAKE_SIZEOF_VOID_P EQUAL 8)
  set(YY_THUNKS_OBJ "${CMAKE_CURRENT_SOURCE_DIR}/third_party/yy_thunks/objs/x64/YY_Thunks_for_Win7.obj")
  set(CMAKE_CXX_STANDARD_LIBRARIES "\"${YY_THUNKS_OBJ}\" ${CMAKE_CXX_STANDARD_LIBRARIES}")
  set(CMAKE_C_STANDARD_LIBRARIES   "\"${YY_THUNKS_OBJ}\" ${CMAKE_C_STANDARD_LIBRARIES}")
endif()
```

obj 取自 YY-Thunks release 的 `YY-Thunks-Objs.zip`，存放于 app 仓库的 `third_party/yy_thunks/`。
同时需随包分发动态 CRT：`msvcp140.dll`、`vcruntime140.dll`、`vcruntime140_1.dll`（或改用 `/MT`）。

校验方式：对构建产物运行 `YY.Depends.Analyzer <Release 目录> /IgnoreReady /Target:6.1.7600`，
输出为空即无缺失 API（该工具同样在 `YY-Thunks-Objs.zip` 中）。

## 兼容性

* 目标系统：Windows 7 SP1 x64；Windows 8/10/11 上行为与官方一致（补丁只在旧系统路径上生效）。
* 导入表已按 Win7 的系统导出表逐项校验：**0 个缺失 API**（官方 DLL 缺 9 个）。
* 导出符号与官方 DLL 完全一致，**已发布的 app 不需要重新编译**，换 DLL 即可。

## 自己构建

`.github/workflows/build-flutter-windows-win7.yml`（手动触发）负责编译并发布上述包；
`patches/` 是各仓库的补丁，`tools/check_win7_imports.py` 是导入表校验脚本。
