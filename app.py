from flask import Flask, render_template, url_for, redirect, request, session, flash
from sejong_univ_auth import auth, ClassicSession
from bson.objectid import ObjectId 
import functools
import bcrypt 
import secrets
from datetime import datetime
import pymongo


client = pymongo.MongoClient("mongodb://localhost:27017/") 
db = client["virtual_tour"] 
user_collection = db['user'] 
post_collection = db['post'] 
post_comment_collection = db['post_comment']

app = Flask(__name__)

app.secret_key = secrets.token_hex(32)

PAGE_SIZE = 10

def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        _id = session.get('_id')

        if _id is None:
            return redirect(url_for('login'))
        
        return view(**kwargs)
    return wrapped_view

@app.route('/')
def home():
    return render_template("home.html")

# community 시작

@app.route('/community')
def post_list():
    page = request.args.get('page', default = 0, type = int)
    page_offset = page * PAGE_SIZE
    
    post_count = post_collection.count_documents({})
    posts = post_collection.find().sort("create_date", pymongo.DESCENDING).skip(page_offset).limit(PAGE_SIZE)

    return render_template("post_list.html", posts = posts, page = page, post_count = post_count, page_size = PAGE_SIZE)


@app.route('/community/post/write', methods=['GET', 'POST'])
@login_required
def post_write():
    if request.method == 'GET':
        return render_template("post_form.html")
    
    #POST
    title = request.form['title'].strip()
    content = request.form['content'].strip()

    post_data = {
        'title' : title,
        'content' : content,
        'create_date' : datetime.now(),
        'author' : session['nickname'],
        'author_id' : session['_id'],
        'view_count' : 0
    }

    result = post_collection.insert_one(post_data)

    return redirect(url_for('post_detail', id=str(result.inserted_id)))

@app.route('/community/post/<id>')
def post_detail(id):
    increase_view_count(id)

    post = post_collection.find_one({"_id" : ObjectId(id)})
    comments = list(get_comments(id))
    
    return render_template("post_detail.html", post = post, comments = comments)

def increase_view_count(id):
    filter = {"_id" : ObjectId(id)}

    post = post_collection.find_one(filter)

    data ={
    "$set" : {
        "view_count" : post["view_count"]+1,
        }
    }

    post_collection.update_one(filter, data)
    

@app.route('/community/post/modify/<id>', methods=['GET', 'POST'])
@login_required
def post_modify(id):
    if request.method == 'GET':
        post = post_collection.find_one({"_id" : ObjectId(id)})

        return render_template("post_form.html", post = post)
    
    #POST
    filter = {"_id" : ObjectId(id)}

    title = request.form['title'].strip()
    content = request.form['content'].strip()
    data ={
    "$set" : {
        'title' : title,
        'content' : content,
        'modify_date' : datetime.now()
        }
    }

    post_collection.update_one(filter, data)

    return redirect(url_for('post_detail', id=id))

@app.route('/community/post/delete/<id>')
@login_required
def post_delete(id):
    filter = {"_id" : ObjectId(id)}

    post_collection.delete_one(filter)

    return redirect(url_for('post_list'))

# 댓글 시작

@app.route('/community/post/<id>/comment/write', methods = ["POST"])
def comment_write(id):
    content = request.form["comment_content"].strip()
    author_id = session.get("_id")
    author_name = session.get("nickname")

    data = {
        "post_id" : ObjectId(id),
        "content" : content,
        "author_id" : author_id,
        "author_name" : author_name,
        "create_date" : datetime.now()
    }

    post_comment_collection.insert_one(data)

    return redirect(url_for('post_detail', id=id))

@app.route('/community/post/<post_id>/comment/delete/<comment_id>')
def comment_delete(post_id, comment_id):
    filter = {"_id" : ObjectId(comment_id)}
    post_comment_collection.delete_one(filter)

    return redirect(url_for('post_detail', id = post_id))

def get_comments(id):
    comments = post_comment_collection.find({"post_id" : ObjectId(id)}).sort("create_date", pymongo.DESCENDING)

    return comments

# community 끝


# mypage 시작
@app.route('/mypage')
@login_required
def mypage_show():
    user = user_collection.find_one({"_id" : ObjectId(session["_id"])})

    
    
    return

# mypage 끝

# 회원 기능 시작

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == "GET":
        return render_template("signup.html")
    
    #POST
    #sejong auth 시작
    sejong_id = request.form['sejong_id'].strip()
    sejong_password = request.form['sejong_password'].strip()

    result = auth(sejong_id, sejong_password, methods=ClassicSession)
    if result.success == False:
        flash('학번과 비밀번호를 다시 한번 확인해주세요.')
        return redirect(url_for('signup'))
    
    student_id = sejong_id
    major = result.body['major']
    name = result.body['name']
    grade = result.body['grade']
    status = result.body['status']

    #sejong auth 끝

    nickname = request.form['nickname'].strip()
    nickname_check = user_collection.find_one({"nickname": nickname})
    if nickname_check:
        flash('Nickname is in use. Please choose another nickname.')
        return redirect(url_for('signup'))

    email = request.form['email'].strip()
    email_check = user_collection.find_one({"email": email})
    if email_check:
        flash('Email is in use. Please use another email.')
        return redirect(url_for('signup'))

    password = request.form['password'].strip()
    password_confirm = request.form['password_confirm'].strip()
    if password != password_confirm:
        flash('Please confirm password.')
        return redirect(url_for('signup'))

    encrypted_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    user_data = {
        'nickname' : nickname,
        'email' : email,
        'password' : encrypted_password,
        'create_date' : datetime.now(),

        'student_id' : student_id,
        'major' : major,
        'name' : name,
        'grade' : grade,
        'status' : status
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
            session["_id"] = str(user_data['_id'])
            session["nickname"] = user_data['nickname']
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

# 회원 기능 끝

if __name__ == '__main__':
    app.run(debug=True) 