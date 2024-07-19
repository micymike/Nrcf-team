from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, FloatField, IntegerField
from wtforms.validators import DataRequired, Length, NumberRange
import google.generativeai as genai
import os
import json
import markdown

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback_secret_key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///nrcf_football.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WTF_CSRF_ENABLED'] = True

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Configure the Gemini API
genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))

# Hardcoded coach credentials
COACH_USERNAME = "coach"
COACH_PASSWORD = "nrcf@2024"

# User model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    is_coach = db.Column(db.Boolean, default=False)

# Player model
class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    position = db.Column(db.String(50), nullable=False)
    age = db.Column(db.Integer)
    height = db.Column(db.Float)
    weight = db.Column(db.Float)
    goals = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    matches_played = db.Column(db.Integer, default=0)

# Forms
class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=80)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])

class PlayerForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(max=80)])
    position = StringField('Position', validators=[DataRequired(), Length(max=50)])
    age = IntegerField('Age', validators=[DataRequired(), NumberRange(min=15, max=50)])
    height = FloatField('Height (cm)', validators=[DataRequired(), NumberRange(min=150, max=220)])
    weight = FloatField('Weight (kg)', validators=[DataRequired(), NumberRange(min=50, max=120)])

class PlayerUpdateForm(FlaskForm):
    goals = IntegerField('Goals', validators=[NumberRange(min=0)])
    assists = IntegerField('Assists', validators=[NumberRange(min=0)])
    matches_played = IntegerField('Matches Played', validators=[NumberRange(min=0)])

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        existing_user = User.query.filter_by(username=form.username.data).first()
        if existing_user:
            flash('Username already exists', 'error')
            return redirect(url_for('register'))
        
        new_user = User(
            username=form.username.data,
            password=generate_password_hash(form.password.data, method='pbkdf2:sha256'),
            is_coach=False  # All registered users are players by default
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        if form.username.data == COACH_USERNAME and form.password.data == COACH_PASSWORD:
            # Check if coach user already exists in the database
            coach_user = User.query.filter_by(username=COACH_USERNAME).first()
            if not coach_user:
                # Create coach user if it doesn't exist
                coach_user = User(username=COACH_USERNAME, 
                                  password=generate_password_hash(COACH_PASSWORD, method='pbkdf2:sha256'),
                                  is_coach=True)
                db.session.add(coach_user)
                db.session.commit()
            else:
                # Ensure existing coach user has is_coach set to True
                coach_user.is_coach = True
                db.session.commit()
            
            login_user(coach_user)
            flash('Logged in successfully as Coach', 'success')
            return redirect(url_for('dashboard'))
        else:
            user = User.query.filter_by(username=form.username.data).first()
            if user and check_password_hash(user.password, form.password.data):
                login_user(user)
                flash('Logged in successfully', 'success')
                return redirect(url_for('dashboard'))
        flash('Invalid username or password', 'error')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    players = Player.query.all()
    if current_user.is_coach:
        print("Redirecting to coach dashboard")  # Debug print
        return render_template('coach_dashboard.html', players=players)
    else:
        print("Redirecting to player dashboard")  # Debug print
        return render_template('player_dashboard.html', players=players)

@app.route('/add_player', methods=['GET', 'POST'])
@login_required
def add_player():
    if not current_user.is_coach:
        flash('Only coaches can add players', 'error')
        return redirect(url_for('dashboard'))
    
    form = PlayerForm()
    if form.validate_on_submit():
        new_player = Player(
            name=form.name.data,
            position=form.position.data,
            age=form.age.data,
            height=form.height.data,
            weight=form.weight.data
        )
        db.session.add(new_player)
        db.session.commit()
        flash('Player added successfully', 'success')
        return redirect(url_for('dashboard'))
    return render_template('player_form.html', form=form, title='Add Player')

@app.route('/update_player/<int:player_id>', methods=['GET', 'POST'])
@login_required
def update_player(player_id):
    if not current_user.is_coach:
        flash('Only coaches can update player records', 'error')
        return redirect(url_for('dashboard'))
    
    player = Player.query.get_or_404(player_id)
    form = PlayerUpdateForm(obj=player)
    if form.validate_on_submit():
        form.populate_obj(player)
        db.session.commit()
        flash('Player record updated successfully', 'success')
        return redirect(url_for('dashboard'))
    return render_template('player_form.html', form=form, player=player, title='Update Player')

@app.route('/delete_player/<int:player_id>', methods=['POST'])
@login_required
def delete_player(player_id):
    if not current_user.is_coach:
        flash('Only coaches can delete players', 'error')
        return redirect(url_for('dashboard'))
    
    player = Player.query.get_or_404(player_id)
    db.session.delete(player)
    db.session.commit()
    flash('Player deleted successfully', 'success')
    return redirect(url_for('dashboard'))

@app.route('/generate_tactics', methods=['GET', 'POST'])
@login_required
def generate_tactics():
    if not current_user.is_coach:
        flash('Only coaches can generate tactics', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        players = Player.query.all()
        player_data = [
            {
                "name": p.name,
                "position": p.position,
                "age": p.age,
                "height": p.height,
                "weight": p.weight,
                "goals": p.goals,
                "assists": p.assists,
                "matches_played": p.matches_played
            } for p in players
        ]
        
        prompt = f"""
        As an expert football tactician, analyze the following player data and provide a comprehensive tactical plan:

        {json.dumps(player_data, indent=2)}

        Your analysis should include:
        1. Recommended formation with detailed explanations
        2. Offensive strategies tailored to the team's strengths
        3. Defensive approach considering the team's composition
        4. Set-piece tactics for both attacking and defending
        5. Player roles and key responsibilities
        6. Suggestions for player development and team improvement

        Provide your analysis in a structured format, using markdown for headers and bullet points.
        """
        
        try:
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(prompt)
            tactics_html = markdown.markdown(response.text)
            return render_template('tactics.html', tactics=tactics_html)
        except Exception as e:
            flash(f"Error generating tactics: {str(e)}", 'error')
            return redirect(url_for('dashboard'))
    
    return render_template('tactics.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Ensure coach user exists and has is_coach set to True
        coach_user = User.query.filter_by(username=COACH_USERNAME).first()
        if not coach_user:
            coach_user = User(username=COACH_USERNAME, 
                              password=generate_password_hash(COACH_PASSWORD, method='pbkdf2:sha256'),
                              is_coach=True)
            db.session.add(coach_user)
        else:
            coach_user.is_coach = True
        db.session.commit()
        
    app.run(debug=True)