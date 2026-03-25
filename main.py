import random
import asyncio
import json
import os
from typing import Dict, List, Optional, Tuple

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import At, Plain, Image

try:
    from astrbot.core import DATA_DIR as CORE_DATA_DIR
except ImportError:
    CORE_DATA_DIR = None

@register("astrbot_plugin_welcome_verification", "YourName", "入群欢迎与验证插件", "2.0.0")
class WelcomeVerificationPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.user_states: Dict[str, dict] = {}
        self.secondary_tasks: Dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

        # 确定数据根目录
        if CORE_DATA_DIR and os.path.exists(CORE_DATA_DIR):
            data_root = CORE_DATA_DIR
        elif hasattr(context, 'data_dir') and context.data_dir:
            data_root = context.data_dir
        else:
            data_root = os.path.join(os.path.dirname(__file__), 'data')
            logger.warning(f"未找到 AstrBot 数据目录，将使用插件自身目录下的 data 文件夹: {data_root}")

        self.data_dir = os.path.join(data_root, "welcome_verification")
        self.warehouse_dir = os.path.join(self.data_dir, "warehouse")
        self.config_file = os.path.join(self.data_dir, "group_config.json")

        try:
            os.makedirs(self.data_dir, exist_ok=True)
            os.makedirs(self.warehouse_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"创建数据目录失败: {e}，插件将无法持久化数据")

        self.question_banks: Dict[str, List[dict]] = {}
        self.group_configs: Dict[str, dict] = {}
        self._load_group_configs()
        self._load_all_question_banks()

    def _load_group_configs(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.group_configs = json.load(f)
            else:
                self.group_configs = {}
        except Exception as e:
            logger.error(f"加载群配置失败: {e}")
            self.group_configs = {}

    def _save_group_configs(self):
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.group_configs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存群配置失败: {e}")

    def _load_all_question_banks(self):
        if not os.path.exists(self.warehouse_dir):
            return
        for filename in os.listdir(self.warehouse_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.warehouse_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, list) and all('question' in item and 'answer' in item for item in data):
                            self.question_banks[filename] = data
                            logger.info(f"加载题库 {filename}，共 {len(data)} 题")
                        else:
                            logger.warning(f"题库 {filename} 格式错误，跳过")
                except Exception as e:
                    logger.error(f"加载题库 {filename} 失败: {e}")

    def _get_group_question_bank(self, group_id: str) -> Optional[str]:
        return self.group_configs.get(str(group_id), {}).get("question_bank")

    def _set_group_question_bank(self, group_id: str, bank_name: Optional[str]):
        gid = str(group_id)
        if gid not in self.group_configs:
            self.group_configs[gid] = {}
        self.group_configs[gid]["question_bank"] = bank_name
        self._save_group_configs()

    async def _get_question_for_group(self, group_id: int) -> Tuple[str, int]:
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
            await event.send(event.plain_result("该命令仅在群聊中可用。"))
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
                msg = "没有发现任何题库文件，请将 JSON 格式的题库放入 data/welcome_verification/warehouse/ 文件夹。"
            await event.send(event.plain_result(msg))
            return

        elif subcmd == "default":
            if not is_admin:
                await event.send(event.plain_result("只有管理员或群主可以切换题库。"))
                return
            self._set_group_question_bank(group_id, None)
            await event.send(event.plain_result("已恢复为随机生成题目。"))
            return

        else:
            if not is_admin:
                await event.send(event.plain_result("只有管理员或群主可以切换题库。"))
                return
            bank_name = subcmd
            if not bank_name.endswith('.json'):
                bank_name += '.json'
            if bank_name not in self.question_banks:
                await event.send(event.plain_result(f"题库 {bank_name} 不存在，请使用 wv ls 查看可用题库。"))
                return
            self._set_group_question_bank(group_id, bank_name)
            await event.send(event.plain_result(f"已切换题库为 {bank_name}，共 {len(self.question_banks[bank_name])} 道题。"))
            return

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_group_increase(self, event: AstrMessageEvent):
        if not self._is_group_increase(event):
            return
        user_id = event.get_sender_id()
        group_id = event.message_obj.group_id
        user_name = event.get_sender_name()
        logger.info(f"新成员入群: {user_name}({user_id}) 进入群 {group_id}")
        await self._send_welcome(event, user_name)
        if self.config.get("enable_verification", True):
            await self._start_verification(event, user_id, group_id)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        if not event.message_obj.group_id:
            return
        await self._handle_wv_command(event)
        await self._check_answer(event)
        await self._check_secondary_answer(event)

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

    async def _start_verification(self, event: AstrMessageEvent, user_id: str, group_id: str):
        max_attempts = self.config.get("verification_max_attempts", 3)
        timeout = self.config.get("verification_timeout", 300)
        attempts = 0
        while attempts < max_attempts:
            question, answer = await self._get_question_for_group(group_id)
            question_text = self.config.get("verification_question_format", "请回答：{question} = ?").format(question=question)
            await event.send(event.chain_result([At(qq=user_id), Plain(" " + question_text)]))

            future = asyncio.get_event_loop().create_future()
            expire_time = asyncio.get_event_loop().time() + timeout
            async with self._lock:
                self.user_states[user_id] = {
                    "group_id": group_id,
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
                        self.user_states.pop(user_id, None)
                    return
                else:
                    attempts += 1
                    remaining = max_attempts - attempts
                    if remaining > 0:
                        msg = self.config.get("verification_failed_message", "答案错误，您还有 {remaining} 次机会。").format(remaining=remaining)
                        await event.send(event.plain_result(msg))
                    else:
                        await self._secondary_verification(event, user_id, group_id)
                        return
            except asyncio.TimeoutError:
                attempts += 1
                remaining = max_attempts - attempts
                if remaining > 0:
                    await event.send(event.plain_result(f"验证超时，您还有 {remaining} 次机会。"))
                else:
                    await self._secondary_verification(event, user_id, group_id)
                    return
            finally:
                async with self._lock:
                    if user_id in self.user_states:
                        self.user_states[user_id].pop("future", None)

    async def _check_answer(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        async with self._lock:
            state = self.user_states.get(user_id)
            if not state or "future" not in state:
                return
            if state.get("expire_time") and asyncio.get_event_loop().time() > state["expire_time"]:
                return
            user_input = event.message_str.strip()
            if not user_input.isdigit():
                await event.send(event.plain_result("请输入数字答案。"))
                return
            answer = int(user_input)
            correct = state["current_answer"]
            future = state.get("future")
            if future and not future.done():
                future.set_result(answer == correct)

    async def _secondary_verification(self, event: AstrMessageEvent, user_id: str, group_id: str):
        if not self.config.get("secondary_verification_enabled", True):
            await self._kick_user(event, user_id)
            await event.send(event.plain_result(self.config.get("verification_ban_message", "您已超过最大尝试次数，将被移出群聊。")))
            async with self._lock:
                self.user_states.pop(user_id, None)
            return

        owner, admins = await self._get_group_owner_and_admins(event, group_id)
        if not owner and not admins:
            logger.warning(f"无法获取群 {group_id} 的管理员/群主，直接踢出用户 {user_id}")
            await self._kick_user(event, user_id)
            return

        question, answer = await self._get_question_for_group(group_id)
        question_text = self.config.get("secondary_verification_question", "请 @{user_name} 并回答：{question} = ?").format(
            user_name=event.get_sender_name(), question=question
        )
        at_list = []
        if owner:
            at_list.append(owner)
        at_list.extend(admins)
        at_mentions = [At(qq=uid) for uid in at_list]
        message_chain = at_mentions + [Plain(f" {question_text}")]
        await event.send(event.chain_result(message_chain))

        future = asyncio.get_event_loop().create_future()
        timeout = self.config.get("secondary_verification_timeout", 60)
        async with self._lock:
            self.user_states[user_id] = {
                "group_id": group_id,
                "secondary_answer": answer,
                "secondary_future": future,
                "secondary_expire": asyncio.get_event_loop().time() + timeout
            }
        try:
            is_correct = await asyncio.wait_for(future, timeout)
            if is_correct:
                await event.send(event.plain_result(self.config.get("secondary_verification_correct_message", "二级验证通过，欢迎入群！")))
                async with self._lock:
                    self.user_states.pop(user_id, None)
                return
        except asyncio.TimeoutError:
            await event.send(event.plain_result(self.config.get("secondary_verification_failed_message", "二级验证超时，将通知管理员。")))
        finally:
            async with self._lock:
                if user_id in self.user_states:
                    self.user_states[user_id].pop("secondary_future", None)
                if user_id in self.user_states and "secondary_future" not in self.user_states[user_id]:
                    self.user_states.pop(user_id, None)

        check_interval = self.config.get("warning_check_interval", 10)
        max_notifications = self.config.get("warning_cycle_max", 10)
        task = asyncio.create_task(self._warning_loop(event, user_id, group_id, owner, admins, check_interval, max_notifications))
        async with self._lock:
            self.secondary_tasks[user_id] = task

    async def _check_secondary_answer(self, event: AstrMessageEvent):
        group_id = event.message_obj.group_id
        at_targets = [comp.qq for comp in event.message_obj.message if isinstance(comp, At)]

        async with self._lock:
            target_user_id = None
            target_state = None
            for uid, state in self.user_states.items():
                if state.get("group_id") == group_id and "secondary_future" in state and uid in at_targets:
                    target_user_id = uid
                    target_state = state
                    break
            if not target_state:
                return
            correct = target_state["secondary_answer"]
            future = target_state.get("secondary_future")

        owner, admins = await self._get_group_owner_and_admins(event, group_id)
        sender = event.get_sender_id()
        is_authorized = (owner == sender) or (sender in admins)
        if not is_authorized:
            await event.send(event.plain_result("只有管理员或群主可以参与二级验证。"))
            return

        user_input = event.message_str.strip()
        if not user_input.isdigit():
            await event.send(event.plain_result("请输入数字答案。"))
            return
        answer = int(user_input)
        if future and not future.done():
            if answer == correct:
                future.set_result(True)
            else:
                await event.send(event.plain_result("答案错误，请管理员或群主再次尝试。"))

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

    async def _warning_loop(self, event: AstrMessageEvent, user_id: str, group_id: int,
                           owner: Optional[str], admins: List[str],
                           check_interval: int, max_notifications: int):
        if owner:
            await self._send_warning_private(event, owner, user_id, group_id, is_owner=True)
            await asyncio.sleep(check_interval)
            if not await self._is_member_in_group(event, group_id, user_id):
                logger.info(f"用户 {user_id} 已被移出，停止警告循环")
                return

        notified_admins = set()
        notifications_sent = 0
        while notifications_sent < max_notifications:
            available = [aid for aid in admins if aid not in notified_admins]
            if not available:
                notified_admins.clear()
                available = admins[:]
            chosen = random.choice(available)
            notified_admins.add(chosen)
            await self._send_warning_private(event, chosen, user_id, group_id, is_owner=False)
            notifications_sent += 1
            await asyncio.sleep(check_interval)
            if not await self._is_member_in_group(event, group_id, user_id):
                logger.info(f"用户 {user_id} 已被移出，停止警告循环")
                return

    async def _send_warning_private(self, event: AstrMessageEvent, target_id: str,
                                   user_id: str, group_id: int, is_owner: bool):
        try:
            group_name = "该群"
            try:
                group_info = await event.bot.api.call_action('get_group_info', group_id=group_id)
                if group_info and isinstance(group_info, dict):
                    group_name = group_info.get('group_name', group_name)
            except:
                pass

            user_name = "新成员"
            try:
                member_info = await event.bot.api.call_action('get_group_member_info',
                                                              group_id=group_id,
                                                              user_id=user_id)
                if member_info and isinstance(member_info, dict):
                    user_name = member_info.get('nickname', user_name)
            except:
                pass

            if is_owner:
                msg_template = self.config.get("warning_owner_message",
                                               "【风险提示】群内有新成员 {user_name}({user_id}) 未通过验证，请处理。")
                message = msg_template.format(user_name=user_name, user_id=user_id, group_name=group_name)
            else:
                msg_template = self.config.get("warning_admin_message",
                                               "【风险提示】群 {group_name} 内有新成员 {user_name}({user_id}) 未通过验证，请处理。")
                message = msg_template.format(user_name=user_name, user_id=user_id, group_name=group_name)

            await event.bot.api.call_action('send_private_msg',
                                            user_id=int(target_id),
                                            message=message)
            logger.info(f"已发送警告私信给 {'群主' if is_owner else '管理员'} {target_id} 关于用户 {user_id}")
        except Exception as e:
            logger.error(f"发送私信警告失败: {e}")

    def _generate_question(self):
        operators = ['+', '-', '*']
        for _ in range(100):
            op1 = random.choice(operators)
            op2 = random.choice(operators)
            if op1 == '*' or op2 == '*':
                a, b, c = random.randint(1, 10), random.randint(1, 10), random.randint(1, 10)
            else:
                a, b, c = random.randint(0, 50), random.randint(0, 50), random.randint(0, 50)
            expr = f"{a} {op1} {b} {op2} {c}"
            try:
                result = eval(expr)
                if 0 <= result <= 100 and isinstance(result, int):
                    return expr, result
            except:
                continue
        a, b = random.randint(0, 50), random.randint(0, 50)
        return f"{a} + {b}", a + b

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
                user_id=user_id,
                reject_add_request=False
            )
            logger.info(f"已将用户 {user_id} 移出群 {group_id}")
        except Exception as e:
            logger.error(f"踢出用户失败: {e}")

    async def terminate(self):
        async with self._lock:
            for state in self.user_states.values():
                future = state.get("future")
                if future and not future.done():
                    future.cancel()
                sec_future = state.get("secondary_future")
                if sec_future and not sec_future.done():
                    sec_future.cancel()
            self.user_states.clear()
            for task in self.secondary_tasks.values():
                if not task.done():
                    task.cancel()
            self.secondary_tasks.clear()