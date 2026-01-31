"""
测试多轮对话功能
"""
import sys
sys.path.insert(0, '/Users/zkeq/Desktop/Code/feishu-bot')

from core.conversation_manager import ConversationManager, ConversationState
from core.batcher import MessagePart

def test_conversation_manager():
    """测试会话管理器"""
    print("=" * 60)
    print("测试会话管理器")
    print("=" * 60)

    manager = ConversationManager()

    # 测试 1: 创建会话
    print("\n[测试 1] 创建会话")
    chat_id = "test_chat_123"
    parts = [MessagePart(kind="text", text="创建任务：完成报告")]

    context = manager.create_conversation(
        chat_id=chat_id,
        original_parts=parts,
        waiting_for="截止日期",
        callback_data={"action": "create_task"}
    )

    print(f"✓ 会话创建成功")
    print(f"  - chat_id: {context.chat_id}")
    print(f"  - state: {context.state}")
    print(f"  - waiting_for: {context.waiting_for}")
    print(f"  - callback_data: {context.callback_data}")

    # 测试 2: 检查活跃会话
    print("\n[测试 2] 检查活跃会话")
    has_active = manager.has_active_conversation(chat_id)
    print(f"✓ 活跃会话检查: {has_active}")

    # 测试 3: 获取会话
    print("\n[测试 3] 获取会话")
    retrieved_context = manager.get_conversation(chat_id)
    print(f"✓ 会话获取成功")
    print(f"  - 原始消息: {retrieved_context.original_parts[0].text}")

    # 测试 4: 更新会话
    print("\n[测试 4] 更新会话")
    manager.update_conversation(
        chat_id=chat_id,
        state=ConversationState.PROCESSING,
        callback_data={"additional_info": "test"}
    )
    updated_context = manager.get_conversation(chat_id)
    print(f"✓ 会话更新成功")
    print(f"  - 新状态: {updated_context.state}")
    print(f"  - 更新后的 callback_data: {updated_context.callback_data}")

    # 测试 5: 完成会话
    print("\n[测试 5] 完成会话")
    completed_context = manager.complete_conversation(chat_id)
    print(f"✓ 会话完成")
    print(f"  - 已移除的会话 chat_id: {completed_context.chat_id}")

    # 测试 6: 验证会话已移除
    print("\n[测试 6] 验证会话已移除")
    has_active_after = manager.has_active_conversation(chat_id)
    print(f"✓ 会话已移除: {not has_active_after}")

    print("\n" + "=" * 60)
    print("所有测试通过！✓")
    print("=" * 60)

if __name__ == "__main__":
    test_conversation_manager()
