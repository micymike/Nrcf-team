from functools import cache
from flask import Flask, render_template, request, redirect, send_from_directory, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm, CSRFProtect
from wtforms import StringField, PasswordField, BooleanField, FloatField, IntegerField, FileField
from wtforms.validators import DataRequired, Length, NumberRange, Email
from werkzeug.utils import secure_filename
import google.generativeai as genai
from pymongo import MongoClient
from bson import ObjectId
import os
import json
import markdown

from models import LoginForm, PlayerForm, PlayerUpdateForm, RegistrationForm, User, db

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24).hex()
app.config['WTF_CSRF_ENABLED'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
csrf = CSRFProtect(app)

# MongoDB connection


login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Configure the Gemini API
genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))

# Hardcoded coach credentials
COACH_USERNAME = "coach"
COACH_PASSWORD = "nrcf@2024"

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        existing_user = db.users.find_one({'username': form.username.data})
        if existing_user:
            flash('Username already exists', 'error')
            return redirect(url_for('register'))
        
        new_user = {
            'username': form.username.data,
            'password': generate_password_hash(form.password.data, method='pbkdf2:sha256'),
            'is_coach': False  # All registered users are players by default
        }
        db.users.insert_one(new_user)
        flash('Registration successful. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = db.users.find_one({'username': form.username.data})
        if user and check_password_hash(user['password'], form.password.data):
            # Ensure the coach user has the correct credentials
            if form.username.data == COACH_USERNAME:
                user['is_coach'] = True
                db.users.update_one({'username': COACH_USERNAME}, {'$set': {'is_coach': True}})
            
            login_user(User(user))  # Ensure User instance is passed here
            flash('Logged in successfully', 'success')
            return redirect(url_for('dashboard'))
        else:
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
    players = list(db.players.find())
    if current_user.is_coach:
        return render_template('coach_dashboard.html', players=players)
    else:
        return render_template('player_dashboard.html', players=players)

@app.route('/add_player', methods=['GET', 'POST'])
@login_required
def add_player():
    if not current_user.is_coach:
        flash('Only coaches can add players', 'error')
        return redirect(url_for('dashboard'))
    
    form = PlayerForm()
    if form.validate_on_submit():
        new_player = {
            'name': form.name.data,
            'position': form.position.data,
            'age': form.age.data,
            'height': form.height.data,
            'weight': form.weight.data,
            'goals': 0,
            'assists': 0,
            'matches_played': 0
        }
        if form.picture.data:
            filename = secure_filename(form.picture.data.filename)
            form.picture.data.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            new_player['picture'] = filename
        db.players.insert_one(new_player)
        flash('Player added successfully', 'success')
        return redirect(url_for('dashboard'))
    return render_template('player_form.html', form=form, title='Add Player')

@app.route('/update_player/<player_id>', methods=['GET', 'POST'])
@login_required
def update_player(player_id):
    if not current_user.is_coach:
        flash('Only coaches can update player records', 'error')
        return redirect(url_for('dashboard'))
    
    player = db.players.find_one({'_id': ObjectId(player_id)})
    if not player:
        flash('Player not found', 'error')
        return redirect(url_for('dashboard'))
    
    form = PlayerUpdateForm(obj=player)
    if form.validate_on_submit():
        update_data = {
            'goals': form.goals.data,
            'assists': form.assists.data,
            'matches_played': form.matches_played.data
        }
        
        if form.picture.data:
            filename = secure_filename(form.picture.data.filename)
            if filename:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                form.picture.data.save(file_path)
                update_data['picture'] = filename
        
        db.players.update_one({'_id': ObjectId(player_id)}, {'$set': update_data})
        flash('Player record updated successfully', 'success')
        return redirect(url_for('dashboard'))
    return render_template('player_form.html', form=form, player=player, title='Update Player')

@app.route('/delete_player/<player_id>', methods=['POST'])
@login_required
def delete_player(player_id):
    if not current_user.is_coach:
        flash('Only coaches can delete players', 'error')
        return redirect(url_for('dashboard'))
    
    result = db.players.delete_one({'_id': ObjectId(player_id)})
    if result.deleted_count:
        flash('Player deleted successfully', 'success')
    else:
        flash('Player not found', 'error')
    return redirect(url_for('dashboard'))

@app.route('/generate_tactics', methods=['GET', 'POST'])
@login_required
def generate_tactics():
    if not current_user.is_coach:
        flash('Only coaches can generate tactics', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        players = list(db.players.find({}, {'_id': 0}))
        prompt = f"""
        As an expert football tactician, analyze the following player data and provide a comprehensive tactical plan:

        {json.dumps(players, indent=2)}

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

@app.route('/update_profile', methods=['GET', 'POST'])
@login_required
def update_profile():
    form = PlayerUpdateForm(obj=current_user)
    if form.validate_on_submit():
        update_data = {
            'username': form.username.data,
        }
        if form.password.data:
            update_data['password'] = generate_password_hash(form.password.data, method='pbkdf2:sha256')
        db.users.update_one({'_id': ObjectId(current_user.id)}, {'$set': update_data})
        flash('Profile updated successfully', 'success')
        return redirect(url_for('dashboard'))
    return render_template('update_profile.html', form=form)

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form['email']
        user = db.users.find_one({'email': email})
        if user:
            # Add logic to send password reset email/link
            flash('Password reset instructions have been sent to your email.', 'info')
        else:
            flash('Email not found', 'error')
        return redirect(url_for('login'))
    return render_template('reset_password.html')

@app.route('/search_players', methods=['GET'])
@login_required
def search_players():
    if not current_user.is_coach:
        flash('Only coaches can search players', 'error')
        return redirect(url_for('dashboard'))
    
    query = request.args.get('query', '')
    players = list(db.players.find({'name': {'$regex': query, '$options': 'i'}}))
    return render_template('coach_dashboard.html', players=players)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Route to delete a file
@app.route('/delete/<filename>', methods=['POST'])
def delete_file(filename):
    try:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            flash('File successfully deleted.', 'success')
        else:
            flash('File not found.', 'error')
    except Exception as e:
        flash(str(e), 'error')
    return redirect(url_for('post'))

# Render the post template with file data
@app.route('/post')
def post():
    files = [{'name': f, 'path': f} for f in os.listdir(app.config['UPLOAD_FOLDER']) if os.path.isfile(os.path.join(app.config['UPLOAD_FOLDER'], f))]
    return render_template('post.html', files=files)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    # Ensure coach user exists and has is_coach set to True
    coach_user = db.users.find_one({'username': COACH_USERNAME})
    if not coach_user:
        coach_user = {
            'username': COACH_USERNAME,
            'password': generate_password_hash(COACH_PASSWORD, method='pbkdf2:sha256'),
            'is_coach': True
        }
        db.users.insert_one(coach_user)
    else:
        db.users.update_one({'username': COACH_USERNAME}, {'$set': {'is_coach': True}})
    
    app.run(debug=True)
