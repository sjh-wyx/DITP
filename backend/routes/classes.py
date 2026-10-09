"""班级路由 — 班级-课程多对多版"""
from flask import Blueprint, request, jsonify
from database import db
from models import Course, CourseClass, ClassStudent, ClassCourse, TaskProgress, Subtask, User
from routes.auth import token_required, teacher_required
import redis_client

classes_bp = Blueprint('classes', __name__)


def _next_class_code():
    """按顺序生成唯一班级码：DS2026-01、DS2026-02 …（后端保证不重复）"""
    import re
    from datetime import datetime
    prefix = f'DS{datetime.utcnow().year}-'
    max_num = 0
    for c in CourseClass.query.filter(CourseClass.class_code.like(prefix + '%')).all():
        m = re.match(r'DS\d{4}-(\d+)', c.class_code or '')
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f'{prefix}{str(max_num + 1).zfill(2)}'


@classes_bp.route('/create', methods=['POST'])
@teacher_required
def create_class(current_user):
    """教师创建班级（不关联课程）。班级码为空或重复时，后端按顺序自动生成唯一码"""
    data = request.get_json()
    name = data.get('name', '').strip()
    class_code = data.get('class_code', '').strip()
    if not name:
        return jsonify({'error': '班级名称不能为空'}), 400
    if not class_code or CourseClass.query.filter_by(class_code=class_code).first():
        class_code = _next_class_code()
    cls = CourseClass(teacher_id=current_user.id, name=name, class_code=class_code)
    db.session.add(cls)
    db.session.commit()
    return jsonify({'id': cls.id, 'name': cls.name, 'class_code': cls.class_code}), 201


@classes_bp.route('/assign_course', methods=['POST'])
@teacher_required
def assign_course(current_user):
    """教师给班级分配课程（仅能分配自己创建或全站公开的课程；admin 无限制）"""
    data = request.get_json()
    class_id = data.get('class_id')
    course_id = data.get('course_id')
    cls = CourseClass.query.get_or_404(class_id)
    if cls.teacher_id != current_user.id:
        return jsonify({'error': '无权操作'}), 403
    # 归属权限校验：admin 可分配任意课程；教师仅能分配自己创建或全站公开(1)的课程
    course = Course.query.get_or_404(course_id)
    if current_user.role != 'admin' and course.teacher_id != current_user.id and course.is_public != 1:
        return jsonify({'error': '无权分配该课程（仅创建人或全站公开课程可分配）'}), 403
    existing = ClassCourse.query.filter_by(class_id=class_id, course_id=course_id).first()
    if existing:
        return jsonify({'error': '已分配该课程'}), 400
    cc = ClassCourse(class_id=class_id, course_id=course_id)
    db.session.add(cc)
    db.session.commit()
    return jsonify({'message': '课程已分配'})


@classes_bp.route('/remove_course', methods=['POST'])
@teacher_required
def remove_course(current_user):
    """教师移除班级课程"""
    data = request.get_json()
    class_id = data.get('class_id')
    course_id = data.get('course_id')
    cls = CourseClass.query.get_or_404(class_id)
    if cls.teacher_id != current_user.id:
        return jsonify({'error': '无权操作'}), 403
    ClassCourse.query.filter_by(class_id=class_id, course_id=course_id).delete()
    db.session.commit()
    return jsonify({'message': '课程已移除'})


@classes_bp.route('/list', methods=['GET'])
@token_required
def list_classes(current_user):
    """列出班级（教师看自己的，学生看已加入的）"""
    if current_user.role == 'teacher':
        classes = CourseClass.query.filter_by(teacher_id=current_user.id).all()
    else:
        student_classes = ClassStudent.query.filter_by(student_id=current_user.id).all()
        class_ids = [sc.class_id for sc in student_classes]
        classes = CourseClass.query.filter(CourseClass.id.in_(class_ids)).all() if class_ids else []
    return jsonify({'classes': [{
        'id': c.id, 'name': c.name, 'class_code': c.class_code,
        'student_count': ClassStudent.query.filter_by(class_id=c.id).count(),
        'course_ids': [cc.course_id for cc in ClassCourse.query.filter_by(class_id=c.id).all()]
    } for c in classes]})


@classes_bp.route('/<int:class_id>', methods=['DELETE'])
@teacher_required
def delete_class(current_user, class_id):
    """教师删除班级"""
    cls = CourseClass.query.get_or_404(class_id)
    if cls.teacher_id != current_user.id:
        return jsonify({'error': '无权操作'}), 403
    db.session.delete(cls)
    db.session.commit()
    return jsonify({'message': '已删除'})


@classes_bp.route('/join', methods=['POST'])
@token_required
def join_class(current_user):
    """学生通过班级码加入班级"""
    data = request.get_json()
    cls = CourseClass.query.filter_by(class_code=data['class_code']).first()
    if not cls:
        return jsonify({'error': '班级码无效'}), 404
    existing = ClassStudent.query.filter_by(class_id=cls.id, student_id=current_user.id).first()
    if existing:
        return jsonify({'error': '已加入该班级'}), 400
    cs = ClassStudent(class_id=cls.id, student_id=current_user.id)
    db.session.add(cs)
    db.session.commit()
    return jsonify({'message': '加入班级成功', 'class_id': cls.id, 'class_name': cls.name})


@classes_bp.route('/join-by-id', methods=['POST'])
@token_required
def join_class_by_id(current_user):
    """学生通过班级ID加入班级"""
    data = request.get_json()
    cls = CourseClass.query.get(data.get('class_id'))
    if not cls:
        return jsonify({'error': '班级不存在'}), 404
    existing = ClassStudent.query.filter_by(class_id=cls.id, student_id=current_user.id).first()
    if existing:
        return jsonify({'error': '已加入该班级'}), 400
    cs = ClassStudent(class_id=cls.id, student_id=current_user.id)
    db.session.add(cs)
    db.session.commit()
    return jsonify({'message': '加入班级成功', 'class_id': cls.id, 'class_name': cls.name})


@classes_bp.route('/<int:class_id>/progress', methods=['GET'])
@teacher_required
def get_class_progress(current_user, class_id):
    """教师查看班级学生进度"""
    cls = CourseClass.query.get_or_404(class_id)
    if cls.teacher_id != current_user.id:
        return jsonify({'error': '无权访问'}), 403
    # 支持按课程过滤
    course_id = request.args.get('course_id', type=int)
    if course_id:
        course_ids = [course_id]
    else:
        course_ids = [cc.course_id for cc in ClassCourse.query.filter_by(class_id=class_id).all()]
    enrollments = ClassStudent.query.filter_by(class_id=class_id).all()
    students = []
    for e in enrollments:
        student = User.query.get(e.student_id)
        completed = TaskProgress.query.filter(
            TaskProgress.student_id == e.student_id,
            TaskProgress.status == 'completed',
            TaskProgress.subtask_id.in_(
                db.session.query(Subtask.id).filter(Subtask.course_id.in_(course_ids))
            )
        ).count()
        total = Subtask.query.filter(Subtask.course_id.in_(course_ids)).count()
        status = 'completed' if completed >= total else ('in_progress' if completed > 0 else 'not_started')
        students.append({
            'student_id': student.id, 'name': student.display_name or student.username,
            'progress': completed, 'total': total, 'status': status
        })
    students.sort(key=lambda x: (-x['progress'], x['name']))
    return jsonify({'students': students})


@classes_bp.route('/online', methods=['GET'])
def online_count():
    return jsonify({'online_count': redis_client.get_online_count()})
