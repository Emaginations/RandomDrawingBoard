# DrawingBoard v1.1

1080x920 绘图画板，60fps 刷新率，支持鼠标手绘与三种自动绘制模式。

## 功能

- **窗口**: 1080x920 分辨率，锁定 60fps
- **TCP 服务**: 监听端口 11451，支持远程清屏/暂停/退出指令
- **鼠标手绘**: 按住左键拖拽自由绘制黑色线条
- **边界缓存**: 灰色边界框始终跟随鼠标，越界时清除对侧缓存并重定位边界
- **自动绘制**: 鼠标在手绘线条末端停止 10-39 秒（随机）后，自动从该点开始随机选择一种模式继续绘制
  - **阿基米德螺旋线**（蓝色）— 紧凑尺寸，逐步展开
  - **布朗运动**（绿色）— 高斯步长随机游走
  - **逆时针圆**（橙色）— 随机半径，线速度约 1 cm/s

## 控制

| 操作 | 功能 |
|------|------|
| 鼠标左键拖拽 | 自由绘制 |
| 鼠标停止 10-39s | 自动绘制（从手绘末端开始） |
| 鼠标移动 | 终止自动绘制 |
| `C` 键 | 清空画布 |
| `Space` 键 | 手动切换自动绘制 |
| `Esc` 键 | 退出程序 |

## 安装与运行

```bash
pip install pygame
python drawing_board.py
```

## 编译为 EXE

```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --name DrawingBoard drawing_board.py
```

生成文件位于 `dist/DrawingBoard.exe`。

## 网络指令

向 `localhost:11451` 发送 TCP 文本指令：

| 指令 | 效果 |
|------|------|
| `clear` | 清空画布 |
| `pause` | 暂停自动绘制 |
| `quit` | 退出程序 |

## 项目结构

```
DrawingBoard/
  drawing_board.py  主程序
  README.md         本文件
  LICENSE           MIT 许可证
  NOREADME.md       AI 对话记录
  .gitignore        Git 忽略规则
```

## 作者

QQ: 331701160

## 许可证

MIT License — 详见 [LICENSE](LICENSE) 文件。

### 附加条款

若您让 AI 使用了本项目，请创建并将与 AI 对话的过程开源并写入 `NOREADME.md` 文件中（仅限用户发言，省略 AI 回复）。
