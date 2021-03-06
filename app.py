import sqlite3

import sqlalchemy.exc
from flask import Flask, render_template, request, url_for, redirect, abort
from flask_sqlalchemy import SQLAlchemy
from os.path import abspath, dirname, join
from datetime import date


app = Flask(__name__)
BASE_DIR = abspath(dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{join(BASE_DIR, "db.sqlite")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'JAOSIUE8U903820ISKDJF'
db = SQLAlchemy(app)


class BookExists(BaseException):
    pass


class BookNotFound(BaseException):
    pass


class OutOfBooks(BaseException):
    pass


class ReturnFirst(BaseException):
    pass


class SubjectNotFound(BaseException):
    pass


class Subjects(db.Model):
    __tablename__ = 'subjects'

    subject = db.Column(db.String, primary_key=True)
    books = db.relationship('Book', backref='subject', uselist=True)


class Book(db.Model):
    __tablename__ = 'book'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(32), unique=True, index=True)
    book_subject = db.Column(db.String, db.ForeignKey('subjects.subject'))
    author = db.Column(db.String)
    count = db.Column(db.Integer, default=1)
    total_count = db.Column(db.Integer, default=1)
    borrowed = db.relationship('Borrows', backref='book')


class Borrows(db.Model):
    __tablename__ = 'borrows'

    id = db.Column(db.Integer, primary_key=True)
    borrower = db.Column(db.String(32), index=True)
    borrower_class = db.Column(db.String(4))
    book_title = db.Column(db.String, db.ForeignKey('book.title'))
    librarian = db.Column(db.String)
    borrow_date = db.Column(db.Date, default=date.today())
    return_date = db.Column(db.Date)
    is_returned = db.Column(db.Boolean, default=False)
    is_due = db.Column(db.Boolean, default=False)


def add_book(title: str, count=1, subject=None, author=''):
    title = ' '.join(title.split()).title()
    existing_book = Book.query.filter_by(title=title).first()

    if not existing_book:
        subject = Subjects.query.filter_by(subject=subject).first()

        if subject:
            book = Book(title=title, count=count, total_count=count, subject=subject, author=author)

            db.session.add(book)
            db.session.commit()

            return book.id
    elif existing_book.total_count != count:
        borrowed_books = len(Borrows.query.filter_by(book_title=existing_book.title).filter_by(is_returned=False).all())
        existing_book.total_count = count
        existing_book.count = count - borrowed_books
        db.session.add(existing_book)
        db.session.commit()
    else:
        raise BookExists
    

def borrow_book(book: str, name: str, return_date: date, student_class:str, librarian:str):
    book = ' '.join(book.split()).title()
    name = ' '.join(name.split()).title()
    librarian = ' '.join(librarian.split()).title()
    book = Book.query.filter_by(title=book).first()
    borrower = Borrows.query.filter_by(borrower=name).first()
    is_returned = True if borrower is None else borrower.is_returned

    if book and book.count and is_returned:
        borrow = Borrows(
            borrower=name,
            book=book,
            return_date=return_date,
            borrower_class=student_class,
            librarian=librarian,
        )

        book.count -= 1

        db.session.add_all([borrow, book])
        db.session.commit()

        return borrow.id
    elif not book:
        raise BookNotFound
    elif not book.count:
        raise OutOfBooks
    elif not is_returned:
        raise ReturnFirst


def return_book(borrow_id: int):
    borrow = Borrows.query.filter_by(id=borrow_id).first()

    book = borrow.book
    book.count += 1
    db.session.add(book)

    borrow.is_returned = True
    db.session.add(borrow)

    db.session.commit()


try:
    SUBJECTS = [subject.subject for subject in Subjects.query.all()]
except sqlalchemy.exc.OperationalError:
    db.create_all()
    subjects_list = {
        'Stories',
        'Math',
        'Physics',
        'Chemistry',
        'Biology',
        'Psychology',
        'English',
        'Computer',
        'general knowledge'
    }
    for subject in subjects_list:
        db.session.add(Subjects(subject=subject))

    db.session.commit()


@app.route('/')
def home():
    obj = request.args
    return render_template('home.html', **obj)


@app.route('/add_book')
def add_book_get():
    return render_template('add_book.html', subjects=SUBJECTS)


@app.route('/add_book', methods=['POST'])
def add_book_post():
    title = request.form.get('title')
    count = int(request.form.get('count'))
    subject = request.form.get('subject')
    author = request.form.get('author')
    try:
        new = add_book(title, count, subject, author)
    except BookExists:
        return '<h1>That book is already added</h1>'

    return redirect(url_for('book_search', new=new))


@app.route('/borrow/<title>')
def borrow_get(title=None):
    return render_template('borrow.html', title=title)


@app.route('/borrow', methods=['POST'])
def borrow_post():
    book = request.form.get('book')
    name = request.form.get('student_name')
    return_date = request.form.get('return_date')
    student_class = request.form.get('student_class')
    librarian = request.form.get('librarian')
    return_date = [int(i) for i in return_date.split('-')]
    return_date = date(*return_date)

    try:
        borrow_info = borrow_book(book, name, return_date, student_class, librarian)
        return redirect(url_for('view_borrows', borrow_id=borrow_info))
    except OutOfBooks:
        return '<h1> Out of that book </h1>'
    except ReturnFirst:
        return '<h1> Return the book you last borrowed </h1>'


@app.route('/return/<int:return_id>')
def return_book_get(return_id):
    return return_book_post(return_id)


@app.route('/return', methods=['POST'])
def return_book_post(borrow_id):
    return_book(borrow_id=borrow_id)
    return redirect(url_for('view_borrows'))


@app.route('/search')
def book_search():
    subject_query = request.args.get('subject')
    show_0 = request.args.get('only_available')
    new = request.args.get('new')

    context = {
        'subjects': [subject.subject for subject in Subjects.query.all()],
        'results': None,
        'new': int(new) if new is not None else None,
    }

    query = generate_query(show_0, subject_query)
    query_result = db.engine.execute(query).all()
    context['results'] = query_result

    return render_template('search.html', **context)


@app.route('/view_borrows/')
def view_borrows():
    unreturned_filter = request.args.get('returned')
    # over_due_filter = request.args.get('overdue')
    borrow_id = request.args.get('borrow_id')
    borrow_id = int(borrow_id) if borrow_id is not None else None

    unreturned_borrows = Borrows.query.filter_by(is_returned=False).all()
    borrows = unreturned_borrows if unreturned_filter else Borrows.query.all()

    overdue_books = Borrows.query.filter(Borrows.return_date <= date.today()).filter(Borrows.is_returned == False).all()
    if overdue_books:
        new_books = []

        for book in overdue_books:
            book.is_due = True
            new_books.append(book)
        else:
            db.session.add_all(new_books)
            db.session.commit()
    return render_template('view_borowed.html', borrows=borrows, borrow_id=borrow_id)


def generate_query(show_0, subject_query):
    query = 'SELECT title, book_subject, count, author, id FROM book '

    if subject_query:
        query += f'WHERE book_subject = "{subject_query}" '
        if show_0:
            query += 'AND count > 0'
    elif show_0:
        query += 'WHERE count > 0'

    return query


@app.shell_context_processor
def imports():
    return dict(
        db=db,
        add_book=add_book,
        borrow_book=borrow_book,
        Book=Book,
        Borrows=Borrows,
        Return=return_book,
    )
