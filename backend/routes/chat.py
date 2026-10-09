"""对话持久化路由 — 实训对话和知识面板对话的存储与读取"""
from flask import Blueprint, request, jsonify
from database import db
from routes.auth import token_required
from models import ChatMessage, KnowledgeChat
from db_doris import log_chat_event

chat_bp = Blueprint('chat', __name__)


# ========== 实训对话 ==========

@chat_bp.route('/history/<int:subtask_id>', methods=['GET'])
@token_required
def get_chat_history(current_user, subtask_id):
    """获取某个子任务的实训对话历史"""
    messages = (
        ChatMessage.query
        .filter_by(student_id=current_user.id, subtask_id=subtask_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return jsonify({
        'messages': [{'role': m.role, 'content': m.content} for m in messages]
    })


@chat_bp.route('/save', methods=['POST'])
@token_required
def save_chat_message(current_user):
    """保存实训对话消息（每轮调用）"""
    data = request.get_json()
    subtask_id = data.get('subtask_id')
    role = data.get('role')        # 'user' or 'assistant'
    content = data.get('content', '')

    if not subtask_id or not role:
        return jsonify({'error': '缺少 subtask_id 或 role'}), 400

    msg = ChatMessage(
        student_id=current_user.id,
        subtask_id=subtask_id,
        role=role,
        content=content,
    )
    db.session.add(msg)
    db.session.commit()

    # Doris: 记录聊天事件
    try:
        from models import Subtask
        st = Subtask.query.get(subtask_id)
        log_chat_event(current_user.id, st.course_id if st else 0, subtask_id, role, content)
    except:
        pass

    return jsonify({'message': '保存成功'})


# ========== 知识面板对话（独立记忆体） ==========

@chat_bp.route('/knowledge/<int:subtask_id>', methods=['GET'])
@token_required
def get_knowledge_chats(current_user, subtask_id):
    """获取某个子任务的知识面板对话历史"""
    messages = (
        KnowledgeChat.query
        .filter_by(student_id=current_user.id, subtask_id=subtask_id)
        .order_by(KnowledgeChat.created_at.asc())
        .all()
    )
    return jsonify({
        'messages': [{'role': m.role, 'content': m.content} for m in messages]
    })


@chat_bp.route('/knowledge/save', methods=['POST'])
@token_required
def save_knowledge_chat(current_user):
    """保存知识面板对话消息"""
    data = request.get_json()
    subtask_id = data.get('subtask_id')
    role = data.get('role')
    content = data.get('content', '')

    if not subtask_id or not role:
        return jsonify({'error': '缺少 subtask_id 或 role'}), 400

    msg = KnowledgeChat(
        student_id=current_user.id,
        subtask_id=subtask_id,
        role=role,
        content=content,
    )
    db.session.add(msg)
    db.session.commit()

    return jsonify({'message': '保存成功'})
