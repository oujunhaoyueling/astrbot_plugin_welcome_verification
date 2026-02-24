import random
import asyncio
from typing import Dict, Optional

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import At, Plain, Image
from astrbot.core.utils.session_waiter import session_waiter, SessionController

@register("astrbot_plugin_welcome_verification", "YourName", "入群欢迎与验证插件", "1.0.0")
class WelcomeVerificationPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        # 存储每个用户的验证状态：{user_id: {"answer": int, "attempts": int, "group_id": str}}
        self.user_states: Dict[str, dict] = {}
        self._lock = asyncio.Lock()  # 用于保护user_states的并发访问

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_group_increase(self, event: AstrMessageEvent):
        """监听所有事件，筛选群成员增加事件"""
        if not self._is_group_increase(event):
            return

        platform = event.get_platform_name()
        if platform != "aiocqhttp":
            logger.warning(f"当前平台 {platform} 可能不支持入群事件和踢人操作，插件功能可能受限")
            # 如果希望在其他平台也尝试，可移除上述警告，但踢人功能可能失效

        user_id = event.get_sender_id()
        group_id = event.message_obj.group_id
        user_name = event.get_sender_name()

        logger.info(f"检测到新成员入群: {user_name}({user_id}) 进入群 {group_id}")

        # 发送欢迎消息（如果开启）
        await self._send_welcome(event, user_name)

        # 处理验证（如果开启）
        if self.config.get("enable_verification", True):
            await self._start_verification(event, user_id, group_id)

    def _is_group_increase(self, event: AstrMessageEvent) -> bool:
        """判断是否为群成员增加事件（目前仅支持aiocqhttp）"""
        if event.get_platform_name() != "aiocqhttp":
            return False
        raw = event.message_obj.raw_message
        if isinstance(raw, dict):
            if raw.get('post_type') == 'notice' and raw.get('notice_type') == 'group_increase':
                return True
        return False

    async def _send_welcome(self, event: AstrMessageEvent, user_name: str):
        """发送欢迎消息"""
        welcome_text = self.config.get("welcome_text", "欢迎 {user_name} 加入本群！").format(user_name=user_name)
        enable_image = self.config.get("enable_welcome_image", False)
        image_path = self.config.get("welcome_image", "")

        chain = [At(qq=event.get_sender_id()), Plain(" " + welcome_text)]

        if enable_image and image_path:
            if image_path.startswith(("http://", "https://")):
                chain.append(Image.fromURL(image_path))
            else:
                # 本地路径，需要确保AstrBot有权限访问
                chain.append(Image.fromFileSystem(image_path))

        await event.send(event.chain_result(chain))

    async def _start_verification(self, event: AstrMessageEvent, user_id: str, group_id: str):
        """启动验证流程"""
        # 生成计算题（两步以内，结果0-100）
        question, answer = self._generate_question()

        async with self._lock:
            self.user_states[user_id] = {
                "answer": answer,
                "attempts": 0,
                "group_id": group_id
            }

        # 发送验证问题（@用户）
        question_text = self.config.get("verification_question_format", "请回答：{question} = ?").format(question=question)
        await event.send(event.chain_result([At(qq=user_id), Plain(" " + question_text)]))

        # 启动会话等待用户回答
        try:
            await self._verification_session(event, user_id)
        except TimeoutError:
            # 超时未回答，按失败处理
            await self._handle_verification_failure(event, user_id, timeout=True)

    def _generate_question(self):
        """生��两步以内的计算题，结果在0-100之间"""
        ops = ['+', '-', '*']
        while True:
            op = random.choice(ops)
            if op == '+':
                a = random.randint(0, 50)
                b = random.randint(0, 50)
                result = a + b
                if result <= 100:
                    return f"{a} + {b}", result
            elif op == '-':
                a = random.randint(0, 100)
                b = random.randint(0, a)  # 确保非负
                result = a - b
                return f"{a} - {b}", result
            else:  # '*'
                a = random.randint(1, 10)
                b = random.randint(1, 10)
                result = a * b
                if result <= 100:
                    return f"{a} × {b}", result

    @session_waiter(timeout=300)  # 默认超时300秒，实际从配置读取
    async def _verification_session(self, controller: SessionController, event: AstrMessageEvent, user_id: str):
        """等待用户回答的会话处理器"""
        # 从配置获取实际超时时间
        timeout = self.config.get("verification_timeout", 300)
        max_attempts = self.config.get("verification_max_attempts", 3)

        # 检查用户是否还在状态中（可能已被清理）
        async with self._lock:
            state = self.user_states.get(user_id)
        if not state:
            controller.stop()
            return

        # 获取用户输入
        user_input = event.message_str.strip()
        if not user_input.isdigit():
            # 非数字输入，提示错误，但不计入次数
            await event.send(event.plain_result("请输入数字答案。"))
            controller.keep(timeout=timeout, reset_timeout=True)
            return

        answer = int(user_input)
        correct = state["answer"]

        if answer == correct:
            # 回答正确
            await event.send(event.plain_result(self.config.get("verification_correct_message", "验证通过，欢迎入群！")))
            async with self._lock:
                self.user_states.pop(user_id, None)
            controller.stop()
        else:
            # 回答错误
            async with self._lock:
                state["attempts"] += 1
                attempts = state["attempts"]
            remaining = max_attempts - attempts

            if remaining <= 0:
                # 超过最大次数，踢出
                await self._kick_user(event, user_id)
                await event.send(event.plain_result(self.config.get("verification_ban_message", "您已超过最大尝试次数，将被移出群聊。")))
                async with self._lock:
                    self.user_states.pop(user_id, None)
                controller.stop()
            else:
                # 提示剩余次数
                msg = self.config.get("verification_failed_message", "答案错误，您还有 {remaining} 次机会。").format(remaining=remaining)
                await event.send(event.plain_result(msg))
                # 重置超时，继续等待
                controller.keep(timeout=timeout, reset_timeout=True)

    async def _handle_verification_failure(self, event: AstrMessageEvent, user_id: str, timeout: bool = False):
        """处理验证失败（超时）"""
        async with self._lock:
            state = self.user_states.pop(user_id, None)
        if not state:
            return
        # 超时视为一次失败，直接踢出（或可根据配置决定是否给多次机会，这里简化为直接踢出）
        await self._kick_user(event, user_id)
        await event.send(event.plain_result("验证超时，您已被移出群聊。"))

    async def _kick_user(self, event: AstrMessageEvent, user_id: str):
        """调用平台API踢出用户"""
        if event.get_platform_name() != "aiocqhttp":
            logger.warning(f"当前平台不支持踢人操作，无法移出���户 {user_id}")
            return

        group_id = event.message_obj.group_id
        if not group_id:
            logger.error("无法获取群ID，踢人失败")
            return

        try:
            # 通过event.bot调用cqhttp API
            await event.bot.api.call_action(
                'set_group_kick',
                group_id=group_id,
                user_id=user_id,
                reject_add_request=False  # 允许再次加群
            )
            logger.info(f"已将用户 {user_id} 移出群 {group_id}")
        except Exception as e:
            logger.error(f"踢出用户失败: {e}")

    async def terminate(self):
        """插件卸载时清理状态"""
        self.user_states.clear()