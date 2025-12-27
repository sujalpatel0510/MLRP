from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'workzen-secret-key-2025')

# PostgreSQL Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f"postgresql://{os.environ.get('DB_USER', 'postgres')}:"
    f"{os.environ.get('DB_PASSWORD', '8511')}@"
    f"{os.environ.get('DB_HOST', 'localhost')}:"
    f"{os.environ.get('DB_PORT', 5432)}/"
    f"{os.environ.get('DB_NAME', 'workzen_db')}"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ======================== DATABASE MODELS ========================

class User(db.Model):
    """Minimal User model - Email, Password, and Role only"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default='STUDENT')  # STUDENT, COUNSELOR, HOD
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def set_password(self, password):
        """Store plain text password"""
        self.password = password
    
    def check_password(self, password):
        """Check plain text password"""
        return self.password == password


class Attendance(db.Model):
    """Attendance tracking model"""
    __tablename__ = 'attendance'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    attendance_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(50))  # Present, Absent
    remarks = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'attendance_date', name='uq_user_date'),)


class Leave(db.Model):
    """Leave request model"""
    __tablename__ = 'leaves'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requester = db.relationship('User', foreign_keys=[user_id])
    leave_type = db.Column(db.String(50), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text)
    status = db.Column(db.String(50), default='Pending')  # Pending, Approved, Rejected
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approver = db.relationship('User', foreign_keys=[approved_by])
    number_of_days = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LeaveBalance(db.Model):
    """Leave balance tracking"""
    __tablename__ = 'leave_balance'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    leave_type = db.Column(db.String(50), nullable=False)
    total_days = db.Column(db.Integer)
    used_days = db.Column(db.Integer, default=0)
    remaining_days = db.Column(db.Integer)
    year = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'leave_type', 'year', name='uq_user_leave_year'),)


# ======================== DECORATORS ========================

def login_required(f):
    """Decorator to require login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    """Decorator for role-based access"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = User.query.get(session.get('user_id'))
            if not user or user.role not in roles:
                return redirect(url_for('login')), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# ======================== AUTHENTICATION ROUTES ========================

@app.route('/')
def index():
    """Redirect to login"""
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login with email and password"""
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['role'] = user.role
            return redirect(url_for('dashboard'))
        
        return render_template('login.html', error='Invalid credentials'), 401
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    """User logout"""
    session.clear()
    return redirect(url_for('login'))


# ======================== DASHBOARD ========================

@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard page"""
    user = User.query.get(session.get('user_id'))
    return render_template('dashboard.html', user=user)


# ======================== TIME OFF (LEAVES) ========================

@app.route('/timeoff')
@login_required
def timeoff():
    """Time off / Leave management page"""
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    current_year = datetime.now().year
    
    # Get user's own leaves
    leaves = Leave.query.filter_by(user_id=user_id).order_by(Leave.created_at.desc()).all()
    
    # Get user's leave balance
    leave_balance = LeaveBalance.query.filter_by(user_id=user_id, year=current_year).all()
    
    # Get ALL leave requests (for "All Leave Requests" tab)
    all_leaves = Leave.query.order_by(Leave.created_at.desc()).all()
    
    # For Counselor and HOD - get pending approvals
    pending_leaves = []
    pending_count = 0
    approved_today = 0
    rejected_today = 0
    today = datetime.now().date()
    
    if user.role in ['COUNSELOR', 'HOD']:
        pending_leaves = Leave.query.filter_by(status='Pending').order_by(Leave.created_at.desc()).all()
        pending_count = len(pending_leaves)
        approved_today = Leave.query.filter(
            Leave.status == 'Approved',
            Leave.updated_at >= today
        ).count()
        rejected_today = Leave.query.filter(
            Leave.status == 'Rejected',
            Leave.updated_at >= today
        ).count()
    
    return render_template('timeoff.html',
                         user=user,
                         leaves=leaves,
                         leave_balance=leave_balance,
                         current_year=current_year,
                         all_leaves=all_leaves,
                         pending_leaves=pending_leaves,
                         pending_count=pending_count,
                         approved_today=approved_today,
                         rejected_today=rejected_today)


@app.route('/api/leaves/apply', methods=['POST'])
@login_required
def apply_leave():
    """Apply for leave"""
    try:
        user_id = session.get('user_id')
        data = request.get_json()
        
        start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date()
        leave_type = data.get('leave_type')
        reason = data.get('reason')
        num_days = (end_date - start_date).days + 1
        current_year = datetime.now().year
        
        # Find Counselor (first available)
        counselor = User.query.filter_by(role='COUNSELOR').first()
        
        # Check or create leave balance
        balance = LeaveBalance.query.filter_by(
            user_id=user_id,
            leave_type=leave_type,
            year=current_year
        ).first()
        
        if not balance:
            default_days = {'Annual': 20, 'Sick': 10, 'Casual': 5}
            balance = LeaveBalance(
                user_id=user_id,
                leave_type=leave_type,
                total_days=default_days.get(leave_type, 5),
                used_days=0,
                remaining_days=default_days.get(leave_type, 5),
                year=current_year
            )
            db.session.add(balance)
            db.session.commit()
        
        if balance.remaining_days < num_days:
            return jsonify(
                error=f'Insufficient leave balance. Available: {balance.remaining_days} days, Requested: {num_days} days'
            ), 400
        
        # Create leave request
        leave = Leave(
            user_id=user_id,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            number_of_days=num_days,
            status='Pending',
            approved_by=counselor.id if counselor else None
        )
        
        db.session.add(leave)
        db.session.commit()
        
        return jsonify(
            message='Leave request submitted successfully',
            leave_id=leave.id
        ), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500


@app.route('/api/leaves/approve/<int:leave_id>', methods=['PUT'])
@login_required
@role_required('HOD', 'COUNSELOR')
def approve_leave(leave_id):
    """Approve leave request"""
    leave = Leave.query.get(leave_id)
    
    if not leave:
        return jsonify({'error': 'Leave request not found'}), 404
    
    leave.status = 'Approved'
    leave.approved_by = session.get('user_id')
    
    balance = LeaveBalance.query.filter_by(
        user_id=leave.user_id,
        leave_type=leave.leave_type,
        year=datetime.now().year
    ).first()
    
    if balance:
        balance.used_days += leave.number_of_days
        balance.remaining_days = balance.total_days - balance.used_days
    
    db.session.commit()
    
    return jsonify({'message': 'Leave approved successfully'}), 200


@app.route('/api/leaves/reject/<int:leave_id>', methods=['PUT'])
@login_required
@role_required('HOD', 'COUNSELOR')
def reject_leave(leave_id):
    """Reject leave request"""
    leave = Leave.query.get(leave_id)
    
    if not leave:
        return jsonify({'error': 'Leave request not found'}), 404
    
    leave.status = 'Rejected'
    leave.approved_by = session.get('user_id')
    
    db.session.commit()
    
    return jsonify({'message': 'Leave rejected successfully'}), 200


# ======================== REPORTS ========================

@app.route('/reports')
@login_required
@role_required('HOD', 'COUNSELOR')
def reports():
    """Reports page"""
    user = User.query.get(session.get('user_id'))
    
    # Get attendance data
    today = datetime.now().date()
    month_start = today.replace(day=1)
    
    total_students = User.query.filter_by(role='STUDENT').count()
    present_today = Attendance.query.filter(
        Attendance.attendance_date == today,
        Attendance.status == 'Present'
    ).count()
    
    pending_leaves = Leave.query.filter_by(status='Pending').count()
    approved_leaves = Leave.query.filter_by(status='Approved').count()
    
    return render_template('reports.html',
                         user=user,
                         total_students=total_students,
                         present_today=present_today,
                         pending_leaves=pending_leaves,
                         approved_leaves=approved_leaves)


# ======================== PROFILE ========================

@app.route('/profile')
@login_required
def profile():
    """User profile page"""
    user = User.query.get(session.get('user_id'))
    return render_template('profile.html', user=user)


@app.route('/api/settings/change-password', methods=['POST'])
@login_required
def change_password():
    """Change password"""
    user = User.query.get(session.get('user_id'))
    data = request.get_json()
    
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    
    if not user.check_password(old_password):
        return jsonify({'error': 'Old password is incorrect'}), 401
    
    user.set_password(new_password)
    db.session.commit()
    
    return jsonify({'message': 'Password changed successfully'}), 200


@app.route('/api/settings/update-profile', methods=['PUT'])
@login_required
def update_profile():
    """Update profile"""
    user = User.query.get(session.get('user_id'))
    data = request.get_json()
    
    # Add additional profile fields as needed
    db.session.commit()
    
    return jsonify({'message': 'Profile updated successfully'}), 200


# ======================== ERROR HANDLERS ========================

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500


# ======================== DATABASE INITIALIZATION ========================

def init_db():
    """Create all database tables"""
    with app.app_context():
        db.create_all()
        print("✅ Database tables created successfully")


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)