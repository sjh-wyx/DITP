"""课程路由 — 完整实现"""
from flask import Blueprint, request, jsonify
from database import db
from models import Course, Subtask, ClassCourse, TaskProgress
from routes.auth import token_required, teacher_required
import json

courses_bp = Blueprint('courses', __name__)


def admin_required(f):
    """装饰器：仅 admin 可访问"""
    from functools import wraps
    @wraps(f)
    @token_required
    def decorated(current_user, *args, **kwargs):
        if current_user.role != 'admin':
            return jsonify({'error': '仅管理员可操作'}), 403
        return f(current_user, *args, **kwargs)
    return decorated


def _generate_course_code(course_id):
    return f'COURSE-{course_id:04d}'


@courses_bp.route('', methods=['GET'])
@token_required
def list_courses(current_user):
    """获取课程列表：admin 看全部；教师看自己创建 + 全站公开；学生看公开课"""
    from models import User
    if current_user.role == 'admin':
        courses = Course.query.all()
    elif current_user.role == 'teacher':
        # 归属权限：教师仅能查看自己创建的课程或全站公开(1)的课程
        courses = Course.query.filter(
            db.or_(Course.teacher_id == current_user.id, Course.is_public == 1)
        ).all()
    else:
        courses = Course.query.filter_by(is_public=True).all()

    # 课程创建者姓名映射（用于分配弹窗归属标识展示）
    creator_ids = {c.teacher_id for c in courses}
    creators = {u.id: (u.display_name or u.username) for u in User.query.filter(User.id.in_(creator_ids)).all()} if creator_ids else {}

    result = []
    for c in courses:
        total = len(c.subtasks) if c.subtasks else 0
        completed = TaskProgress.query.filter_by(
            student_id=current_user.id,
            status='completed'
        ).join(Subtask, TaskProgress.subtask_id == Subtask.id).filter(
            Subtask.course_id == c.id
        ).count() if total > 0 else 0
        pct = round((completed / total) * 100) if total > 0 else 0
        result.append({
            'id': c.id,
            'name': c.name,
            'description': c.description,
            'is_public': c.is_public,
            'teacher_id': c.teacher_id,
            'teacher_name': creators.get(c.teacher_id, ''),
            'course_code': c.course_code or '',
            'subtask_count': total,
            'progress_percent': pct,
        })
    return jsonify(result)


@courses_bp.route('/class/<int:class_id>', methods=['GET'])
@token_required
def get_class_courses(current_user, class_id):
    """获取某班级下的所有课程"""
    from models import ClassCourse
    cc = ClassCourse.query.filter_by(class_id=class_id).all()
    course_ids = [c.course_id for c in cc]
    courses = Course.query.filter(Course.id.in_(course_ids)).all() if course_ids else []
    result = []
    for c in courses:
        total = len(c.subtasks) if c.subtasks else 0
        completed = TaskProgress.query.filter_by(
            student_id=current_user.id,
            status='completed'
        ).join(Subtask, TaskProgress.subtask_id == Subtask.id).filter(
            Subtask.course_id == c.id
        ).count() if total > 0 else 0
        pct = round((completed / total) * 100) if total > 0 else 0
        result.append({
            'id': c.id, 'name': c.name, 'description': c.description,
            'is_public': c.is_public,
            'subtask_count': total,
            'progress_percent': pct,
        })
    return jsonify({'courses': result})


@courses_bp.route('/<int:course_id>', methods=['GET'])
@token_required
def get_course(current_user, course_id):
    """获取课程详情"""
    course = Course.query.get_or_404(course_id)
    return jsonify({
        'id': course.id,
        'name': course.name,
        'description': course.description,
        'is_public': course.is_public,
        'teacher_id': course.teacher_id,
    })


@courses_bp.route('', methods=['POST'])
@teacher_required
def create_course(current_user):
    """创建课程"""
    data = request.get_json()
    # 公开状态：admin 创建直接公开(1)；教师勾选「全站公开」则进入待审核(2)；否则私有(0)
    if current_user.role == 'admin':
        is_public = 1
    elif data.get('is_public'):
        is_public = 2  # 待审核，等待管理员审批
    else:
        is_public = 0
    course = Course(
        teacher_id=current_user.id,
        name=data['name'],
        description=data.get('description', ''),
        is_public=is_public,
    )
    db.session.add(course)
    db.session.flush()  # 获取 ID
    course.course_code = _generate_course_code(course.id)
    db.session.commit()
    # admin 创建的公开课自动分配给所有教师
    if is_public == 1:
        from models import CourseClass
        all_classes = CourseClass.query.all()
        for cls in all_classes:
            if not ClassCourse.query.filter_by(class_id=cls.id, course_id=course.id).first():
                db.session.add(ClassCourse(class_id=cls.id, course_id=course.id))
        db.session.commit()
    # 如果有提交子任务，一并创建
    subtasks_data = data.get('subtasks', [])
    for i, st in enumerate(subtasks_data):
        if isinstance(st, dict) and st.get('name'):
            db.session.add(Subtask(
                course_id=course.id,
                order_index=i,
                name=st['name'],
                command=st.get('command', ''),
                expected_output=st.get('expected_output', ''),
                # AI 返回的 description 映射到 knowledge_text（知识点）字段
                knowledge_text=st.get('knowledge_text', '') or st.get('description', ''),
            ))
    db.session.commit()
    return jsonify({'id': course.id, 'course_code': course.course_code, 'message': '课程创建成功'}), 201


@courses_bp.route('/<int:course_id>', methods=['PUT'])
@teacher_required
def update_course(current_user, course_id):
    """编辑课程"""
    course = Course.query.get_or_404(course_id)
    # 管理员可以修改任何课程；教师只能修改自己创建的课程
    if current_user.role != 'admin' and course.teacher_id != current_user.id:
        return jsonify({'error': '无权操作'}), 403
    data = request.get_json()
    course.name = data.get('name', course.name)
    course.description = data.get('description', course.description)
    if 'is_public' in data:
        course.is_public = data['is_public']
    db.session.commit()
    return jsonify({'message': '课程已更新'})


@courses_bp.route('/<int:course_id>', methods=['DELETE'])
@teacher_required
def delete_course(current_user, course_id):
    """删除课程（级联清理关联数据）"""
    course = Course.query.get_or_404(course_id)
    # 管理员可以删除任何课程；教师只能删除自己创建的课程
    if current_user.role != 'admin' and course.teacher_id != current_user.id:
        return jsonify({'error': '无权操作'}), 403

    from models import Subtask, TaskProgress, ChatMessage, KnowledgeChat, CourseClass, ClassStudent, Report, ClassCourse
    st_ids = [s.id for s in Subtask.query.filter_by(course_id=course_id).all()]
    if st_ids:
        TaskProgress.query.filter(TaskProgress.subtask_id.in_(st_ids)).delete(synchronize_session=False)
        ChatMessage.query.filter(ChatMessage.subtask_id.in_(st_ids)).delete(synchronize_session=False)
        KnowledgeChat.query.filter(KnowledgeChat.subtask_id.in_(st_ids)).delete(synchronize_session=False)
    Subtask.query.filter_by(course_id=course_id).delete()
    # ClassCourse 才是 班级-课程 多对多关联表（包含 course_id 列）
    # CourseClass 是"班级"实体（classes 表），无 course_id 列，之前误用会导致 DELETE 500
    ClassCourse.query.filter_by(course_id=course_id).delete()
    Report.query.filter_by(course_id=course_id).delete()
    db.session.delete(course)
    db.session.commit()
    return jsonify({'message': '课程已删除'})


@courses_bp.route('/<int:course_id>/subtasks', methods=['GET'])
@token_required
def get_subtasks(current_user, course_id):
    """获取课程的子任务列表"""
    course = Course.query.get_or_404(course_id)
    return jsonify({
        'subtasks': [{
            'id': s.id,
            'name': s.name,
            'command': s.command,
            'expected_output': s.expected_output,
            'knowledge_text': s.knowledge_text,
            'order_index': s.order_index,
        } for s in sorted(course.subtasks, key=lambda x: x.order_index)]
    })


@courses_bp.route('/<int:course_id>/subtasks', methods=['POST'])
@teacher_required
def save_subtasks(current_user, course_id):
    """批量保存子任务（替换当前课程所有子任务）"""
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        return jsonify({'error': '无权操作'}), 403
    data = request.get_json()
    subtask_list = data.get('subtasks', [])

    # 删除旧子任务及进度记录和聊天历史
    from models import TaskProgress, ChatMessage
    old_ids = [s.id for s in Subtask.query.filter_by(course_id=course_id).all()]
    if old_ids:
        TaskProgress.query.filter(TaskProgress.subtask_id.in_(old_ids)).delete()
        ChatMessage.query.filter(ChatMessage.subtask_id.in_(old_ids)).delete()
    Subtask.query.filter_by(course_id=course_id).delete()

    # 插入新子任务
    for i, st in enumerate(subtask_list):
        s = Subtask(
            course_id=course_id,
            order_index=i,
            name=st.get('name', ''),
            command=st.get('command', ''),
            expected_output=st.get('expected_output', ''),
            knowledge_text=st.get('knowledge_text', ''),
        )
        db.session.add(s)
    db.session.commit()
    return jsonify({'message': f'已保存 {len(subtask_list)} 个子任务'})


import os as _os
COURSE_UPLOAD_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), 'uploads')

@courses_bp.route('/<int:course_id>/files', methods=['POST'])
@token_required
def upload_course_file(current_user, course_id):
    """上传课程文件（CSV/数据文件等），AI 会读到此文件信息"""
    course = Course.query.get_or_404(course_id)
    if 'file' not in request.files:
        return jsonify({'error': '请选择文件'}), 400
    f = request.files['file']
    if f.filename == '':
        return jsonify({'error': '文件名为空'}), 400
    course_dir = _os.path.join(COURSE_UPLOAD_DIR, str(course_id))
    _os.makedirs(course_dir, exist_ok=True)
    save_path = _os.path.join(course_dir, f.filename)
    f.save(save_path)
    # 尝试读取前几行做预览
    try:
        with open(save_path, 'r', encoding='utf-8') as pf:
            preview = ''.join(pf.readline() for _ in range(11))  # 表头+前10行
    except Exception:
        preview = ''
    return jsonify({
        'filename': f.filename,
        'size': _os.path.getsize(save_path),
        'path': save_path,
        'preview': preview[:200],
        'message': '上传成功，学生实训时 AI 可读取此文件'
    })

@courses_bp.route('/<int:course_id>/files', methods=['GET'])
@token_required
def list_course_files(current_user, course_id):
    """列出课程上传的文件"""
    Course.query.get_or_404(course_id)
    course_dir = _os.path.join(COURSE_UPLOAD_DIR, str(course_id))
    if not _os.path.exists(course_dir):
        return jsonify({'files': []})
    files = []
    for fn in _os.listdir(course_dir):
        fp = _os.path.join(course_dir, fn)
        if _os.path.isfile(fp):
            files.append({'filename': fn, 'size': _os.path.getsize(fp)})
    return jsonify({'files': files})


@courses_bp.route('/<int:course_id>/files/<path:filename>/download', methods=['GET'])
@token_required
def download_course_file(current_user, course_id, filename):
    """下载课程文件（支持 query token）"""
    Course.query.get_or_404(course_id)
    from flask import send_file, request
    # 也支持 ?token=xxx 方式（<a> 标签下载用）
    filepath = _os.path.join(COURSE_UPLOAD_DIR, str(course_id), filename)
    if not _os.path.exists(filepath):
        return jsonify({'error': '文件不存在'}), 404
    return send_file(filepath, as_attachment=True, download_name=filename)



@courses_bp.route('/<int:course_id>/files/<path:filename>/raw', methods=['GET'])
def raw_download_course_file(course_id, filename):
    from flask import request, send_file
    client_ip = request.remote_addr or ''
    if not (client_ip.startswith('172.17.') or client_ip == '127.0.0.1'):
        return jsonify({'error': 'forbidden'}), 403
    Course.query.get_or_404(course_id)
    filepath = _os.path.join(COURSE_UPLOAD_DIR, str(course_id), filename)
    if not _os.path.exists(filepath):
        return jsonify({'error': 'file not found'}), 404
    return send_file(filepath, as_attachment=True, download_name=filename)


def get_course_files_for_ai(course_id):
    """获取课程文件信息，供 AI 上下文使用"""
    course_dir = _os.path.join(COURSE_UPLOAD_DIR, str(course_id))
    if not _os.path.exists(course_dir):
        return ''
    lines = []
    for fn in sorted(_os.listdir(course_dir)):
        fp = _os.path.join(course_dir, fn)
        if _os.path.isfile(fp):
            size_kb = _os.path.getsize(fp) / 1024
            try:
                with open(fp, 'r', encoding='utf-8') as pf:
                    header = pf.readline().strip()[:120]
                    sample_rows = [pf.readline().strip()[:120] for _ in range(10) if pf.readline().strip()]
                    sample = header + '\n' + '\n'.join(sample_rows[:10])
            except Exception:
                sample = '(无法读取)'
            lines.append(f'  📄 {fn} ({size_kb:.0f}KB)\n{sample[:600]}')
    if lines:
        return '可用数据文件：\n' + '\n'.join(lines)
    return ''


# ===== 公开课程 & 审核 =====

@courses_bp.route('/public', methods=['GET'])
@token_required
def search_public_courses(current_user):
    """搜索公开课程（按course_code/name）"""
    q = request.args.get('q', '')
    query = Course.query.filter(Course.is_public == 1)
    if q:
        query = query.filter(
            db.or_(Course.course_code.like(f'%{q}%'), Course.name.like(f'%{q}%'))
        )
    courses = query.limit(20).all()
    return jsonify({'courses': [{
        'id': c.id, 'name': c.name, 'course_code': c.course_code,
        'teacher_id': c.teacher_id, 'description': c.description,
        'subtask_count': len(c.subtasks) if c.subtasks else 0
    } for c in courses]})


@courses_bp.route('/<int:course_id>/apply-public', methods=['POST'])
@teacher_required
def apply_public(current_user, course_id):
    """教师申请课程全站公开"""
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        return jsonify({'error': '只能申请自己的课程'}), 403
    course.is_public = 2  # 待审核
    db.session.commit()
    return jsonify({'message': '已提交审核，等待管理员审批'})


@courses_bp.route('/admin/pending', methods=['GET'])
@admin_required
def pending_courses(current_user):
    """管理员查看待审核课程（附教师姓名/工号，便于审核）"""
    from models import User
    courses = Course.query.filter_by(is_public=2).all()
    result = []
    for c in courses:
        teacher = User.query.get(c.teacher_id)
        result.append({
            'id': c.id, 'name': c.name,
            'teacher_uid': c.teacher_id,                        # 创建者 User.id
            'teacher_name': (teacher.display_name or teacher.username) if teacher else '',  # 创建者姓名
            'teacher_no': (teacher.teacher_id or '') if teacher else '',                      # 创建者工号
            'course_code': c.course_code, 'description': c.description,
            'subtask_count': len(c.subtasks) if c.subtasks else 0
        })
    return jsonify({'courses': result})


@courses_bp.route('/admin/approve/<int:course_id>', methods=['POST'])
@admin_required
def approve_course(current_user, course_id):
    """管理员通过课程公开申请"""
    course = Course.query.get_or_404(course_id)
    course.is_public = 1
    if not course.course_code:
        course.course_code = _generate_course_code(course_id)
    db.session.commit()
    return jsonify({'message': '已通过审核，课程已全站公开'})


@courses_bp.route('/admin/reject/<int:course_id>', methods=['POST'])
@admin_required
def reject_course(current_user, course_id):
    """管理员驳回课程公开申请"""
    course = Course.query.get_or_404(course_id)
    course.is_public = 0
    db.session.commit()
    return jsonify({'message': '已驳回'})


@courses_bp.route('/admin/assign-to-class', methods=['POST'])
@admin_required
def assign_to_class(current_user):
    """管理员把公开课分配给指定班级"""
    data = request.get_json()
    course_id = data.get('course_id')
    class_id = data.get('class_id')
    from models import CourseClass
    cls = CourseClass.query.get_or_404(class_id)
    course = Course.query.get_or_404(course_id)
    existing = ClassCourse.query.filter_by(class_id=class_id, course_id=course_id).first()
    if not existing:
        db.session.add(ClassCourse(class_id=class_id, course_id=course_id))
        db.session.commit()
    return jsonify({'message': f'已将 {course.name} 分配给 {cls.name}'})
@courses_bp.route('/admin/teachers', methods=['GET'])
@admin_required
def list_teachers(current_user):
    q = request.args.get('q', '')
    from models import User, CourseClass, Course, ClassCourse
    query = User.query.filter(User.role == 'teacher')
    if q:
        query = query.filter(User.teacher_id.like('%' + q + '%'))
    teachers = query.all()
    result = []
    for t in teachers:
        teacher_classes = CourseClass.query.filter_by(teacher_id=t.id).all()
        cls_count = len(teacher_classes)
        cls_ids = [c.id for c in teacher_classes]
        # 统计该教师「创建」的课程数（Course.teacher_id）—— 之前的实现只统计
        # 班级-课程关联表，会漏掉教师已创建但未分配到班级的课程，导致显示为 0
        created_count = Course.query.filter_by(teacher_id=t.id).count()
        # 同时统计分配到该教师班级的课程数（含其他教师创建后分配进来的公开课）
        assigned_count = 0
        if cls_ids:
            assigned_count = db.session.query(ClassCourse.course_id).filter(
                ClassCourse.class_id.in_(cls_ids)
            ).distinct().count()
        # 取两者较大值，确保教师创建的课程一定被计入
        course_count = max(created_count, assigned_count)
        result.append({
            'id': t.id, 'username': t.username,
            'display_name': t.display_name or t.username,
            'teacher_id': t.teacher_id or '',
            'class_count': cls_count,
            'course_count': course_count,
            'created_course_count': created_count,
        })
    return jsonify({'teachers': result})

