import random
import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import re

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import At, Plain, Image
from astrbot.core.star.star_tools import StarTools


@register("astrbot_plugin_welcome_verification", "Yueling", "入群欢迎与验证插件", "2.4.2")
class WelcomeVerificationPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.user_states: Dict[str, dict] = {}
        self.timeout_kick_tasks: Dict[str, asyncio.Task] = {}
        self.warning_tasks: Dict[str, asyncio.Task] = {}
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
        self._question_cache = self._generate_all_questions()
        self._check_platform_compatibility()

        logger.info("入群欢迎与验证插件已加载")

    def _check_platform_compatibility(self):
        try:
            platform_mgr = self.context.platform_manager
            adapters = platform_mgr.get_insts() if platform_mgr else []
            supported = False
            for adapter in adapters:
                adapter_type = getattr(adapter, 'type', None) or getattr(adapter, 'adapter_type', '')
                if 'aiocqhttp' in str(adapter_type).lower():
                    supported = True
                    break
            if not supported:
                logger.warning("当前未检测到 aiocqhttp 平台适配器，本插件仅支持 OneBot V11 协议")
        except Exception as e:
            logger.warning(f"平台兼容性检查失败: {e}")

    def _extract_number_from_text(self, text: str) -> Optional[Union[int, float]]:
        match = re.search(r'-?\d+(?:\.\d+)?', text.strip())
        if match:
            num_str = match.group()
            if '.' in num_str:
                return float(num_str)
            return int(num_str)
        return None

    def _normalize_text(self, text: str) -> str:
        normalized = re.sub(r'[^\w\u4e00-\u9fff]', '', text.lower())
        return normalized.strip()

    def _get_plain_text(self, event) -> str:
        text_parts = []
        for comp in event.message_obj.message:
            if isinstance(comp, Plain):
                text_parts.append(comp.text)
        return "".join(text_parts).strip()

    def _is_answer_match(self, user_input: str, correct_answer: Union[str, int, float]) -> bool:
        if isinstance(correct_answer, (int, float)):
            user_num = self._extract_number_from_text(user_input)
            if user_num is None:
                return False
            if isinstance(correct_answer, float):
                if user_num == 0 and correct_answer == 0:
                    return True
                relative_error = abs(user_num - correct_answer) / max(abs(user_num), abs(correct_answer), 1.0)
                return relative_error < 1e-6
            return user_num == correct_answer
        else:
            user_normalized = self._normalize_text(user_input)
            correct_normalized = self._normalize_text(str(correct_answer))
            return user_normalized == correct_normalized

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

    def _get_group_verification_enabled(self, group_id: str) -> bool:
        return self.group_configs.get(group_id, {}).get("verification_enabled", True)

    def _set_group_verification_enabled(self, group_id: str, enabled: bool):
        if group_id not in self.group_configs:
            self.group_configs[group_id] = {}
        self.group_configs[group_id]["verification_enabled"] = enabled
        self._save_group_configs()

    def _is_group_in_blacklist(self, group_id: str) -> bool:
        blacklist = self.config.get("verification_disabled_groups", [])
        return group_id in blacklist

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

    async def _get_question_for_group(self, group_id: int) -> Tuple[str, Union[str, int, float]]:
        bank_name = self._get_group_question_bank(str(group_id))
        if bank_name and bank_name in self.question_banks:
            bank = self.question_banks[bank_name]
            if bank:
                idx = random.randrange(len(bank))
                item = bank[idx]
                return item["question"], item["answer"]
        return self._generate_question()

    async def _handle_wv_command(self, event):
        msg = event.message_str.strip()
        if not msg.startswith("wv"):
            return
        if not event.message_obj.group_id:
            await event.send(event.plain_result("该命令仅在群聊中可用"))
            return

        parts = msg.split()
        if len(parts) < 2:
            help_text = (
                "入群验证管理命令：\n"
                "wv on - 开启本群入群验证\n"
                "wv off - 关闭本群入群验证\n"
                "wv ls - 查看可用题库\n"
                "wv <文件名> - 切换题库\n"
                "wv default - 恢复随机生成"
            )
            await event.send(event.plain_result(help_text))
            return

        subcmd = parts[1].lower()
        group_id = str(event.message_obj.group_id)
        sender_id = event.get_sender_id()

        owner, admins = await self._get_group_owner_and_admins(event, event.message_obj.group_id)
        is_admin = (owner == sender_id) or (sender_id in admins)

        if not is_admin and subcmd not in ["ls"]:
            await event.send(event.plain_result("只有管理员或群主可以使用此命令"))
            return

        if subcmd == "on":
            self._set_group_verification_enabled(group_id, True)
            await event.send(event.plain_result("已开启本群入群验证"))
        elif subcmd == "off":
            self._set_group_verification_enabled(group_id, False)
            await event.send(event.plain_result("已关闭本群入群验证"))
        elif subcmd == "ls":
            banks = list(self.question_banks.keys())
            if banks:
                msg = "可用题库：\n" + "\n".join(f"- {name} ({len(self.question_banks[name])}题)" for name in banks)
            else:
                msg = "没有发现题库文件，请将 JSON 格式的题库放入 data/plugin_data/welcome_verification/warehouse/"
            await event.send(event.plain_result(msg))
        elif subcmd == "default":
            self._set_group_question_bank(group_id, None)
            await event.send(event.plain_result("已恢复为随机生成题目"))
        else:
            bank_name = subcmd
            if not bank_name.endswith('.json'):
                bank_name += '.json'
            if bank_name not in self.question_banks:
                await event.send(event.plain_result(f"题库 {bank_name} 不存在"))
                return
            self._set_group_question_bank(group_id, bank_name)
            await event.send(event.plain_result(f"已切换题库为 {bank_name}，共 {len(self.question_banks[bank_name])} 道题"))

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_group_increase(self, event):
        if not self._is_group_increase(event):
            return

        raw = event.message_obj.raw_message
        if not isinstance(raw, dict):
            return
        
        user_id = raw.get('user_id')
        if not user_id:
            return
        user_id = str(user_id)
        
        group_id = event.message_obj.group_id
        if not group_id:
            return
        group_id_str = str(group_id)
        
        user_name = user_id
        try:
            member_info = await event.bot.api.call_action('get_group_member_info',
                                                          group_id=group_id,
                                                          user_id=int(user_id))
            if member_info and isinstance(member_info, dict):
                user_name = member_info.get('nickname', user_id)
        except Exception as e:
            logger.warning(f"获取新成员昵称失败: {e}")

        if self._is_group_in_blacklist(group_id_str):
            return

        if not self.config.get("enable_verification", True):
            return
        if not self._get_group_verification_enabled(group_id_str):
            return

        logger.info(f"新成员入群: {user_name}({user_id}) 进入群 {group_id}")

        key = f"{group_id}:{user_id}"
        async with self._lock:
            if key in self.user_states:
                return
            await self._cleanup_user_state(group_id, user_id)
            self.user_states[key] = {
                "group_id": group_id,
                "user_id": user_id,
                "user_name": user_name,
                "attempts": 0,
                "status": "pending",
            }

        await self._send_welcome(event, user_name, user_id)
        asyncio.create_task(self._start_verification(event, user_id, group_id))

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event):
        if not event.message_obj.group_id:
            return
        await self._handle_wv_command(event)
        await self._check_answer(event)
        await self._check_pass_command(event)
        await self._check_cancel_command(event)

    def _is_group_increase(self, event) -> bool:
        if event.get_platform_name() != "aiocqhttp":
            return False
        
        raw = event.message_obj.raw_message
        if not isinstance(raw, dict):
            return False
        
        if raw.get('post_type') == 'notice' and raw.get('notice_type') == 'group_increase':
            bot_id = str(getattr(event.bot, 'self_id', ''))
            user_id = str(raw.get('user_id', ''))
            return user_id != bot_id and user_id != ''
        return False

    async def _is_member_in_group(self, event, group_id: int, user_id: str) -> bool:
        for retry in range(3):
            try:
                result = await event.bot.api.call_action('get_group_member_list', group_id=group_id)
                if not result or not isinstance(result, list):
                    if retry < 2:
                        await asyncio.sleep(0.5)
                        continue
                    return False
                for member in result:
                    if str(member.get('user_id')) == user_id:
                        return True
                return False
            except Exception as e:
                logger.error(f"检查群成员存在性失败: {e}")
                if retry < 2:
                    await asyncio.sleep(0.5)
        return False

    async def _send_welcome(self, event, user_name: str, user_id: str):
        welcome_text = self.config.get("welcome_text", "欢迎 {user_name} 加入本群！").format(user_name=user_name)
        enable_image = self.config.get("enable_welcome_image", False)
        image_path = self.config.get("welcome_image", "")
        chain = [At(qq=user_id), Plain(" " + welcome_text)]
        if enable_image and image_path:
            if image_path.startswith(("http://", "https://")):
                chain.append(Image.fromURL(image_path))
            else:
                path = Path(image_path)
                if path.exists():
                    chain.append(Image.fromFileSystem(image_path))
                else:
                    logger.warning(f"欢迎图片不存在: {image_path}")
        await event.send(event.chain_result(chain))

    async def _start_verification(self, event, user_id: str, group_id: int):
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
                if key not in self.user_states:
                    self.user_states[key] = {}
                self.user_states[key].update({
                    "attempts": attempts,
                    "expire_time": expire_time,
                    "current_answer": answer,
                    "future": future,
                    "status": "verifying",
                    "is_secondary": False,
                })

            try:
                result = await asyncio.wait_for(future, timeout=timeout)

                async with self._lock:
                    if key in self.user_states:
                        self.user_states[key].pop("future", None)
                        if self.user_states[key].get("status") == "verifying":
                            self.user_states[key]["status"] = "completed"

                if result is True:
                    await event.send(event.plain_result(self.config.get("verification_correct_message", "验证通过，欢迎入群！")))
                    await self._cleanup_user_state(group_id, user_id)
                    return
                else:
                    attempts += 1
                    remaining = max_attempts - attempts
                    if remaining > 0:
                        msg = self.config.get("verification_failed_message", "答案错误，您还有 {remaining} 次机会").format(remaining=remaining)
                        await event.send(event.plain_result(msg))
                    else:
                        if self.config.get("secondary_verification_enabled", True):
                            await self._secondary_verification(event, user_id, group_id)
                        else:
                            await self._schedule_timeout_kick(event, user_id, group_id)
                        return

            except asyncio.TimeoutError:
                async with self._lock:
                    if key in self.user_states:
                        self.user_states[key].pop("future", None)

                attempts += 1
                remaining = max_attempts - attempts
                if remaining > 0:
                    await event.send(event.plain_result(f"验证超时，您还有 {remaining} 次机会"))
                else:
                    if self.config.get("secondary_verification_enabled", True):
                        await self._secondary_verification(event, user_id, group_id)
                    else:
                        await self._schedule_timeout_kick(event, user_id, group_id)
                    return

        await self._cleanup_user_state(group_id, user_id)

    async def _check_answer(self, event):
        user_id = event.get_sender_id()
        group_id = event.message_obj.group_id
        key = f"{group_id}:{user_id}"

        plain_text = self._get_plain_text(event)
        
        is_match = False

        async with self._lock:
            state = self.user_states.get(key)
            if not state or state.get("is_secondary") or state.get("status") != "verifying":
                return

            future = state.get("future")
            if not future or future.done():
                return

            if state.get("expire_time") and asyncio.get_event_loop().time() > state["expire_time"]:
                return

            correct = state["current_answer"]
            is_match = self._is_answer_match(plain_text, correct)

            if is_match:
                future.set_result(True)
                state["status"] = "completed"

    async def _secondary_verification(self, event, user_id: str, group_id: int):
        if not self.config.get("secondary_verification_enabled", True):
            await self._schedule_timeout_kick(event, user_id, group_id)
            return

        owner, admins = await self._get_group_owner_and_admins(event, group_id)
        if not owner and not admins:
            logger.warning(f"无法获取群 {group_id} 的管理员列表，允许用户通过")
            await event.send(event.plain_result("验证系统故障，已允许您入群"))
            await self._cleanup_user_state(group_id, user_id)
            return

        key = f"{group_id}:{user_id}"
        async with self._lock:
            state = self.user_states.get(key, {})
            user_name = state.get("user_name", "该成员")
            self.user_states[key]["status"] = "waiting_approval"
            self.user_states[key]["is_secondary"] = True

        at_list = []
        if owner:
            at_list.append(owner)
        at_list.extend(admins)
        at_mentions = [At(qq=uid) for uid in at_list]
        
        msg = (f" 用户 {user_name}({user_id}) 验证失败，请管理员决定是否允许入群\n"
               f"发送 /pass @{user_id} 同意入群，否则将在 {self.config.get('secondary_verification_timeout', 60)} 秒后移出")
        message_chain = at_mentions + [Plain(msg)]
        await event.send(event.chain_result(message_chain))

        timeout = self.config.get("secondary_verification_timeout", 60)
        
        async with self._lock:
            if key in self.user_states:
                self.user_states[key]["pass_future"] = asyncio.get_event_loop().create_future()
                self.user_states[key]["pass_expire"] = asyncio.get_event_loop().time() + timeout

        try:
            future = self.user_states[key]["pass_future"]
            await asyncio.wait_for(future, timeout=timeout)
            await event.send(event.plain_result(f"管理员已同意 {user_name} 入群"))
            await self._cleanup_user_state(group_id, user_id)
        except asyncio.TimeoutError:
            await event.send(event.plain_result(f"管理员未响应，将移出 {user_name}"))
            await self._kick_user(event, user_id)
            await self._cleanup_user_state(group_id, user_id)

    async def _check_pass_command(self, event):
        msg = event.message_str.strip()
        if not msg.startswith("/pass"):
            return
        
        group_id = event.message_obj.group_id
        if not group_id:
            return
        
        sender = event.get_sender_id()
        owner, admins = await self._get_group_owner_and_admins(event, group_id)
        is_admin = (owner == sender) or (sender in admins)
        
        if not is_admin:
            await event.send(event.plain_result("只有管理员或群主可以使用此命令"))
            return
        
        parts = msg.split()
        if len(parts) < 2:
            await event.send(event.plain_result("用法：/pass @用户"))
            return
        
        at_targets = [str(comp.qq) for comp in event.message_obj.message if isinstance(comp, At)]
        if not at_targets:
            await event.send(event.plain_result("请 @ 要允许入群的用户"))
            return
        
        target_id = at_targets[0]
        key = f"{group_id}:{target_id}"
        
        async with self._lock:
            state = self.user_states.get(key)
            if not state:
                await event.send(event.plain_result("该用户没有待处理的验证请求"))
                return
            
            if state.get("status") != "waiting_approval":
                await event.send(event.plain_result("该用户不在等待审批状态"))
                return
            
            future = state.get("pass_future")
            if future and not future.done():
                future.set_result(True)
                await event.send(event.plain_result(f"已允许用户入群"))
            else:
                await event.send(event.plain_result("该用户的审批已超时"))

    async def _get_group_owner_and_admins(self, event, group_id: int) -> Tuple[Optional[str], List[str]]:
        for retry in range(3):
            try:
                result = await event.bot.api.call_action('get_group_member_list', group_id=group_id)
                if not result or not isinstance(result, list):
                    if retry < 2:
                        await asyncio.sleep(0.5)
                        continue
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
                logger.error(f"获取群管理员列表失败: {e}")
                if retry < 2:
                    await asyncio.sleep(0.5)
        return None, []

    async def _schedule_timeout_kick(self, event, user_id: str, group_id: int):
        key = f"{group_id}:{user_id}"
        
        old_task = None
        async with self._lock:
            old_task = self.timeout_kick_tasks.get(key)
            if old_task and not old_task.done():
                old_task.cancel()
                self.timeout_kick_tasks.pop(key, None)
        
        if old_task and not old_task.done():
            try:
                await old_task
            except asyncio.CancelledError:
                pass
        
        task = asyncio.create_task(self._timeout_kick_process(event, user_id, group_id))
        async with self._lock:
            self.timeout_kick_tasks[key] = task

    async def _timeout_kick_process(self, event, user_id: str, group_id: int):
        key = f"{group_id}:{user_id}"
        try:
            if not await self._check_bot_admin(event, group_id):
                await event.send(event.plain_result("机器人没有管理员权限，无法移出用户"))
                return

            delay = self.config.get("timeout_kick_delay", 30)
            user_name = "该成员"
            try:
                member_info = await event.bot.api.call_action('get_group_member_info',
                                                              group_id=group_id,
                                                              user_id=int(user_id))
                if member_info and isinstance(member_info, dict):
                    user_name = member_info.get('nickname', user_name)
            except Exception:
                pass

            cancel_cmd = self.config.get("timeout_kick_cancel_command", "/cancel_kick")
            warning_msg = f"用户 {user_name} 验证失败，将在 {delay} 秒后被移出，如需取消请发送：{cancel_cmd} @{user_name}"
            await event.send(event.plain_result(warning_msg))

            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                await event.send(event.plain_result(f"已取消踢出 {user_name}"))
                return

            if not await self._check_bot_admin(event, group_id):
                await event.send(event.plain_result("机器人没有管理员权限，无法移出用户"))
                return

            if not await self._is_member_in_group(event, group_id, user_id):
                return

            await self._kick_user(event, user_id)
            await event.send(event.plain_result(f"已移出用户 {user_name}"))
        finally:
            async with self._lock:
                self.timeout_kick_tasks.pop(key, None)

    async def _check_bot_admin(self, event, group_id: int) -> bool:
        for retry in range(3):
            try:
                bot_id = event.bot.self_id
                if not bot_id:
                    return False
                result = await event.bot.api.call_action('get_group_member_info',
                                                         group_id=group_id,
                                                         user_id=bot_id)
                if not result or not isinstance(result, dict):
                    if retry < 2:
                        await asyncio.sleep(0.5)
                        continue
                    return False
                role = result.get('role')
                return role in ['owner', 'admin']
            except Exception as e:
                logger.error(f"检查机器人权限失败: {e}")
                if retry < 2:
                    await asyncio.sleep(0.5)
        return False

    async def _check_cancel_command(self, event):
        if not event.message_obj.group_id:
            return

        msg = event.message_str.strip()
        cancel_cmd = self.config.get("timeout_kick_cancel_command", "/cancel_kick")
        if not msg.startswith(cancel_cmd):
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
            await event.send(event.plain_result("请指定要取消踢人的用户，例如：/cancel_kick @用户"))
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

    async def _kick_user(self, event, user_id: str):
        if event.get_platform_name() != "aiocqhttp":
            logger.warning(f"当前平台不支持踢人操作")
            return

        group_id = event.message_obj.group_id
        if not group_id:
            return

        for retry in range(3):
            try:
                await event.bot.api.call_action('set_group_kick', group_id=group_id, user_id=int(user_id))
                logger.info(f"已将用户 {user_id} 移出群 {group_id}")
                return
            except Exception as e:
                logger.error(f"踢出用户失败: {e}")
                if retry < 2:
                    await asyncio.sleep(0.5)

    async def _cleanup_user_state(self, group_id: int, user_id: str):
        key = f"{group_id}:{user_id}"
        
        tasks_to_cancel = []
        async with self._lock:
            if key in self.timeout_kick_tasks:
                task = self.timeout_kick_tasks[key]
                if not task.done():
                    task.cancel()
                tasks_to_cancel.append(task)
                del self.timeout_kick_tasks[key]
            
            if key in self.warning_tasks:
                task = self.warning_tasks[key]
                if not task.done():
                    task.cancel()
                tasks_to_cancel.append(task)
                del self.warning_tasks[key]
            
            if key in self.user_states:
                state = self.user_states[key]
                future = state.get("future")
                if future and not future.done():
                    future.cancel()
                pass_future = state.get("pass_future")
                if pass_future and not pass_future.done():
                    pass_future.cancel()
            
            self.user_states.pop(key, None)
        
        for task in tasks_to_cancel:
            if task and not task.done():
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    def _generate_all_questions(self) -> List[Tuple[str, int]]:
        safe_questions = [
            (f"{a} + {b}", a + b)
            for a in range(0, 51)
            for b in range(0, 51)
            if 0 <= a + b <= 100
        ] + [
            (f"{a} - {b}", a - b)
            for a in range(0, 101)
            for b in range(0, 101)
            if 0 <= a - b <= 100
        ] + [
            (f"{a} * {b}", a * b)
            for a in range(0, 11)
            for b in range(0, 11)
            if 0 <= a * b <= 100
        ]

        two_step = []
        for a in range(0, 21):
            for b in range(0, 21):
                for c in range(0, 21):
                    if 0 <= a + b + c <= 100:
                        two_step.append((f"{a} + {b} + {c}", a + b + c))
                    if 0 <= a + b - c <= 100:
                        two_step.append((f"{a} + {b} - {c}", a + b - c))
                    if 0 <= a - b + c <= 100:
                        two_step.append((f"{a} - {b} + {c}", a - b + c))

        return safe_questions + two_step

    def _generate_question(self) -> Tuple[str, int]:
        return random.choice(self._question_cache)

    async def terminate(self):
        logger.info("正在清理验证插件...")
        keys_to_clean = []
        async with self._lock:
            keys_to_clean = list(self.user_states.keys())
        
        for key in keys_to_clean:
            parts = key.split(":", 1)
            if len(parts) == 2:
                try:
                    group_id = int(parts[0])
                    user_id = parts[1]
                    await self._cleanup_user_state(group_id, user_id)
                except ValueError:
                    continue
        logger.info("验证插件已清理完成")
