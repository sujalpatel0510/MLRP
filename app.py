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
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from flask import send_file
import csv

#git testing(tithi)
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
    leaves = db.relationship('Leave', backref='employee', lazy=True, foreign_keys='[Leave.user_id]', cascade='save-update')

    payslips = db.relationship('Payslip', backref='employee', lazy=True, cascade='save-update')
    attendances = db.relationship('Attendance', backref='employee', lazy=True, cascade='save-update')
    

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
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # User who requested leave
    requester = db.relationship('User', foreign_keys=[user_id])

    leave_type = db.Column(db.String(50), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text)
    status = db.Column(db.String(50), default='Pending')
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
    
    # FIX: Add backref=False or custom backref names
    employee = db.relationship('User', foreign_keys=[user_id], backref='adjusted_salaries')
    approver = db.relationship('User', foreign_keys=[approved_by], backref='approved_adjustments')
    
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
        role = request.form.get('role', 'EMPLOYEE')  # Get from form

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
    user = User.query.get(session.get('user_id'))
    today = datetime.now().date()
    
    # Total Employees
    total_employees = User.query.filter_by(role='EMPLOYEE', is_active=True).count()
    
    # Attendance Rate (percentage of present today)
    total_present_today = Attendance.query.filter_by(attendance_date=today, status='Present').count()
    total_employees_active = User.query.filter_by(is_active=True).count()
    attendance_rate = round((total_present_today / total_employees_active * 100) if total_employees_active > 0 else 0)
    
    # Pending Leaves
    pending_leaves = Leave.query.filter_by(status='Pending').count()
    
    # Total Payroll (sum of all net salaries for current month)
    current_month = today.replace(day=1)
    total_payroll = db.session.query(db.func.sum(Payslip.net_salary)).filter_by(payroll_month=current_month).scalar() or 0
    total_payroll = round(total_payroll / 100000, 1)  # Convert to Lakhs
    
    # Today's Attendance (for logged-in employee)
    today_attendance = Attendance.query.filter_by(user_id=user.id, attendance_date=today).first()
    
    # Leave Balance
    leave_balance = LeaveBalance.query.filter_by(user_id=user.id, year=today.year).all()
    
    # Recent Payslips
    recent_payslips = Payslip.query.filter_by(user_id=user.id).order_by(Payslip.payroll_month.desc()).limit(3).all()
    
    return render_template('dashboard.html', 
                         user=user,
                         total_employees=total_employees,
                         attendance_rate=attendance_rate,
                         pending_leaves=pending_leaves,
                         total_payroll=total_payroll,
                         today_attendance=today_attendance,
                         leave_balance=leave_balance,
                         recent_payslips=recent_payslips)


@app.route('/attendance')
@login_required
def attendance_page():
    user = User.query.get(session.get('user_id'))
    # Fetch data from database, e.g., attendance records for user or all users
    # Example: attendance_records = Attendance.query.filter_by(user_id=user.id).all()

    attendance_records = Attendance.query.order_by(Attendance.attendance_date.desc()).limit(20).all()
    
    return render_template('attendance.html', user=user, attendance_records=attendance_records)

@app.route('/mark_attendance')
@login_required
def mark_attendance():
    # Render a template or redirect as needed for marking attendance
    return render_template('mark_attendance.html')


@app.route('/employees')
@login_required
@role_required('ADMIN', 'HR_OFFICER', 'PAYROLL_OFFICER', 'EMPLOYEE')
def employees_page():
    """Employee directory (view-only for Employees)"""
    users = User.query.all()
    return render_template('employees.html', users=users)


@app.route('/admin/initialize-all-leave-balances', methods=['POST'])
@login_required
@role_required(['ADMIN', 'PAYROLLOFFICER'])
def initialize_all_leave_balances():
    """Initialize leave balances for all active employees"""
    try:
        current_year = datetime.now().year
        
        # Get all active employees
        employees = User.query.filter_by(role='EMPLOYEE', is_active=True).all()
        
        # Define leave types
        leave_types = [
            {'type': 'Annual', 'days': 20},
            {'type': 'Sick', 'days': 10},
            {'type': 'Casual', 'days': 5},
            {'type': 'Maternity', 'days': 90},
            {'type': 'Unpaid', 'days': 10}
        ]
        
        created_count = 0
        
        for employee in employees:
            for leave_type in leave_types:
                # Check if balance already exists
                existing = LeaveBalance.query.filter_by(
                    user_id=employee.id,
                    leave_type=leave_type['type'],
                    year=current_year
                ).first()
                
                if not existing:
                    balance = LeaveBalance(
                        user_id=employee.id,
                        leave_type=leave_type['type'],
                        total_days=leave_type['days'],
                        used_days=0,
                        remaining_days=leave_type['days'],
                        year=current_year
                    )
                    db.session.add(balance)
                    created_count += 1
        
        db.session.commit()
        
        return jsonify(
            message=f'Successfully initialized leave balances for {len(employees)} employees',
            created_records=created_count,
            status='success'
        ), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e), status='error'), 500

        
@app.route('/timeoff')
@login_required
def timeoff():
    """Time off / Leave management page"""
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    current_year = datetime.now().year
    today = datetime.now().date()

    # Get user's own leaves
    leaves = Leave.query.filter_by(user_id=user_id).order_by(Leave.created_at.desc()).all()
    
    # Get user's leave balance
    leave_balance = LeaveBalance.query.filter_by(user_id=user_id, year=current_year).all()

    # Get ALL leave requests (for "All Leave Requests" tab - everyone can see)
    all_leaves = Leave.query.order_by(Leave.created_at.desc()).all()
    
    # For HR Officers and Admins - get pending approvals
    pending_leaves = []
    pending_count = 0
    approved_today = 0
    rejected_today = 0
    
    if user.role in ['HR_OFFICER', 'ADMIN']:
        # Get pending leave requests
        pending_leaves = Leave.query.filter_by(status='Pending').order_by(Leave.created_at.desc()).all()
        pending_count = len(pending_leaves)
        
        # Get today's approved requests
        approved_today = Leave.query.filter(
            Leave.status == 'Approved',
            Leave.updated_at >= today
        ).count()
        
        # Get today's rejected requests
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



# Add these routes to your app.py file

@app.route('/employees/<int:user_id>')
@login_required
def employee_profile(user_id):
    """View individual employee profile"""
    user = User.query.get_or_404(user_id)
    
    # Get salary adjustments
    salary_adjustments = SalaryAdjustment.query.filter_by(
        user_id=user_id
    ).order_by(SalaryAdjustment.adjustment_date.desc()).all()
    
    # Get badges
    badges = Badge.query.filter_by(user_id=user_id).all()
    
    # Get certifications
    certifications = Certification.query.filter_by(user_id=user_id).all()
    
    return render_template('profile.html',
                         user=user,
                         salary_adjustments=salary_adjustments,
                         badges=badges,
                         certifications=certifications)

@app.route('/employees/add')
@login_required
@role_required('ADMIN', 'HR_OFFICER')
def add_employee():
    """Add new employee page (Admin or HR Officer only)"""
    return render_template('add_employee.html')

@app.route('/api/employees/add', methods=['POST'])
@login_required
@role_required('ADMIN', 'HR_OFFICER')
def create_employee():
    """Create new employee (Admin or HR Officer only)"""
    try:
        data = request.get_json()
        
        # Check if email already exists
        if User.query.filter_by(email=data.get('email')).first():
            return jsonify({'error': 'Email already exists'}), 400
        
        # Generate login ID
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        
        if not first_name or not last_name:
            return jsonify({'error': 'First name and last name are required'}), 400
        
        full_name = f"{first_name} {last_name}"
        login_id = generate_login_id(first_name, last_name, datetime.now().year)
        temp_password = generate_temp_password()
        
        # Parse date fields
        date_of_birth = None
        if data.get('date_of_birth'):
            date_of_birth = datetime.strptime(data.get('date_of_birth'), '%Y-%m-%d').date()
        
        date_of_joining = datetime.now().date()
        if data.get('date_of_joining'):
            date_of_joining = datetime.strptime(data.get('date_of_joining'), '%Y-%m-%d').date()
        
        # Create new user
        user = User(
            login_id=login_id,
            email=data.get('email'),
            full_name=full_name,
            phone=data.get('phone'),
            role=data.get('role', 'EMPLOYEE'),
            department=data.get('department'),
            job_position=data.get('job_position'),
            job_title=data.get('job_title'),
            employment_type=data.get('employment_type'),
            contract_type=data.get('contract_type'),
            date_of_joining=date_of_joining,
            date_of_birth=date_of_birth,
            gender=data.get('gender'),
            nationality=data.get('nationality'),
            work_location=data.get('work_location'),
            work_address=data.get('work_address'),
            time_zone=data.get('time_zone'),
            shift_time=data.get('shift_time'),
            working_hours=data.get('working_hours'),
            wage_type=data.get('wage_type'),
            wage=float(data.get('wage')) if data.get('wage') else None,
            basic_salary=float(data.get('basic_salary')) if data.get('basic_salary') else None,
            emergency_contact_name=data.get('emergency_contact_name'),
            emergency_contact_relation=data.get('emergency_contact_relation'),
            emergency_contact_phone=data.get('emergency_contact_phone'),
            is_active=True
        )
        
        user.set_password(temp_password)
        db.session.add(user)
        db.session.commit()
        # Create default leave balances
        current_year = datetime.now().year
        leave_types = [
            {'type': 'Annual', 'days': 20},
            {'type': 'Sick', 'days': 10},
            {'type': 'Casual', 'days': 5}
        ]
        
        for leave in leave_types:
            balance = LeaveBalance(
                user_id=user.id,
                leave_type=leave['type'],
                total_days=leave['days'],
                used_days=0,
                remaining_days=leave['days'],
                year=current_year
            )
            db.session.add(balance)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Employee added successfully',
            'employee_id': user.id,
            'login_id': login_id,
            'temp_password': temp_password
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    
# --- Attendance Routes ---
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



@app.route('/api/leaves/apply', methods=['POST'])
@login_required
def apply_leave():
    """Apply for leave (Employee)"""
    try:
        user_id = session.get('user_id')
        data = request.get_json()

        start_date = datetime.strptime(data.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(data.get('end_date'), '%Y-%m-%d').date()
        leave_type = data.get('leave_type')
        reason = data.get('reason')

        num_days = (end_date - start_date).days + 1
        current_year = datetime.now().year

        # Find HR Officer (first available)
        hr_officer = User.query.filter_by(role='HR_OFFICER', is_active=True).first()

        # Check or create leave balance
        balance = LeaveBalance.query.filter_by(
            user_id=user_id,
            leave_type=leave_type,
            year=current_year
        ).first()

        if not balance:
            default_days = {'Annual': 20, 'Sick': 10, 'Casual': 5, 'Maternity': 90, 'Unpaid': 10}
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

        # Create leave request assigned to HR Officer
        leave = Leave(
            user_id=user_id,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            reason=reason,
            number_of_days=num_days,
            status='Pending',
            approved_by=hr_officer.id if hr_officer else None
        )

        db.session.add(leave)
        db.session.commit()

        return jsonify(
            message='Leave request submitted successfully and sent to HR Officer for approval',
            leave_id=leave.id,
            assigned_to=hr_officer.full_name if hr_officer else 'No HR Officer assigned'
        ), 201

    except Exception as e:
        db.session.rollback()
        return jsonify(error=str(e)), 500

    


@app.route('/api/leaves/approve/<int:leave_id>', methods=['PUT'])
@login_required
@role_required('ADMIN', 'HR_OFFICER')  # Added HR_OFFICER here
def approve_leave(leave_id):
    """Approve leave request (Admin or HR Officer)"""
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
@role_required('ADMIN', 'HR_OFFICER')  # Added HR_OFFICER here
def reject_leave(leave_id):
    """Reject leave request (Admin or HR Officer)"""
    leave = Leave.query.get(leave_id)
    if not leave:
        return jsonify({'error': 'Leave request not found'}), 404

    leave.status = 'Rejected'
    leave.approved_by = session.get('user_id')
    db.session.commit()
    return jsonify({'message': 'Leave rejected successfully'}), 200


# --- Payroll Routes ---

# ======================== COMPLETE PAYROLL ROUTES ========================
# Add these routes to your app.py file

@app.route('/payroll')
@login_required
def payroll():
    """Main payroll page - shows own payslips for employees, overview for admin/payroll officer"""
    user_id = session.get('user_id')
    user = User.query.get(user_id)
    
    # Get payslips for current user
    payslips = Payslip.query.filter_by(user_id=user_id).order_by(
        Payslip.payroll_month.desc()
    ).limit(12).all()
    
    # Get current month payslip
    current_month = datetime.now().replace(day=1).date()
    current_payslip = Payslip.query.filter_by(
        user_id=user_id,
        payroll_month=current_month
    ).first()
    
    # Get salary adjustments
    salary_adjustments = SalaryAdjustment.query.filter_by(
        user_id=user_id
    ).order_by(SalaryAdjustment.adjustment_date.desc()).limit(5).all()
    
    # For Admin/Payroll Officer - get statistics
    total_employees = None
    total_payroll_current = None
    processed_payslips = None
    pending_payslips = None
    
    if user.role in ['ADMIN', 'PAYROLL_OFFICER']:
        total_employees = User.query.filter_by(is_active=True).count()
        
        # Get current month payroll total
        current_month_payslips = Payslip.query.filter_by(
            payroll_month=current_month
        ).all()
        total_payroll_current = sum(p.net_salary or 0 for p in current_month_payslips)
        
        processed_payslips = Payslip.query.filter_by(
            payroll_month=current_month,
            status='Processed'
        ).count()
        
        pending_payslips = Payslip.query.filter_by(
            payroll_month=current_month,
            status='Draft'
        ).count()
    
    return render_template('payroll.html',
                         user=user,
                         payslips=payslips,
                         current_payslip=current_payslip,
                         salary_adjustments=salary_adjustments,
                         total_employees=total_employees,
                         total_payroll_current=total_payroll_current,
                         processed_payslips=processed_payslips,
                         pending_payslips=pending_payslips)

@app.route('/payroll/generate')
@login_required
@role_required('ADMIN', 'PAYROLL_OFFICER')
def generate_payroll_page():
    """Generate payroll page"""
    user = User.query.get(session.get('user_id'))
    
    # Get all active employees
    employees = User.query.filter_by(is_active=True).all()
    
    # Get unique departments
    departments = db.session.query(User.department).distinct().filter(
        User.department.isnot(None)
    ).all()
    departments = [d[0] for d in departments]
    
    # Calculate estimates
    total_basic_salary = sum(emp.basic_salary or 0 for emp in employees)
    estimated_gross = total_basic_salary * 1.25  # Basic + HRA + DA
    estimated_deductions = total_basic_salary * 0.22  # PF + Tax + Prof Tax
    estimated_net = estimated_gross - estimated_deductions
    
    return render_template('generate_payroll.html',
                         user=user,
                         employees=employees,
                         departments=departments,
                         total_basic_salary=total_basic_salary,
                         estimated_gross=estimated_gross,
                         estimated_deductions=estimated_deductions,
                         estimated_net=estimated_net)

@app.route('/api/payroll/generate', methods=['POST'])
@login_required
@role_required('ADMIN', 'PAYROLL_OFFICER')
def generate_payroll():
    """Generate payslips for employees"""
    try:
        data = request.get_json()
        payroll_month_str = data.get('payroll_month')
        department = data.get('department')
        include_inactive = data.get('include_inactive', False)
        
        # Parse payroll month
        payroll_month = datetime.strptime(payroll_month_str, '%Y-%m-%d').date()
        
        # Query employees
        query = User.query
        if not include_inactive:
            query = query.filter_by(is_active=True)
        if department:
            query = query.filter_by(department=department)
        
        employees = query.all()
        
        generated_count = 0
        skipped_count = 0
        
        for employee in employees:
            # Check if payslip already exists
            existing = Payslip.query.filter_by(
                user_id=employee.id,
                payroll_month=payroll_month
            ).first()
            
            if existing:
                skipped_count += 1
                continue
            
            # Calculate attendance for the month
            month_start = payroll_month.replace(day=1)
            if payroll_month.month == 12:
                next_month = payroll_month.replace(year=payroll_month.year + 1, month=1, day=1)
            else:
                next_month = payroll_month.replace(month=payroll_month.month + 1, day=1)
            
            attendance_count = Attendance.query.filter(
                Attendance.user_id == employee.id,
                Attendance.attendance_date >= month_start,
                Attendance.attendance_date < next_month,
                Attendance.status == 'Present'
            ).count()
            
            # Calculate salary
            basic = employee.basic_salary or 0
            hra = basic * 0.20  # 20% HRA
            da = basic * 0.05   # 5% DA
            gross = basic + hra + da
            
            # Deductions
            pf = basic * 0.12           # 12% PF
            income_tax = basic * 0.05   # 5% Income Tax
            prof_tax = 200              # Fixed Professional Tax
            
            net = gross - pf - income_tax - prof_tax
            
            # Create payslip
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
                status='Processed',
                processed_date=datetime.now()
            )
            
            db.session.add(payslip)
            generated_count += 1
        
        db.session.commit()
        
        return jsonify({
            'message': f'Payroll generated successfully! {generated_count} payslips created, {skipped_count} skipped (already exists)',
            'generated': generated_count,
            'skipped': skipped_count
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/payroll/payslip/<int:payslip_id>')
@login_required
def view_payslip(payslip_id):
    """View detailed payslip"""
    payslip = Payslip.query.get_or_404(payslip_id)
    employee = User.query.get(payslip.user_id)
    
    # Check access - users can only view their own payslips unless they're admin/payroll officer
    user = User.query.get(session.get('user_id'))
    if user.role not in ['ADMIN', 'PAYROLL_OFFICER'] and payslip.user_id != user.id:
        return "Unauthorized", 403
    
    # Calculate attendance statistics for the month
    month_start = payslip.payroll_month.replace(day=1)
    if payslip.payroll_month.month == 12:
        next_month = payslip.payroll_month.replace(year=payslip.payroll_month.year + 1, month=1, day=1)
    else:
        next_month = payslip.payroll_month.replace(month=payslip.payroll_month.month + 1, day=1)
    
    # Count working days (excluding Sundays)
    working_days = 0
    current = month_start
    while current < next_month:
        if current.weekday() != 6:  # Not Sunday
            working_days += 1
        current += timedelta(days=1)
    
    present_days = Attendance.query.filter(
        Attendance.user_id == employee.id,
        Attendance.attendance_date >= month_start,
        Attendance.attendance_date < next_month,
        Attendance.status == 'Present'
    ).count()
    
    absent_days = Attendance.query.filter(
        Attendance.user_id == employee.id,
        Attendance.attendance_date >= month_start,
        Attendance.attendance_date < next_month,
        Attendance.status == 'Absent'
    ).count()
    
    # Get approved leaves for the month
    leave_days = db.session.query(db.func.sum(Leave.number_of_days)).filter(
        Leave.user_id == employee.id,
        Leave.status == 'Approved',
        Leave.start_date >= month_start,
        Leave.start_date < next_month
    ).scalar() or 0
    
    attendance_stats = {
        'working_days': working_days,
        'present_days': present_days,
        'absent_days': absent_days,
        'leave_days': int(leave_days)
    }
    
    return render_template('view_payslip.html',
                         payslip=payslip,
                         employee=employee,
                         user=user,
                         attendance_stats=attendance_stats)

@app.route('/api/payslip/<int:payslip_id>/download')
@login_required
def download_payslip_pdf(payslip_id):
    """Download payslip as PDF"""
    payslip = Payslip.query.get_or_404(payslip_id)
    employee = User.query.get(payslip.user_id)
    
    # Check access
    user = User.query.get(session.get('user_id'))
    if user.role not in ['ADMIN', 'PAYROLL_OFFICER'] and payslip.user_id != user.id:
        return "Unauthorized", 403
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#3498db'),
        spaceAfter=30,
        alignment=1
    )
    
    # Title
    title = Paragraph(f"Salary Slip - {employee.full_name}", title_style)
    elements.append(title)
    elements.append(Spacer(1, 12))
    
    # Employee Info
    info_data = [
        ['Employee Information', ''],
        ['Name:', employee.full_name],
        ['Employee ID:', employee.login_id],
        ['Department:', employee.department or 'N/A'],
        ['Position:', employee.job_position or 'N/A'],
        ['Pay Period:', payslip.payroll_month.strftime('%B %Y')],
    ]
    
    info_table = Table(info_data, colWidths=[2*inch, 4*inch])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 20))
    
    # Earnings
    earnings_data = [
        ['Earnings', 'Amount (₹)'],
        ['Basic Salary', f"{payslip.basic_salary:,.2f}"],
        ['HRA', f"{payslip.hra:,.2f}"],
        ['DA', f"{payslip.da:,.2f}"],
        ['Gross Earnings', f"{payslip.gross_earnings:,.2f}"],
    ]
    
    earnings_table = Table(earnings_data, colWidths=[4*inch, 2*inch])
    earnings_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.green),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(earnings_table)
    elements.append(Spacer(1, 20))
    
    # Deductions
    deductions_data = [
        ['Deductions', 'Amount (₹)'],
        ['Provident Fund (PF)', f"{payslip.pf:,.2f}"],
        ['Income Tax', f"{payslip.income_tax:,.2f}"],
        ['Professional Tax', f"{payslip.professional_tax:,.2f}"],
        ['Total Deductions', f"{(payslip.pf + payslip.income_tax + payslip.professional_tax):,.2f}"],
    ]
    
    deductions_table = Table(deductions_data, colWidths=[4*inch, 2*inch])
    deductions_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.red),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(deductions_table)
    elements.append(Spacer(1, 20))
    
    # Net Pay
    net_data = [
        ['NET PAY', f"₹ {payslip.net_salary:,.2f}"],
    ]
    
    net_table = Table(net_data, colWidths=[4*inch, 2*inch])
    net_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#4CAF50')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 16),
        ('GRID', (0, 0), (-1, -1), 2, colors.black)
    ]))
    elements.append(net_table)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'payslip_{employee.login_id}_{payslip.payroll_month.strftime("%B_%Y")}.pdf'
    )

@app.route('/payroll/salary-adjustments')
@login_required
def salary_adjustments():
    # Put your logic here, e.g.
    user = User.query.get(session.get('user_id'))
    adjustments = SalaryAdjustment.query.order_by(SalaryAdjustment.adjustment_date.desc()).all()
    return render_template('salary_adjustments.html', user=user, adjustments=adjustments)




@app.route('/reports/<report_type>')
@login_required
@role_required('ADMIN', 'PAYROLL_OFFICER')
def report_detail(report_type):
    # Render your detailed report here
    return render_template('report_detail.html', report_type=report_type)


@app.route('/payroll/all-payslips')
@login_required
@role_required('ADMIN', 'PAYROLL_OFFICER')
def all_payslips_page():
    """All employee payslips page"""
    user = User.query.get(session.get('user_id'))
    
    # Get filters
    search = request.args.get('search', '')
    month = request.args.get('month')
    department = request.args.get('department')
    status = request.args.get('status')
    
    # Build query
    query = Payslip.query.join(User)
    
    if search:
        query = query.filter(
            db.or_(
                User.full_name.ilike(f'%{search}%'),
                User.login_id.ilike(f'%{search}%')
            )
        )
    if month:
        month_date = datetime.strptime(month + '-01', '%Y-%m-%d').date()
        query = query.filter(Payslip.payroll_month == month_date)
    if department:
        query = query.filter(User.department == department)
    if status:
        query = query.filter(Payslip.status == status)
    
    payslips = query.order_by(Payslip.payroll_month.desc()).all()
    
    # Calculate statistics
    total_payslips = len(payslips)
    processed_count = sum(1 for p in payslips if p.status == 'Processed')
    draft_count = sum(1 for p in payslips if p.status == 'Draft')
    total_amount = sum(p.net_salary or 0 for p in payslips)
    
    # Get departments for filter
    departments = db.session.query(User.department).distinct().filter(
        User.department.isnot(None)
    ).all()
    departments = [d[0] for d in departments]
    
    return render_template('all_payslips.html',
                         user=user,
                         payslips=payslips,
                         total_payslips=total_payslips,
                         processed_count=processed_count,
                         draft_count=draft_count,
                         total_amount=total_amount,
                         departments=departments)

@app.route('/api/payslips/export')
@login_required
@role_required('ADMIN', 'PAYROLL_OFFICER')
def export_payslips():
    """Export payslips to CSV"""
    # Get same filters as all_payslips_page
    search = request.args.get('search', '')
    month = request.args.get('month')
    department = request.args.get('department')
    status = request.args.get('status')
    
    # Build query
    query = Payslip.query.join(User)
    
    if search:
        query = query.filter(
            db.or_(
                User.full_name.ilike(f'%{search}%'),
                User.login_id.ilike(f'%{search}%')
            )
        )
    if month:
        month_date = datetime.strptime(month + '-01', '%Y-%m-%d').date()
        query = query.filter(Payslip.payroll_month == month_date)
    if department:
        query = query.filter(User.department == department)
    if status:
        query = query.filter(Payslip.status == status)
    
    payslips = query.order_by(Payslip.payroll_month.desc()).all()
    
    # Create CSV
    output = BytesIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Employee ID', 'Employee Name', 'Department', 'Month',
        'Basic Salary', 'HRA', 'DA', 'Gross Earnings',
        'PF', 'Income Tax', 'Professional Tax', 'Net Salary', 'Status'
    ])
    
    # Write data
    for payslip in payslips:
        writer.writerow([
            payslip.employee.login_id,
            payslip.employee.full_name,
            payslip.employee.department or '',
            payslip.payroll_month.strftime('%B %Y'),
            payslip.basic_salary or 0,
            payslip.hra or 0,
            payslip.da or 0,
            payslip.gross_earnings or 0,
            payslip.pf or 0,
            payslip.income_tax or 0,
            payslip.professional_tax or 0,
            payslip.net_salary or 0,
            payslip.status
        ])
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'payslips_export_{datetime.now().strftime("%Y%m%d")}.csv'
    )
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

    return render_template('profile.html',
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


# ======================== REPORT GENERATION FUNCTIONS ========================

def generate_attendance_report(start_date, end_date, department=None):
    """Generate attendance report data"""
    query = db.session.query(
        Attendance, User
    ).join(User).filter(
        Attendance.attendance_date >= start_date,
        Attendance.attendance_date <= end_date
    )
    
    if department:
        query = query.filter(User.department == department)
    
    records = query.all()
    
    # Calculate statistics
    total_records = len(records)
    present = sum(1 for r in records if r[0].status == 'Present')
    absent = sum(1 for r in records if r[0].status == 'Absent')
    late = sum(1 for r in records if r[0].status == 'Late')
    avg_hours = sum(r[0].working_hours or 0 for r in records) / total_records if total_records > 0 else 0
    
    summary_stats = [
        {'icon': '📊', 'value': total_records, 'label': 'Total Records'},
        {'icon': '✅', 'value': present, 'label': 'Present Days'},
        {'icon': '❌', 'value': absent, 'label': 'Absent Days'},
        {'icon': '⏰', 'value': f'{avg_hours:.1f}h', 'label': 'Avg Working Hours'}
    ]
    
    table_headers = ['Date', 'Employee ID', 'Name', 'Department', 'Check In', 'Check Out', 'Hours', 'Status']
    table_data = []
    
    for att, user in records:
        table_data.append([
            att.attendance_date.strftime('%d %b %Y'),
            user.login_id,
            user.full_name,
            user.department or '-',
            att.check_in.strftime('%I:%M %p') if att.check_in else '-',
            att.check_out.strftime('%I:%M %p') if att.check_out else '-',
            f'{att.working_hours:.2f}' if att.working_hours else '-',
            att.status
        ])
    
    return {
        'summary_stats': summary_stats,
        'table_headers': table_headers,
        'table_data': table_data,
        'show_chart': True,
        'chart_title': 'Attendance Trends'
    }

def generate_payroll_report(start_date, end_date, department=None):
    """Generate payroll report data"""
    query = db.session.query(
        Payslip, User
    ).join(User).filter(
        Payslip.payroll_month >= start_date,
        Payslip.payroll_month <= end_date
    )
    
    if department:
        query = query.filter(User.department == department)
    
    records = query.all()
    
    # Calculate statistics
    total_payslips = len(records)
    total_gross = sum(r[0].gross_earnings or 0 for r in records)
    total_deductions = sum((r[0].pf or 0) + (r[0].income_tax or 0) + (r[0].professional_tax or 0) for r in records)
    total_net = sum(r[0].net_salary or 0 for r in records)
    
    summary_stats = [
        {'icon': '💰', 'value': f'₹{total_gross:,.0f}', 'label': 'Total Gross'},
        {'icon': '💸', 'value': f'₹{total_deductions:,.0f}', 'label': 'Total Deductions'},
        {'icon': '💵', 'value': f'₹{total_net:,.0f}', 'label': 'Total Net Pay'},
        {'icon': '👥', 'value': total_payslips, 'label': 'Employees Paid'}
    ]
    
    table_headers = ['Month', 'Employee ID', 'Name', 'Basic Salary', 'HRA', 'Gross', 'Deductions', 'Net Salary']
    table_data = []
    
    for payslip, user in records:
        deductions = (payslip.pf or 0) + (payslip.income_tax or 0) + (payslip.professional_tax or 0)
        table_data.append([
            payslip.payroll_month.strftime('%b %Y'),
            user.login_id,
            user.full_name,
            f'₹{payslip.basic_salary:,.2f}' if payslip.basic_salary else '-',
            f'₹{payslip.hra:,.2f}' if payslip.hra else '-',
            f'₹{payslip.gross_earnings:,.2f}' if payslip.gross_earnings else '-',
            f'₹{deductions:,.2f}',
            f'₹{payslip.net_salary:,.2f}' if payslip.net_salary else '-'
        ])
    
    return {
        'summary_stats': summary_stats,
        'table_headers': table_headers,
        'table_data': table_data,
        'show_chart': True,
        'chart_title': 'Payroll Distribution'
    }

def generate_employee_report(department=None):
    """Generate employee report data"""
    query = User.query.filter(User.is_active == True)
    
    if department:
        query = query.filter(User.department == department)
    
    employees = query.all()
    
    # Calculate statistics
    total_employees = len(employees)
    by_role = {}
    for emp in employees:
        by_role[emp.role] = by_role.get(emp.role, 0) + 1
    
    summary_stats = [
        {'icon': '👥', 'value': total_employees, 'label': 'Total Employees'},
        {'icon': '💼', 'value': by_role.get('EMPLOYEE', 0), 'label': 'Employees'},
        {'icon': '👔', 'value': by_role.get('HR_OFFICER', 0), 'label': 'HR Officers'},
        {'icon': '🔧', 'value': by_role.get('ADMIN', 0), 'label': 'Admins'}
    ]
    
    table_headers = ['Employee ID', 'Name', 'Department', 'Position', 'Role', 'Joining Date', 'Email', 'Phone']
    table_data = []
    
    for emp in employees:
        table_data.append([
            emp.login_id,
            emp.full_name,
            emp.department or '-',
            emp.job_position or '-',
            emp.role.replace('_', ' ').title(),
            emp.date_of_joining.strftime('%d %b %Y') if emp.date_of_joining else '-',
            emp.email,
            emp.phone or '-'
        ])
    
    return {
        'summary_stats': summary_stats,
        'table_headers': table_headers,
        'table_data': table_data,
        'show_chart': False
    }

def generate_leave_report(start_date, end_date, department=None):
    """Generate leave report data"""
    query = db.session.query(
        Leave, User
    ).join(User).filter(
        Leave.start_date >= start_date,
        Leave.start_date <= end_date
    )
    
    if department:
        query = query.filter(User.department == department)
    
    records = query.all()
    
    # Calculate statistics
    total_leaves = len(records)
    approved = sum(1 for r in records if r[0].status == 'Approved')
    pending = sum(1 for r in records if r[0].status == 'Pending')
    rejected = sum(1 for r in records if r[0].status == 'Rejected')
    
    summary_stats = [
        {'icon': '📋', 'value': total_leaves, 'label': 'Total Requests'},
        {'icon': '✅', 'value': approved, 'label': 'Approved'},
        {'icon': '⏳', 'value': pending, 'label': 'Pending'},
        {'icon': '❌', 'value': rejected, 'label': 'Rejected'}
    ]
    
    table_headers = ['Employee ID', 'Name', 'Leave Type', 'Start Date', 'End Date', 'Days', 'Status', 'Reason']
    table_data = []
    
    for leave, user in records:
        table_data.append([
            user.login_id,
            user.full_name,
            leave.leave_type,
            leave.start_date.strftime('%d %b %Y'),
            leave.end_date.strftime('%d %b %Y'),
            leave.number_of_days,
            leave.status,
            leave.reason[:50] + '...' if leave.reason and len(leave.reason) > 50 else leave.reason or '-'
        ])
    
    return {
        'summary_stats': summary_stats,
        'table_headers': table_headers,
        'table_data': table_data,
        'show_chart': True,
        'chart_title': 'Leave Trends'
    }

def generate_overtime_report(start_date, end_date, department=None):
    """Generate overtime report data"""
    query = db.session.query(
        Attendance, User
    ).join(User).filter(
        Attendance.attendance_date >= start_date,
        Attendance.attendance_date <= end_date,
        Attendance.working_hours > 8
    )
    
    if department:
        query = query.filter(User.department == department)
    
    records = query.all()
    
    # Calculate statistics
    total_overtime_days = len(records)
    total_overtime_hours = sum(max(0, (r[0].working_hours or 0) - 8) for r in records)
    avg_overtime = total_overtime_hours / total_overtime_days if total_overtime_days > 0 else 0
    
    summary_stats = [
        {'icon': '⏰', 'value': total_overtime_days, 'label': 'Overtime Days'},
        {'icon': '⏱️', 'value': f'{total_overtime_hours:.1f}h', 'label': 'Total OT Hours'},
        {'icon': '📊', 'value': f'{avg_overtime:.1f}h', 'label': 'Avg OT/Day'},
        {'icon': '💰', 'value': f'₹{total_overtime_hours * 200:.0f}', 'label': 'Estimated Cost'}
    ]
    
    table_headers = ['Date', 'Employee ID', 'Name', 'Department', 'Working Hours', 'OT Hours']
    table_data = []
    
    for att, user in records:
        ot_hours = max(0, (att.working_hours or 0) - 8)
        table_data.append([
            att.attendance_date.strftime('%d %b %Y'),
            user.login_id,
            user.full_name,
            user.department or '-',
            f'{att.working_hours:.2f}' if att.working_hours else '-',
            f'{ot_hours:.2f}'
        ])
    
    return {
        'summary_stats': summary_stats,
        'table_headers': table_headers,
        'table_data': table_data,
        'show_chart': True,
        'chart_title': 'Overtime Trends'
    }

def generate_performance_report(start_date, end_date, department=None):
    """Generate performance report data (placeholder)"""
    query = User.query.filter(User.is_active == True)
    
    if department:
        query = query.filter(User.department == department)
    
    employees = query.all()
    
    summary_stats = [
        {'icon': '⭐', 'value': len(employees), 'label': 'Employees Evaluated'},
        {'icon': '🏆', 'value': '85%', 'label': 'Avg Score'},
        {'icon': '📈', 'value': '12', 'label': 'Top Performers'},
        {'icon': '📉', 'value': '3', 'label': 'Need Improvement'}
    ]
    
    table_headers = ['Employee ID', 'Name', 'Department', 'Performance Score', 'Attendance %', 'Rating']
    table_data = []
    
    # This is placeholder data - in real scenario, you'd calculate from actual performance metrics
    for emp in employees[:20]:  # Limit to 20 for demo
        table_data.append([
            emp.login_id,
            emp.full_name,
            emp.department or '-',
            f'{85 + (hash(emp.id) % 15)}%',
            f'{90 + (hash(emp.id) % 10)}%',
            '⭐' * (3 + (hash(emp.id) % 3))
        ])
    
    return {
        'summary_stats': summary_stats,
        'table_headers': table_headers,
        'table_data': table_data,
        'show_chart': True,
        'chart_title': 'Performance Distribution'
    }

# ======================== DOWNLOAD ROUTES ========================

@app.route('/api/reports/download/<report_type>/pdf')
@login_required
@role_required('ADMIN', 'PAYROLL_OFFICER')
def download_report_pdf(report_type):
    """Download report as PDF"""
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    
    # Set default dates
    if not end_date:
        end_date = datetime.now().date()
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    if not start_date:
        start_date = end_date - timedelta(days=30)
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    # Generate report data
    if report_type == 'attendance':
        data = generate_attendance_report(start_date, end_date, department)
    elif report_type == 'payroll':
        data = generate_payroll_report(start_date, end_date, department)
    elif report_type == 'employee':
        data = generate_employee_report(department)
    elif report_type == 'leave':
        data = generate_leave_report(start_date, end_date, department)
    elif report_type == 'overtime':
        data = generate_overtime_report(start_date, end_date, department)
    elif report_type == 'performance':
        data = generate_performance_report(start_date, end_date, department)
    else:
        return "Invalid report type", 404
    
    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#3498db'),
        spaceAfter=30,
        alignment=1  # Center
    )
    
    # Title
    title = Paragraph(f"{report_type.title()} Report", title_style)
    elements.append(title)
    elements.append(Spacer(1, 12))
    
    # Date range
    date_text = Paragraph(
        f"Period: {start_date.strftime('%d %b %Y')} - {end_date.strftime('%d %b %Y')}",
        styles['Normal']
    )
    elements.append(date_text)
    elements.append(Spacer(1, 20))
    
    # Summary stats
    summary_data = [['Metric', 'Value']]
    for stat in data['summary_stats']:
        summary_data.append([stat['label'], str(stat['value'])])
    
    summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 30))
    
    # Detailed table (limit to first 50 rows for PDF)
    table_data = [data['table_headers']]
    table_data.extend(data['table_data'][:50])
    
    # Adjust column widths based on number of columns
    col_count = len(data['table_headers'])
    col_width = 7.5*inch / col_count
    
    detail_table = Table(table_data, colWidths=[col_width] * col_count)
    detail_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(detail_table)
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'{report_type}_report_{datetime.now().strftime("%Y%m%d")}.pdf'
    )

@app.route('/api/reports/download/<report_type>/excel')
@login_required
@role_required('ADMIN', 'PAYROLL_OFFICER')
def download_report_excel(report_type):
    """Download report as Excel (CSV)"""
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    department = request.args.get('department')
    
    # Set default dates
    if not end_date:
        end_date = datetime.now().date()
    else:
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    if not start_date:
        start_date = end_date - timedelta(days=30)
    else:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    # Generate report data
    if report_type == 'attendance':
        data = generate_attendance_report(start_date, end_date, department)
    elif report_type == 'payroll':
        data = generate_payroll_report(start_date, end_date, department)
    elif report_type == 'employee':
        data = generate_employee_report(department)
    elif report_type == 'leave':
        data = generate_leave_report(start_date, end_date, department)
    elif report_type == 'overtime':
        data = generate_overtime_report(start_date, end_date, department)
    elif report_type == 'performance':
        data = generate_performance_report(start_date, end_date, department)
    else:
        return "Invalid report type", 404
    
    # Create CSV
    output = BytesIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([f"{report_type.title()} Report"])
    writer.writerow([f"Period: {start_date.strftime('%d %b %Y')} - {end_date.strftime('%d %b %Y')}"])
    writer.writerow([])
    
    # Write summary
    writer.writerow(['Summary Statistics'])
    for stat in data['summary_stats']:
        writer.writerow([stat['label'], stat['value']])
    writer.writerow([])
    
    # Write data table
    writer.writerow(data['table_headers'])
    writer.writerows(data['table_data'])
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'{report_type}_report_{datetime.now().strftime("%Y%m%d")}.csv'
    )
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
