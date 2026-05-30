import random
import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import At, Plain, Image
from astrbot.core.star.star_tools import StarTools


@register(
    "astrbot_plugin_welcome_verification",
    "月凌",
    "入群欢迎与验证插件，支持群组自定义配置",
    "2.8.0",
    repo="https://github.com/oujunhaoyueling/astrbot_plugin_welcome_verification"
)
class WelcomeVerificationPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.user_states: Dict[str, dict] = {}
        self.secondary_tasks: Dict[str, asyncio.Task] = {}
        self.timeout_kick_tasks: Dict[str, asyncio.Task] = {}
        self.verification_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()
        self._kicking_users: Set[str] = set()  # 防止重复踢人

        self.data_dir: Path = StarTools.get_data_dir("welcome_verification")
        self.warehouse_dir = self.data_dir / "warehouse"
        self.config_file = self.data_dir / "group_config.json"

        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.warehouse_dir.mkdir(exist_ok=True)
        except Exception as e:
            logger.error(f"创建数据目录失败: {e}")

        self.question_banks: Dict[str, List[dict]] = {}
        self.group_configs: Dict[str, dict] = {}
        self._load_group_configs()
        self._load_all_question_banks()

    def _load_group_configs(self):
        """从 WebUI 配置或本地文件加载群组配置"""
        try:
            # 优先从 WebUI 的 template_list 配置中加载
            template_list_configs = self.config.get("group_configs", [])
            if template_list_configs and isinstance(template_list_configs, list):
                # 将 template_list 格式转换为内部 dict 格式
                self.group_configs = self._convert_template_list_to_dict(template_list_configs)
                logger.info(f"已从 WebUI 配置加载 {len(self.group_configs)} 个群组配置")
                return
            
            # 如果 WebUI 配置为空或无效，尝试从本地文件加载
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    if isinstance(loaded_config, dict):
                        self.group_configs = loaded_config
                        logger.info(f"已从本地文件加载 {len(self.group_configs)} 个群组配置")
                    else:
                        self.group_configs = {}
            else:
                self.group_configs = {}
        except (json.JSONDecodeError, OSError, Exception) as e:
            logger.error(f"加载群配置失败: {e}")
            self.group_configs = {}

    def _convert_template_list_to_dict(self, template_list: list) -> dict:
        """将 template_list 格式转换为内部使用的 dict 格式"""
        result = {}
        for item in template_list:
            if not isinstance(item, dict):
                continue
            group_id = item.get("group_id")
            if not group_id:
                continue
            
            # 构建群组配置
            group_config = {}
            
            # 处理欢迎文本
            welcome_text = item.get("welcome_text")
            if welcome_text and welcome_text.strip():
                group_config["welcome"] = group_config.get("welcome", {})
                group_config["welcome"]["text"] = welcome_text
            
            # 处理欢迎图片启用状态
            enable_image = item.get("enable_welcome_image")
            if enable_image is not None:
                group_config["welcome"] = group_config.get("welcome", {})
                group_config["welcome"]["enable_image"] = enable_image
            
            # 处理欢迎图片路径
            welcome_image = item.get("welcome_image")
            if welcome_image and welcome_image.strip():
                group_config["welcome"] = group_config.get("welcome", {})
                group_config["welcome"]["image"] = welcome_image
            
            # 处理题库
            question_bank = item.get("question_bank")
            if question_bank and question_bank.strip():
                group_config["question_bank"] = question_bank
            
            if group_config:
                result[str(group_id)] = group_config
        
        return result

    def _convert_dict_to_template_list(self, group_configs: dict) -> list:
        """将内部 dict 格式转换为 template_list 格式"""
        result = []
        for group_id, config in group_configs.items():
            item = {
                "__template_key": "group_config",
                "group_id": str(group_id)
            }
            
            # 处理欢迎配置
            welcome = config.get("welcome", {})
            if "text" in welcome:
                item["welcome_text"] = welcome["text"]
            if "enable_image" in welcome:
                item["enable_welcome_image"] = welcome["enable_image"]
            if "image" in welcome:
                item["welcome_image"] = welcome["image"]
            
            # 处理题库
            if "question_bank" in config:
                item["question_bank"] = config["question_bank"]
            
            result.append(item)
        
        return result

    def _save_group_configs(self):
        """保存群组配置到本地文件并尝试同步到 WebUI"""
        try:
            # 保存到本地文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.group_configs, f, ensure_ascii=False, indent=2)
            
            # 尝试同步到 WebUI 配置（AstrBot 的 template_list 格式）
            template_list = self._convert_dict_to_template_list(self.group_configs)
            self.config["group_configs"] = template_list
            
            # 尝试调用配置保存方法（AstrBotConfig 支持 save_config）
            if hasattr(self.config, 'save_config'):
                self.config.save_config()
                logger.info(f"已同步 {len(self.group_configs)} 个群组配置到 WebUI")
            else:
                logger.info(f"已保存 {len(self.group_configs)} 个群组配置到本地文件（WebUI 同步不可用）")
        except Exception as e:
            logger.error(f"保存群配置失败: {e}")

    def _load_all_question_banks(self):
        if not self.warehouse_dir.exists():
            return
        for file in self.warehouse_dir.glob("*.json"):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list) and all('question' in item and 'answer' in item for item in data):
                    self.question_banks[file.name] = data
                    logger.info(f"加载题库 {file.name}，共 {len(data)} 题")
                else:
                    logger.warning(f"题库 {file.name} 格式错误，跳过")
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"加载题库 {file.name} 失败: {e}")

    def _get_group_question_bank(self, group_id: str) -> Optional[str]:
        return self.group_configs.get(str(group_id), {}).get("question_bank")

    def _set_group_question_bank(self, group_id: str, bank_name: Optional[str]):
        gid = str(group_id)
        if gid not in self.group_configs:
            self.group_configs[gid] = {}
        self.group_configs[gid]["question_bank"] = bank_name
        self._save_group_configs()

    def _get_group_welcome_config(self, group_id: str) -> dict:
        gid = str(group_id)
        return self.group_configs.get(gid, {}).get("welcome", {})

    def _set_group_welcome_text(self, group_id: str, text: Optional[str]):
        gid = str(group_id)
        if gid not in self.group_configs:
            self.group_configs[gid] = {}
        if "welcome" not in self.group_configs[gid]:
            self.group_configs[gid]["welcome"] = {}
        if text:
            self.group_configs[gid]["welcome"]["text"] = text
        else:
            self.group_configs[gid]["welcome"].pop("text", None)
        self._save_group_configs()

    def _set_group_welcome_image(self, group_id: str, image_path: Optional[str]):
        gid = str(group_id)
        if gid not in self.group_configs:
            self.group_configs[gid] = {}
        if "welcome" not in self.group_configs[gid]:
            self.group_configs[gid]["welcome"] = {}
        if image_path:
            self.group_configs[gid]["welcome"]["image"] = image_path
        else:
            self.group_configs[gid]["welcome"].pop("image", None)
        self._save_group_configs()

    def _set_group_welcome_image_enabled(self, group_id: str, enabled: bool):
        gid = str(group_id)
        if gid not in self.group_configs:
            self.group_configs[gid] = {}
        if "welcome" not in self.group_configs[gid]:
            self.group_configs[gid]["welcome"] = {}
        self.group_configs[gid]["welcome"]["enable_image"] = enabled
        self._save_group_configs()

    def _reset_group_welcome_config(self, group_id: str):
        gid = str(group_id)
        if gid in self.group_configs:
            self.group_configs[gid].pop("welcome", None)
            self._save_group_configs()

    async def _get_question_for_group(self, group_id: int | str) -> Tuple[str, any]:
        bank_name = self._get_group_question_bank(str(group_id))
        if bank_name and bank_name in self.question_banks:
            bank = self.question_banks[bank_name]
            if bank:
                idx = random.randrange(len(bank))
                item = bank[idx]
                return item["question"], item["answer"]
        return self._generate_question()

    def _match_command(self, msg: str, cmd: str) -> bool:
        """精确匹配命令，防止误匹配（如 /pass 不会匹配 /password）"""
        cmd_with_slash = cmd if cmd.startswith('/') else f'/{cmd}'
        cmd_without_slash = cmd.lstrip('/')
        
        parts = msg.split()
        if not parts:
            return False
        
        first_part = parts[0]
        return first_part == cmd_with_slash or first_part == cmd_without_slash

    async def _handle_wv_command(self, event: AstrMessageEvent):
        msg = event.message_str.strip()
        if not self._match_command(msg, "wv"):
            return
        if not event.message_obj.group_id:
            await event.send(event.plain_result("该命令仅在群聊中可用"))
            return

        parts = msg.split()
        group_id = str(event.message_obj.group_id)
        sender_id = event.get_sender_id()

        owner, admins = await self._get_group_owner_and_admins(event, event.message_obj.group_id)
        is_admin = (owner == sender_id) or (sender_id in admins)

        if len(parts) < 2:
            help_text = (
                "入群欢迎与验证 命令列表：\n\n"
                "欢迎配置：\n"
                "wv welcome - 查看当前欢迎配置\n"
                "wv welcome text <内容> - 设置欢迎文本（仅管理员）\n"
                "wv welcome image <路径> - 设置欢迎图片（仅管理员）\n"
                "wv welcome image on/off - 启用/禁用图片（仅管理员）\n"
                "wv welcome reset - 重置为全局配置（仅管理员）\n\n"
                "题库管理：\n"
                "wv ls - 查看可用题库\n"
                "wv <文件名> - 切换题库（仅管理员，如 wv math.json，可省略 .json）\n"
                "wv default - 恢复随机出题（仅管理员）\n\n"
                "管理操作：\n"
                "wv pass @用户 - 允许用户入群（仅管理员）\n"
                "wv kick @用户 - 踢出用户（仅管理员）\n"
                "wv cancel @用户 - 取消踢人（仅管理员）"
            )
            await event.send(event.plain_result(help_text))
            return

        subcmd = parts[1].lower()

        # ── 题库管理 ──
        if subcmd == "ls":
            banks = list(self.question_banks.keys())
            if banks:
                msg = "可用题库：\n" + "\n".join(f"- {name} ({len(self.question_banks[name])}题)" for name in banks)
            else:
                msg = "没有发现任何可用题库文件，请将 JSON 格式的题库放入 AstrBot/data/plugin_data/welcome_verification/warehouse/ 文件夹并重载插件"
            await event.send(event.plain_result(msg))
            return

        elif subcmd == "default":
            if not is_admin:
                await event.send(event.plain_result("只有管理员或群主可以切换题库"))
                return
            self._set_group_question_bank(group_id, None)
            await event.send(event.plain_result("已恢复为随机生成题目"))
            return

        # ── 欢迎配置 ──
        elif subcmd == "welcome":
            welcome_config = self._get_group_welcome_config(group_id)
            has_custom = bool(welcome_config)

            if len(parts) < 3:
                if has_custom:
                    text = welcome_config.get("text")
                    if not text:
                        text = self.config.get("welcome_text", "欢迎 {user_name} 加入本群！")
                    enable_image = welcome_config.get("enable_image")
                    if enable_image is None:
                        enable_image = self.config.get("enable_welcome_image", True)
                    image = welcome_config.get("image")
                    if not image:
                        image = self.config.get("welcome_image", "")
                else:
                    text = self.config.get("welcome_text", "欢迎 {user_name} 加入本群！")
                    enable_image = self.config.get("enable_welcome_image", True)
                    image = self.config.get("welcome_image", "")

                image_status = "已启用" if enable_image else "已禁用"
                help_msg = (
                    f"当前欢迎配置：\n"
                    f"欢迎文本: {text}\n"
                    f"启用图片: {image_status}\n"
                    f"图片路径: {image or '（无）'}\n"
                    f"{'（使用群组自定义配置）' if has_custom else '（使用全局配置）'}\n\n"
                    f"子命令：\n"
                    f"wv welcome text <内容> - 设置欢迎文本\n"
                    f"wv welcome image <路径/URL> - 设置欢迎图片\n"
                    f"wv welcome image on/off - 启用/禁用图片\n"
                    f"wv welcome reset - 重置为全局配置"
                )
                await event.send(event.plain_result(help_msg))
                return

            subcmd2 = parts[2].lower()

            if subcmd2 == "text":
                if not is_admin:
                    await event.send(event.plain_result("只有管理员或群主可以修改配置"))
                    return
                if len(parts) < 4:
                    await event.send(event.plain_result("请指定欢迎文本内容"))
                    return
                welcome_text = msg.split(maxsplit=3)[3]
                self._set_group_welcome_text(group_id, welcome_text)
                await event.send(event.plain_result(f"已设置欢迎文本：{welcome_text}"))
                return

            elif subcmd2 == "image":
                if not is_admin:
                    await event.send(event.plain_result("只有管理员或群主可以修改配置"))
                    return
                if len(parts) < 4:
                    await event.send(event.plain_result("请指定图片路径/URL，或使用 on/off 开关"))
                    return
                image_param = parts[3]
                if image_param == "on":
                    self._set_group_welcome_image_enabled(group_id, True)
                    await event.send(event.plain_result("已启用欢迎图片"))
                elif image_param == "off":
                    self._set_group_welcome_image_enabled(group_id, False)
                    await event.send(event.plain_result("已禁用欢迎图片"))
                else:
                    self._set_group_welcome_image(group_id, image_param)
                    await event.send(event.plain_result(f"已设置欢迎图片：{image_param}"))
                return

            elif subcmd2 == "reset":
                if not is_admin:
                    await event.send(event.plain_result("只有管理员或群主可以修改配置"))
                    return
                self._reset_group_welcome_config(group_id)
                await event.send(event.plain_result("已重置为全局配置"))
                return

            else:
                await event.send(event.plain_result(f"未知子命令：{subcmd2}，请使用 wv welcome 查看帮助"))
                return

        # ── pass：允许入群 ──
        elif subcmd == "pass":
            if not is_admin:
                await event.send(event.plain_result("只有管理员或群主可以使用此命令"))
                return

            at_targets = [str(comp.qq) for comp in event.message_obj.message if isinstance(comp, At)]
            if not at_targets:
                await event.send(event.plain_result("请指定要允许入群的用户，例如：wv pass @用户"))
                return

            target_id = at_targets[0]
            key = f"{group_id}:{target_id}"

            task_to_cancel = None
            state_exists = False
            async with self._lock:
                state = self.user_states.get(key)
                if state and state.get("pending_decision"):
                    state_exists = True
                    self.user_states.pop(key, None)
                    task_to_cancel = self.secondary_tasks.pop(key, None)

            if not state_exists:
                await event.send(event.plain_result("该用户没有等待审批的验证请求"))
                return

            if task_to_cancel and not task_to_cancel.done():
                task_to_cancel.cancel()

            success_msg = self.config.get("pass_success_message", "已允许该用户入群")
            await event.send(event.plain_result(success_msg))
            try:
                await event.send(event.chain_result([At(qq=target_id), Plain(" 管理员已允许您入群")]))
            except Exception:
                pass
            return

        # ── kick：踢出用户 ──
        elif subcmd == "kick":
            if not is_admin:
                await event.send(event.plain_result("只有管理员或群主可以使用此命令"))
                return

            at_targets = [str(comp.qq) for comp in event.message_obj.message if isinstance(comp, At)]
            if not at_targets:
                await event.send(event.plain_result("请指定要踢出的用户，例如：wv kick @用户"))
                return

            target_id = at_targets[0]

            if target_id == sender_id:
                await event.send(event.plain_result("不能踢出自己"))
                return

            key = f"{group_id}:{target_id}"

            tasks_to_cancel = []
            async with self._lock:
                self.user_states.pop(key, None)
                for task_dict in [self.secondary_tasks, self.timeout_kick_tasks, self.verification_tasks]:
                    t = task_dict.pop(key, None)
                    if t and not t.done():
                        tasks_to_cancel.append(t)

            for t in tasks_to_cancel:
                t.cancel()

            kick_success = await self._kick_user(event, target_id)
            if kick_success:
                success_msg = self.config.get("kick_success_message", "已移出该用户")
                await event.send(event.plain_result(success_msg))
            return

        # ── cancel：取消踢人 ──
        elif subcmd == "cancel":
            if not is_admin:
                await event.send(event.plain_result("只有管理员或群主可以取消踢人"))
                return

            at_targets = [str(comp.qq) for comp in event.message_obj.message if isinstance(comp, At)]
            if not at_targets:
                await event.send(event.plain_result("请指定要取消踢人的用户，例如：wv cancel @用户"))
                return

            target_id = at_targets[0]
            key = f"{group_id}:{target_id}"
            task_to_cancel = None
            async with self._lock:
                task_to_cancel = self.timeout_kick_tasks.pop(key, None)

            if task_to_cancel and not task_to_cancel.done():
                task_to_cancel.cancel()
                await event.send(event.plain_result("已取消踢人操作"))
            else:
                await event.send(event.plain_result("该用户没有等待踢人的任务"))
            return

        # ── 切换题库 ──
        else:
            if not is_admin:
                await event.send(event.plain_result("只有管理员或群主可以切换题库"))
                return
            bank_name = subcmd
            if not bank_name.endswith('.json'):
                bank_name += '.json'
            if bank_name not in self.question_banks:
                await event.send(event.plain_result(f"题库 {bank_name} 不存在，请使用 wv ls 查看可用题库"))
                return
            self._set_group_question_bank(group_id, bank_name)
            await event.send(event.plain_result(f"已切换题库为 {bank_name}，共 {len(self.question_banks[bank_name])} 道题"))
            return

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_event(self, event: AstrMessageEvent):
        if event.get_platform_name() != "aiocqhttp":
            return

        if not event.message_obj or not event.message_obj.raw_message:
            return

        raw = event.message_obj.raw_message
        if not isinstance(raw, dict):
            return

        post_type = raw.get("post_type")

        if post_type == "notice":
            notice_type = raw.get("notice_type")
            if notice_type == "group_increase":
                user_id = str(raw.get("user_id"))
                group_id = raw.get("group_id")

                if user_id == str(event.get_self_id()):
                    logger.info(f"机器人自身入群，忽略欢迎和验证")
                    return

                await self._handle_group_increase(event, user_id, group_id)

        elif post_type == "message" and raw.get("message_type") == "group":
            await self._handle_message_event(event)

    async def _handle_group_increase(self, event: AstrMessageEvent, user_id: str, group_id: int | str):
        user_name = await self._get_user_display_name(event, user_id, group_id)

        logger.info(f"新成员入群: {user_name}({user_id}) 进入群 {group_id}")

        await self._send_welcome_with_id(event, user_id, user_name)

        if self.config.get("enable_verification", True):
            has_permission = await self._check_bot_admin(event, group_id)
            task = asyncio.create_task(self._start_verification(event, user_id, group_id, has_permission))
            task.add_done_callback(lambda t: self._check_task_exception(t, f"验证任务 {group_id}:{user_id}"))
            async with self._lock:
                self.verification_tasks[f"{group_id}:{user_id}"] = task

    async def _handle_message_event(self, event: AstrMessageEvent):
        await self._handle_wv_command(event)
        await self._check_answer(event)

    async def _is_member_in_group(self, event: AstrMessageEvent, group_id: int | str, user_id: str) -> bool:
        try:
            result = await event.bot.api.call_action('get_group_member_info', group_id=int(group_id), user_id=int(user_id))
            return result is not None and isinstance(result, dict)
        except Exception as e:
            logger.debug(f"检查群成员存在性失败: {e}")
            return False

    async def _send_welcome_with_id(self, event: AstrMessageEvent, user_id: str, user_name: str):
        group_id = str(event.message_obj.group_id)
        group_welcome_config = self._get_group_welcome_config(group_id)
        
        # 优先使用群组特定配置，否则使用全局配置
        welcome_text = group_welcome_config.get("text", self.config.get("welcome_text", "欢迎 {user_name} 加入本群！")).format(user_name=user_name)
        enable_image = group_welcome_config.get("enable_image", self.config.get("enable_welcome_image", True))
        image_path = group_welcome_config.get("image", self.config.get("welcome_image", ""))
        
        chain = [At(qq=user_id), Plain(" " + welcome_text)]
        if enable_image and image_path:
            if image_path.startswith(("http://", "https://")):
                chain.append(Image.fromURL(image_path))
            else:
                chain.append(Image.fromFileSystem(image_path))
        await event.send(event.chain_result(chain))

    async def _send_welcome(self, event: AstrMessageEvent, user_name: str):
        await self._send_welcome_with_id(event, event.get_sender_id(), user_name)

    async def _get_user_display_name(self, event: AstrMessageEvent, user_id: str, group_id: int | str) -> str:
        try:
            member_info = await event.bot.api.call_action(
                'get_group_member_info',
                group_id=int(group_id),
                user_id=int(user_id)
            )
            if member_info and isinstance(member_info, dict):
                card = member_info.get("card", "")
                nickname = member_info.get("nickname", "")
                return card or nickname or str(user_id)
        except Exception as e:
            logger.warning(f"获取用户 {user_id} 昵称失败: {e}")
        return str(user_id)

    async def _start_verification(self, event: AstrMessageEvent, user_id: str, group_id: int | str, has_permission: bool):
        max_attempts = self.config.get("verification_max_attempts", 3)
        timeout = self.config.get("verification_timeout", 300)

        attempts = 0
        key = f"{group_id}:{user_id}"

        try:
            while attempts < max_attempts:
                question, answer = await self._get_question_for_group(group_id)
                question_text = self.config.get("verification_question_format", "请回答：{question} = ?").format(question=question)
                try:
                    await event.send(event.chain_result([At(qq=user_id), Plain(" " + question_text)]))
                except Exception as e:
                    logger.warning(f"发送验证问题失败: {e}")
                    return

                future = asyncio.get_event_loop().create_future()
                expire_time = asyncio.get_event_loop().time() + timeout

                async with self._lock:
                    self.user_states[key] = {
                        "group_id": group_id,
                        "user_id": user_id,
                        "attempts": attempts,
                        "expire_time": expire_time,
                        "current_answer": answer,
                        "future": future
                    }

                try:
                    is_correct = await asyncio.wait_for(future, timeout)
                    if is_correct:
                        try:
                            await event.send(event.plain_result(self.config.get("verification_correct_message", "验证通过，欢迎入群！")))
                        except Exception:
                            pass
                        async with self._lock:
                            self.user_states.pop(key, None)
                        return
                    else:
                        attempts += 1
                        remaining = max_attempts - attempts
                        if remaining > 0:
                            msg = self.config.get("verification_failed_message", "答案错误，您还有 {remaining} 次机会。").format(remaining=remaining)
                            try:
                                await event.send(event.plain_result(msg))
                            except Exception:
                                pass
                        else:
                            await self._handle_verification_failed(event, user_id, group_id, has_permission)
                            return
                except asyncio.TimeoutError:
                    attempts += 1
                    remaining = max_attempts - attempts
                    if remaining > 0:
                        try:
                            await event.send(event.plain_result(f"验证超时，您还有 {remaining} 次机会"))
                        except Exception:
                            pass
                    else:
                        await self._handle_verification_failed(event, user_id, group_id, has_permission)
                        return
                finally:
                    async with self._lock:
                        if key in self.user_states:
                            self.user_states[key].pop("future", None)
        finally:
            async with self._lock:
                self.verification_tasks.pop(key, None)

    async def _handle_verification_failed(self, event: AstrMessageEvent, user_id: str, group_id: int | str, has_permission: bool):
        user_name = await self._get_user_display_name(event, user_id, group_id)
        if not self.config.get("secondary_verification_enabled", True):
            if has_permission:
                await self._schedule_timeout_kick(event, user_id, user_name, group_id)
            else:
                await self._notify_admins_no_permission(event, user_id, user_name, group_id)
            return

        if has_permission:
            await self._secondary_verification_with_commands(event, user_id, user_name, group_id)
        else:
            await self._notify_admins_no_permission(event, user_id, user_name, group_id)

    async def _notify_admins_no_permission(self, event: AstrMessageEvent, user_id: str, user_name: str, group_id: int | str):
        owner, admins = await self._get_group_owner_and_admins(event, group_id)
        if not owner and not admins:
            logger.warning(f"群 {group_id} 没有管理员，无法通知")
            return

        prompt_template = self.config.get(
            "no_permission_prompt",
            "用户 {user_name}({user_id}) 未通过入群验证，但我没有管理员权限无法处理，请管理员手动处理。"
        )
        prompt = prompt_template.format(user_name=user_name, user_id=user_id, group_id=group_id)

        at_list = []
        if owner:
            at_list.append(owner)
        at_list.extend(admins)
        at_mentions = [At(qq=uid) for uid in at_list]
        message_chain = at_mentions + [Plain(f" {prompt}")]
        await event.send(event.chain_result(message_chain))

        key = f"{group_id}:{user_id}"
        async with self._lock:
            self.user_states.pop(key, None)

    async def _secondary_verification_with_commands(self, event: AstrMessageEvent, user_id: str, user_name: str, group_id: int | str):
        owner, admins = await self._get_group_owner_and_admins(event, group_id)
        if not owner and not admins:
            logger.warning(f"无法获取群 {group_id} 的管理员/群主，直接踢出用户 {user_id}")
            await self._schedule_timeout_kick(event, user_id, user_name, group_id)
            return

        prompt_template = self.config.get(
            "secondary_verification_prompt",
            "用户 {user_name}({user_id}) 未通过入群验证，请管理员/群主使用以下命令处理（注意命令和@用户之间要有空格）：\n"
            "{pass_cmd} @用户 - 允许入群\n"
            "{kick_cmd} @用户 - 移出群聊\n"
            "超时时间 {timeout} 秒。"
        )
        pass_cmd = "wv pass"
        kick_cmd = "wv kick"
        timeout_sec = self.config.get("secondary_verification_timeout", 60)

        prompt = prompt_template.format(
            user_name=user_name,
            user_id=user_id,
            pass_cmd=pass_cmd,
            kick_cmd=kick_cmd,
            timeout=timeout_sec
        )

        at_list = []
        if owner:
            at_list.append(owner)
        at_list.extend(admins)
        at_mentions = [At(qq=uid) for uid in at_list]
        message_chain = at_mentions + [Plain(f" {prompt}")]
        await event.send(event.chain_result(message_chain))

        key = f"{group_id}:{user_id}"
        expire_time = asyncio.get_event_loop().time() + timeout_sec

        async with self._lock:
            self.user_states[key] = {
                "group_id": group_id,
                "user_id": user_id,
                "secondary_expire": expire_time,
                "pending_decision": True,
                "user_name": user_name
            }

        async def wait_for_decision():
            should_kick = False
            try:
                while True:
                    try:
                        await asyncio.sleep(1)
                    except asyncio.CancelledError:
                        raise
                    
                    async with self._lock:
                        state = self.user_states.get(key)
                        if not state:
                            return
                        if not state.get("pending_decision"):
                            return
                        if asyncio.get_event_loop().time() > state.get("secondary_expire", 0):
                            should_kick = True
                            self.user_states.pop(key, None)
                            break
            except asyncio.CancelledError:
                logger.debug(f"二级验证任务取消: {key}")
                raise
            
            if should_kick:
                await self._auto_kick_after_timeout(event, user_id, group_id, user_name)

        task = asyncio.create_task(wait_for_decision())
        task.set_name(f"wv_secondary_{group_id}_{user_id}")
        async with self._lock:
            self.secondary_tasks[key] = task

        def cleanup(task):
            if task.exception():
                logger.error(f"二级验证任务异常: {task.exception()}")
            async def _remove():
                async with self._lock:
                    self.secondary_tasks.pop(key, None)
            asyncio.create_task(_remove())
        task.add_done_callback(cleanup)

    async def _auto_kick_after_timeout(self, event: AstrMessageEvent, user_id: str, group_id: int | str, user_name: str):
        if not await self._check_bot_admin(event, group_id):
            await self._notify_admins_no_permission(event, user_id, user_name, group_id)
            return

        if not await self._is_member_in_group(event, group_id, user_id):
            logger.info(f"跳过踢人: 用户 {user_id} 已不在群 {group_id}")
            return

        kick_success = await self._kick_user(event, user_id)
        if kick_success:
            still_in_group = await self._is_member_in_group(event, group_id, user_id)
            if not still_in_group:
                msg_template = self.config.get(
                    "secondary_timeout_auto_kick_message",
                    "用户 {user_name} 未在时间内得到处理，已自动移出群聊。"
                )
                msg = msg_template.format(user_name=user_name, user_id=user_id)
                await event.send(event.plain_result(msg))
            else:
                logger.warning(f"踢人未生效: 用户 {user_id} 仍在群 {group_id}")

    async def _check_answer(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.message_obj.group_id
        key = f"{group_id}:{user_id}"

        future_to_set = None
        is_correct = None
        send_prompt = False

        async with self._lock:
            state = self.user_states.get(key)
            if not state or "future" not in state:
                return
            if state.get("expire_time") and asyncio.get_event_loop().time() > state["expire_time"]:
                return

            correct_answer = state["current_answer"]
            user_input = event.message_str.strip()
            future = state.get("future")

            if future and not future.done():
                if isinstance(correct_answer, int):
                    try:
                        user_answer = int(user_input)
                        future_to_set = future
                        is_correct = user_answer == correct_answer
                    except ValueError:
                        send_prompt = True
                else:
                    future_to_set = future
                    is_correct = user_input == correct_answer

        if send_prompt:
            await event.send(event.plain_result("请输入数字答案"))

        if future_to_set is not None:
            future_to_set.set_result(is_correct)

    async def _get_group_owner_and_admins(self, event: AstrMessageEvent, group_id: int | str) -> Tuple[Optional[str], List[str]]:
        if event.get_platform_name() != "aiocqhttp":
            return None, []
        try:
            result = await event.bot.api.call_action('get_group_member_list', group_id=int(group_id))
            if not result or not isinstance(result, list):
                return None, []
            owner = None
            admins = []
            for member in result:
                role = member.get('role')
                uid = str(member.get('user_id'))
                if role == 'owner':
                    owner = uid
                elif role == 'admin':
                    admins.append(uid)
            return owner, admins
        except Exception as e:
            logger.error(f"获取群 {group_id} 管理员列表失败: {e}")
            return None, []

    async def _schedule_timeout_kick(self, event: AstrMessageEvent, user_id: str, user_name: str, group_id: int | str):
        if not await self._check_bot_admin(event, group_id):
            await self._notify_admins_no_permission(event, user_id, user_name, group_id)
            return

        if not self.config.get("timeout_kick_enabled", True):
            kick_msg = self.config.get("timeout_kick_immediate_message", "验证失败，您即将被移出群聊")
            await event.send(event.plain_result(kick_msg))
            await self._kick_user(event, user_id)
            return

        key = f"{group_id}:{user_id}"
        async with self._lock:
            old_task = self.timeout_kick_tasks.get(key)
            if old_task and not old_task.done():
                old_task.cancel()
            task = asyncio.create_task(self._timeout_kick_process(event, user_id, user_name, group_id))
            task.set_name(f"wv_timeoutkick_{group_id}_{user_id}")
            self.timeout_kick_tasks[key] = task
            task.add_done_callback(lambda t, k=key: asyncio.create_task(self._clean_timeout_task(k)))

    async def _clean_timeout_task(self, key: str):
        await asyncio.sleep(0)
        async with self._lock:
            self.timeout_kick_tasks.pop(key, None)

    async def _timeout_kick_process(self, event: AstrMessageEvent, user_id: str, user_name: str, group_id: int | str):
        delay = self.config.get("timeout_kick_delay", 30)
        warning_template = self.config.get(
            "timeout_kick_warning_message",
            "用户 {user_name} 验证失败，将在 {delay} 秒后被移出群聊。如需取消，请管理员发送：{cancel_command} @用户(有空格)"
        )

        cancel_cmd = "wv cancel"
        warning_msg = warning_template.format(
            user_name=user_name,
            delay=delay,
            cancel_command=cancel_cmd
        )
        await event.send(event.plain_result(warning_msg))

        key = f"{group_id}:{user_id}"
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            cancel_msg_template = self.config.get(
                "timeout_kick_cancel_message",
                "已取消踢出 {user_name}"
            )
            cancel_msg = cancel_msg_template.format(user_name=user_name)
            await event.send(event.plain_result(cancel_msg))
            return

        if not await self._is_member_in_group(event, group_id, user_id):
            logger.info(f"跳过踢人: 用户 {user_id} 已不在群 {group_id}")
            return

        kick_success = await self._kick_user(event, user_id)
        if kick_success:
            still_in_group = await self._is_member_in_group(event, group_id, user_id)
            if not still_in_group:
                await event.send(event.plain_result(f"已移出用户 {user_name}"))
            else:
                logger.warning(f"踢人未生效: 用户 {user_id} 仍在群 {group_id}")

    async def _check_bot_admin(self, event: AstrMessageEvent, group_id: int | str) -> bool:
        if event.get_platform_name() != "aiocqhttp":
            return False
        try:
            bot_id = event.get_self_id()
            if not bot_id:
                bot_id = event.message_obj.self_id
            if not bot_id:
                logger.error("无法获取机器人自身ID")
                return False

            result = await event.bot.api.call_action('get_group_member_info',
                                                     group_id=int(group_id),
                                                     user_id=int(bot_id))
            if not result or not isinstance(result, dict):
                logger.warning(f"获取机器人成员信息失败: {result}")
                return False

            role = result.get('role')
            return role in ('owner', 'admin')
        except Exception as e:
            logger.error(f"检查机器人权限失败: {e}")
            return False

    async def _kick_user(self, event: AstrMessageEvent, user_id: str, group_id: int | str | None = None) -> bool:
        if event.get_platform_name() != "aiocqhttp":
            logger.warning(f"当前平台不支持踢人操作，无法移出用户 {user_id}")
            return False

        actual_group_id = group_id or event.message_obj.group_id
        if not actual_group_id:
            logger.error(f"无法获取群ID，踢人失败: user_id={user_id}")
            return False

        key = f"{actual_group_id}:{user_id}"
        if key in self._kicking_users:
            return False

        self._kicking_users.add(key)
        try:
            await event.bot.api.call_action(
                'set_group_kick',
                group_id=int(actual_group_id),
                user_id=int(user_id),
                reject_add_request=False
            )
            logger.info(f"已踢出用户 {user_id}")
            return True
        except Exception as e:
            logger.error(f"踢出用户 {user_id} 失败: {e}")
            return False
        finally:
            self._kicking_users.discard(key)

    def _generate_question(self):
        while True:
            op = random.choice(['+', '-', '*'])
            if op == '*':
                a, b = random.randint(1, 9), random.randint(1, 9)
            else:
                a, b = random.randint(0, 50), random.randint(0, 50)

            if op == '+':
                result = a + b
            elif op == '-':
                result = a - b
            else:
                result = a * b

            if 0 <= result <= 100:
                return f"{a} {op} {b}", result

    async def terminate(self):
        logger.info(f"开始清理插件 {self.name}")
        async with self._lock:
            for tasks_dict in [self.secondary_tasks, self.timeout_kick_tasks, self.verification_tasks]:
                for task in tasks_dict.values():
                    if not task.done():
                        task.cancel()
                tasks_dict.clear()
            for state in self.user_states.values():
                future = state.get("future")
                if future and not future.done():
                    future.cancel()
            self.user_states.clear()
        await asyncio.sleep(0.5)
        logger.info(f"插件 {self.name} 已清理")

    def _check_task_exception(self, task: asyncio.Task, name: str = ""):
        if task.done() and task.exception():
            logger.error(f"任务 {name} 异常: {task.exception()}")
