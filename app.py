from flask import Flask, request, render_template, redirect, flash, url_for, session, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from supabase import create_client, StorageException
import os
import tempfile
from datetime import timedelta, datetime
import uuid
from itsdangerous import URLSafeTimedSerializer
from search import GelişmişArama
import zipfile
import io
from flask import jsonify ,send_file
from sqlalchemy import desc,or_
from models import db, User, Project, Model, ForumPost, ForumReply,Report,Like
from admin import admin
from flask_migrate import Migrate
from werkzeug.utils import secure_filename


app = Flask(__name__, static_folder="static")

load_dotenv()

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "supersecret")
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
db.init_app(app)
migrate = Migrate(app, db)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

with app.app_context():
    pass

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)

ALLOWED_EXTENSIONS = {'stl', 'obj'}
MAX_TOTAL_SIZE = 20 * 1024 * 1024

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_token(email):
    return serializer.dumps(email, salt='remember-me')

def validate_token(token, max_age=864000):
    try:
        email = serializer.loads(token, salt='remember-me', max_age=max_age)
        return email
    except:
        return None

# Admin panel
admin.init_app(app)

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 40
    
    projects_pagination = Project.query.filter_by(type='Normal').order_by(
        desc(Project.created_at)
    ).paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    return render_template(
        'index.html', 
        projects=projects_pagination.items,
        pagination=projects_pagination,
        SUPABASE_URL=SUPABASE_URL
    )

@app.route('/frc')
def frc_index():
    page = request.args.get('page', 1, type=int)
    per_page = 40
    
    frc_projects = Project.query.filter_by(type='FRC').order_by(
        desc(Project.created_at)
    ).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )

    return render_template(
        'frc_index.html',
        projects=frc_projects.items,
        pagination=frc_projects,
        SUPABASE_URL=SUPABASE_URL
    )


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        new_user = User(username=username, email=email, password_hash=hashed_password)

        try:
            db.session.add(new_user)
            db.session.commit()
            flash("Kayıt başarılı! Lütfen giriş yapın.", "success")
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f"Kayıt sırasında hata oluştu: {str(e)}", "error")

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember_me = request.form.get('remember_me')

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            session['user'] = user.email
            session['user_id'] = user.id

            if remember_me:
                token = generate_token(user.email)
                resp = make_response(redirect(request.args.get('next') or url_for('index')))
                resp.set_cookie('remember_me', token, max_age=timedelta(days=10).total_seconds())
                return resp

            flash("Başarıyla giriş yaptınız!", "success")   
            return redirect(request.args.get('next') or url_for('index'))
        else:
            flash("Giriş başarısız. Lütfen bilgilerinizi kontrol edin.", "error")

    return render_template('login.html', next=request.args.get('next'))


@app.route('/logout')
def logout():
    session.pop('user', None)
    resp = make_response(redirect(url_for('login')))
    resp.set_cookie('remember_me', '', expires=0)
    flash("Başarıyla çıkış yaptınız!", "success")
    return resp

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(email=session['user']).first()
    if not user:
        flash("Kullanıcı bulunamadı.", "error")
        return redirect(url_for('index'))

    if request.method == 'POST':
        files = request.files.getlist('file')
        cover_file = request.files.get('cover')
        name = request.form.get('name')
        description = request.form.get('description') or "Bu proje için bir açıklama girilmemiş."
        directive = request.form.get('directive')
        license = request.form.get('license')
        project_type = request.form.get('type', 'Normal')

        total_size = 0
        if cover_file and cover_file.filename:
            cover_file.seek(0, 2)
            total_size += cover_file.tell()
            cover_file.seek(0)
        for f in files:
            f.seek(0, 2)
            total_size += f.tell()
            f.seek(0)
        if total_size > MAX_TOTAL_SIZE:
            flash("Yüklenen dosyaların toplam boyutu 20MB'ı geçemez!", "error")
            return redirect(request.url)

        new_project = Project(
            title=name,
            description=description,
            user_id=user.id,
            type=project_type
        )
        db.session.add(new_project)
        db.session.commit()

        project_folder = f"{new_project.id}_{uuid.uuid4().hex}"

        if cover_file and cover_file.filename:
            ext = cover_file.filename.rsplit('.', 1)[1].lower()
            secure_name = secure_filename(cover_file.filename)
            unique_cover = f"cover_{uuid.uuid4().hex}.{ext}"
            cover_path = f"{project_folder}/{unique_cover}"

            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                cover_file.save(tmp.name)

            try:
                print("→ uploading cover to bucket 'covers':", cover_path)
                supabase_client.storage.from_('covers').upload(cover_path, open(tmp.name, 'rb'))
                new_project.cover_image = cover_path
                db.session.commit()
            except StorageException as e:
                flash(f"Supabase cover upload hatası: {e}", "error")
            finally:
                os.unlink(tmp.name)

        for f in files:
            if not allowed_file(f.filename):
                flash(f"{f.filename}: geçersiz uzantı", "error")
                continue

            ext = f.filename.rsplit('.', 1)[1].lower()
            secure_name = secure_filename(f.filename)
            unique_file = f"{uuid.uuid4().hex}_{secure_name}"
            file_path = f"{project_folder}/{unique_file}"

            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                f.save(tmp.name)

            try:
                print("→ uploading model to bucket 'uploads':", file_path)
                supabase_client.storage.from_('uploads').upload(file_path, open(tmp.name, 'rb'))
                new_model = Model(
                    name=name,
                    filename=file_path,
                    original_filename=secure_name,
                    project_id=new_project.id,
                    license=license,
                    directive=directive
                )
                db.session.add(new_model)
                db.session.commit()
                flash(f"{secure_name} başarıyla yüklendi!", "success")
            except StorageException as e:
                flash(f"Supabase model upload hatası: {e}", "error")
                db.session.rollback()
            finally:
                os.unlink(tmp.name)

        return redirect(url_for('profile'))

    return render_template('upload.html')


@app.route('/delete_project/<int:project_id>', methods=['POST'])
def delete_project(project_id):
    if 'user' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(email=session['user']).first()
    if not user:
        flash("didnt find user", "error")
        return redirect(url_for('index'))

    project = Project.query.get_or_404(project_id)
    
    if project.user_id != user.id:
        flash("you don't have authority", "error")
        return redirect(url_for('profile'))

    try:
        for model in project.models:
            supabase_client.storage.from_('uploads').remove([model.filename])
            db.session.delete(model)
        
        db.session.delete(project)
        db.session.commit()

        flash("Proje ve bağlı tüm dosyalar başarıyla silindi.", "success")
    except StorageException as e:
        flash(f"Supabase error: {str(e)}", "error")
        db.session.rollback()
    except Exception as e:
        flash(f"delete project error: {str(e)}", "error")
        db.session.rollback()

    return redirect(url_for('profile'))

@app.route('/project/<int:project_id>')
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    current_user_id = session.get('user_id') 
    liked = False
    if current_user_id:
        liked = any(like.user_id == current_user_id for like in project.likes)
    return render_template('model.html', project=project,liked=liked, SUPABASE_URL=SUPABASE_URL)

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(email=session['user']).first()
    if not user:
        flash("Kullanıcı bulunamadı", "error")
        return redirect(url_for('index'))

    projects = Project.query.filter_by(user_id=user.id).all()

    models = []
    for project in projects:
        models.extend(project.models)

    posts = ForumPost.query.filter_by(user_id=user.id).order_by(desc(ForumPost.created_at)).all()

    if request.method == 'POST':
        model_id = request.form.get('model_id')
        model = Model.query.get(model_id)

        if model and model.project.user_id == user.id:
            try:
                supabase_client.storage.from_('uploads').remove([model.filename])
                db.session.delete(model)
                db.session.commit()
                flash("Model başarıyla silindi.", "success")
            except StorageException as e:
                flash(f"Supabase Storage hatası: {str(e)}", "error")
            except Exception as e:
                flash(f"Model silinirken hata oluştu: {str(e)}", "error")
        else:
            flash("Bu modeli silme yetkiniz yok.", "error")

    return render_template('profile.html', user=user, projects=projects, models=models, posts=posts)

@app.route('/forum/post/<int:post_id>')
def view_forum_post(post_id):
    post = ForumPost.query.get_or_404(post_id)
    return render_template('forum_post.html', post=post)


@app.route('/search')
def search():
    query = request.args.get('q', '').strip()

    if not query:
        return redirect(url_for('index'))
    
    projects = Project.query.filter(
        Project.title.ilike(f'%{query}%')
    ).order_by(Project.created_at.desc()).all()
    
    models = Model.query.join(Project).filter(
        Model.name.ilike(f'%{query}%')
    ).all()
    
    return render_template('search_results.html', 
                         projects=projects,
                         models=models,
                         query=query,
                         SUPABASE_URL=SUPABASE_URL)

@app.route('/download_project/<int:project_id>')
def download_project(project_id):
    project = Project.query.get_or_404(project_id)
    try:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for model in project.models:
                try:
                    file_data = supabase_client.storage.from_('uploads').download(model.filename)
                    zipf.writestr(model.original_filename, file_data)
                except Exception as e:
                    print(f"Hata: {model.filename} indirilemedi. {str(e)}")
                    continue

        zip_buffer.seek(0)
        return send_file(
            zip_buffer,
            as_attachment=True,
            download_name=f"{project.title}.zip",
            mimetype='application/zip'
        )

    except Exception as e:
        flash(f"İndirme hatası: {str(e)}", "error")
        return redirect(url_for('project_detail', project_id=project_id))

@app.route('/like', methods=['POST'])
def like():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Giriş yapmalısınız.'}), 401

    user_id = session['user_id']
    data = request.json
    project_id = data.get('project_id')
    forum_post_id = data.get('forum_post_id')

    existing_like = Like.query.filter_by(
        user_id=user_id,
        project_id=project_id,
        forum_post_id=forum_post_id
    ).first()

    if existing_like:
        db.session.delete(existing_like)
        db.session.commit()
        return jsonify({'success': True, 'liked': False})
    else:
        like = Like(user_id=user_id, project_id=project_id, forum_post_id=forum_post_id)
        db.session.add(like)
        db.session.commit()
        return jsonify({'success': True, 'liked': True})

    
@app.route('/report', methods=['POST'])
def report():
    if 'user' not in session:
        flash('You must log in to submit a complaint..', 'error')
        return redirect(url_for('login'))

    user_id = session['user_id']
    project_id = request.form.get('project_id')
    project_url = request.form.get('project_url')

    if not project_id or not project_url:
        flash('Proje bilgileri eksik.', 'error')
        return redirect(request.referrer)

    report = Report(user_id=user_id, project_id=project_id, project_url=project_url)
    db.session.add(report)
    db.session.commit()

    flash('Şikayet gönderildi.', 'success')
    return render_template('email_succes.html')

@app.route('/report/error')
def report_error():
    error = request.args.get('error', 'Bilinmeyen hata')
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Error</title>
    </head>
    <body>
        <p>An error occurred while sending the report: {error}</p>
        <p><a href="/">Return Home Page</a></p>
        <p><a href="javascript:history.back()">Return Back</a></p>
    </body>
    </html>
    """

@app.route('/privacy-policy')
def privacy_policy():
    return render_template('privacyPolicy.html')

@app.route('/forum')
def forum_home():
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)

    if query:
        posts_query = ForumPost.query.filter(
            or_(
                ForumPost.title.ilike(f'%{query}%'),
                ForumPost.content.ilike(f'%{query}%')
            )
        ).order_by(ForumPost.created_at.desc())
    else:
        posts_query = ForumPost.query.order_by(ForumPost.created_at.desc())

    pagination = posts_query.paginate(page=page, per_page=10)
    return render_template('forum_home.html', posts=pagination.items, pagination=pagination)

@app.route('/forum/new', methods=['GET', 'POST'])
def new_forum_post():
    if 'user' not in session:
        return redirect(url_for('login'))

    user = User.query.filter_by(email=session['user']).first()

    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        if title and content:
            post = ForumPost(title=title, content=content, user=user)
            db.session.add(post)
            db.session.commit()
            return redirect(url_for('forum_home'))
        else:
            flash("Başlık ve içerik boş olamaz.", "error")

    return render_template('new_forum_post.html')


@app.route('/forum/post/<int:post_id>', methods=['GET', 'POST'])
def forum_post_detail(post_id):
    post = ForumPost.query.get_or_404(post_id)
    user = None
    if 'user' in session:
        user = User.query.filter_by(email=session['user']).first()

    if request.method == 'POST':
        if not user:
            return redirect(url_for('login'))

        content = request.form.get('content')
        if content:
            reply = ForumReply(content=content, post=post, user=user)
            db.session.add(reply)
            db.session.commit()
            return redirect(url_for('forum_post_detail', post_id=post_id))

    return render_template('forum_post_detail.html', post=post)

@app.route('/forum/post/<int:post_id>/reply', methods=['POST'])
def reply_to_post(post_id):
    post = ForumPost.query.get_or_404(post_id)
    user = None
    if 'user' in session:
        user = User.query.filter_by(email=session['user']).first()

    if request.method == 'POST' and user:
        content = request.form.get('content')
        if content:
            reply = ForumReply(content=content, post=post, user=user)
            db.session.add(reply)
            db.session.commit()
            return redirect(url_for('forum_post_detail', post_id=post_id))
    
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)