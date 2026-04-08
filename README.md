# AstrBot 入群欢迎与验证插件

## 简介

本插件为 AstrBot 提供了入群欢迎和入群验证功能，支持自定义题库，并根据机器人权限智能处理验证失败场景。

## 功能特性

- ✅ **入群欢迎**：自定义欢迎文本，支持 `{user_name}` 变量替换
- ✅ **欢迎图片**：可选择是否附带图片，支持本地路径或网络 URL（默认二次元图片 API）
- ✅ **入群验证**：数学题或自定义题库验证
- ✅ **智能权限处理**：
  - 有管理员权限：提供 `/pass`、`/kick` 命令让管理员快速处理
  - 无管理员权限：仅 @ 管理员提醒手动处理
- ✅ **二级验证超时自动踢人**：管理员未在时间内处理则自动踢出
- ✅ **自定义题库**：支持导入 JSON 格式的题库文件
- ✅ **全量配置**：所有文本、参数均可通过 AstrBot WebUI 动态配置

## 安装方法
1. 将本插件下载到 AstrBot 的插件目录：
 
 ```
 
 cd data/plugins  git clone https://github.com/oujunhaoyueling/astrbot_plugin_welcome_verification.git
 
 ```

2. 重启 AstrBot 或在 WebUI 的插件管理页面中点击"重载插件"

3. 在 WebUI 的插件配置页面中根据需求修改配置项

## 配置说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `welcome_text` | string | 欢迎 {user_name} 加入本群！ | 欢迎文本，支持 `{user_name}` 变量 |
| `enable_welcome_image` | bool | true | 是否发送欢迎图片 |
| `welcome_image` | string | https://t.alcy.cc/moe | 欢迎图片路径（本地或 URL） |
| `enable_verification` | bool | true | 是否开启入群验证 |
| `verification_timeout` | int | 300 | 主验证超时时间（秒） |
| `verification_max_attempts` | int | 3 | 主验证最大尝试次数 |
| `verification_question_format` | string | 请回答：{question} = ? | 验证问题格式，支持 `{question}` 变量 |
| `verification_correct_message` | string | 验证通过，欢迎入群！ | 验证成功提示 |
| `verification_failed_message` | string | 答案错误，您还有 {remaining} 次机会。 | 验证失败提示，支持 `{remaining}` 变量 |
| `verification_ban_message` | string | 您已超过最大尝试次数，将被移出群聊。 | 验证失败且未开启二级验证时的提示 |
| `secondary_verification_enabled` | bool | true | 是否启用二级验证（管理员审批） |
| `secondary_verification_timeout` | int | 60 | 二级验证等待管理员决策的超时时间（秒） |
| `secondary_verification_prompt` | string | （见配置） | 发送给管理员的提示文本，支持 `{user_name}`, `{user_id}`, `{pass_cmd}`, `{kick_cmd}`, `{timeout}` 变量 |
| `pass_command` | string | /pass | 允许入群的命令关键词 |
| `kick_command` | string | /kick | 踢出入群的命令关键词 |
| `pass_success_message` | string | 已允许该用户入群 | pass 命令执行成功后的回复 |
| `kick_success_message` | string | 已移出该用户 | kick 命令执行成功后的回复 |
| `no_permission_prompt` | string | （见配置） | 机器人无管理员权限时 @ 管理员的提示，支持 `{user_name}`, `{user_id}`, `{group_id}` 变量 |
| `secondary_timeout_auto_kick_message` | string | 用户 {user_name} 未在时间内得到处理，已自动移出群聊。 | 二级验证超时后自动踢人的提醒，支持 `{user_name}`, `{user_id}` 变量 |
| `timeout_kick_enabled` | bool | true | 是否启用超时踢人（踢人前等待管理员取消） |
| `timeout_kick_delay` | int | 30 | 超时踢人等待时间（秒） |
| `timeout_kick_warning_message` | string | （见配置） | 即将踢人的提示文本，支持 `{user_name}`, `{delay}`, `{cancel_command}` 变量 |
| `timeout_kick_cancel_command` | string | /cancel_kick | 取消踢人的命令关键词 |
| `timeout_kick_cancel_message` | string | 已取消踢出 {user_name} | 取消踢人后的提示文本，支持 `{user_name}` 变量 |
| `timeout_kick_immediate_message` | string | 验证失败，您即将被移出群聊 | 当超时踢人关闭时，直接踢人前的提示文本 |

## 使用说明

### 验证流程

1. 新成员入群后自动发送欢迎消息（如有配置图片则同时发送）
2. 机器人发送验证问题（数学题或自定义题库）
3. 用户回答：
- **回答正确**：发送验证通过消息，流程结束
- **回答错误/超时**：扣除次数，次数用尽进入二级验证
4. 二级验证：
- **机器人有管理员权限**：@ 所有管理员+群主，提供 `/pass @用户` 和 `/kick @用户` 命令，超时自动踢人
- **机器人无管理员权限**：@ 所有管理员+群主提醒手动处理，不执行踢人操作

### 管理命令

| 命令 | 说明 | 权限 |
|------|------|------|
| `wv` | 获取题库管理帮助 | 所有人 |
| `wv ls` | 查看可用题库 | 所有人 |
| `wv <文件名>` | 切换题库（如 `wv math.json`） | 管理员/群主 |
| `wv default` | 恢复随机生成数学题 | 管理员/群主 |
| `/pass @用户` | 同意用户入群（二级验证时使用） | 管理员/群主 |
| `/kick @用户` | 踢出用户（二级验证时使用） | 管理员/群主 |
| `/cancel_kick @用户` | 取消即将执行的踢人 | 管理员/群主 |

### 自定义题库

在 `AstrBot/data/plugin_data/welcome_verification/warehouse/` 目录下放入 JSON 格式的题库文件，格式如下：

```json
[
{"question": "1 + 1", "answer": 2},
{"question": "中国的首都是哪里", "answer": "北京"},
{"question": "3 * 4", "answer": 12}
]
```

文件名即为题库名，如  math.json 使用  wv ls  查看已加载的题库。
注意事项
 
本插件仅支持 aiocqhttp（OneBot V11）平台（如 NapCat、LLOneBot）
 
机器人需要拥有群管理员权限才能执行踢人操作
 
验证过程中成员输入非数字内容不计入尝试次数（数学题模式下）
 
建议给机器人管理员权限以获得最佳体验，否则需要管理员手动处理验证失败的用户
## 作者
 
- 月凌
 
GitHub: https://github.com/oujunhaoyueling
## 许可证
MIT License