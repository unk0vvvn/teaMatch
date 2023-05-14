from flask import Flask, render_template, url_for, redirect, request, session, flash
from pymongo import MongoClient 
from bson.objectid import ObjectId 
import functools
import bcrypt 
from datetime import datetime

client = MongoClient("mongodb://localhost:27017/") 
db = client["virtual_tour"] 
user_collection = db['user'] 

app = Flask(__name__)

app.secret_key = 'fad62b7c1a6a9e67dbb66c3571a23ff2425650965f80047ea2fadce543b088cf'

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        user_email = session.get('user_email')

        if user_email is None:
            return redirect(url_for('login'))
        
        return view(**kwargs)
    return wrapped_view

@app.route('/')
def home():
    return render_template("home.html")

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == "GET":
        return render_template("signup.html")
    
    #POST
    email = request.form['email'].strip()
    password = request.form['password'].strip()
    password_confirm = request.form['password_confirm'].strip()

    email_check = user_collection.find_one({"email": email})
    if email_check:
        flash('Email is in use. Please use another email.')
        return redirect(url_for('signup'))
    
    if password != password_confirm:
        flash('Please confirm password.')
        return redirect(url_for('signup'))
    
    encrypted_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    user_data = {
        'email' : email,
        'password' : encrypted_password,
        'create_date' : datetime.now(),
        'role' : 'user' # TODO: enum 클래스로 변경 
    }

    user_collection.insert_one(user_data)

    flash('Signup successed! Please login.')
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == "GET":
        return render_template("login.html")    
    
    #POST 
    email = request.form['email'].strip()
    password = request.form['password'].strip()

    user_data = user_collection.find_one({"email": email})

    if user_data:
        user_data_password = user_data['password']
        if bcrypt.checkpw(password.encode('utf-8'), user_data_password):
            session["user_email"] = email
            return redirect(url_for('home'))
        else:
            flash('Email/password is invalid. Please try again.')
            return redirect(url_for('login'))
    else:
        flash('Email/password is invalid. Please try again.')
        return redirect(url_for('login'))
    
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.run(debug=True) 