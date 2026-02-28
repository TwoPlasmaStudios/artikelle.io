import os
import json
from datetime import datetime, date, timedelta
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError
from werkzeug.security import generate_password_hash, check_password_hash
from flask_babel import Babel

# ========== Admin paneli için importlar ==========
try:
    from flask_admin import Admin, AdminIndexView
    from flask_admin.contrib.sqla import ModelView
    ADMIN_AVAILABLE = True
except ImportError:
    ADMIN_AVAILABLE = False
    print("Flask-Admin kurulu değil, admin paneli devre dışı.")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'gizli-anahtar-buraya'  # production'da env kullan!
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///artikelle.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
babel = Babel(app)  # Sadece başlat

# -------------------------------------------------------------------
# VERİTABANI MODELLERİ
# -------------------------------------------------------------------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    scores = db.relationship('Score', backref='user', lazy=True)
    profile = db.relationship('UserProfile', backref='user', uselist=False)
    achievements = db.relationship('UserAchievement', backref='user', lazy=True)
    daily_progress = db.relationship('UserDailyProgress', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Word(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    german = db.Column(db.String(100), nullable=False)
    article = db.Column(db.String(10), nullable=False)  # 'der', 'die', 'das'
    meaning = db.Column(db.String(200))
    plural = db.Column(db.String(50))

class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    category = db.Column(db.String(10), nullable=False)  # '30sn', '1dk', '3dk', '5dk'
    correct_count = db.Column(db.Integer, default=0)
    wrong_count = db.Column(db.Integer, default=0)

class UserProfile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True)
    avatar = db.Column(db.String(200), default='default.png')
    total_games = db.Column(db.Integer, default=0)
    total_correct = db.Column(db.Integer, default=0)
    total_wrong = db.Column(db.Integer, default=0)
    total_score = db.Column(db.Integer, default=0)
    best_score_30sn = db.Column(db.Integer, default=0)
    best_score_1dk = db.Column(db.Integer, default=0)
    best_score_3dk = db.Column(db.Integer, default=0)
    best_score_5dk = db.Column(db.Integer, default=0)
    correct_der = db.Column(db.Integer, default=0)
    correct_die = db.Column(db.Integer, default=0)
    correct_das = db.Column(db.Integer, default=0)
    wrong_der = db.Column(db.Integer, default=0)
    wrong_die = db.Column(db.Integer, default=0)
    wrong_das = db.Column(db.Integer, default=0)

class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    icon = db.Column(db.String(100))
    condition_type = db.Column(db.String(50))
    condition_value = db.Column(db.Integer)
    reward_points = db.Column(db.Integer, default=0)

class UserAchievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievement.id'))
    earned_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'achievement_id'),)

class DailyChallenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    description = db.Column(db.String(200))
    goal_type = db.Column(db.String(50))
    goal_value = db.Column(db.Integer)
    reward_points = db.Column(db.Integer, default=0)
    reward_achievement_id = db.Column(db.Integer, db.ForeignKey('achievement.id'), nullable=True)
    active = db.Column(db.Boolean, default=True)

class UserDailyProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    challenge_id = db.Column(db.Integer, db.ForeignKey('daily_challenge.id'))
    date = db.Column(db.Date, default=date.today)
    progress = db.Column(db.Integer, default=0)
    completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (db.UniqueConstraint('user_id', 'challenge_id', 'date'),)

    challenge = db.relationship('DailyChallenge')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------------------------------------------------------------
# FORMLAR
# -------------------------------------------------------------------

class RegistrationForm(FlaskForm):
    username = StringField('Kullanıcı Adı', validators=[DataRequired(), Length(min=3, max=20)])
    email = StringField('E-posta', validators=[DataRequired(), Email()])
    password = PasswordField('Şifre', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Şifre Tekrar', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Kayıt Ol')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Bu kullanıcı adı zaten alınmış.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Bu e-posta adresi zaten kayıtlı.')

class LoginForm(FlaskForm):
    email = StringField('E-posta', validators=[DataRequired(), Email()])
    password = PasswordField('Şifre', validators=[DataRequired()])
    submit = SubmitField('Giriş Yap')

# -------------------------------------------------------------------
# KELİME YÜKLEME
# -------------------------------------------------------------------

def load_words_from_json():
    json_path = os.path.join(app.root_path, 'words.json')
    if not os.path.exists(json_path):
        print("Uyarı: words.json bulunamadı! Örnek kelimeler kullanılacak.")
        return [
            {"german": "Haus", "article": "das", "meaning": "ev", "plural": "Häuser"},
            {"german": "Mann", "article": "der", "meaning": "adam", "plural": "Männer"},
            {"german": "Frau", "article": "die", "meaning": "kadın", "plural": "Frauen"}
        ]
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"CRITICAL: words.json dosyasında JSON hatası: {e}")
        return [
            {"german": "Haus", "article": "das", "meaning": "ev", "plural": "Häuser"},
            {"german": "Mann", "article": "der", "meaning": "adam", "plural": "Männer"},
            {"german": "Frau", "article": "die", "meaning": "kadın", "plural": "Frauen"}
        ]

def add_words_to_db():
    if Word.query.count() > 0:
        return
    words_data = load_words_from_json()
    for item in words_data:
        word = Word(
            german=item['german'],
            article=item['article'],
            meaning=item.get('meaning', ''),
            plural=item.get('plural', '')
        )
        db.session.add(word)
    db.session.commit()
    print(f"{Word.query.count()} kelime veritabanında.")

# -------------------------------------------------------------------
# BAŞLANGIÇ VERİLERİ (Achievements, DailyChallenges)
# -------------------------------------------------------------------

def init_achievements():
    if Achievement.query.count() > 0:
        return
    achievements = [
        {"name": "İlk Adım", "description": "İlk oyununu oyna", "condition_type": "total_games", "condition_value": 1, "icon": "step.png"},
        {"name": "Çaylak", "description": "Toplam 10 doğru cevap", "condition_type": "total_correct", "condition_value": 10, "icon": "rookie.png"},
        {"name": "Uzman", "description": "Toplam 100 doğru cevap", "condition_type": "total_correct", "condition_value": 100, "icon": "expert.png"},
        {"name": "Hızlı Parmaklar", "description": "1 dakikada 100 puan", "condition_type": "best_score_1dk", "condition_value": 100, "icon": "fast.png"},
        {"name": "Dayanıklı", "description": "5 dakikada 200 puan", "condition_type": "best_score_5dk", "condition_value": 200, "icon": "durable.png"},
    ]
    for a in achievements:
        db.session.add(Achievement(**a))
    db.session.commit()
    print("Başarımlar eklendi.")

def init_daily_challenges():
    if DailyChallenge.query.count() > 0:
        return
    challenges = [
        {"name": "Günlük 10 Doğru", "description": "Bugün 10 doğru cevap ver", "goal_type": "correct_count", "goal_value": 10, "reward_points": 50},
        {"name": "Puan Avcısı", "description": "Bugün toplam 200 puan topla", "goal_type": "total_score", "goal_value": 200, "reward_points": 100},
        {"name": "3 Dakika Mücadelesi", "description": "3 dakikalık oyunda 60 puan al", "goal_type": "score_in_category", "goal_value": 60, "reward_points": 75},
    ]
    for c in challenges:
        db.session.add(DailyChallenge(**c))
    db.session.commit()
    print("Günlük görevler eklendi.")

with app.app_context():
    db.create_all()
    add_words_to_db()
    init_achievements()
    init_daily_challenges()

# -------------------------------------------------------------------
# DİL DOSYASI
# -------------------------------------------------------------------

translations = {
    'tr': {
        'home': 'Ana Sayfa',
        'dashboard': 'Panel',
        'game': 'Oyuna Başla',
        'leaderboard': 'Lider Tablosu',
        'logout': 'Çıkış',
        'login': 'Giriş',
        'register': 'Kayıt',
        'profile': 'Profil',
        'admin': 'Yönetim',
        'welcome': 'Artikelle.io\'ya Hoş Geldiniz!',
        'description': 'Almanca kelimelerin artikellerini öğrenmek için eğlenceli bir oyun. Giriş yap ve hemen başla!',
        'signup': 'Kayıt Ol',
        'signin': 'Giriş Yap',
        'choose_duration': 'Süre Seç',
        'seconds': 'saniye',
        'minute': 'dakika',
        'minutes': 'dakika',
        'score': 'Puan',
        'leaderboard_title': 'Lider Tablosu',
        'rank': 'Sıra',
        'user': 'Kullanıcı',
        'score_header': 'Skor',
        'no_scores': 'Henüz skor yok.',
        'correct': 'Doğru!',
        'wrong': 'Yanlış!',
        'correct_answer': 'Doğru cevap',
        'continue_btn': 'Devam',
        'game_over': 'Oyun bitti!',
        'new_record': 'Yeni rekor! 🏆',
        'try_again': 'Tekrar dene!',
        'have_account': 'Zaten hesabınız var mı?',
        'no_account': 'Hesabınız yok mu?',
        'welcome_user': 'Hoş geldin',
        'dashboard_desc': 'Bu senin panelin. Oyuna başlamak için aşağıdaki butona tıkla.',
        'register_success': 'Kayıt başarılı! Giriş yapabilirsiniz.',
        'login_success': 'Giriş başarılı!',
        'login_error': 'E-posta veya şifre hatalı.',
        'logout_msg': 'Çıkış yapıldı.',
        'username': 'Kullanıcı Adı',
        'email': 'E-posta',
        'password': 'Şifre',
        'confirm_password': 'Şifre Tekrar',
        'stats': 'İstatistikler',
        'total_games': 'Toplam Oyun',
        'total_correct': 'Toplam Doğru',
        'total_wrong': 'Toplam Yanlış',
        'accuracy': 'Doğruluk Oranı',
        'best_scores': 'En İyi Skorlar',
        'achievements': 'Başarımlar',
        'daily_challenges': 'Günlük Görevler',
        'completed': 'Tamamlandı',
        'in_progress': 'Devam Ediyor',
        'reward': 'Ödül',
        'points': 'puan',
        'share': 'Paylaş',
        'weekly': 'Haftalık',
        'monthly': 'Aylık',
        'all_time': 'Tüm Zamanlar',
    },
    'en': {
        'home': 'Home',
        'dashboard': 'Dashboard',
        'game': 'Start Game',
        'leaderboard': 'Leaderboard',
        'logout': 'Logout',
        'login': 'Login',
        'register': 'Register',
        'profile': 'Profile',
        'admin': 'Admin',
        'welcome': 'Welcome to Artikelle.io!',
        'description': 'A fun game to learn German articles. Login and start now!',
        'signup': 'Sign Up',
        'signin': 'Sign In',
        'choose_duration': 'Choose Duration',
        'seconds': 'seconds',
        'minute': 'minute',
        'minutes': 'minutes',
        'score': 'Score',
        'leaderboard_title': 'Leaderboard',
        'rank': 'Rank',
        'user': 'User',
        'score_header': 'Score',
        'no_scores': 'No scores yet.',
        'correct': 'Correct!',
        'wrong': 'Wrong!',
        'correct_answer': 'Correct answer',
        'continue_btn': 'Continue',
        'game_over': 'Game over!',
        'new_record': 'New record! 🏆',
        'try_again': 'Try again!',
        'have_account': 'Already have an account?',
        'no_account': 'No account?',
        'welcome_user': 'Welcome',
        'dashboard_desc': 'This is your dashboard. Start the game by clicking below.',
        'register_success': 'Registration successful! You can login now.',
        'login_success': 'Login successful!',
        'login_error': 'Email or password incorrect.',
        'logout_msg': 'Logged out.',
        'username': 'Username',
        'email': 'Email',
        'password': 'Password',
        'confirm_password': 'Confirm Password',
        'stats': 'Statistics',
        'total_games': 'Total Games',
        'total_correct': 'Total Correct',
        'total_wrong': 'Total Wrong',
        'accuracy': 'Accuracy',
        'best_scores': 'Best Scores',
        'achievements': 'Achievements',
        'daily_challenges': 'Daily Challenges',
        'completed': 'Completed',
        'in_progress': 'In Progress',
        'reward': 'Reward',
        'points': 'points',
        'share': 'Share',
        'weekly': 'Weekly',
        'monthly': 'Monthly',
        'all_time': 'All Time',
    }
}

def get_text(key, lang='tr'):
    return translations.get(lang, translations['tr']).get(key, key)

# -------------------------------------------------------------------
# ROUTES
# -------------------------------------------------------------------

@app.route('/')
def index():
    lang = request.cookies.get('lang', 'tr')
    return render_template('main.html', page='index', lang=lang, get_text=get_text)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = RegistrationForm()
    lang = request.cookies.get('lang', 'tr')
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()
        profile = UserProfile(user_id=user.id)
        db.session.add(profile)
        db.session.commit()
        flash(get_text('register_success', lang), 'success')
        return redirect(url_for('login'))
    return render_template('main.html', page='register', form=form, lang=lang, get_text=get_text)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    lang = request.cookies.get('lang', 'tr')
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash(get_text('login_success', lang), 'success')
            return redirect(url_for('dashboard'))
        else:
            flash(get_text('login_error', lang), 'danger')
    return render_template('main.html', page='login', form=form, lang=lang, get_text=get_text)

@app.route('/dashboard')
@login_required
def dashboard():
    lang = request.cookies.get('lang', 'tr')
    return render_template('main.html', page='dashboard', name=current_user.username, lang=lang, get_text=get_text)

@app.route('/game')
@login_required
def game():
    lang = request.cookies.get('lang', 'tr')
    return render_template('main.html', page='game', lang=lang, get_text=get_text)

@app.route('/profile')
@login_required
def profile():
    lang = request.cookies.get('lang', 'tr')
    user = current_user
    profile = user.profile
    achievements = UserAchievement.query.filter_by(user_id=user.id).all()
    today = date.today()
    daily_progress = UserDailyProgress.query.filter_by(user_id=user.id, date=today).all()
    if not daily_progress:
        challenges = DailyChallenge.query.filter_by(active=True).limit(3).all()
        for c in challenges:
            dp = UserDailyProgress(user_id=user.id, challenge_id=c.id, date=today)
            db.session.add(dp)
        db.session.commit()
        daily_progress = UserDailyProgress.query.filter_by(user_id=user.id, date=today).all()
    stats = {
        'total_games': profile.total_games,
        'total_correct': profile.total_correct,
        'total_wrong': profile.total_wrong,
        'accuracy': (profile.total_correct / (profile.total_correct + profile.total_wrong) * 100) if (profile.total_correct + profile.total_wrong) > 0 else 0,
        'best_scores': {
            '30sn': profile.best_score_30sn,
            '1dk': profile.best_score_1dk,
            '3dk': profile.best_score_3dk,
            '5dk': profile.best_score_5dk,
        },
        'article_stats': {
            'der': {'correct': profile.correct_der, 'wrong': profile.wrong_der},
            'die': {'correct': profile.correct_die, 'wrong': profile.wrong_die},
            'das': {'correct': profile.correct_das, 'wrong': profile.wrong_das},
        }
    }
    return render_template('main.html', page='profile', user=user, profile=profile,
                           achievements=achievements, daily_progress=daily_progress, stats=stats,
                           lang=lang, get_text=get_text)

@app.route('/leaderboard')
def leaderboard():
    category = request.args.get('cat', '1dk')
    period = request.args.get('period', 'all')
    lang = request.cookies.get('lang', 'tr')
    
    query = db.session.query(Score, User.username).join(User)
    query = query.filter(Score.category == category)
    
    if period == 'week':
        week_ago = datetime.utcnow() - timedelta(days=7)
        query = query.filter(Score.date >= week_ago)
    elif period == 'month':
        month_ago = datetime.utcnow() - timedelta(days=30)
        query = query.filter(Score.date >= month_ago)
    
    subquery = query.with_entities(
        Score.user_id,
        db.func.max(Score.score).label('max_score')
    ).group_by(Score.user_id).subquery()
    
    scores = db.session.query(
        subquery.c.max_score,
        User.username
    ).join(User, User.id == subquery.c.user_id
    ).order_by(subquery.c.max_score.desc()).limit(10).all()
    
    scores_list = [(i+1, username, max_score) for i, (max_score, username) in enumerate(scores)]
    return render_template('main.html', page='leaderboard', scores=scores_list, category=category, period=period, lang=lang, get_text=get_text)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    lang = request.cookies.get('lang', 'tr')
    flash(get_text('logout_msg', lang), 'info')
    return redirect(url_for('index'))

# -------------------------------------------------------------------
# API'LER
# -------------------------------------------------------------------

@app.route('/api/random_word')
def random_word():
    word = Word.query.order_by(db.func.random()).first()
    if word:
        return jsonify({
            'id': word.id,
            'german': word.german,
            'article': word.article,
            'meaning': word.meaning,
            'plural': word.plural
        })
    return jsonify({'error': 'Kelime yok'}), 404

@app.route('/api/submit_score', methods=['POST'])
@login_required
def submit_score():
    data = request.get_json()
    score_value = data.get('score')
    category = data.get('category', '1dk')
    correct_count = data.get('correct_count', 0)
    wrong_count = data.get('wrong_count', 0)
    article_correct = data.get('article_correct', {})
    article_wrong = data.get('article_wrong', {})
    
    if score_value is None:
        return jsonify({'error': 'Skor gerekli'}), 400
    
    new_score = Score(user_id=current_user.id, score=score_value, category=category,
                      correct_count=correct_count, wrong_count=wrong_count)
    db.session.add(new_score)
    
    profile = current_user.profile
    if not profile:
        profile = UserProfile(user_id=current_user.id)
        db.session.add(profile)
        db.session.flush()
    
    profile.total_games += 1
    profile.total_correct += correct_count
    profile.total_wrong += wrong_count
    profile.total_score += score_value
    
    if category == '30sn' and score_value > profile.best_score_30sn:
        profile.best_score_30sn = score_value
    elif category == '1dk' and score_value > profile.best_score_1dk:
        profile.best_score_1dk = score_value
    elif category == '3dk' and score_value > profile.best_score_3dk:
        profile.best_score_3dk = score_value
    elif category == '5dk' and score_value > profile.best_score_5dk:
        profile.best_score_5dk = score_value
    
    profile.correct_der += article_correct.get('der', 0)
    profile.correct_die += article_correct.get('die', 0)
    profile.correct_das += article_correct.get('das', 0)
    profile.wrong_der += article_wrong.get('der', 0)
    profile.wrong_die += article_wrong.get('die', 0)
    profile.wrong_das += article_wrong.get('das', 0)
    
    db.session.commit()
    
    check_achievements(current_user.id)
    update_daily_challenges(current_user.id, correct_count, score_value, category)
    
    best = Score.query.filter_by(user_id=current_user.id, category=category).order_by(Score.score.desc()).first()
    is_highscore = (best is None) or (score_value >= best.score)
    
    return jsonify({'success': True, 'is_highscore': is_highscore, 'score': score_value})

@app.route('/api/share_score', methods=['POST'])
@login_required
def share_score():
    data = request.get_json()
    score = data.get('score')
    category = data.get('category')
    platform = data.get('platform')
    text = f"Artikelle.io'da {category} kategorisinde {score} puan yaptım! Sen de dene: https://artikelle.io"
    if platform == 'twitter':
        url = f"https://twitter.com/intent/tweet?text={text}"
    elif platform == 'whatsapp':
        url = f"https://wa.me/?text={text}"
    else:
        return jsonify({'error': 'Geçersiz platform'}), 400
    return jsonify({'url': url})

# -------------------------------------------------------------------
# BAŞARIM KONTROL VE GÜNCELLEME
# -------------------------------------------------------------------

def check_achievements(user_id):
    user = User.query.get(user_id)
    profile = user.profile
    if not profile:
        return
    achievements = Achievement.query.all()
    for ach in achievements:
        existing = UserAchievement.query.filter_by(user_id=user_id, achievement_id=ach.id).first()
        if existing:
            continue
        condition = ach.condition_type
        value = ach.condition_value
        achieved = False
        if condition == 'total_games' and profile.total_games >= value:
            achieved = True
        elif condition == 'total_correct' and profile.total_correct >= value:
            achieved = True
        elif condition == 'total_score' and profile.total_score >= value:
            achieved = True
        elif condition == 'best_score_30sn' and profile.best_score_30sn >= value:
            achieved = True
        elif condition == 'best_score_1dk' and profile.best_score_1dk >= value:
            achieved = True
        elif condition == 'best_score_3dk' and profile.best_score_3dk >= value:
            achieved = True
        elif condition == 'best_score_5dk' and profile.best_score_5dk >= value:
            achieved = True
        if achieved:
            ua = UserAchievement(user_id=user_id, achievement_id=ach.id)
            db.session.add(ua)
            db.session.commit()
            flash(f"🏆 '{ach.name}' başarımını kazandın!", 'success')

def update_daily_challenges(user_id, correct_count, score_value, category):
    today = date.today()
    progresses = UserDailyProgress.query.filter_by(user_id=user_id, date=today, completed=False).all()
    for prog in progresses:
        challenge = DailyChallenge.query.get(prog.challenge_id)
        if not challenge:
            continue
        goal_type = challenge.goal_type
        if goal_type == 'correct_count':
            prog.progress += correct_count
        elif goal_type == 'total_score':
            prog.progress += score_value
        elif goal_type == 'score_in_category' and category == challenge.name.split()[-1]:
            prog.progress = max(prog.progress, score_value)
        if prog.progress >= challenge.goal_value:
            prog.completed = True
            prog.completed_at = datetime.utcnow()
            flash(f"🎉 Günlük görev tamamlandı: {challenge.name}", 'success')
        db.session.commit()

# -------------------------------------------------------------------
# DİL DEĞİŞTİRME
# -------------------------------------------------------------------

@app.route('/set_language/<lang>')
def set_language(lang):
    if lang not in ['tr', 'en']:
        lang = 'tr'
    resp = make_response(redirect(request.referrer or url_for('index')))
    resp.set_cookie('lang', lang, max_age=60*60*24*365)
    return resp

# -------------------------------------------------------------------
# PWA DOSYALARI
# -------------------------------------------------------------------

@app.route('/manifest.json')
def manifest():
    return app.send_static_file('manifest.json')

@app.route('/sw.js')
def service_worker():
    return app.send_static_file('sw.js')

# -------------------------------------------------------------------
# ADMIN PANELİ (Try-Except ile, hata verse de uygulama çalışır)
# -------------------------------------------------------------------

if ADMIN_AVAILABLE:
    try:
        class AdminModelView(ModelView):
            def is_accessible(self):
                return current_user.is_authenticated and current_user.is_admin

            def inaccessible_callback(self, name, **kwargs):
                return redirect(url_for('login', next=request.url))

        class MyAdminIndexView(AdminIndexView):
            def is_accessible(self):
                return current_user.is_authenticated and current_user.is_admin

            def inaccessible_callback(self, name, **kwargs):
                return redirect(url_for('login', next=request.url))

        # Admin panelini oluştur (template_mode parametresi yok - eski sürümlerle uyumlu)
        admin = Admin(app, name='Artikelle Admin', index_view=MyAdminIndexView())
        
        # View'ları ekle
        admin.add_view(AdminModelView(User, db.session))
        admin.add_view(AdminModelView(Word, db.session))
        admin.add_view(AdminModelView(Score, db.session))
        admin.add_view(AdminModelView(UserProfile, db.session))
        admin.add_view(AdminModelView(Achievement, db.session))
        admin.add_view(AdminModelView(UserAchievement, db.session))
        admin.add_view(AdminModelView(DailyChallenge, db.session))
        admin.add_view(AdminModelView(UserDailyProgress, db.session))
        
        print("Admin paneli başarıyla yüklendi.")
    except Exception as e:
        print(f"Admin paneli yüklenirken hata oluştu (ancak uygulama çalışmaya devam ediyor): {e}")
else:
    print("Flask-Admin kurulu olmadığı için admin paneli eklenmedi.")

if __name__ == '__main__':
    app.run(debug=True)
