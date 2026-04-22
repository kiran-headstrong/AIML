import os
from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# Get DB URL from environment
# Defaults to a local file 'db.sqlite'
DB_URL = os.environ.get(
    'DATABASE_URL',
    'sqlite:///db.sqlite'
)
app.config['SQLALCHEMY_DATABASE_URI'] = DB_URL
db = SQLAlchemy(app)

class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)

@app.route('/')
def index():
    todos = Todo.query.all()
    # this uses a template file we'll create
    return render_template('index.html', todos=todos)

@app.route('/add', methods=['POST'])
def add():
    title = request.form.get('title')
    new_todo = Todo(title=title)
    db.session.add(new_todo)
    db.session.commit()
    return 'Added!' # A real app would redirect
