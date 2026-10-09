"""
DataTutor 输入校验模块
对注册/登录接口做硬性长度限制，防止超大输入攻击
"""
import re


# 允许的用户名字符：字母、数字、中文、下划线、短横线
_USERNAME_PATTERN = re.compile(r'^[\w\u4e00-\u9fff-]+$')


def _assert_len(value, field_name, min_len=1, max_len=50):
    """通用长度校验"""
    if not isinstance(value, str):
        raise ValueError(f'{field_name} 必须是字符串')
    if len(value) < min_len:
        raise ValueError(f'{field_name} 不能为空')
    if len(value) > max_len:
        raise ValueError(f'{field_name} 不能超过 {max_len} 个字符')


def validate_register_input(data):
    """注册输入校验，不通过则 raise ValueError"""
    username = data.get('username', '')
    password = data.get('password', '')
    display_name = data.get('display_name', username)
    role = data.get('role', 'student')
    student_id = data.get('student_id', '')
    teacher_id = data.get('teacher_id', '')

    # 用户名：1-50字符，合法字符
    _assert_len(username, '用户名', 1, 50)
    if not _USERNAME_PATTERN.match(username):
        raise ValueError('用户名只能包含字母、数字、中文、下划线和短横线')

    # 密码：6-128字符
    _assert_len(password, '密码', 6, 128)

    # 显示名：≤100字符
    _assert_len(display_name, '显示名', 1, 100)

    # 角色
    if role not in ('student', 'teacher', 'admin'):
        raise ValueError('角色无效')

    # 学号/工号：≤20字符
    if role == 'student' and student_id:
        _assert_len(student_id, '学号', 0, 20)
    if role == 'teacher' and teacher_id:
        _assert_len(teacher_id, '工号', 0, 20)


def validate_login_input(data):
    """登录输入校验，不通过则 raise ValueError"""
    username = data.get('username', '')
    password = data.get('password', '')

    _assert_len(username, '用户名', 1, 50)
    if not _USERNAME_PATTERN.match(username):
        raise ValueError('用户名只能包含字母、数字、中文、下划线和短横线')
    _assert_len(password, '密码', 1, 128)
