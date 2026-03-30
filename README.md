# AstrBot 入群欢迎与验证插件
## 简介
本插件为 AstrBot 提供了入群欢迎和入群验证功能。当新成员加入群聊时，机器人可发送自定义欢迎消息（支持文本和图片），并开启入群验证：生成一道简单计算题（两步以内，结果在0~100），新成员需在规定次数内回答正确，否则进入二级验证（@管理员/群主协助验证）。若最终验证失败，将私信通知群主和管理员，直至成员被移出。
## 功能特性
- ✅ **入群欢迎**：自定义欢迎文本，支持 `{user_name}` 变量。
- ✅ **欢迎图片**：可选择是否附带图片，支持本地路径或网络URL。
- ✅ **主验证**：新成员需回答计算题，支持自定义题目格式、超时时间、最大尝试次数。
- ✅ **二级验证**：主验证失败后，@群主及管理员进行二次验证（可自定义题目、超时时间）。
- ✅ **题库切换**：支持加载 JSON 格式的静态题库，管理员可通过 `wv` 命令切换（每个群独立配置）。
- ✅ **管理员警告**：二级验证失败后，通过私信依次通知群主和所有管理员，支持自定义警告内容和循环间隔。
- ✅ **全量配置**：所有文本、参数均可通过 AstrBot WebUI 动态配置。
- ✅ **群聊隔离**：每个群的验证状态、题库配置相互独立。
- ✅ **持久化**：群题库配置、验证状态持久化存储于 `data/welcome_verification/` 目录，防止插件更新丢失。
## 安装方法
1. 将本插件克隆或下载到 AstrBot 的插件目录：
   ```bash
   cd data/plugins
   git clone https://github.com/yourusername/astrbot_plugin_welcome_verification.git
   ```
   或手动创建文件夹并放入所有文件。
2. 重启 AstrBot 或在 WebUI 的插件管理页面中点击“重载插件”。
3. 在 WebUI 的插件配置页面中根据需求修改配置项。
## 配置说明
插件支持以下配置项（在 WebUI 中可视化编辑）：
| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `welcome_text` | string | `欢迎 {user_name} 加入本群！` | 欢迎文本 |
| `enable_welcome_image` | bool | `false` | 是否发送欢迎图片 |
| `welcome_image` | string | `\"\"` | 欢迎图片路径（本地绝对路径或http/https链接） |
| `enable_verification` | bool | `true` | 是否开启入群验证 |
| `verification_timeout` | int | `300` | 主验证超时时间（秒） |
| `verification_max_attempts` | int | `3` | 主验证最大尝试次数 |
| `verification_question_format` | string | `请回答：{question} = ?` | 主验证问题格式 |
| `verification_correct_message` | string | `验证通过，欢迎入群！` | 主验证成功消息 |
| `verification_failed_message` | string | `答案错误，您还有 {remaining} 次机会。` | 主验证失败提示 |
| `verification_ban_message` | string | `您已超过最大尝试次数，将被移出群聊。` | 主验证失败（未启用二级验证）踢出提示 |
| `secondary_verification_enabled` | bool | `true` | 是否启用二级验证 |
| `secondary_verification_timeout` | int | `60` | 二级验证等待时间（秒） |
| `secondary_verification_question` | string | `请 @{user_name} 并回答：{question} = ?` | 二级验证问题格式 |
| `secondary_verification_correct_message` | string | `二级验证通过，欢迎入群！` | 二级验证通过消息 |
| `secondary_verification_failed_message` | string | `二级验证超时，将通知管理员。` | 二级验证超时提示 |
| `warning_owner_message` | string | `【风险提示】群内有新成员 {user_name}({user_id}) 未通过验证，请处理。` | 私信群主的警告内容 |
| `warning_admin_message` | string | `【风险提示】群 {group_name} 内有新成员 {user_name}({user_id}) 未通过验证，请处理。` | 私信管理员的警告内容 |
| `warning_check_interval` | int | `10` | 警告循环中检查成员是否在群的时间间隔（秒） |
| `warning_cycle_max` | int | `10` | 最大警告循环次数 |
## 题库管理
插件支持使用 JSON 格式的静态题库，题库文件需存放在 `AstrBot/data/plugin_data/welcome_verification/warehouse/` 目录下，格式如下：
```json
[
    {\"question\": \"1 + 1\", \"answer\": 2},
    {\"question\": \"2 × 3\", \"answer\": 6},
    {\"question\": \"10 - 4\", \"answer\": 6}
]
```
### 命令说明
群内发送以下命令（仅管理员/群主可切换题库，查看命令所有人可用）：
- `wv ls`：查看可用题库列表及题目数量。
- `wv <文件名>`：切换题库，支持省略 `.json` 扩展名（例如 `wv math` 或 `wv math.json`）。
- `wv default`：恢复为随机生成题目（默认模式）。
## 使用说明
1. **入群欢迎**  
   当新成员加入群时，机器人会自动发送欢迎消息。若开启图片，则会附带指定图片。
2. **主验证**  
   - 新成员入群后，机器人会 @ 该成员并发送一道计算题。
   - 成员需在超时时间内发送数字答案。
   - 若答案正确，验证通过。
   - 若答案错误，提示剩余机会次数，可继续尝试。
   - 若尝试次数用尽或超时，且未开启二级验证，则直接踢出；若开启二级验证，则进入二级验证流程。
3. **二级验证**  
   - 主验证失败后，机器人会 @ 群主及所有管理员，发送一道新题目。
   - 管理员或群主需在指定时间内 @ 新成员并发送数字答案。
   - 若答案正确，验证通过，成员留在群内。
   - 若超时无人回答，则进入警告流程。
4. **警告流程**  
   - 二级验证超时后，机器人会先私信群主发出警告。
   - 等待指定间隔后，若成员仍在群内，则依次私信未通知过的管理员（循环直至最大次数或成员被移出）。
   - 警告内容可自定义，支持替换成员昵称、ID、群名称。
   - 警告循环期间，若成员被踢出，则自动终止后续通知。
## 平台支持
当前版本**仅支持 aiocqhttp（OneBot V11）平台**，例如 NapCat、LLOneBot 等。其他平台可能无法正常工作（入群事件检测和踢人功能失效）。
## 依赖
- AstrBot >= 4.16
- 无额外 Python 依赖
## 作者
- 月凌 (Yueling)
- GitHub: [https://github.com/oujunhaoyueling/astrbot_plugin_welcome_verification](https://github.com/oujunhaoyueling/astrbot_plugin_welcome_verification)
## 许可证
MIT