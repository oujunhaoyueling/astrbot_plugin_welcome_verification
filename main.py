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


@register("astrbot_plugin_welcome_verification", "月凌", "入群欢迎与验证插件", "2.5.2")
class WelcomeVerificationPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.user_states: Dict[str, dict] = {}
        self.secondary_tasks: Dict[str, asyncio.Task] = {}
        self.timeout_kick_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

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
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.group_configs = json.load(f)
            else:
                self.group_configs = {}
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"加载群配置失败: {e}")
            self.group_configs = {}

    def _save_group_configs(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.group_configs, f, ensure_ascii=False, indent=2)
        except OSError as e:
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

    async def _get_question_for_group(self, group_id: int) -> Tuple[str, any]:
        bank_name = self._get_group_question_bank(str(group_id))
        if bank_name and bank_name in self.question_banks:
            bank = self.question_banks[bank_name]
            if bank:
                idx = random.randrange(len(bank))
                item = bank[idx]
                return item["question"], item["answer"]
        return self._generate_question()

    async def _handle_wv_command(self, event: AstrMessageEvent):
        msg = event.message_str.strip()
        if not msg.startswith("wv"):
            return
        if not event.message_obj.group_id:
            await event.send(event.plain_result("该命令仅在群聊中可用"))
            return
        parts = msg.split()
        if len(parts) < 2:
            help_text = (
                "题库管理命令：\n"
                "wv ls - 查看可用题库\n"
                "wv <文件名> - 切换题库（仅管理员/群主）\n"
                "wv default - 恢复随机生成（仅管理员/群主）\n"
                "示例：wv math.json 或 wv math（自动补全 .json）"
            )
            await event.send(event.plain_result(help_text))
            return

        subcmd = parts[1].lower()
        group_id = str(event.message_obj.group_id)
        sender_id = event.get_sender_id()

        owner, admins = await self._get_group_owner_and_admins(event, event.message_obj.group_id)
        is_admin = (owner == sender_id) or (sender_id in admins)

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
    async def on_group_increase(self, event: AstrMessageEvent):
        if not self._is_group_increase(event):
            return

        raw = event.message_obj.raw_message
        if isinstance(raw, dict):
            user_id_raw = str(raw.get('user_id', ''))
            self_id_raw = str(raw.get('self_id', ''))
            if user_id_raw and self_id_raw and user_id_raw == self_id_raw:
                logger.info(f"机器人自身入群，忽略欢迎和验证")
                return

        user_id = event.get_sender_id()
        group_id = event.message_obj.group_id
        user_name = event.get_sender_name()

        logger.info(f"新成员入群: {user_name}({user_id}) 进入群 {group_id}")

        await self._send_welcome(event, user_name)

        if self.config.get("enable_verification", True):
            has_permission = await self._check_bot_admin(event, group_id)
            asyncio.create_task(self._start_verification(event, user_id, group_id, has_permission))

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        if not event.message_obj.group_id:
            return
        await self._handle_wv_command(event)
        await self._check_answer(event)
        await self._handle_pass_command(event)
        await self._handle_kick_command(event)
        await self._check_cancel_command(event)

    def _is_group_increase(self, event: AstrMessageEvent) -> bool:
        if event.get_platform_name() != "aiocqhttp":
            return False
        raw = event.message_obj.raw_message
        if isinstance(raw, dict):
            return raw.get('post_type') == 'notice' and raw.get('notice_type') == 'group_increase'
        return False

    async def _is_member_in_group(self, event: AstrMessageEvent, group_id: int, user_id: str) -> bool:
        try:
            result = await event.bot.api.call_action('get_group_member_list', group_id=group_id)
            if not result or not isinstance(result, list):
                return False
            for member in result:
                if str(member.get('user_id')) == user_id:
                    return True
            return False
        except Exception as e:
            logger.error(f"检查群成员存在性失败: {e}")
            return False

    async def _send_welcome(self, event: AstrMessageEvent, user_name: str):
        welcome_text = self.config.get("welcome_text", "欢迎 {user_name} 加入本群！").format(user_name=user_name)
        enable_image = self.config.get("enable_welcome_image", False)
        image_path = self.config.get("welcome_image", "")
        chain = [At(qq=event.get_sender_id()), Plain(" " + welcome_text)]
        if enable_image and image_path:
            if image_path.startswith(("http://", "https://")):
                chain.append(Image.fromURL(image_path))
            else:
                chain.append(Image.fromFileSystem(image_path))
        await event.send(event.chain_result(chain))

    async def _start_verification(self, event: AstrMessageEvent, user_id: str, group_id: int, has_permission: bool):
        max_attempts = self.config.get("verification_max_attempts", 3)
        timeout = self.config.get("verification_timeout", 300)

        attempts = 0
        key = f"{group_id}:{user_id}"

        while attempts < max_attempts:
            question, answer = await self._get_question_for_group(group_id)
            question_text = self.config.get("verification_question_format", "请回答：{question} = ?").format(question=question)
            await event.send(event.chain_result([At(qq=user_id), Plain(" " + question_text)]))

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
                    await event.send(event.plain_result(self.config.get("verification_correct_message", "验证通过，欢迎入群！")))
                    async with self._lock:
                        self.user_states.pop(key, None)
                    return
                else:
                    attempts += 1
                    remaining = max_attempts - attempts
                    if remaining > 0:
                        msg = self.config.get("verification_failed_message", "答案错误，您还有 {remaining} 次机会。").format(remaining=remaining)
                        await event.send(event.plain_result(msg))
                    else:
                        await self._handle_verification_failed(event, user_id, group_id, has_permission)
                        return
            except asyncio.TimeoutError:
                attempts += 1
                remaining = max_attempts - attempts
                if remaining > 0:
                    await event.send(event.plain_result(f"验证超时，您还有 {remaining} 次机会"))
                else:
                    await self._handle_verification_failed(event, user_id, group_id, has_permission)
                    return
            finally:
                async with self._lock:
                    if key in self.user_states:
                        self.user_states[key].pop("future", None)

    async def _handle_verification_failed(self, event: AstrMessageEvent, user_id: str, group_id: int, has_permission: bool):
        if not self.config.get("secondary_verification_enabled", True):
            if has_permission:
                await self._schedule_timeout_kick(event, user_id, group_id)
            else:
                await self._notify_admins_no_permission(event, user_id, group_id)
            return

        if has_permission:
            await self._secondary_verification_with_commands(event, user_id, group_id)
        else:
            await self._notify_admins_no_permission(event, user_id, group_id)

    async def _notify_admins_no_permission(self, event: AstrMessageEvent, user_id: str, group_id: int):
        owner, admins = await self._get_group_owner_and_admins(event, group_id)
        if not owner and not admins:
            logger.warning(f"群 {group_id} 没有管理员，无法通知")
            return

        user_name = event.get_sender_name()
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

    async def _secondary_verification_with_commands(self, event: AstrMessageEvent, user_id: str, group_id: int):
        owner, admins = await self._get_group_owner_and_admins(event, group_id)
        if not owner and not admins:
            logger.warning(f"无法获取群 {group_id} 的管理员/群主，直接踢出用户 {user_id}")
            await self._schedule_timeout_kick(event, user_id, group_id)
            return

        prompt_template = self.config.get(
            "secondary_verification_prompt",
            "用户 {user_name}({user_id}) 未通过入群验证，请管理员/群主使用以下命令处理：\n"
            "{pass_cmd} @用户 - 允许入群\n"
            "{kick_cmd} @用户 - 移出群聊\n"
            "超时时间 {timeout} 秒。"
        )
        pass_cmd = self.config.get("pass_command", "/pass").lstrip('/')
        kick_cmd = self.config.get("kick_command", "/kick").lstrip('/')
        timeout_sec = self.config.get("secondary_verification_timeout", 60)

        user_name = event.get_sender_name()
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
            try:
                while True:
                    await asyncio.sleep(1)
                    async with self._lock:
                        state = self.user_states.get(key)
                        if not state:
                            return
                        if not state.get("pending_decision"):
                            return
                        if asyncio.get_event_loop().time() > state.get("secondary_expire", 0):
                            self.user_states.pop(key, None)
                            task = self.secondary_tasks.pop(key, None)
                            if task and not task.done():
                                task.cancel()
                            await self._auto_kick_after_timeout(event, user_id, group_id, user_name)
                            return
            except asyncio.CancelledError:
                logger.debug(f"二级验证等待任务被取消: {key}")
                raise

        task = asyncio.create_task(wait_for_decision())
        task.set_name(f"wv_secondary_{group_id}_{user_id}")
        async with self._lock:
            self.secondary_tasks[key] = task

        def cleanup(task):
            async def _remove():
                async with self._lock:
                    self.secondary_tasks.pop(key, None)
            asyncio.create_task(_remove())
        task.add_done_callback(cleanup)

    async def _auto_kick_after_timeout(self, event: AstrMessageEvent, user_id: str, group_id: int, user_name: str):
        await self._kick_user(event, user_id)
        msg_template = self.config.get(
            "secondary_timeout_auto_kick_message",
            "用户 {user_name} 未在时间内得到处理，已自动移出群聊。"
        )
        msg = msg_template.format(user_name=user_name, user_id=user_id)
        await event.send(event.plain_result(msg))

    async def _check_answer(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        group_id = event.message_obj.group_id
        key = f"{group_id}:{user_id}"

        async with self._lock:
            state = self.user_states.get(key)
            if not state or "future" not in state:
                return
            if state.get("expire_time") and asyncio.get_event_loop().time() > state["expire_time"]:
                return

            correct_answer = state["current_answer"]
            user_input = event.message_str.strip()
            future = state.get("future")

            if isinstance(correct_answer, int):
                if not user_input.isdigit():
                    pass
                else:
                    answer = int(user_input)
                    if future and not future.done():
                        future.set_result(answer == correct_answer)
                    return
            else:
                if future and not future.done():
                    future.set_result(user_input == correct_answer)
                return

        if not user_input.isdigit():
            await event.send(event.plain_result("请输入数字答案"))

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def _handle_pass_command(self, event: AstrMessageEvent):
        if not event.message_obj.group_id:
            return
        
        msg = event.message_str.strip()
        pass_cmd = self.config.get("pass_command", "/pass")
        pass_cmd_variants: Set[str] = {pass_cmd, pass_cmd.lstrip('/')}
        
        if not any(msg.startswith(v) for v in pass_cmd_variants):
            return

        group_id = event.message_obj.group_id
        owner, admins = await self._get_group_owner_and_admins(event, group_id)
        sender = event.get_sender_id()
        is_admin = (owner == sender) or (sender in admins)
        if not is_admin:
            await event.send(event.plain_result("只有管理员或群主可以使用此命令"))
            return

        at_targets = [str(comp.qq) for comp in event.message_obj.message if isinstance(comp, At)]
        if not at_targets:
            detected_cmd = pass_cmd if msg.startswith(pass_cmd) else pass_cmd.lstrip('/')
            await event.send(event.plain_result(f"请指定要允许入群的用户，例如：{detected_cmd} @用户"))
            return

        target_id = at_targets[0]
        key = f"{group_id}:{target_id}"
        
        async with self._lock:
            state = self.user_states.get(key)
            if not state or not state.get("pending_decision"):
                await event.send(event.plain_result("该用户没有等待审批的验证请求"))
                return
            
            self.user_states.pop(key, None)
            task = self.secondary_tasks.pop(key, None)
            if task and not task.done():
                task.cancel()

        success_msg = self.config.get("pass_success_message", "已允许该用户入群")
        await event.send(event.plain_result(success_msg))
        
        try:
            await event.send(event.chain_result([At(qq=target_id), Plain(" 管理员已允许您入群")]))
        except Exception:
            pass

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def _handle_kick_command(self, event: AstrMessageEvent):
        if not event.message_obj.group_id:
            return
            
        msg = event.message_str.strip()
        kick_cmd = self.config.get("kick_command", "/kick")
        kick_cmd_variants: Set[str] = {kick_cmd, kick_cmd.lstrip('/')}
        
        if not any(msg.startswith(v) for v in kick_cmd_variants):
            return

        group_id = event.message_obj.group_id
        owner, admins = await self._get_group_owner_and_admins(event, group_id)
        sender = event.get_sender_id()
        is_admin = (owner == sender) or (sender in admins)
        if not is_admin:
            await event.send(event.plain_result("只有管理员或群主可以使用此命令"))
            return

        at_targets = [str(comp.qq) for comp in event.message_obj.message if isinstance(comp, At)]
        if not at_targets:
            detected_cmd = kick_cmd if msg.startswith(kick_cmd) else kick_cmd.lstrip('/')
            await event.send(event.plain_result(f"请指定要踢出的用户，例如：{detected_cmd} @用户"))
            return

        target_id = at_targets[0]
        key = f"{group_id}:{target_id}"
        
        async with self._lock:
            state = self.user_states.get(key)
            if state and state.get("pending_decision"):
                self.user_states.pop(key, None)
            task = self.secondary_tasks.pop(key, None)
            if task and not task.done():
                task.cancel()
                
        await self._kick_user(event, target_id)
        success_msg = self.config.get("kick_success_message", "已移出该用户")
        await event.send(event.plain_result(success_msg))

    async def _get_group_owner_and_admins(self, event: AstrMessageEvent, group_id: int) -> Tuple[Optional[str], List[str]]:
        try:
            result = await event.bot.api.call_action('get_group_member_list', group_id=group_id)
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

    async def _schedule_timeout_kick(self, event: AstrMessageEvent, user_id: str, group_id: int):
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
            task = asyncio.create_task(self._timeout_kick_process(event, user_id, group_id))
            task.set_name(f"wv_timeoutkick_{group_id}_{user_id}")
            self.timeout_kick_tasks[key] = task
            task.add_done_callback(lambda t, k=key: asyncio.create_task(self._clean_timeout_task(k)))

    async def _clean_timeout_task(self, key: str):
        await asyncio.sleep(0)
        async with self._lock:
            self.timeout_kick_tasks.pop(key, None)

    async def _timeout_kick_process(self, event: AstrMessageEvent, user_id: str, group_id: int):
        if not await self._check_bot_admin(event, group_id):
            await event.send(event.plain_result("机器人没有管理员权限，无法移出用户"))
            return

        delay = self.config.get("timeout_kick_delay", 30)
        warning_template = self.config.get(
            "timeout_kick_warning_message",
            "用户 {user_name} 验证失败，将在 {delay} 秒后被移出群聊。如需取消，请管理员发送：{cancel_command} @用户(有空格)"
        )

        user_name = "该成员"
        try:
            member_info = await event.bot.api.call_action('get_group_member_info',
                                                          group_id=group_id,
                                                          user_id=int(user_id))
            if member_info and isinstance(member_info, dict):
                user_name = member_info.get('nickname', user_name)
        except Exception:
            pass

        cancel_cmd = self.config.get("timeout_kick_cancel_command", "/cancel_kick").lstrip('/')
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

        if not await self._check_bot_admin(event, group_id):
            await event.send(event.plain_result("机器人没有管理员权限，无法移出用户"))
            return

        if not await self._is_member_in_group(event, group_id, user_id):
            logger.info(f"用户 {user_id} 已不在群 {group_id} 中，跳过踢人")
            return

        await self._kick_user(event, user_id)
        await event.send(event.plain_result(f"已移出用户 {user_name}"))

    async def _check_bot_admin(self, event: AstrMessageEvent, group_id: int) -> bool:
        try:
            bot_id = event.bot.self_id
            if not bot_id:
                return False
            result = await event.bot.api.call_action('get_group_member_info',
                                                     group_id=group_id,
                                                     user_id=bot_id)
            if not result or not isinstance(result, dict):
                return False
            role = result.get('role')
            return role in ['owner', 'admin']
        except Exception as e:
            logger.error(f"检查机器人权限失败: {e}")
            return False

    async def _check_cancel_command(self, event: AstrMessageEvent):
        if not event.message_obj.group_id:
            return

        msg = event.message_str.strip()
        cancel_cmd = self.config.get("timeout_kick_cancel_command", "/cancel_kick")
        cancel_cmd_variants: Set[str] = {cancel_cmd, cancel_cmd.lstrip('/')}
        
        if not any(msg.startswith(v) for v in cancel_cmd_variants):
            return

        group_id = event.message_obj.group_id
        owner, admins = await self._get_group_owner_and_admins(event, group_id)
        sender = event.get_sender_id()
        is_admin = (owner == sender) or (sender in admins)
        if not is_admin:
            await event.send(event.plain_result("只有管理员或群主可以取消踢人"))
            return

        at_targets = [str(comp.qq) for comp in event.message_obj.message if isinstance(comp, At)]
        if not at_targets:
            detected_cmd = cancel_cmd if msg.startswith(cancel_cmd) else cancel_cmd.lstrip('/')
            await event.send(event.plain_result(f"请指定要取消踢人的用户，例如：{detected_cmd} @用户"))
            return

        target_id = at_targets[0]
        key = f"{group_id}:{target_id}"
        async with self._lock:
            task = self.timeout_kick_tasks.get(key)
            if task and not task.done():
                task.cancel()
                await event.send(event.plain_result("已取消踢人操作"))
            else:
                await event.send(event.plain_result("该用户没有等待踢人的任务"))

    async def _kick_user(self, event: AstrMessageEvent, user_id: str):
        if event.get_platform_name() != "aiocqhttp":
            logger.warning(f"当前平台不支持踢人操作，无法移出用户 {user_id}")
            return

        group_id = event.message_obj.group_id
        if not group_id:
            logger.error("无法获取群ID，踢人失败")
            return

        try:
            await event.bot.api.call_action(
                'set_group_kick',
                group_id=group_id,
                user_id=int(user_id),
                reject_add_request=False
            )
            logger.info(f"已将用户 {user_id} 移出群 {group_id}")
        except Exception as e:
            logger.error(f"踢出用户失败: {e}")

    def _generate_question(self):
        operators = ['+', '-', '*']
        for _ in range(100):
            op1 = random.choice(operators)
            op2 = random.choice(operators)
            if op1 == '*' or op2 == '*':
                a = random.randint(1, 10)
                b = random.randint(1, 10)
                c = random.randint(1, 10)
            else:
                a = random.randint(0, 50)
                b = random.randint(0, 50)
                c = random.randint(0, 50)

            try:
                if op1 == '+':
                    part1 = a + b
                elif op1 == '-':
                    part1 = a - b
                else:
                    part1 = a * b

                if op2 == '+':
                    result = part1 + c
                elif op2 == '-':
                    result = part1 - c
                else:
                    result = part1 * c

                if 0 <= result <= 100:
                    expr = f"{a} {op1} {b} {op2} {c}"
                    return expr, result
            except:
                continue
        a = random.randint(0, 50)
        b = random.randint(0, 50)
        return f"{a} + {b}", a + b

    async def terminate(self):
        logger.info(f"开始清理插件 {self.name}")
        async with self._lock:
            for task in self.secondary_tasks.values():
                if not task.done():
                    task.cancel()
            self.secondary_tasks.clear()
            for task in self.timeout_kick_tasks.values():
                if not task.done():
                    task.cancel()
            self.timeout_kick_tasks.clear()
            for state in self.user_states.values():
                future = state.get("future")
                if future and not future.done():
                    future.cancel()
            self.user_states.clear()
        await asyncio.sleep(0.5)
        logger.info(f"插件 {self.name} 已清理")