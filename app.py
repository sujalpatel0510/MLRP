# WorkZen HRMS - Flask Application

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import secrets
import string

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
    """User model for Admin, HR Officer, Payroll Officer, and Employees"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    login_id = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    role = db.Column(db.String(50), default='EMPLOYEE')  
    # Roles: ADMIN, HR_OFFICER, PAYROLL_OFFICER, EMPLOYEE
    department = db.Column(db.String(100))
    job_position = db.Column(db.String(100))
    job_title = db.Column(db.String(100))
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    employment_type = db.Column(db.String(50))  # Full-time, Part-time
    contract_type = db.Column(db.String(50))    # Permanent, Contract
    work_address = db.Column(db.String(255))
    work_location = db.Column(db.String(100))
    time_zone = db.Column(db.String(50))
    wage_type = db.Column(db.String(50))        # Fixed Wage, Hourly
    wage = db.Column(db.Float)                 # Monthly/Hourly wage
    working_hours = db.Column(db.String(50))   # e.g., "40 hours/week"
    shift_time = db.Column(db.String(100))     # e.g., "9:00 AM - 6:00 PM"
    date_of_joining = db.Column(db.Date)
    date_of_birth = db.Column(db.Date)
    gender = db.Column(db.String(20))
    nationality = db.Column(db.String(100))
    emergency_contact_name = db.Column(db.String(255))
    emergency_contact_relation = db.Column(db.String(100))
    emergency_contact_phone = db.Column(db.String(20))
    basic_salary = db.Column(db.Float)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    leaves = db.relationship('Leave', backref='employee', lazy=True, foreign_keys='Leave.user_id')
    payslips = db.relationship('Payslip', backref='employee', lazy=True)
    attendances = db.relationship('Attendance', backref='employee', lazy=True)
    salary_adjustments = db.relationship(
        'SalaryAdjustment',
        foreign_keys='SalaryAdjustment.user_id',
        backref='employee',
        lazy=True
    )

    def set_password(self, password):
        """Hash password"""
        self.password = generate_password_hash(password)

    def check_password(self, password):
        """Verify password"""
        return check_password_hash(self.password, password)

class Attendance(db.Model):
    """Attendance tracking model"""
    __tablename__ = 'attendance'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    attendance_date = db.Column(db.Date, nullable=False)
    check_in = db.Column(db.Time)
    check_out = db.Column(db.Time)
    status = db.Column(db.String(50))  # Present, Absent, Late
    working_hours = db.Column(db.Float)
    remarks = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'attendance_date', name='uq_user_date'),)

class Leave(db.Model):
    """Leave request model"""
    __tablename__ = 'leaves'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    leave_type = db.Column(db.String(50), nullable=False)  # Annual, Sick, Casual
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

class Payslip(db.Model):
    """Payslip model"""
    __tablename__ = 'payslips'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    payroll_month = db.Column(db.Date, nullable=False)
    basic_salary = db.Column(db.Float)
    hra = db.Column(db.Float)  # House Rent Allowance
    da = db.Column(db.Float)   # Dearness Allowance
    gross_earnings = db.Column(db.Float)
    pf = db.Column(db.Float)   # Provident Fund
    income_tax = db.Column(db.Float)
    professional_tax = db.Column(db.Float)
    net_salary = db.Column(db.Float)
    status = db.Column(db.String(50), default='Draft')  # Draft, Processed
    processed_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'payroll_month', name='uq_user_month'),)

class SalaryAdjustment(db.Model):
    """Salary adjustment history"""
    __tablename__ = 'salary_adjustments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    adjustment_date = db.Column(db.Date, nullable=False)
    old_salary = db.Column(db.Float)
    new_salary = db.Column(db.Float)
    reason = db.Column(db.Text)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Badge(db.Model):
    """Badges and awards model"""
    __tablename__ = 'badges'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    badge_name = db.Column(db.String(100))
    badge_description = db.Column(db.Text)
    awarded_date = db.Column(db.Date)
    awarded_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Certification(db.Model):
    """Employee certifications"""
    __tablename__ = 'certifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    certification_name = db.Column(db.String(255))
    issuing_organization = db.Column(db.String(255))
    issue_date = db.Column(db.Date)
    expiration_date = db.Column(db.Date)
    credential_id = db.Column(db.String(100))
    credential_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Report(db.Model):
    """Reports storage"""
    __tablename__ = 'reports'

    id = db.Column(db.Integer, primary_key=True)
    report_type = db.Column(db.String(50))  # Attendance, Payroll, Employee, Leave, Overtime, Performance
    report_data = db.Column(db.JSON)
    generated_date = db.Column(db.DateTime, default=datetime.utcnow)
    generated_by = db.Column(db.Integer, db.ForeignKey('users.id'))

# ======================== UTILITY FUNCTIONS ========================

def generate_login_id(first_name, last_name, year):
    """Generate unique login ID"""
    name_abbr = (first_name[:2] + last_name[:2]).upper()
    year_str = str(year)
    count = User.query.filter(User.login_id.ilike(f"{name_abbr}{year_str}%")).count()
    serial = str(count + 1).zfill(4)
    return f"{name_abbr}{year_str}{serial}"

def generate_temp_password(length=12):
    """Generate secure temporary password"""
    return ''.join(secrets.choice(string.ascii_letters + string.digits + '!@#$') for _ in range(length))

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

# ======================== ROUTES ========================

@app.route('/')
def index():
    return redirect(url_for('login'))

# --- Authentication Routes ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        login_id = request.form.get('login_id')
        password = request.form.get('password')

        user = User.query.filter_by(login_id=login_id, is_active=True).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['role'] = user.role
            session['full_name'] = user.full_name
            return redirect(url_for('dashboard'))

        return render_template('login.html', error='Invalid credentials'), 401

    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """User signup (new Employees)"""
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        if not first_name or not last_name:
            return render_template('signup.html', error='First name and last name are required'), 400

        full_name = f"{first_name} {last_name}"
        email = request.form.get('email')
        phone = request.form.get('phone')
        department = request.form.get('department')
        # By default new signups are 'EMPLOYEE' role
        role = 'EMPLOYEE'

        if User.query.filter_by(email=email).first():
            return render_template('signup.html', error='Email already exists'), 400

        login_id = generate_login_id(first_name, last_name, datetime.now().year)
        temp_password = generate_temp_password()

        user = User(
            login_id=login_id,
            email=email,
            full_name=full_name,
            phone=phone,
            department=department,
            role=role,
            date_of_joining=datetime.now().date()
        )
        user.set_password(temp_password)
        db.session.add(user)
        db.session.commit()

        # Auto-login after signup
        session['user_id'] = user.id
        session['role'] = user.role
        session['full_name'] = user.full_name
        return redirect(url_for('dashboard'))

    return render_template('signup.html')

@app.route('/register')
def register():
    """Redirect to signup page"""
    return redirect(url_for('signup'))

@app.route('/logout')
def logout():
    """User logout"""
    session.clear()
    return redirect(url_for('login'))

# --- Dashboard Routes ---

@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard (shows own attendance, leave balance, payslips)"""
    user = User.query.get(session.get('user_id'))
    today = datetime.now().date()

    today_attendance = Attendance.query.filter_by(
        user_id=user.id, attendance_date=today
    ).first()

    leave_balance = LeaveBalance.query.filter_by(
        user_id=user.id, year=datetime.now().year
    ).all()

    recent_payslips = Payslip.query.filter_by(
        user_id=user.id
    ).order_by(Payslip.payroll_month.desc()).limit(3).all()

    return render_template('dashboard.html',
                           user=user,
                           today_attendance=today_attendance,
                           leave_balance=leave_balance,
                           recent_payslips=recent_payslips)

@app.route('/attendance')
@login_required
def attendance_page():
    """Attendance page view (own records only)"""
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    attendance_records = Attendance.query.filter_by(user_id=user_id).order_by(Attendance.attendance_date.desc()).all()
    return render_template('attendance.html', user=user, attendance_records=attendance_records)

@app.route('/employees')
@login_required
@role_required('ADMIN', 'HR_OFFICER', 'PAYROLL_OFFICER', 'EMPLOYEE')
def employees_page():
    """Employee directory (view-only for Employees)"""
    users = User.query.all()
    return render_template('employees.html', users=users)

@app.route('/api/attendance/checkin', methods=['POST'])
@login_required
def checkin():
    """Mark check-in (Employee)"""
    user_id = session.get('user_id')
    today = datetime.now().date()
    existing = Attendance.query.filter_by(user_id=user_id, attendance_date=today).first()
    if existing:
        return jsonify({'error': 'Already checked in today'}), 400

    attendance = Attendance(
        user_id=user_id,
        attendance_date=today,
        check_in=datetime.now().time(),
        status='Present'
    )
    db.session.add(attendance)
    db.session.commit()
    return jsonify({'message': 'Checked in successfully'}), 200

@app.route('/api/attendance/checkout', methods=['POST'])
@login_required
def checkout():
    """Mark check-out (Employee)"""
    user_id = session.get('user_id')
    today = datetime.now().date()
    attendance = Attendance.query.filter_by(user_id=user_id, attendance_date=today).first()
    if not attendance:
        return jsonify({'error': 'No check-in record found'}), 404

    attendance.check_out = datetime.now().time()
    if attendance.check_in and attendance.check_out:
        check_in_dt = datetime.combine(today, attendance.check_in)
        check_out_dt = datetime.combine(today, attendance.check_out)
        attendance.working_hours = (check_out_dt - check_in_dt).total_seconds() / 3600
    db.session.commit()
    return jsonify({'message': 'Checked out successfully'}), 200

# --- Leave Routes ---

@app.route('/timeoff')
@login_required
def timeoff():
    """Time off / Leave management page (own requests only)"""
    user_id = session.get('user_id')
    user = User.query.get(user_id)

    leaves = Leave.query.filter_by(user_id=user_id).order_by(Leave.created_at.desc()).all()
    leave_balance = LeaveBalance.query.filter_by(user_id=user_id, year=datetime.now().year).all()

    return render_template('timeoff.html',
                           user=user,
                           leaves=leaves,
                           leave_balance=leave_balance)

@app.route('/api/leaves/apply', methods=['POST'])
@login_required
def apply_leave():
    """Apply for leave (Employee)"""
    user_id = session.get('user_id')
    data = request.get_json()
    start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
    end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date()
    leave_type = data.get('leave_type')
    reason = data.get('reason')

    num_days = (end_date - start_date).days + 1
    balance = LeaveBalance.query.filter_by(
        user_id=user_id, leave_type=leave_type, year=datetime.now().year
    ).first()
    if not balance or balance.remaining_days < num_days:
        return jsonify({'error': 'Insufficient leave balance'}), 400

    leave = Leave(
        user_id=user_id,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        number_of_days=num_days,
        status='Pending'
    )
    db.session.add(leave)
    db.session.commit()
    return jsonify({'message': 'Leave request submitted successfully', 'leave_id': leave.id}), 201

@app.route('/api/leaves/approve/<int:leave_id>', methods=['PUT'])
@login_required
@role_required('ADMIN', 'PAYROLL_OFFICER')
def approve_leave(leave_id):
    """Approve leave request (Admin or Payroll Officer)"""
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
@role_required('ADMIN', 'PAYROLL_OFFICER')
def reject_leave(leave_id):
    """Reject leave request (Admin or Payroll Officer)"""
    leave = Leave.query.get(leave_id)
    if not leave:
        return jsonify({'error': 'Leave request not found'}), 404

    leave.status = 'Rejected'
    leave.approved_by = session.get('user_id')
    db.session.commit()
    return jsonify({'message': 'Leave rejected successfully'}), 200

# --- Payroll Routes ---

@app.route('/payroll')
@login_required
@role_required('ADMIN', 'PAYROLL_OFFICER', 'EMPLOYEE')
def payroll():
    """Payroll / Salary page (view own payslips)"""
    user_id = session.get('user_id')
    user = User.query.get(user_id)

    payslips = Payslip.query.filter_by(user_id=user_id).order_by(
        Payslip.payroll_month.desc()
    ).limit(12).all()

    current_month = datetime.now().replace(day=1).date()
    current_payslip = Payslip.query.filter_by(
        user_id=user_id, payroll_month=current_month
    ).first()

    salary_adjustments = SalaryAdjustment.query.filter_by(user_id=user_id).order_by(
        SalaryAdjustment.adjustment_date.desc()
    ).limit(5).all()

    return render_template('payroll.html',
                           user=user,
                           payslips=payslips,
                           current_payslip=current_payslip,
                           salary_adjustments=salary_adjustments)

@app.route('/api/payroll/generate', methods=['POST'])
@login_required
@role_required('ADMIN', 'PAYROLL_OFFICER')
def generate_payroll():
    """Generate payslips for all employees (Admin or Payroll Officer)"""
    data = request.get_json()
    payroll_month = datetime.strptime(data.get('payroll_month'), '%Y-%m-%d').date()

    employees = User.query.filter_by(role='EMPLOYEE', is_active=True).all()
    for employee in employees:
        existing = Payslip.query.filter_by(
            user_id=employee.id, payroll_month=payroll_month
        ).first()
        if existing:
            continue

        month_start = payroll_month.replace(day=1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        attendance_count = Attendance.query.filter(
            Attendance.user_id == employee.id,
            Attendance.attendance_date >= month_start,
            Attendance.attendance_date < next_month,
            Attendance.status == 'Present'
        ).count()

        basic = employee.basic_salary or 0
        hra = basic * 0.2
        da = basic * 0.05
        gross = basic + hra + da
        pf = basic * 0.12
        income_tax = basic * 0.05
        prof_tax = 200
        net = gross - pf - income_tax - prof_tax

        payslip = Payslip(
            user_id=employee.id,
            payroll_month=payroll_month,
            basic_salary=basic,
            hra=hra,
            da=da,
            gross_earnings=gross,
            pf=pf,
            income_tax=income_tax,
            professional_tax=prof_tax,
            net_salary=net,
            status='Draft'
        )
        db.session.add(payslip)
    db.session.commit()

    return jsonify({'message': 'Payroll generated successfully'}), 201

# --- Profile & Settings Routes ---

@app.route('/profile')
@login_required
def profile():
    """Employee profile page (own profile)"""
    user = User.query.get(session.get('user_id'))

    salary_adjustments = SalaryAdjustment.query.filter_by(user_id=user.id).order_by(
        SalaryAdjustment.adjustment_date.desc()
    ).all()
    badges = Badge.query.filter_by(user_id=user.id).all()
    certifications = Certification.query.filter_by(user_id=user.id).all()

    return render_template('employee-profile-integrated.html',
                           user=user,
                           salary_adjustments=salary_adjustments,
                           badges=badges,
                           certifications=certifications)

@app.route('/settings')
@login_required
def settings():
    """Settings / Account page (own account)"""
    user = User.query.get(session.get('user_id'))
    return render_template('settings.html', user=user)

@app.route('/api/settings/change-password', methods=['POST'])
@login_required
def change_password():
    """Change password (own account)"""
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
    """Update profile settings (own account)"""
    user = User.query.get(session.get('user_id'))
    data = request.get_json()
    user.phone = data.get('phone', user.phone)
    user.date_of_birth = data.get('date_of_birth', user.date_of_birth)
    user.gender = data.get('gender', user.gender)
    user.nationality = data.get('nationality', user.nationality)
    db.session.commit()
    return jsonify({'message': 'Profile updated successfully'}), 200

# --- Reports Routes ---

@app.route('/reports')
@login_required
@role_required('ADMIN', 'PAYROLL_OFFICER')
def reports():
    """Reports page (Admin or Payroll Officer)"""
    user = User.query.get(session.get('user_id'))

    today = datetime.now().date()
    month_start = today.replace(day=1)
    departments = db.session.query(User.department).distinct().all()

    attendance_data = {}
    for dept in departments:
        if dept[0]:
            present = Attendance.query.join(User).filter(
                User.department == dept[0],
                Attendance.attendance_date >= month_start,
                Attendance.status == 'Present'
            ).count()
            absent = Attendance.query.join(User).filter(
                User.department == dept[0],
                Attendance.attendance_date >= month_start,
                Attendance.status == 'Absent'
            ).count()
            late = Attendance.query.join(User).filter(
                User.department == dept[0],
                Attendance.attendance_date >= month_start,
                Attendance.status == 'Late'
            ).count()
            total = present + absent + late
            attendance_pct = (present / total * 100) if total > 0 else 0
            attendance_data[dept[0]] = {
                'present': present, 'absent': absent, 'late': late,
                'percentage': round(attendance_pct, 1)
            }

    return render_template('reports.html', user=user, attendance_data=attendance_data)

# --- Error Handlers ---

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

def init_db():
    """Create all database tables"""
    with app.app_context():
        db.create_all()
        print("✅ Database tables created successfully")

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
