"""实训报告路由 — 教师查看学生实训评估报告"""
from flask import Blueprint, request, jsonify
from database import db
from routes.auth import token_required
from models import Assessment

assessments_bp = Blueprint('assessments', __name__)


@assessments_bp.route('/<int:student_id>/<int:course_id>', methods=['GET'])
@token_required
def get_assessment(current_user, student_id, course_id):
    """获取学生的实训评估报告

    权限：教师可查看任意学生报告，学生只能查看自己的。
    """
    if current_user.role != 'teacher' and current_user.id != student_id:
        return jsonify({'error': '无权查看此报告'}), 403

    assessment = Assessment.query.filter_by(
        student_id=student_id,
        course_id=course_id,
    ).first()

    return jsonify({
        'content_json': assessment.content_json if assessment else None,
    })
