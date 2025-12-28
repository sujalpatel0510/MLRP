# ======================== IMPORTS ========================
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import send_file
import os

# ======================== NEW IMPORTS FOR PDF REPORTS ========================
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from io import BytesIO
# import qrcode

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

class Achievement(db.Model):
    __tablename__ = 'achievements'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User', backref='achievements')
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    file_url = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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

    # Different behavior for different roles
    all_leaves = []
    if user.role in ['HOD', 'COUNSELOR']:
        all_leaves = Leave.query.order_by(Leave.created_at.desc()).all()
    else:
        all_leaves = [leave for leave in leaves]

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

# ======================== PDF REPORT GENERATION ========================

@app.route('/api/leaves/report', methods=['GET'])
@login_required
def generate_leave_report():

    """Generate comprehensive PDF report for all leave requests"""
    try:
        user_id = session.get('user_id')
        user = User.query.get(user_id)
        leaves = Leave.query.all()
        
        # Get statistics
        total_leaves = len(leaves)
        pending_leaves = len([l for l in leaves if l.status == 'Pending'])
        approved_leaves = len([l for l in leaves if l.status == 'Approved'])
        rejected_leaves = len([l for l in leaves if l.status == 'Rejected'])
        
        # Create PDF in memory
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(
            pdf_buffer,
            pagesize=A4,
            rightMargin=0.5*inch,
            leftMargin=0.5*inch,
            topMargin=0.75*inch,
            bottomMargin=0.75*inch,
            title='Leave Management Report'
        )
        
        story = []
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#134252'),
            spaceAfter=6,
            alignment=1  # Center
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#208099'),
            spaceAfter=12,
            spaceBefore=12
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=6
        )
        
        # Title
        story.append(Paragraph('Leave Management Report', title_style))
        story.append(Paragraph(f'Generated on {datetime.now().strftime("%d %B %Y at %H:%M:%S")}', normal_style))
        story.append(Spacer(1, 0.3*inch))
        
        # Summary Statistics
        story.append(Paragraph('Summary Statistics', heading_style))
        
        summary_data = [
            ['Metric', 'Count'],
            ['Total Leave Requests', str(total_leaves)],
            ['Pending Approvals', str(pending_leaves)],
            ['Approved Requests', str(approved_leaves)],
            ['Rejected Requests', str(rejected_leaves)],
        ]
        
        summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#208099')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')])
        ]))
        
        story.append(summary_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Detailed Leave Records
        story.append(Paragraph('Detailed Leave Records', heading_style))
        
        if leaves:
            # Create detailed table
            leave_data = [['Employee', 'Leave Type', 'Start Date', 'End Date', 'Days', 'Status', 'Reason']]
            
            for leave in leaves:
                emp_name = leave.requester.email.split('@')[0] if leave.requester else 'N/A'
                leave_data.append([
                    emp_name,
                    leave.leave_type,
                    leave.start_date.strftime('%d/%m/%Y'),
                    leave.end_date.strftime('%d/%m/%Y'),
                    str(leave.number_of_days),
                    leave.status,
                    leave.reason[:30] + '...' if leave.reason and len(leave.reason) > 30 else leave.reason or 'N/A'
                ])
            
            leave_table = Table(leave_data, colWidths=[1.2*inch, 1*inch, 1*inch, 1*inch, 0.7*inch, 0.9*inch, 1.4*inch])
            leave_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#208099')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ]))
            
            story.append(leave_table)
        else:
            story.append(Paragraph('No leave records found.', normal_style))
        
        story.append(Spacer(1, 0.3*inch))
        
        # Leave Balance Information
        current_year = datetime.now().year
        balances = LeaveBalance.query.filter_by(year=current_year).all()
        
        if balances:
            story.append(PageBreak())
            story.append(Paragraph('Leave Balance Summary (Current Year)', heading_style))
            
            balance_data = [['Leave Type', 'Total Days', 'Used Days', 'Remaining Days']]
            
            for balance in balances[:10]:  # Limit to 10 entries
                balance_data.append([
                    balance.leave_type,
                    str(balance.total_days),
                    str(balance.used_days),
                    str(balance.remaining_days)
                ])
            
            balance_table = Table(balance_data, colWidths=[2*inch, 1.5*inch, 1.5*inch, 1.5*inch])
            balance_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#208099')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 11),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')])
            ]))
            
            story.append(balance_table)
        
        story.append(Spacer(1, 0.5*inch))
        
        # Footer
        footer_text = f"""
        <b>Report Information:</b><br/>
        Generated by: {user.email}<br/>
        Role: {user.role}<br/>
        System: WorkZen Leave Management<br/>
        <br/>
        <i>This is an auto-generated report. Please verify the data before taking any action.</i>
        """
        story.append(Paragraph(footer_text, normal_style))
        
        # Build PDF
        doc.build(story)
        
        # Get PDF bytes
        pdf_buffer.seek(0)
        
        # Send PDF response
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'leave_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        )
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to generate report: {str(e)}'}), 500


@app.route('/api/leaves/report/filtered', methods=['POST'])
@login_required
def generate_filtered_report():
    """Generate PDF report with filters (date range, status, leave type)"""
    try:
        data = request.get_json()
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        status_filter = data.get('status')
        leave_type_filter = data.get('leave_type')
        
        # Build query
        query = Leave.query
        
        if start_date:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            query = query.filter(Leave.start_date >= start)
        
        if end_date:
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            query = query.filter(Leave.end_date <= end)
        
        if status_filter:
            query = query.filter_by(status=status_filter)
        
        if leave_type_filter:
            query = query.filter_by(leave_type=leave_type_filter)
        
        leaves = query.all()
        
        # Generate PDF
        pdf_buffer = BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=A4)
        
        story = []
        styles = getSampleStyleSheet()
        
        # Title and filters applied
        story.append(Paragraph('Leave Report (Filtered)', styles['Heading1']))
        
        filter_info = f"Filters Applied: "
        if start_date:
            filter_info += f"From {start_date} "
        if end_date:
            filter_info += f"To {end_date} "
        if status_filter:
            filter_info += f"Status: {status_filter} "
        if leave_type_filter:
            filter_info += f"Type: {leave_type_filter}"
        
        story.append(Paragraph(filter_info, styles['Normal']))
        story.append(Spacer(1, 0.2*inch))
        
        # Table
        if leaves:
            table_data = [['Employee', 'Type', 'Start', 'End', 'Days', 'Status', 'Reason']]
            for leave in leaves:
                emp_name = leave.requester.email.split('@')[0] if leave.requester else 'N/A'
                table_data.append([
                    emp_name,
                    leave.leave_type,
                    leave.start_date.strftime('%d/%m/%Y'),
                    leave.end_date.strftime('%d/%m/%Y'),
                    str(leave.number_of_days),
                    leave.status,
                    leave.reason[:20] + '...' if leave.reason and len(leave.reason) > 20 else leave.reason or 'N/A'
                ])
            
            table = Table(table_data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            story.append(table)
        else:
            story.append(Paragraph('No matching leave records found.', styles['Normal']))
        
        doc.build(story)
        pdf_buffer.seek(0)
        
        return send_file(
            pdf_buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'leave_filtered_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        )
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ======================== SICK LEAVE PDF UPLOAD ========================

class MedicalRecord(db.Model):
    """Medical certificate for sick leave"""
    __tablename__ = 'medical_records'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    leave_type = db.Column(db.String(50), default='Sick')
    reason = db.Column(db.Text)
    file_url = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

@app.route('/api/sick-leave/upload-certificate', methods=['POST'])
@login_required
def upload_sick_certificate():
    """Upload medical certificate for sick leave"""
    try:
        user_id = session.get('user_id')
        file = request.files.get('file')
        reason = request.form.get('reason')
        
        if not file or not reason:
            return jsonify({'error': 'Missing file or reason'}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files allowed'}), 400
        
        # Check file size (5 MB)
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > 5 * 1024 * 1024:
            return jsonify({'error': 'File size exceeds 5 MB'}), 400
        
        os.makedirs('uploads/medical', exist_ok=True)
        
        import secrets
        safe_name = f"{user_id}_{secrets.token_hex(8)}.pdf"
        path = os.path.join('uploads/medical', safe_name)
        
        file.save(path)
        
        record = MedicalRecord(
            user_id=user_id,
            reason=reason,
            file_url=f'/uploads/medical/{safe_name}',
            file_size=file_size
        )
        
        db.session.add(record)
        db.session.commit()
        
        return jsonify({'message': 'Certificate uploaded successfully'}), 201
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/sick-leave/medical-records', methods=['GET'])
@login_required
def get_medical_records():
    """Get user's medical records"""
    user_id = session.get('user_id')
    records = MedicalRecord.query.filter_by(user_id=user_id).order_by(MedicalRecord.created_at.desc()).all()
    
    return jsonify({
        'records': [
            {
                'id': r.id,
                'reason': r.reason,
                'file_url': r.file_url,
                'created_at': r.created_at.isoformat(),
                'file_size': r.file_size
            }
            for r in records
        ]
    }), 200

@app.route('/api/sick-leave/medical-records/<int:record_id>', methods=['DELETE'])
@login_required
def delete_medical_record(record_id):
    """Delete medical record"""
    user_id = session.get('user_id')
    record = MedicalRecord.query.filter_by(id=record_id, user_id=user_id).first()
    
    if not record:
        return jsonify({'error': 'Record not found'}), 404
    
    # Delete file from disk
    try:
        if 'uploads/medical' in record.file_url:
            file_path = record.file_url.replace('/uploads/medical/', 'uploads/medical/')
            if os.path.exists(file_path):
                os.remove(file_path)
    except:
        pass
    
    db.session.delete(record)
    db.session.commit()
    
    return jsonify({'message': 'Record deleted'}), 200

@app.route('/uploads/medical/<filename>')
@login_required
def download_medical_record(filename):
    """Download medical record PDF"""
    return send_file(os.path.join('uploads/medical', filename), as_attachment=True)

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


@app.route('/reports/<report_type>')
@login_required
@role_required('HOD', 'COUNSELOR')
def report_detail(report_type):
    """Detailed report view"""
    user = User.query.get(session.get('user_id'))
    
    if report_type == 'attendance':
        attendance_data = Attendance.query.all()
        return render_template('report_detail.html', 
                             report_type=report_type,
                             data=attendance_data,
                             user=user)
    
    elif report_type == 'leaves':
        leave_data = Leave.query.all()
        return render_template('report_detail.html',
                             report_type=report_type,
                             data=leave_data,
                             user=user)
    
    else:
        return redirect(url_for('reports'))


# ======================== PROFILE ========================

@app.route('/profile')
@login_required
def profile():
    """User profile page"""
    user = User.query.get(session.get('user_id'))
    return render_template('profile.html', user=user)

@app.route('/api/settings/change-password', methods=['POST'])
@login_required
@role_required('HOD', 'COUNSELOR')
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

@app.route('/api/achievements/upload', methods=['POST'])
@login_required
def upload_achievement():
    try:
        user_id = session.get('user_id')
        title = request.form.get('title')
        description = request.form.get('description')
        file = request.files.get('file')

        if not title or not description or not file:
            return jsonify({'error': 'Missing fields'}), 400

        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Only PDF files allowed'}), 400

        # size check: max 5 MB
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)

        max_size = 5 * 1024 * 1024
        if file_size > max_size:
            return jsonify({'error': 'File cannot exceed 5 MB'}), 400

        import secrets
        os.makedirs('uploads/achievements', exist_ok=True)

        safe_name = f"{user_id}_{secrets.token_hex(8)}.pdf"
        path = os.path.join('uploads/achievements', safe_name)

        file.save(path)

        achievement = Achievement(
            user_id=user_id,
            title=title,
            description=description,
            file_url=f'/uploads/achievements/{safe_name}',
            file_size=file_size,
        )

        db.session.add(achievement)
        db.session.commit()

        return jsonify({'message': 'Achievement uploaded successfully'}), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/achievements/list')
@login_required
def achievements_list():
    user_id = session.get('user_id')
    achs = Achievement.query.filter_by(user_id=user_id).order_by(Achievement.created_at.desc()).all()

    return jsonify({
        'achievements': [
            {
                'id': a.id,
                'title': a.title,
                'description': a.description,
                'file_url': a.file_url,
                'created_at': a.created_at.isoformat()
            }
            for a in achs
        ]
    }), 200

@app.route('/api/achievements/<int:achievement_id>', methods=['DELETE'])
@login_required
def delete_achievement(achievement_id):
    user_id = session.get('user_id')
    ach = Achievement.query.filter_by(id=achievement_id, user_id=user_id).first()

    if not ach:
        return jsonify({'error': 'Achievement not found'}), 404

    # optionally delete file from disk here

    db.session.delete(ach)
    db.session.commit()

    return jsonify({'message': 'Achievement deleted'}), 200

@app.route('/uploads/achievements/<filename>')
@login_required
def download_achievement(filename):
    return send_file(os.path.join('uploads/achievements', filename), as_attachment=True)

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