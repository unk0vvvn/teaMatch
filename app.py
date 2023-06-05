from flask import Flask, render_template, url_for, redirect, request, session, flash
from werkzeug.utils import secure_filename
from sejong_univ_auth import auth, ClassicSession
from bson.objectid import ObjectId 
import functools
import bcrypt 
import secrets
from datetime import datetime
import pymongo
import pandas
import os

client = pymongo.MongoClient("mongodb://localhost:27017/") 
db = client["virtual_tour"] 
user_collection = db['user'] 
post_collection = db['post'] 
post_collection.create_index([('title', 'text'),('content', 'text')])

comment_collection = db['comment']

recruit_collection = db['recruit']
recruit_collection.create_index([('title', 'text'),('content', 'text')])

configure_collection = db['configure']

app = Flask(__name__)

app.secret_key = secrets.token_hex(32)

PAGE_SIZE = 10
FILE_UPLOAD_PATH = "./upload/"

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
    #설정 데이터 삽입. 기본 데이터 같이 들고 다닐 수 있는 방법 찾기
    if configure_collection.find_one({'name': '포지션'}) is None:
        configure_collection.insert_one({
            'name': '포지션',
            'positions': ['AI', 'FRONTEND', 'BACKEND', 'SECURITY']
        })

    #설정 데이터 끝
    posts = post_collection.find().sort("view_count", pymongo.DESCENDING).limit(PAGE_SIZE//2)
    recruits = recruit_collection.find().sort("view_count", pymongo.DESCENDING).limit(PAGE_SIZE//2)

    return render_template("home.html", posts = posts, recruits = recruits)

def get_positions():
    return configure_collection.find_one({"name":"포지션"})['positions']

#댓글 공통 함수

def create_comment(parent_id, content, author_id, author_name):
    data = {
        "parent_id" : ObjectId(parent_id),
        "content" : content,
        "author_id" : author_id,
        "author_name" : author_name,
        "create_date" : datetime.now().strftime('%Y-%m-%d, %H:%M:%S')
    }

    comment_collection.insert_one(data)


def delete_comment(comment_id):
    comment_collection.delete_one({"_id" : ObjectId(comment_id)})

def get_comments(id):
    comments = comment_collection.find({"parent_id" : ObjectId(id)}).sort("create_date", pymongo.DESCENDING)

    return comments

#댓글 공통함수 끝

# 팀원 모집 recruit 시작

@app.route('/recruit')
def recruit_list():
    keyword = request.args.get('keyword', default = '', type = str).strip()
    filter = {}
    if keyword != '':
        filter = {
            "$text": 
                {"$search": keyword}
            }
        
    page = request.args.get('page', default = 0, type = int)
    page_offset = page * PAGE_SIZE
    
    recruit_count = recruit_collection.count_documents(filter)
    recruits = recruit_collection.find(filter).sort("create_date", pymongo.DESCENDING).skip(page_offset).limit(PAGE_SIZE)

    return render_template("recruit_list.html", recruits = recruits, page = page, recruit_count = recruit_count, page_size = PAGE_SIZE)

@app.route('/recruit/write', methods=['GET', 'POST'])
@login_required
def recruit_write():
    if request.method == 'GET':
        return render_template("recruit_form.html", positions = get_positions())
    
    #POST
    title = request.form['title'].strip()
    content = request.form['content'].strip()
    required_positions = request.form.getlist('required_positions')

    data = {
        'title' : title,
        'content' : content,
        'required_positions' : required_positions,
        'create_date' : datetime.now().strftime('%Y-%m-%d, %H:%M:%S'),
        'leader' : session['nickname'],
        'leader_id' : session['_id'],
        'applicants' : [],
        'view_count' : 0
    }

    result = recruit_collection.insert_one(data)

    return redirect(url_for('recruit_detail', id=str(result.inserted_id)))

@app.route('/recruit/<id>')
def recruit_detail(id):
    recruit_collection.update_one({"_id" : ObjectId(id)},
                                {
                                '$inc': {
                                    'view_count':1
                                }})

    recruit = recruit_collection.find_one({"_id" : ObjectId(id)})
    comments = list(get_comments(id))
    
    return render_template("recruit_detail.html", recruit = recruit, comments = comments)

@app.route('/recruit/modify/<id>', methods=['GET', 'POST'])
@login_required
def recruit_modify(id):
    if request.method == 'GET':
        recruit = recruit_collection.find_one({"_id" : ObjectId(id)})

        return render_template("recruit_form.html", recruit = recruit, positions = get_positions())
    
    #POST
    filter = {"_id" : ObjectId(id)}

    title = request.form['title'].strip()
    content = request.form['content'].strip()
    required_positions = request.form.getlist('required_positions')
    data ={
    "$set" : {
        'title' : title,
        'content' : content,
        'required_positions' : required_positions,
        'modify_date' : datetime.now().strftime('%Y-%m-%d, %H:%M:%S')
        }
    }

    recruit_collection.update_one(filter, data)

    return redirect(url_for('recruit_detail', id=id))

@app.route('/recruit/delete/<id>')
@login_required
def recruit_delete(id):
    recruit_collection.delete_one({"_id" : ObjectId(id)})

    return redirect(url_for('recruit_list'))

@app.route('/recruit/apply/<id>')
@login_required
def recruit_apply(id):
    applicant_id = ObjectId(session['_id'])
    filter = {'_id' : ObjectId(id)}
    result = recruit_collection.find_one(filter, {'applicants':1, '_id':0})['applicants']
    for r in result:
        print(r)
        if r == applicant_id:
            flash('이전에 지원한 프로젝트입니다.')
            return redirect(url_for('recruit_detail', id=id))

    data ={
    '$push' : {
        'applicants':applicant_id
        }   
    }
    recruit_collection.update_one(filter, data)

    return redirect(url_for('recruit_detail', id=id))

#recruit 댓글 시작

@app.route('/recruit/<id>/comment/write', methods = ["POST"])
def recruit_comment_write(id):
    content = request.form["comment_content"].strip()
    author_id = session.get("_id")
    author_name = session.get("nickname")
    create_comment(id, content, author_id, author_name)

    recruit_collection.update_one({'_id' : ObjectId(id)}, 
                               {'$inc': {'comment_count': 1}})

    return redirect(url_for('recruit_detail', id=id))

@app.route('/recruit/<recruit_id>/comment/delete/<comment_id>')
def recruit_comment_delete(recruit_id, comment_id):
    delete_comment(comment_id)

    recruit_collection.update_one({'_id' : ObjectId(recruit_id)}, 
                               {'$inc': {'comment_count': -1}})

    return redirect(url_for('recruit_detail', id = recruit_id))

#recruit 댓글 끝

# 팀원 모집 recruit 끝


# community 시작

@app.route('/community')
def post_list():
    keyword = request.args.get('keyword', default = '', type = str).strip()
    filter = {}
    if keyword != '':
        filter = {
            "$text": 
                {"$search": keyword}
            }

    page = request.args.get('page', default = 0, type = int)
    page_offset = page * PAGE_SIZE
    
    post_count = post_collection.count_documents(filter)
    posts = post_collection.find(filter).sort("create_date", pymongo.DESCENDING).skip(page_offset).limit(PAGE_SIZE)

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
        'create_date' : datetime.now().strftime('%Y-%m-%d, %H:%M:%S'),
        'author' : session['nickname'],
        'author_id' : session['_id'],
        'view_count' : 0
    }

    result = post_collection.insert_one(post_data)

    return redirect(url_for('post_detail', id=str(result.inserted_id)))

@app.route('/community/post/<id>')
def post_detail(id):
    post_collection.update_one({"_id" : ObjectId(id)},
                                {
                                '$inc': {
                                    'view_count':1
                                }})

    post = post_collection.find_one({"_id" : ObjectId(id)})
    comments = list(get_comments(id))
    
    return render_template("post_detail.html", post = post, comments = comments)
    
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
        'modify_date' : datetime.now().strftime('%Y-%m-%d, %H:%M:%S')
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

#community 댓글 시작

@app.route('/community/post/<id>/comment/write', methods = ["POST"])
def community_comment_write(id):
    content = request.form["comment_content"].strip()
    author_id = session.get("_id")
    author_name = session.get("nickname")
    create_comment(id, content, author_id, author_name)

    post_collection.update_one({'_id' : ObjectId(id)}, 
                               {'$inc': {'comment_count': 1}})

    return redirect(url_for('post_detail', id=id))

@app.route('/community/post/<post_id>/comment/delete/<comment_id>')
def community_comment_delete(post_id, comment_id):
    delete_comment(comment_id)
    post_collection.update_one({'_id' : ObjectId(post_id)}, 
                               {'$inc': {'comment_count': -1}})

    return redirect(url_for('post_detail', id = post_id))

#community 댓글 끝


# community 끝


# mypage 시작
@app.route('/mypage')
@login_required
def mypage_show():
    user = user_collection.find_one({"_id" : ObjectId(session["_id"])})

    return render_template("mypage.html", user = user)

@app.route('/mypage/update', methods=["GET", "POST"])
@login_required
def mypage_update():
    if request.method == "GET":
        user = user_collection.find_one({"_id" : ObjectId(session["_id"])})
        positions = get_positions()

        return render_template("mypage_form.html", user = user, positions = positions)
    
    #post

    data_setter = {'position' : request.form['position']}
    if request.form['github_link'] != '':
        data = request.form['github_link'].strip() 

        data_setter['github_link'] = data

    if request.files['scholarship_history_file'].filename != '':
        file = request.files['scholarship_history_file']
        file.filepath = f'{FILE_UPLOAD_PATH}{secure_filename(file.filename)}'
        data = process_scholarship_history(file)

        data_setter['scholarship_history'] = data

    if request.files['course_history_file'].filename != '':
        file = request.files['course_history_file']
        file.filepath = f'{FILE_UPLOAD_PATH}{secure_filename(file.filename)}'
        course_history, gpa, major_gpa = process_course_history(file)

        transcript = {
            'course_history' : course_history,
            'gpa' : gpa,
            'major_gpa' : major_gpa
        }
        data_setter['transcript'] = transcript

    if request.form['self_introduction'] != '':
        data = request.form['self_introduction'].strip() 

        data_setter['self_introduction'] = data
        
    filter = {'_id' : ObjectId(session['_id'])}
    data ={
        "$set" : data_setter
    }
    user_collection.update_one(filter, data)

    return redirect(url_for('mypage_show'))

def process_scholarship_history(file):
    file.save(file.filepath)

    df = pandas.read_excel(file.filepath, usecols=[1, 2], skiprows=[0,1,2])

    ret = {}
    for row in df.iterrows():
        k = row[1]['년도/학기']
        v = row[1]['장학명']

        if k in ret:
            ret[k].append(v)
        else:
            ret[k] = [v]

    os.unlink(file.filepath)

    return ret

def process_course_history(file):
    file.save(file.filepath)

    df = pandas.read_excel(file.filepath, usecols=[1, 2, 4, 5, 8, 9, 11], skiprows=[0,1,2])

    total_credit = 0
    total_grade = 0

    major_credit = 0
    major_grade = 0
    course_history = {}
    for row in df.iterrows():
        k = f"{row[1]['년도']}/{row[1]['학기']}"
        data = {
            '교과목명':row[1]['교과목명'],
            '이수구분':row[1]['이수구분'],
            '학점':row[1]['학점'],
            '평가방식':row[1]['평가방식'],
            '평점':row[1]['평점']
        }
        if k in course_history:
            course_history[k].append(data)
        else:
            course_history[k] = [data]

        if row[1]['평가방식'] == 'P/NP':
            continue

        total_credit += row[1]['학점']
        total_grade += row[1]['평점'] * row[1]['학점']

        if '전선' == row[1]['이수구분'] or '전필' == row[1]['이수구분']:
            major_credit += row[1]['학점']
            major_grade += row[1]['평점'] * row[1]['학점']

    gpa = round(total_grade / total_credit, 2)
    major_gpa = round(major_grade / major_credit, 2)

    os.unlink(file.filepath)

    return course_history, gpa, major_gpa

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
        'create_date' : datetime.now().strftime('%Y-%m-%d, %H:%M:%S'),

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
    app.run(debug=True, port=5500) 