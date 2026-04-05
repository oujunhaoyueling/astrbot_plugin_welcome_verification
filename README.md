# AstrBot 入群欢迎与验证插件

## 简介

本插件为 AstrBot 提供了入群欢迎和入群验证功能。当新成员加入群聊时，机器人可发送自定义欢迎消息（支持文本和图片），并可选择开启入群验证：生成一道简单计算题（结果在0~100，两步以内），新成员需在规定次数内回答正确，否则将通知管理员审批。

## 功能特性

- ✅ **入群欢迎**：自定义欢迎文本，支持 `{user_name}` 变量替换
- ✅ **欢迎图片**：可选择是否附带图片，支持本地路径或网络URL
- ✅ **入群验证**：开关控制，开启后新成员需回答计算题
- ✅ **计算题生成**：随机生成两步以内的加减乘法题，结果在0~100之间
- ✅ **多次尝试**：可配置最大尝试次数（默认3次）
- ✅ **管理员审批**：验证失败后通知群主和管理员，管理员可使用 `/pass @用户` 命令同意入群
- ✅ **超时踢人**：可配置超时时间，超时后自动移出群聊
- ✅ **自定义题库**：支持导入 JSON 格式的题库文件
- ✅ **全量配置**：所有文本、参数均可通过 AstrBot WebUI 动态配置

## 安装方法

1. 将本插件下载到 AstrBot 的插件目录：
   ```
      cd data/plugins
      git clone https://github.com/oujunhaoyueling/astrbot_plugin_welcome_verification.git
   ```
            
            2. 重启 AstrBot 或在 WebUI 的插件管理页面中点击"重载插件"
            
            3. 在 WebUI 的插件配置页面中根据需求修改配置项
            
   ## 配置说明
            
   | 配置项 | 类型 | 默认值 | 说明 |
   |--------|------|--------|------|
   | `enable_verification` | bool | true | 是否开启入群验证 |
   | `verification_disabled_groups` | list | [] | 黑名单群号列表 |
   | `welcome_text` | string | 欢迎 {user_name} 加入本群！ | 欢迎文本 |
   | `enable_welcome_image` | bool | false | 是否发送欢迎图片 |
   | `welcome_image` | string | "" | 欢迎图片路径 |
   | `verification_timeout` | int | 300 | 验证超时时间（秒） |
   | `verification_max_attempts` | int | 3 | 最大尝试次数 |
   | `verification_question_format` | string | 请回答：{question} = ? | 验证问题格式 |
   | `verification_correct_message` | string | 验证通过，欢迎入群！ | 回答正确提示 |
   | `verification_failed_message` | string | 答案错误，您还有 {remaining} 次机会 | 回答错误提示 |
   | `secondary_verification_enabled` | bool | true | 是否启用管理员审批 |
   | `secondary_verification_timeout` | int | 60 | 管理员审批等待时间（秒） |
   | `timeout_kick_enabled` | bool | true | 是否启用超时踢人 |
   | `timeout_kick_delay` | int | 30 | 踢人前等待时间（秒） |
   | `timeout_kick_cancel_command` | string | /cancel_kick | 取消踢人命令 |
            
   ## 使用说明
            
   ### 入群欢迎
   当新成员加入群时，机器人会自动发送欢迎消息。若开启图片，则会附带指定图片。
            
   ### 入群验证
   1. 新成员加入后，机器人会 @ 该成员并发送一道计算题（如 `请回答：12 + 25 = ?`）
   2. 成员需在指定超时时间内发送数字答案
   3. 若答案正确，验证通过
   4. 若尝试次数用尽，机器人将 @ 群主和管理员请求审批
   5. 管理员发送 `/pass @用户` 即可同意该成员入群，否则超时后自动移出
            
   ### 管理命令
   | 命令 | 说明 | 权限 |
   |------|------|------|
   | `wv on` | 开启本群入群验证 | 管理员/群主 |
   | `wv off` | 关闭本群入群验证 | 管理员/群主 |
   | `wv ls` | 查看可用题库 | 所有人 |
   | `wv default` | 恢复随机生成题目 | 管理员/群主 |
   | `wv <文件名>` | 切换题库 | 管理员/群主 |
   | `/pass @用户` | 同意用户入群 | 管理员/群主 |
   | `/cancel_kick @用户` | 取消即将执行的踢人 | 管理员/群主 |
            
   ### 自定义题库
   在 `data/plugin_data/welcome_verification/warehouse/` 目录下放入 JSON 格式的题库文件，格式如下：
            
   ```
   {"question": "1 + 1", "answer": 2},
   {"question": "中国的首都是哪里", "answer": "北京"},
   {"question": "3 * 4", "answer": 12}
   ```
                  
   ## 注意事项
                  
   - 本插件**仅支持 aiocqhttp（OneBot V11）平台**（如 NapCat、LLOneBot）
   - 机器人需要拥有群管理员权限才能移出用户
   - 验证过程中成员输入非数字内容不计入尝试次数
                  
   ## 依赖
                  
   - AstrBot >= 4.16
   - 无额外 Python 依赖
                  
   ## 作者
                  
   - Yueling
   - GitHub: https://github.com/oujunhaoyueling
                  
   ## 许可证
                  
   MIT License
