from flask import Flask, request, session, redirect, url_for, render_template_string,render_template
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson import ObjectId
import os
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.jinja_env.auto_reload = True
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.secret_key = 'your-secret-key'

# MongoDB Setup
client = MongoClient("mongodb://localhost:27017/")
db = client['book_exchange']    
users_collection = db['users']
books_collection=db['books']
messages_collection=db['messages']



@app.route('/')
def home():
    username = session.get('username')
    return render_template('home.html', username=username)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if users_collection.find_one({'username': username}):
            return "Username already exists."

        hashed_pw = generate_password_hash(password)
        users_collection.insert_one({'username': username, 'password': hashed_pw})
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = users_collection.find_one({'username': username})
        if user and check_password_hash(user['password'], password):
            session['username'] = username
            return redirect(url_for('home'))

        return "Invalid credentials"

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('home'))


@app.route('/post_book', methods=['GET', 'POST'])
def post_book():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        description = request.form.get('description', '')
        image = request.files.get('image')
        image_filename = None

        if image and allowed_file(image.filename):
            filename = secure_filename(image.filename)
            image_filename = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image.save(image_filename)

        books_collection.insert_one({
            'title': title,
            'author': author,
            'description': description,
            'owner': session['username'],
            'available': True,
            'image': image_filename
        })
        return redirect(url_for('view_books'))

    return render_template('post_book.html')

app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

# Create the upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


@app.route('/books')
def view_books():
    query = request.args.get('q', '')
    if query:
        books = books_collection.find({
            "$and": [
                {"available": True},
                {"$or": [
                    {"title": {"$regex": query, "$options": "i"}},
                    {"author": {"$regex": query, "$options": "i"}}
                ]}
            ]
        })
    else:
        books = books_collection.find({"available": True})
    return render_template('browse_books.html', books=books)




# Borrow a Book
@app.route('/borrow/<book_id>', methods=['POST'])
def borrow_book(book_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    book = books_collection.find_one({"_id": ObjectId(book_id)})
    if not book:
        return "Book not found."

    if book['owner'] == session['username']:
        return "You can't borrow your own book."

    if not book['available']:
        return "Sorry, book is already borrowed."

    books_collection.update_one(
        {"_id": ObjectId(book_id)},
        {"$set": {
            "available": False,
            "borrower": session['username']
        }}
    )
    return redirect(url_for('view_books'))


# Return Book
@app.route('/return/<book_id>', methods=['POST'])
def return_book(book_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    book = books_collection.find_one({'_id': ObjectId(book_id)})
    if not book or book.get('borrower') != session['username']:
        return "You can’t return this book."

    books_collection.update_one(
        {'_id': ObjectId(book_id)},
        {'$set': {'available': True}, '$unset': {'borrower': ""}}
    )
    return redirect(url_for('my_books'))


# User Dashboard
@app.route('/my_books')
def my_books():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    borrowed_books = books_collection.find({'borrower': username})
    posted_books = books_collection.find({'owner': username})


    return render_template('my_books.html', borrowed_books=borrowed_books, posted_books=posted_books)



# Chat System
@app.route('/chat/<book_id>', methods=['GET', 'POST'])
def chat(book_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    user = session['username']
    book = books_collection.find_one({'_id': ObjectId(book_id)})

    if not book:
        return "Book not found."

    if user != book['owner'] and user != book.get('borrower'):
        return "You don’t have permission to chat on this book."

    if request.method == 'POST':
        message = request.form['message']
        if message:
            messages_collection.insert_one({
                'book_id': book_id,
                'sender': user,
                'recipient': book['borrower'] if user == book['owner'] else book['owner'],
                'text': message
            })

    messages = list(messages_collection.find({'book_id': book_id}))

  
    return render_template('chat.html', book=book, messages=messages)


@app.route('/profile')
def profile():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    posted_books = list(books_collection.find({'owner': username}))
    borrowed_books = list(books_collection.find({'borrower': username}))

    return render_template('profile.html', username=username, posted_books=posted_books, borrowed_books=borrowed_books)



if __name__ == '__main__':
    app.run(debug=True)
