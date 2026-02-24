# AstrBot 入群欢迎与验证插件

## 简介

本插件为 AstrBot 提供了入群欢迎和入群验证功能。当新成员加入群聊时，机器人可发送自定义欢迎消息（支持文本和图片），并可选择开启入群验证：生成一道简单计算题（结果在0~100，两步以内），新成员需在规定次数内回答正确，否则将被移出群聊。

## 功能特性

- ✅ **入群欢迎**：自定义欢迎文本，支持 `{user_name}` 变量替换。
- ✅ **欢迎图片**：可选择是否附带图片，支持本地路径或网络URL。
- ✅ **入群验证**：开关控制，开启后新成员需回答计算题。
- ✅ **计算题生成**：随机生成两步以内的加减乘法题，结果在0~100之间。
- ✅ **多次尝试**：可配置最大尝试次数（默认3次），超过后自动踢出。
- ✅ **超时处理**：可配置验证超时时间，超时视为失败并移出群聊。
- ✅ **全量配置**：所有文本、参数均可通过 AstrBot WebUI 动态配置。

## 安装方法

1. 将本插件克隆或下载到 AstrBot 的插件目录：
   ```
   cd data/plugins
   git clone https://github.com/yourusername/astrbot_plugin_welcome_verification.git
   ```
   或手动创建文件夹并放入 `main.py`、`metadata.yaml`、`_conf_schema.json` 文件。

2. 重启 AstrBot 或在 WebUI 的插件管理页面中点击“重载插件”。

3. 在 WebUI 的插件配置页面中根据需求修改配置项。

## 配置说明

插件支持以下配置项（在 WebUI 中可视化编辑）：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `welcome_text` | string | `欢迎 {user_name} 加入本群！` | 欢迎文本，`{user_name}` 会被替换为成员昵称 |
| `enable_welcome_image` | bool | `false` | 是否发送欢迎图片 |
| `welcome_image` | string | `""` | 欢迎图片路径（本地绝对路径或http/https链接） |
| `enable_verification` | bool | `true` | 是否开启入群验证 |
| `verification_timeout` | int | `300` | 验证超时时间（秒），超过此时间未回答视为失败一次 |
| `verification_max_attempts` | int | `3` | 最大尝试次数，超过后移出群聊 |
| `verification_question_format` | string | `请回答：{question} = ?` | 验证问题格式，`{question}` 会被替换为算式 |
| `verification_correct_message` | string | `验证通过，欢迎入群！` | 回答正确时的提示 |
| `verification_failed_message` | string | `答案错误，您还有 {remaining} 次机会。` | 回答错误时的提示，`{remaining}` 为剩余次数 |
| `verification_ban_message` | string | `您已超过最大尝试次数，将被移出群聊。` | 最终失败被踢出时的提示 |

## 使用说明

1. **入群欢迎**  
   当新成员加入群时，机器人会自动发送欢迎消息。若开启图片，则会附带指定图片。

2. **入群验证**  
   - 新成员加入后，机器人会 @ 该成员并发送一道计算题（如 `请回答：12 + 25 = ?`）。
   - 成员需在指定超时时间内发送数字答案。
   - 若答案正确，机器人发送成功提示，验证通过。
   - 若答案错误，机器人提示剩余机会次数，成员可继续尝试。
   - 若尝试次数用尽或超时，机器人将调用群管理 API 将该成员移出群聊，并发送提示。

3. **注意事项**  
   - 验证过程中，成员输入非数字内容不计入尝试次数，但会提示“请输入数字答案”。
   - 若成员在验证期间主动退群，插件状态会自动清理。
   - 所有提示文本均可在配置中自定义。

## 平台支持

当前版本**仅支持 aiocqhttp（OneBot V11）平台**，因为需要使用群成员增加事件和群踢人 API。其他平台可能无法正常工作（入群事件检测和踢人功能失效）。如需支持其他平台，请自行适配或联系作者。

## 依赖

- AstrBot >= 4.16
- 无额外 Python 依赖

## 作者

- [月凌]
- [https://github.com/oujunhaoyueling/astrbot_plugin_welcome_verification]

## 许可证

[可选：如 MIT, GPL 等]

---

**提示**：如果发现任何问题或有改进建议，欢迎提交 Issue 或 Pull Request。