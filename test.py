# ======================== IMPORTS ========================
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from datetime import datetime
from dotenv import load_dotenv
import os
from io import BytesIO
from werkzeug.utils import secure_filename

# ======================== PDF IMPORTS ========================
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'workzen-secret-key-2025')

# ======================== DATABASE ========================
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"postgresql://{os.environ.get('DB_USER', 'postgres')}:"
    f"{os.environ.get('DB_PASSWORD', '8511')}@"
    f"{os.environ.get('DB_HOST', 'localhost')}:"
    f"{os.environ.get('DB_PORT', 5432)}/"
    f"{os.environ.get('DB_NAME', 'workzen_db')}"
)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ======================== MODELS ========================

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default='STUDENT')
    counselor_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    def check_password(self, pw): return self.password == pw
    def set_password(self, pw): self.password = pw


class Leave(db.Model):
    __tablename__ = 'leaves'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requester = db.relationship('User', foreign_keys=[user_id])
    leave_type = db.Column(db.String(50))
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    reason = db.Column(db.Text)
    number_of_days = db.Column(db.Integer)
    status = db.Column(db.String(50), default='Pending')
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LeaveDocument(db.Model):
    __tablename__ = 'leave_documents'
    id = db.Column(db.Integer, primary_key=True)
    leave_id = db.Column(db.Integer, db.ForeignKey('leaves.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    file_url = db.Column(db.String(500))
    file_name = db.Column(db.String(255))
    file_size = db.Column(db.Integer)
    document_type = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ======================== AUTH ========================

def login_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*a, **k)
    return wrap


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrap(*a, **k):
            user = User.query.get(session['user_id'])
            if user.role not in roles:
                return "Forbidden", 403
            return f(*a, **k)
        return wrap
    return decorator


@app.route('/')
def index(): return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = User.query.filter_by(email=request.form['email']).first()
        if u and u.check_password(request.form['password']):
            session['user_id'] = u.id
            session['role'] = u.role
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=User.query.get(session['user_id']))


# ======================== LEAVES (UNLIMITED) ========================

@app.route('/api/leaves/apply', methods=['POST'])
@login_required
def apply_leave():
    try:
        uid = session['user_id']
        start = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        end = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        days = (end - start).days + 1

        leave = Leave(
            user_id=uid,
            leave_type=request.form['leave_type'],
            start_date=start,
            end_date=end,
            reason=request.form['reason'],
            number_of_days=days
        )

        db.session.add(leave)
        db.session.commit()

        return jsonify({'message': 'Leave applied successfully (Unlimited Enabled)'}), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@app.route('/api/leaves/approve/<int:id>', methods=['PUT'])
@login_required
@role_required('HOD', 'COUNSELOR')
def approve_leave(id):
    leave = Leave.query.get(id)
    leave.status = 'Approved'
    leave.approved_by = session['user_id']
    db.session.commit()
    return jsonify({'message': 'Approved'})


@app.route('/api/leaves/reject/<int:id>', methods=['PUT'])
@login_required
@role_required('HOD', 'COUNSELOR')
def reject_leave(id):
    leave = Leave.query.get(id)
    leave.status = 'Rejected'
    leave.approved_by = session['user_id']
    db.session.commit()
    return jsonify({'message': 'Rejected'})


# ======================== PDF REPORT ========================

@app.route('/api/leaves/report')
@login_required
def leave_report():
    leaves = Leave.query.all()
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [Paragraph("Leave Report", styles['Heading1']), Spacer(1, 20)]

    data = [['User', 'Type', 'Days', 'Status']]
    for l in leaves:
        data.append([l.requester.email, l.leave_type, l.number_of_days, l.status])

    table = Table(data)
    table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))

    story.append(table)
    doc.build(story)
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name="leave_report.pdf")


# ======================== INIT ========================

def init_db():
    with app.app_context():
        db.create_all()
        print("Database Ready")

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
