from flask import Flask, render_template, request, redirect, url_for, flash, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import csv
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'mysecretkey'  # Needed for secure sessions
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///final_project.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- DATABASE MODELS ---


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    budget = db.Column(db.Float, default=5000.0)
    transactions = db.relationship('Transaction', backref='owner', lazy=True)


class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(10), nullable=False)  # 'Income' or 'Expense'
    date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


# Create Database
with app.app_context():
    db.create_all()


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ROUTES ---


@app.route('/')
@login_required
def index():
    # Get the current date
    now = datetime.now()

    # Fetch ALL transactions for this user from the database
    all_transactions = Transaction.query.filter_by(
        user_id=current_user.id).order_by(Transaction.date.desc()).all()

    # FILTER: Only keep transactions from the CURRENT month and year
    monthly_transactions = [
        t for t in all_transactions if t.date.month == now.month and t.date.year == now.year]

    # Calculate Income, Expenses, and Balance using ONLY this month's data
    total_income = sum(
        t.amount for t in monthly_transactions if t.type == 'Income')
    total_expense = sum(
        t.amount for t in monthly_transactions if t.type == 'Expense')
    balance = total_income - total_expense

    # Send the filtered data to the website (INCLUDING the user!)
    return render_template('index.html',
                           user=current_user,
                           transactions=monthly_transactions,
                           balance=balance,
                           income=total_income,
                           expenses=total_expense)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Login Failed. Check your spelling.')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists.')
            return redirect(url_for('register'))

        # Hash the password (Security!)
        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(username=username, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)
        return redirect(url_for('index'))

    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/add', methods=['POST'])
@login_required
def add_transaction():
    description = request.form.get('description')
    amount = float(request.form.get('amount'))
    type = request.form.get('type')

    # --- NEW ALERT LOGIC START ---
    # Use current_user.budget instead of 5000
    if type == 'Expense' and amount > current_user.budget:
        flash(
            f"⚠️ Alert! You exceeded your budget of ₦{current_user.budget:,.2f}!", "error")
    elif type == 'Income':
        flash(f"🤑 Nice! Income of ₦{amount:,.2f} added.", "success")
    else:
        flash("Transaction added successfully.", "success")
    # --- NEW ALERT LOGIC END ---

    new_trans = Transaction(description=description,
                            amount=amount, type=type, owner=current_user)
    db.session.add(new_trans)
    db.session.commit()

    return redirect(url_for('index'))


@app.route('/delete/<int:id>')
@login_required
def delete_transaction(id):
    transaction = Transaction.query.get_or_404(id)
    # Security check: ensure user owns this transaction
    if transaction.user_id == current_user.id:
        db.session.delete(transaction)
        db.session.commit()
    return redirect(url_for('index'))


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():

    if request.method == 'POST':
        new_budget = float(request.form.get('budget'))
        current_user.budget = new_budget
        db.session.commit()
        flash(f"✅ Budget updated to ₦{new_budget:,.2f}", "success")
        return redirect(url_for('index'))

    return render_template('settings.html', user=current_user)


@app.route('/export')
@login_required
def export_transactions():
    # Get all transactions for the logged-in user
    transactions = Transaction.query.filter_by(
        user_id=current_user.id).order_by(Transaction.date.desc()).all()

    # Create a string buffer to write our CSV data into
    si = io.StringIO()
    cw = csv.writer(si)

    # Write the Header row for the Excel file
    cw.writerow(['Date', 'Description', 'Type', 'Amount (NGN)'])

    # Write the data for each transaction
    for t in transactions:
        cw.writerow([t.date.strftime('%Y-%m-%d'),
                    t.description, t.type, f"{t.amount:.2f}"])

    # Create the HTTP response to trigger a file download
    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-disposition": "attachment; filename=CampusVault_Statement.csv"}
    )


if __name__ == "__main__":
    app.run(debug=True)
