from database import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(10), nullable=False, default='student')
    display_name = db.Column(db.String(100))
    gender = db.Column(db.String(10))
    school = db.Column(db.String(200))
    email = db.Column(db.String(200))
    avatar_url = db.Column(db.String(500))
    teacher_id = db.Column(db.String(20))     # 工号
    student_id = db.Column(db.String(20))     # 学号
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class Course(db.Model):
    __tablename__ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    is_public = db.Column(db.Integer, default=0)  # 0=私有 1=公开 2=待审核
    course_code = db.Column(db.String(20), unique=True)  # 课程号 COURSE-0001
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    subtasks = db.relationship('Subtask', backref='course', lazy=True, order_by='Subtask.order_index')
    class_courses = db.relationship('ClassCourse', backref='course', lazy=True)


class Subtask(db.Model):
    __tablename__ = 'subtasks'
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    order_index = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    command = db.Column(db.Text)
    expected_output = db.Column(db.Text)
    knowledge_text = db.Column(db.Text)


class CourseClass(db.Model):
    __tablename__ = 'classes'
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    class_code = db.Column(db.String(20), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    students = db.relationship('ClassStudent', backref='course_class', lazy=True)
    courses = db.relationship('ClassCourse', backref='course_class', lazy=True, cascade='all, delete-orphan')


class ClassStudent(db.Model):
    __tablename__ = 'class_students'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)


class ClassCourse(db.Model):
    __tablename__ = 'class_courses'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('class_id', 'course_id'),)


class TaskProgress(db.Model):
    __tablename__ = 'task_progress'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subtask_id = db.Column(db.Integer, db.ForeignKey('subtasks.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subtask_id = db.Column(db.Integer, db.ForeignKey('subtasks.id'), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class KnowledgeChat(db.Model):
    __tablename__ = 'knowledge_chats'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subtask_id = db.Column(db.Integer, db.ForeignKey('subtasks.id'), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Assessment(db.Model):
    __tablename__ = 'assessments'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    content_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Report(db.Model):
    __tablename__ = 'reports'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    grade = db.Column(db.String(2))
    total_time_hours = db.Column(db.Float, default=0)
    error_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship('User')
    course = db.relationship('Course')
