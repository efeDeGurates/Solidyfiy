from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from flask import redirect, url_for, session, flash
from models import db, User, Project, ForumPost, ForumReply, Report, Like

class MyAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return 'user' in session and User.query.filter_by(email=session['user'], role='admin').first() is not None

    def inaccessible_callback(self, name, **kwargs):
        flash('Bu sayfaya erişim yetkiniz yok.', 'danger')
        return redirect(url_for('index'))

class SecureModelView(ModelView):
    def is_accessible(self):
        return 'user' in session and User.query.filter_by(email=session['user'], role='admin').first() is not None

    def inaccessible_callback(self, name, **kwargs):
        flash('Bu sayfaya erişim yetkiniz yok.', 'danger')
        return redirect(url_for('index'))

class ProjectModelView(SecureModelView):
    column_searchable_list = ['title','type']

class UserModelView(SecureModelView):
    column_searchable_list = ['username', 'email']

class ForumModelWiew(SecureModelView):
    column_searchable_list = ['title','content']



admin = Admin(name='Admin Panel', index_view=MyAdminIndexView())
admin.add_view(UserModelView(User, db.session))
admin.add_view(ProjectModelView(Project, db.session))
admin.add_view(ForumModelWiew(ForumPost, db.session))
admin.add_view(SecureModelView(ForumReply, db.session))
admin.add_view(SecureModelView(Report,db.session))