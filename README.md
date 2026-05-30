# 此插件与 `meme_manager` 可能产生冲突，若此插件功能不可用，建议尝试更改插件启用顺序(先启用本插件)或使用 `表情包小偷` 等效替代 `meme_manager`

> **⚠️ v2.8.0 迁移提醒**：所有命令统一为 `wv` 前缀。`/pass`、`/kick`、`/cancel_kick`、`welcome` 等旧命令已移除，请使用 `wv pass`、`wv kick`、`wv cancel`、`wv welcome` 替代。
 
# AstrBot 入群欢迎与验证插件

## 简介

本插件为 AstrBot 提供了入群欢迎和入群验证功能，支持自定义题库，并根据机器人权限智能处理验证失败场景。

## 功能特性

- ✅ **入群欢迎**：自定义欢迎文本，支持 `{user_name}` 变量替换
- ✅ **欢迎图片**：可选择是否附带图片，支持本地路径或网络 URL
- ✅ **群组自定义配置**：支持为不同群组设置独立的欢迎文本、图片和题库
  - 通过 WebUI 可视化配置
  - 通过群内命令快速配置
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
| `welcome_image` | string | https://t.alcy.cc/moe | 欢迎图片路径（本地绝对路径或 URL，推荐放在 data/ 目录下） |
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

## 群组自定义配置

本插件支持为每个群组设置独立的欢迎文本、图片和题库配置，优先级高于全局配置。

### 配置方式

插件提供两种配置群组设置的方式：

#### 1. WebUI 配置（推荐）

在 AstrBot 的 WebUI 插件配置页面中，找到 **"群组自定义配置"** 配置项。点击"添加"按钮，可以可视化地为不同群组设置独立的配置。

**配置项说明**：

| 配置项 | 说明 |
|--------|------|
| 群组ID（群号） | 必填，填写需要自定义配置的群号 |
| 欢迎文本 | 可选，留空使用全局配置。支持 {user_name} 变量 |
| 启用欢迎图片 | 可选，是否发送欢迎图片，留空继承全局设置 |
| 欢迎图片URL/路径 | 可选，本地路径或网络URL，留空使用全局配置 |
| 自定义题库文件名 | 可选，如：math.json，留空使用全局题库或自动生成 |

**使用示例**：
1. 在 WebUI 中点击"添加群组配置"
2. 填写群组 ID：123456789
3. 填写欢迎文本：欢迎 {user_name} 来到我们的技术交流群！
4. 填写欢迎图片 URL：https://example.com/tech-banner.jpg
5. 点击保存

#### 2. 群内命令

在群聊中直接使用命令进行配置，操作简单直观。

| 命令 | 说明 | 权限 |
|------|------|------|
| `wv welcome` | 查看当前群组欢迎配置和命令列表 | 所有人 |
| `wv welcome text <内容>` | 设置群组欢迎文本（支持 {user_name} 变量） | 管理员/群主 |
| `wv welcome image <路径/URL>` | 设置群组欢迎图片 | 管理员/群主 |
| `wv welcome image on` | 启用群组欢迎图片 | 管理员/群主 |
| `wv welcome image off` | 禁用群组欢迎图片 | 管理员/群主 |
| `wv welcome reset` | 重置为全局配置 | 管理员/群主 |

**使用示例**：
```
wv welcome text 欢迎 {user_name} 来到我们的技术交流群！
wv welcome image https://example.com/group-banner.jpg
wv welcome reset
```

**注意**：通过群内命令修改的配置会自动同步到 WebUI 配置中。

## 使用说明

### 验证流程

1. 新成员入群后自动发送欢迎消息（如有配置图片则同时发送）
2. 机器人发送验证问题（数学题或自定义题库）
3. 用户回答：
- **回答正确**：发送验证通过消息，流程结束
- **回答错误/超时**：扣除次数，次数用尽进入二级验证
4. 二级验证：
- **机器人有管理员权限**：@ 所有管理员+群主，提供 `wv pass @用户` 和 `wv kick @用户` 命令，超时自动踢人
- **机器人无管理员权限**：@ 所有管理员+群主提醒手动处理，不执行踢人操作

### 管理命令

| 命令 | 说明 | 权限 |
|------|------|------|
| `wv` | 显示完整命令帮助 | 所有人 |
| `wv ls` | 查看可用题库 | 所有人 |
| `wv <文件名>` | 切换题库（如 `wv math.json`） | 管理员/群主 |
| `wv default` | 恢复随机生成数学题 | 管理员/群主 |
| `wv pass @用户` | 同意用户入群（二级验证时使用） | 管理员/群主 |
| `wv kick @用户` | 踢出任意用户（任何时候可用） | 管理员/群主 |
| `wv cancel @用户` | 取消即将执行的踢人 | 管理员/群主 |

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

## 更新日志

### v2.8.0 (2026-05-30)

#### 🚀 统一指令系统

所有命令统一为 `wv` 前缀，告別分散的 `/pass`、`/kick`、`/cancel_kick`、`welcome` 等命令：

| 命令 | 说明 |
|------|------|
| `wv` | 显示完整帮助 |
| `wv welcome` | 欢迎配置管理 |
| `wv ls` / `wv <文件名>` / `wv default` | 题库管理 |
| `wv pass @用户` | 允许入群 |
| `wv kick @用户` | 踢出用户 |
| `wv cancel @用户` | 取消踢人 |

#### 🐛 Bug 修复

- 修复负数答案验证问题（`-4` 被 `isdigit()` 错误拦截）
- 修复命令误触发（普通消息以 `welcome` 开头不再被误判）
- 修复锁内 I/O 问题，提升并发性能
- 修复踢人不清理状态，后台任务空转浪费资源
- 修复后台任务异常被静默吞没的问题

#### ⚡ 优化

- `_is_member_in_group` 改用单成员查询，大群性能显著提升
- 随机出题简化，保证一次生成合法题目
- 验证流程添加异常保护，防止因发送消息失败导致崩溃
- 新增任务生命周期管理，支持插件卸载时完整清理

### v2.7.0 (2026-05-24)

#### ✨ 新增功能

**群组自定义配置**

本版本新增了为不同群组设置独立欢迎配置的功能，包括：

- **独立欢迎文本**：可以为每个群组设置不同的欢迎消息
- **独立欢迎图片**：可以为每个群组设置不同的欢迎图片
- **独立题库**：可以为不同群组使用不同的验证题库
- **WebUI 可视化配置**：通过 AstrBot WebUI 直接管理群组配置
- **群内命令配置**：通过 `welcome` 系列命令快速修改配置
- **自动配置同步**：命令修改的配置自动同步到 WebUI

#### 🔧 功能优化

**踢人命令增强**
- `/kick` 命令现在任何时候都能使用（只要是管理员/群主）
- 不再局限于二级验证阶段，可随时踢出任意群员
- 添加了防止踢出自己的保护

#### 📋 新增命令

| 命令 | 说明 | 权限 |
|------|------|------|
| `welcome` | 查看当前群组配置 | 所有人 |
| `welcome text <内容>` | 设置群组欢迎文本 | 管理员/群主 |
| `welcome image <路径>` | 设置群组欢迎图片 | 管理员/群主 |
| `welcome image on` | 启用欢迎图片 | 管理员/群主 |
| `welcome image off` | 禁用欢迎图片 | 管理员/群主 |
| `welcome reset` | 重置为全局配置 | 管理员/群主 |
| `/kick @用户` | 踢出任意用户（任何时候可用） | 管理员/群主 |

### v2.6.0 (2026-05-16)

#### 🐛 Bug 修复

- 修复入群事件处理逻辑，新成员入群时才触发欢迎和验证
- 修复命令匹配问题，`/pass` 不再错误匹配 `/password`
- 修复插件卡死问题
- 修复用户昵称显示错误问题
- 修复踢人功能在特定情况下不工作的问题

#### ⚡ 优化

- 日志输出优化
- 管理员权限检测优化

## 作者

- 月凌

GitHub: https://github.com/oujunhaoyueling

## 许可证

本插件基于 [GNU AFFERO GENERAL PUBLIC LICENSE Version 3](https://www.gnu.org/licenses/agpl-3.0.html) 开源。

Copyright (C) 2024-2026 AstrBot Plugin Authors

本程序是自由软件，你可以按照自由软件基金会发布的 GNU AGPL v3 的条款重新发布它和/或修改它。

本程序的发布是希望它能有用，但没有任何保证；甚至没有特定用途的隐含保证。详见 GNU AGPL v3 许可证。