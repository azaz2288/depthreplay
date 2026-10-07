# DepthReplay · C++盘口重建与Python研究验证

**v0.1 可运行纵向功能版**。C++20逐事件重建限价簿，Python生成微观结构报告和有时间清除的留出预测评估。含独立全簿重建参考对拍；面向C++开发、量化开发/研究与数据工程，非模拟交易平台。

## 运行与验证

需要Python3.12+、CMake3.20+与C++20编译器（GCC/Clang/MSVC/Zig）。Python研究工具无第三方运行时依赖。

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
python tools/generate_demo.py build/demo.csv --count 10000
# Linux: build/depthreplay；Windows VS: build/Release/depthreplay.exe
build/depthreplay build/demo.csv build/snapshots.csv
python research/report.py build/snapshots.csv build/report
python -m http.server 8783 --bind 127.0.0.1 --directory build/report
python tools/ci_verify.py
```

## 工程证据与边界

[设计与语义](docs/DESIGN.md) · [已实现和后续验收](docs/ROADMAP.md) · [验证记录](docs/PROGRESS.md) · [面试演示](docs/INTERVIEW.md)

所有示例明确为原创合成数据，测试不读取私人资料。本机首版不等于公网生产系统。
