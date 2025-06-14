#this is a change
#this is a change

from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime, timedelta
import logging
from openai import OpenAI
import httpx

# ... 其他代码 ...

# 明确禁用代理
http_client = httpx.Client(proxies=None)

# ... 后续使用 http_client 进行请求 ...
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)

# 设置数据库路径指向 instance 目录中的数据库文件
app.config['SQLALCHEMY_BINDS'] = {
    'users': 'sqlite:///' + os.path.join(app.instance_path, 'user.db'),
    'chat': 'sqlite:///' + os.path.join(app.instance_path, 'chat.db')
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['UPLOAD_FOLDER'] = os.path.join(app.instance_path, 'uploads')

# 确保 instance 文件夹存在
os.makedirs(app.instance_path, exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

logging.basicConfig(level=logging.DEBUG)

# client = OpenAI(
#     base_url="https://api.xiaoai.plus/v1",
#     api_key="sk-02r8CJ90aT5pot5EODezQmESFKxHtYhosUnOLpwjUy4CquOk",
#     http_client=httpx.Client(
#         base_url="https://api.xiaoai.plus/v1",
#         follow_redirects=True,
#     ),
# )
client = OpenAI(
    base_url="https://xiaoai.plus/v1/",
    api_key="sk-02r8CJ90aT5pot5EODezQmESFKxHtYhosUnOLpwjUy4CquO", # 确保这里是您自己的有效密钥
    http_client=httpx.Client(
        base_url="https://xiaoai.plus/v1", # 这个 base_url 要与上面的 base_url 保持一致
        follow_redirects=True,
        proxy=None, # <-- 添加这一行，明确禁用代理
        timeout=30.0, # 可以尝试增加超时时间，以便有足够时间建立连接
    ),
)
# 定义用户模型
class User(UserMixin, db.Model):
    __bind_key__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    resume_content = db.Column(db.Text, nullable=True)  # 增加保存简历内容的字段

# 定义会话模型
class Conversation(db.Model):
    __bind_key__ = 'chat'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    chats = db.relationship('Chat', backref='conversation', lazy=True, cascade='all, delete-orphan')

# 定义对话记录的模型
class Chat(db.Model):
    __bind_key__ = 'chat'
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    user_id = db.Column(db.String(50), nullable=False)
    ai_id = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def get_content(self):
        return self.content

    def get_timestamp(self):
        return (self.timestamp + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')

# 创建所有数据库表
with app.app_context():
    db.create_all('users')
    db.create_all('chat')
    logging.debug("Database tables created")
    logging.debug(f"User database file path: {os.path.abspath(os.path.join(app.instance_path, 'user.db'))}")
    logging.debug(f"Chat database file path: {os.path.abspath(os.path.join(app.instance_path, 'chat.db'))}")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(username=username, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/index')
@login_required
def index():
    return render_template('index.html')

def parse_pdf(file_path):
    import PyPDF2
    reader = PyPDF2.PdfReader(file_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text()
    return text

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        pdf_text = parse_pdf(file_path)
        current_user.resume_content = pdf_text
        db.session.commit()
        flash('Resume uploaded successfully')
        return redirect(url_for('index'))

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    data = request.get_json()
    user_message = data.get('message')
    resume_content = current_user.resume_content or "No resume uploaded."
    messages = [
        {"role": "system", "content": "You're a student who's having an interview, and now I'm going to send you my resume, and I'm going to ask you questions as the interviewer, and you're going to answer my questions in conjunction with your resume"},
        {"role": "user", "content": "Here is my resume: " + resume_content},
        {"role": "user", "content": user_message}
    ]
    completion = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages
    )
    response = completion.choices[0].message.content
    return jsonify({'response': response})

@app.route('/chat/history', methods=['GET'])
@login_required
def chat_history():
    search_term = request.args.get('searchTerm')
    records = Chat.query.filter(Chat.content.contains(search_term)).all()
    return jsonify({'records': [r.get_content() for r in records]})

@app.route('/chat/history/list', methods=['GET'])
@login_required
def chat_history_list():
    records = Conversation.query.order_by(Conversation.timestamp.desc()).all()
    return jsonify({'records': [{'id': r.id, 'timestamp': (r.timestamp + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')} for r in records]})

@app.route('/chat/history/<int:conversation_id>', methods=['GET'])
@login_required
def get_conversation(conversation_id):
    records = Chat.query.filter_by(conversation_id=conversation_id).all()
    return jsonify({'records': [{'content': r.get_content(), 'timestamp': r.get_timestamp()} for r in records]})

@app.route('/chat/record', methods=['POST'])
@login_required
def save_record():
    data = request.get_json()
    logging.debug(f"Received data: {data}")

    conversation = Conversation(
        user_id=data.get('user_id', 'default_user'),
        timestamp=datetime.utcnow()
    )
    db.session.add(conversation)
    db.session.commit()

    for message in data.get('messages', []):
        chat_record = Chat(
            conversation_id=conversation.id,
            user_id=data.get('user_id', 'default_user'),
            ai_id=data.get('ai_id', 'default_ai'),
            content=message['content'],
            timestamp=datetime.utcnow()
        )
        db.session.add(chat_record)

    db.session.commit()
    logging.debug(f"Saved conversation with ID: {conversation.id}")
    return jsonify({'message': 'Conversation saved successfully', 'id': conversation.id})

@app.route('/chat/record/<int:conversation_id>', methods=['DELETE'])
@login_required
def delete_record(conversation_id):
    conversation = Conversation.query.get(conversation_id)
    if conversation:
        db.session.delete(conversation)
        db.session.commit()
        return jsonify({'message': 'Conversation deleted successfully', 'id': conversation_id})
    return jsonify({'message': 'Conversation not found'}), 404

@app.route('/delete_all', methods=['POST'])
def delete_all():
    db.drop_all(bind='users')
    db.drop_all(bind='chat')
    db.create_all(bind='users')
    db.create_all(bind='chat')
    logging.debug("All data deleted and tables recreated.")
    return jsonify({'message': 'All data deleted and tables recreated.'})

@app.route('/insert_test_data')
def insert_test_data():
    conversation = Conversation(
        user_id='test_user',
        timestamp=datetime.utcnow()
    )
    db.session.add(conversation)
    db.session.commit()

    chat_record = Chat(
        conversation_id=conversation.id,
        user_id='test_user',
        ai_id='test_ai',
        content='This is a test message.',
        timestamp=datetime.utcnow()
    )
    db.session.add(chat_record)
    db.session.commit()
    logging.debug("Test data inserted")
    return "Test data inserted."

if __name__ == '__main__':
    app.run(debug=True)
