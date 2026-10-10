# shuai-burn-video-subtitles

![字幕工作流：本地转写或复用 SRT，在浏览器中校对、合并和隐藏字幕，确认样式后烧录为新的 MP4。](assets/readme/hero.svg)

面向中文口播视频的 Agent Skill：从语音转写、字幕校对，到本地网页审核和字幕烧录。

已有 SRT 就直接复用；没有 SRT 才转写。先把字幕改对，再确认样式，最后输出带字幕的新视频。

## 安装与使用

通过 Agent Skills CLI 安装：

```bash
npx skills add qizong007/shuai-burn-video-subtitles
```

选择你使用的 Agent 和安装范围，然后提供本地视频路径：

```text
使用 $shuai-burn-video-subtitles 处理这段中文口播视频。
如果已有 SRT，就复用它；先润色字幕，打开校对页让我审核。
审核完成后先做一段样式预览，确认后再烧录完整视频。
```

只校对已有字幕也可以：

```text
使用 $shuai-burn-video-subtitles 打开这个视频和 SRT 的校对页。
本次只校对并同步字幕，不烧录视频。
```

这是供 Agent 执行的工作流，也附带可独立运行的 Python 脚本。文字润色由 Agent 对照原字幕、音视频和项目资料完成。

## 可以做什么

- **转写中文语音**：使用 faster-whisper，在本地生成 SRT、带时间戳文稿和纯文本；默认优先复用已有字幕。
- **校对字幕**：修正错字、人名和技术术语，保留口述内容，不改写成宣传文案。
- **网页审核**：左侧视频、右侧字幕，点击跳转、双击编辑，支持查找替换。
- **多选与合并**：连续选中两条以上可见字幕，合并时间范围和文字。
- **可恢复隐藏**：单条或批量隐藏；隐藏项仍留在工作记录中，重开后可以恢复。
- **撤回与重做**：最近 50 步操作，覆盖文字编辑、替换、合并和显隐。
- **黑白主题**：默认按本机时间切换深浅，单个太阳／月亮图标手动切换。
- **字幕烧录**：先生成短预览，再输出新的 MP4，保留源视频和原始 SRT。

## 校对页操作

| 操作 | 用法 |
| --- | --- |
| 定位视频 | 单击字幕行 |
| 编辑文字 | 双击字幕文字，或点击铅笔；Enter 提交，Escape 取消 |
| 多选 | 勾选行首复选框，只选择、不隐藏 |
| 合并 | 连续选中两条以上可见字幕后，点击右上角「合并」 |
| 隐藏／显示 | 点击眼睛；或多选后点击右上角「隐藏」 |
| 查找替换 | 「查找」按钮或 `Cmd/Ctrl+F`，Escape 关闭 |
| 撤回 | 左箭头或 `Cmd/Ctrl+Z` |
| 重做 | 右箭头或 `Cmd/Ctrl+Y` |
| 深浅主题 | 点击太阳／月亮图标；右键恢复按时间自动 |

自动主题在 07:00–19:00 使用浅色，其余时间使用深色。撤回历史仅保留在当前页面内，刷新或重开后清空；已保存数据和当前浏览器草稿另行保留。输入框和正在编辑的字幕使用浏览器原生文字撤回。

合并会使用第一条的开始时间、最后一条的结束时间，并按原顺序用空格连接文字。非连续选择，或选择中包含隐藏项时，不提供合并按钮。

## 保存之后，文件会怎样变化？

**「保存并关闭」只保存工作记录，不直接改 SRT，也不烧录视频。**

它会在当前工作目录中写入或覆盖：

| 文件 | 内容 |
| --- | --- |
| `subtitle-transcript.json` | 修改后的文字、时间、合并结果和隐藏标记 |
| `manual-edit-review.json` | 与初始字幕相比的差异 |
| `preview-saved.json` | 保存时间与统计，标记已保存 |

保存成功后清除浏览器草稿，并尝试关闭页面；浏览器阻止关闭时，会保留保存成功提示。服务进程继续运行。

随后由 Agent 执行 `sync_review.py`，才会把可见字幕写回指定 SRT。**同步会覆盖 `--srt` 指定的文件**，正常流程使用 `input_polished.srt`，保留原始 `input.srt`。隐藏项不会写入 SRT，但仍保留在工作 JSON 中。

默认文件位置如下；文件按执行的步骤逐步生成：

```text
视频所在目录/
├── input.mp4                       # 源视频，保留
├── input.srt                       # 原始字幕，保留
├── input_polished.srt              # 校对字幕，后续同步会更新覆盖
├── input_polished_timestamped.txt  # 从校对字幕生成的带时间戳文稿
├── input_polished_clean.txt        # 从校对字幕生成的纯文本
├── input.subtitle-work/            # 编辑记录、原始快照、保存状态和预览资源
├── input_subtitle_preview.mp4       # 单独执行预览后生成
└── input_subtitled.mp4              # 确认样式并执行完整烧录后生成
```

## 环境要求

- Python 3；网页校对与 SRT 同步只使用 Python 标准库。
- FFmpeg 与 ffprobe；烧录需要 FFmpeg 的 **libass / `ass` 滤镜**。
- Pillow：用于测量字幕文字并生成贴合文字的圆角背景。
- 需要转写时，使用 `uv` 运行 faster-whisper 和 OpenCC；首次使用会下载模型。

当前默认烧录样式面向 **macOS**，使用系统字体 `Hiragino Sans GB`。其他平台需要调整字体文件及字体目录，尚未验证。FFmpeg 检测与配置见 [macOS FFmpeg 说明](./skills/shuai-burn-video-subtitles/references/macos-ffmpeg.md)。

## 独立运行校对页

克隆仓库，在仓库根目录执行。示例假设已有视频和校对字幕，请替换成实际路径：

```bash
git clone git@github.com:qizong007/shuai-burn-video-subtitles.git
cd shuai-burn-video-subtitles
SKILL="$PWD/skills/shuai-burn-video-subtitles"

python3 "$SKILL/scripts/preview_editor.py" \
  --video /path/to/input.mp4 \
  --srt /path/to/input_polished.srt \
  --work-dir /path/to/input.subtitle-work
```

打开终端打印的本地 URL，通常为 `http://127.0.0.1:8765/`；端口被占用时会选择后续可用端口。关闭终端或中断进程会停止服务。重新审核时沿用同一工作目录，不要加 `--reset`，以免丢弃工作记录。

点击「保存并关闭」后，再运行以下命令同步字幕和文稿：

```bash
python3 "$SKILL/scripts/sync_review.py" \
  --work-dir /path/to/input.subtitle-work \
  --srt /path/to/input_polished.srt

python3 "$SKILL/scripts/write_transcript_views.py" \
  --srt /path/to/input_polished.srt --force
```

转写、样式预览和烧录的完整命令见 [SKILL.md](./skills/shuai-burn-video-subtitles/SKILL.md)。

## 默认字幕样式

白色、略粗的中文字体，配贴合文字的半透明深色圆角背景，底部居中。字号和边距随视频尺寸调整，超宽文字自动换行，不使用贯穿画面的黑条。网页深浅主题不影响最终烧录样式。

默认保留句内逗号，移除句尾标点，仅允许句尾省略号和感叹号。具体样式及文字规则以 [SKILL.md](./skills/shuai-burn-video-subtitles/SKILL.md) 为准。

## 仓库结构

```text
shuai-burn-video-subtitles/
├── README.md
├── LICENSE
└── skills/shuai-burn-video-subtitles/
    ├── SKILL.md
    ├── agents/openai.yaml
    ├── assets/preview.html
    ├── references/
    └── scripts/
```

维护时同时核对脚本、Skill 说明与 README 的行为描述。提交问题时请说明操作步骤、运行环境和错误输出。

## 许可证

[MIT License](./LICENSE) · 王帅真（qizong007）
