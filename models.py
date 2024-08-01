# User model
from flask_login import UserMixin
from wtforms import FileField, FloatField, IntegerField, PasswordField, StringField
from wtforms.validators import DataRequired, Length, NumberRange
from flask_wtf import FlaskForm
from bson import ObjectId
from pymongo import MongoClient

# Assuming you have a MongoDB setup
client = MongoClient('mongodb+srv://mikemoses:mikemoses@cluster0.jvbhvc3.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
db = client['nrcf_football']

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.username = user_data['username']
        self.password = user_data['password']
        self.is_coach = user_data.get('is_coach', False)

    @staticmethod
    def get(user_id):
        user_data = db.users.find_one({'_id': ObjectId(user_id)})
        return User(user_data) if user_data else None

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
    picture = FileField('Profile Picture')

class PlayerUpdateForm(FlaskForm):
    goals = IntegerField('Goals', validators=[NumberRange(min=0)])
    assists = IntegerField('Assists', validators=[NumberRange(min=0)])
    matches_played = IntegerField('Matches Played', validators=[NumberRange(min=0)])
    picture = FileField('Profile Picture')

# Formation model
class Formation:
    def __init__(self, formation_data):
        self.id = str(formation_data['_id'])
        self.coach_id = str(formation_data['coach_id'])
        self.formation = formation_data['formation']

    @staticmethod
    def save_formation(coach_id, formation_data):
        formation = {
            'coach_id': ObjectId(coach_id),
            'formation': formation_data
        }
        result = db.formations.insert_one(formation)
        return str(result.inserted_id)

    @staticmethod
    def get_formation(formation_id):
        formation_data = db.formations.find_one({'_id': ObjectId(formation_id)})
        return Formation(formation_data) if formation_data else None
